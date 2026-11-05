import csv
import io
import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from xml.etree.ElementTree import ParseError
from openpyxl import load_workbook, Workbook
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import simpleSplit
from .geometry import geometry, marks

FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
if FONT.exists(): pdfmetrics.registerFont(TTFont('Vietnamese',str(FONT)))
FONT_NAME='Vietnamese' if FONT.exists() else 'Helvetica'

def check_zip(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if len(z.infolist())>3000 or sum(i.file_size for i in z.infolist())>60_000_000:
                raise ValueError('Tệp nén có dữ liệu giải nén quá lớn.')
    except zipfile.BadZipFile as e: raise ValueError('Tệp DOCX/XLSX không hợp lệ.') from e

def spreadsheet(data, suffix):
    if suffix=='.csv':
        try: text=data.decode('utf-8-sig')
        except UnicodeDecodeError as e: raise ValueError('CSV phải dùng UTF-8.') from e
        dialect=csv.Sniffer().sniff(text[:4096],delimiters=',;\t') if text.strip() else csv.excel
        return list(csv.reader(io.StringIO(text),dialect))
    check_zip(data)
    wb=load_workbook(io.BytesIO(data),read_only=True,data_only=False)
    try:
        sheet=wb.active
        rows=[]
        for row in sheet.iter_rows():
            if len(rows)>10000: raise ValueError('Tệp vượt quá 10.000 dòng.')
            values=[]
            for c in row[:30]:
                if c.data_type=='f': raise ValueError('Không nhận ô công thức. Hãy dán dưới dạng giá trị.')
                value='' if c.value is None else str(c.value)
                if c.data_type=='n' and re.fullmatch('0+',c.number_format or ''):
                    value=str(int(c.value)).zfill(len(c.number_format))
                values.append(value)
            rows.append(values)
        return rows
    finally: wb.close()

def parse_key(rows):
    """Strict, deliberately documented three-column key format."""
    items=[]; errors=[]; seen=set()
    for line,row in enumerate(rows,1):
        if not any(str(v).strip() for v in row): continue
        if line==1 and str(row[0]).strip().lower() in ('ma_de','mã đề','code'): continue
        if len(row)<3:
            errors.append(f'Dòng {line}: cần ma_de,cau,dap_an[,diem].'); continue
        code,num,answer=[str(v).strip() for v in row[:3]]
        try:
            number=int(num); weight=float(row[3]) if len(row)>3 and row[3] else None
            if number<1 or number>100 or not code or not code.isascii() or not code.isdigit() or answer.upper() not in ('A','B','C','D'):
                raise ValueError()
            if weight is not None and (not 0<weight<=100 or not weight<float('inf')): raise ValueError()
        except (ValueError,TypeError):
            errors.append(f'Dòng {line}: mã đề dạng số, số câu 1–100, một đáp án A–D, điểm dương.'); continue
        if (code,number) in seen: errors.append(f'Dòng {line}: trùng mã đề {code}, câu {number}.')
        seen.add((code,number))
        items.append(dict(code=code,number=number,answer=answer.upper(),weight=weight))
    return dict(items=items,errors=errors)

def parse_questions(text):
    matches=list(re.finditer(r'(?im)^\s*(?:Câu|Question)\s+(\d+)\s*[.:)]\s*',text))
    questions=[]; errors=[]; seen=set()
    for i,m in enumerate(matches):
        number=int(m[1]); body=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip()
        options=list(re.finditer(r'(?m)(?:^|\s)([ABCD])[.)][.,]?\s*',body))
        choices={o[1]:body[o.end():options[j+1].start() if j+1<len(options) else len(body)].strip() for j,o in enumerate(options)}
        if number in seen: errors.append(f'Trùng số câu {number}.')
        seen.add(number)
        if set(choices)!=set('ABCD') or len(options)!=4: errors.append(f'Câu {number}: cần kiểm tra đủ bốn phương án A–D.')
        questions.append(dict(number=number,text=body[:options[0].start()].strip() if options else body,choices=choices))
    if not matches: errors.append('Không tách được câu hỏi. Dùng định dạng “Câu 1. … A. … B. … C. … D. …” hoặc sửa thủ công.')
    return dict(questions=questions,errors=errors)

def extract(data, filename):
    suffix=Path(filename).suffix.lower()
    if len(data)>15_000_000: raise ValueError('Tệp vượt quá 15 MB.')
    if suffix in ('.csv','.xlsx'):
        return dict(kind='key',**parse_key(spreadsheet(data,suffix)),warnings=[])
    warnings=[]
    if suffix=='.docx':
        from docx import Document
        check_zip(data)
        doc=Document(io.BytesIO(data))
        text='\n'.join([p.text for p in doc.paragraphs]+[' | '.join(c.text for c in r.cells) for t in doc.tables for r in t.rows])
        warnings.append('Đối chiếu tệp gốc: thứ tự bảng, hình ảnh, công thức và đoạn mã có thể không được giữ nguyên.')
    elif suffix=='.pdf':
        from pypdf import PdfReader
        if not data.startswith(b'%PDF'): raise ValueError('Nội dung không phải PDF.')
        pdf=PdfReader(io.BytesIO(data))
        if pdf.is_encrypted: raise ValueError('PDF được mã hóa. Hãy bỏ mật khẩu trước khi nhập.')
        if len(pdf.pages)>100: raise ValueError('PDF tối đa 100 trang.')
        parts=[]
        scans=[]
        for i,page in enumerate(pdf.pages,1):
            part=page.extract_text() or ''
            parts.append(part)
            if len(part.strip())<30: scans.append(i)
        warnings.append('PDF: cần đối chiếu bố cục, hình ảnh và công thức với bản gốc.')
        if scans:
            import shutil,subprocess,tempfile
            if not shutil.which('pdftoppm') or not shutil.which('tesseract'):
                warnings.append('Các trang '+', '.join(map(str,scans))+' không có đủ văn bản. OCR PDF cần Poppler và Tesseract; chuyển thành ảnh hoặc nhập thủ công.')
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    source=Path(tmp)/'input.pdf';source.write_bytes(data)
                    for page_no in scans[:10]:
                        prefix=Path(tmp)/f'page-{page_no}'
                        try:
                            rendered=subprocess.run(['pdftoppm','-f',str(page_no),'-l',str(page_no),'-scale-to','2200','-singlefile','-png',str(source),str(prefix)],capture_output=True,timeout=30)
                            if rendered.returncode: raise ValueError('Không kết xuất được trang PDF.')
                            page_result=extract(prefix.with_suffix('.png').read_bytes(),'page.png')
                            parts[page_no-1]=page_result['text']
                            warnings.append(f'Trang {page_no}: OCR cục bộ, cần đối chiếu toàn bộ.')
                        except (ValueError,OSError,subprocess.TimeoutExpired):
                            warnings.append(f'Trang {page_no}: OCR thất bại; không được bỏ qua, cần nhập hoặc tải ảnh trang này riêng.')
                if len(scans)>10: warnings.append('Chỉ OCR tối đa 10 trang mỗi tệp. Các trang còn lại cần nhập riêng: '+', '.join(map(str,scans[10:])))
        text='\n'.join(parts)
    elif suffix in ('.png','.jpg','.jpeg','.webp'):
        import subprocess, tempfile
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            if img.width*img.height>25_000_000: raise ValueError('Ảnh quá lớn.')
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'ocr.png'; img.convert('RGB').save(path)
                try:
                    import os
                    tessdata=Path(os.environ.get('OMR_TESSDATA_DIR','/workspace/omr-ocr'))
                    extra=['--tessdata-dir',str(tessdata)] if (tessdata/'vie.traineddata').is_file() else []
                    langs=subprocess.run(['tesseract',*extra,'--list-langs'],capture_output=True,text=True,timeout=10)
                    available=langs.stdout.split()
                    language='vie+eng' if 'vie' in available and 'eng' in available else ('vie' if 'vie' in available else 'eng')
                    result=subprocess.run(['tesseract',str(path),'stdout',*extra,'-l',language],capture_output=True,text=True,timeout=60)
                except (FileNotFoundError,subprocess.TimeoutExpired) as e: raise ValueError('OCR cục bộ chưa sẵn sàng; nhập văn bản thủ công.') from e
                if result.returncode: raise ValueError('OCR không đọc được ảnh; thử ảnh rõ hơn.')
                text=result.stdout
        warnings.append(f'OCR cục bộ ({language}); tất cả nội dung cần giáo viên kiểm tra. Không dùng OCR để suy đoán đáp án đúng.')
    elif suffix=='.txt':
        try: text=data.decode('utf-8-sig')
        except UnicodeDecodeError as e: raise ValueError('Văn bản phải dùng UTF-8.') from e
    else: raise ValueError('Hỗ trợ DOCX, PDF văn bản, TXT, CSV, XLSX, PNG/JPEG/WebP.')
    key_match=re.search(r'(?im)^\s*\[DAP_AN\]\s*$',text)
    key=None
    if key_match:
        key=parse_key(spreadsheet(text[key_match.end():].strip().encode(),'.csv'))
        text=text[:key_match.start()]
    return dict(kind='questions',text=text,**parse_questions(text),key=key,warnings=warnings)

def sheet_pdf(g, title='', school='', subject=''):
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=(595.276,841.89))
    scale=595.276/1000
    c.scale(scale,scale)
    def text(x,y,t,size=14):
        c.setFont(FONT_NAME,size); c.drawString(x,1414-y,str(t)[:130])
    for x,y in g['anchors']: c.rect(x-12,1414-y-12,24,24,fill=1,stroke=0)
    for i,b in enumerate(g['bits']):
        if b=='1': c.rect(200+i*24,1414-109,14,14,fill=1,stroke=0)
    text(100,145,'PHIẾU TRẢ LỜI TRẮC NGHIỆM',23)
    text(100,168,school,16); text(100,188,f'{title} · {subject}',16)
    text(100,210,'Họ tên: __________________________  Lớp: ____________',15)
    text(100,252,'Số báo danh'); text(620,252,'Mã đề')
    for name in ('sbd','code'):
        for row in g[name]:
            x=row[0][0]; c.rect(x-11,1414-245,22,24,fill=0)
            for k,(x,y) in enumerate(row):
                c.circle(x,1414-y,9,stroke=1,fill=0); text(x+11,y+3,k,8)
    for i,row in enumerate(g['answers']):
        x,y=row[0]; text(x-35,y+5,i+1,13)
        for a,(x,y) in zip('ABCD',row):
            c.circle(x,1414-y,9,stroke=1,fill=0); text(x+11,y+3,a,8)
    text(100,565,'Tô kín một ô mỗi câu. Tô đủ các chữ số SBD và mã đề, kể cả số 0 đầu.',13)
    text(100,588,'Không gấp, cắt hoặc viết lên các mốc vuông. Đặt đầu phiếu lên trên khi chụp.',12)
    text(100,1325,g['id']+' · In A4, kích thước thực 100%, không co giãn.',12)
    c.showPage(); c.save(); return out.getvalue()

def display_score(value, places=2):
    return str(Decimal(str(value)).quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP))

def safe_cell(value):
    text=str(value)
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else text

def export_table(rows, kind):
    rows=[[safe_cell(x) for x in row] for row in rows]
    if kind=='csv':
        out=io.StringIO(); csv.writer(out).writerows(rows); return out.getvalue().encode('utf-8-sig')
    if kind=='xlsx':
        wb=Workbook(); ws=wb.active; ws.title='Kết quả'
        for row in rows: ws.append(row)
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=min(45,max(15,max(len(str(c.value or '')) for c in col)+2))
        out=io.BytesIO(); wb.save(out); return out.getvalue()
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=(842,595))
    y=555
    for row in rows:
        lines=simpleSplit(' | '.join(row),FONT_NAME,9,760)
        for line in lines:
            if y<40: c.showPage(); y=555
            c.setFont(FONT_NAME,9); c.drawString(40,y,line); y-=15
        y-=5
    c.save(); return out.getvalue()
