"""One shared, versioned geometry for printing and reading system sheets."""
import math
import cv2
import numpy as np

WIDTH, HEIGHT = 1000, 1414
ANCHORS = [(50, 50), (950, 50), (950, 1364), (50, 1364)]

def geometry(n=20, sbd_digits=6, code_digits=3, columns=2):
    n, sbd_digits, code_digits, columns = map(int, (n, sbd_digits, code_digits, columns))
    if not (1 <= n <= 100 and 1 <= sbd_digits <= 10 and 1 <= code_digits <= 6 and 2 <= columns <= 4):
        raise ValueError('Mẫu hỗ trợ 1–100 câu, SBD 1–10 chữ số, mã đề 1–6 chữ số, 2–4 cột.')
    rows = math.ceil(n / columns)
    if rows > 27:
        raise ValueError('Quá nhiều câu trong mỗi cột. Hãy tăng số cột.')
    answers = []
    for i in range(n):
        col, row = divmod(i, rows)
        x = 105 + col * (820 / columns)
        answers.append([(round(x + j * 28), 620 + row * 25) for j in range(4)])
    sbd = [[(130 + d * 28, 275 + k * 25) for k in range(10)] for d in range(sbd_digits)]
    code = [[(650 + d * 28, 275 + k * 25) for k in range(10)] for d in range(code_digits)]
    signature = (n << 9) | (sbd_digits << 5) | (code_digits << 2) | (columns - 2)
    bits = f'{signature:016b}'
    checksum = signature % 251
    bits += f'{checksum:08b}'
    return dict(version='OMR-1', id=f'OMR1-{n}-{sbd_digits}-{code_digits}-{columns}', n=n,
                sbd_digits=sbd_digits, code_digits=code_digits, columns=columns,
                width=WIDTH, height=HEIGHT, anchors=ANCHORS, answers=answers, sbd=sbd, code=code, bits=bits)

def marks(g):
    return [p for row in g['answers'] + g['sbd'] + g['code'] for p in row]

def fixture(g, answers=None, sbd='000001', code='001'):
    """Labelled synthetic fixture, never an actual student submission."""
    image = np.full((HEIGHT, WIDTH), 255, np.uint8)
    for x, y in ANCHORS:
        cv2.rectangle(image, (x-12,y-12), (x+12,y+12), 0, -1)
    for i, b in enumerate(g['bits']):
        if b == '1': cv2.rectangle(image,(200+i*24,95),(214+i*24,109),0,-1)
    for x,y in marks(g): cv2.circle(image,(x,y),9,0,1)
    for i, values in enumerate(answers or []):
        for a in values:
            x,y = g['answers'][i]['ABCD'.index(a)]
            cv2.circle(image,(x,y),7,0,-1)
    for name, value in [('sbd',sbd),('code',code)]:
        for i, ch in enumerate(value):
            if i < len(g[name]):
                x,y = g[name][i][int(ch)]
                cv2.circle(image,(x,y),7,0,-1)
    return image

def recognize(data, g):
    if len(data) > 15 * 1024 * 1024: raise ValueError('Ảnh vượt quá 15 MB.')
    # Decode metadata first to avoid decompressing oversized images.
    from PIL import Image
    import io
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ('JPEG','PNG','WEBP') or im.width * im.height > 25_000_000:
                raise ValueError('Chỉ nhận PNG/JPEG/WebP tối đa 25 triệu điểm ảnh.')
            im.verify()
    except (OSError, Image.DecompressionBombError) as e:
        raise ValueError('Không đọc được ảnh.') from e
    image = cv2.imdecode(np.frombuffer(data,np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or min(image.shape) < 500: raise ValueError('Ảnh quá nhỏ hoặc không hợp lệ.')
    scale = min(1., 2000/max(image.shape))
    image = cv2.resize(image,None,fx=scale,fy=scale)
    binary = cv2.adaptiveThreshold(image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,51,15)
    contours,_ = cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    h,w = image.shape
    candidates = []
    for c in contours:
        a = cv2.contourArea(c)
        if not (40 < a < h*w*.008): continue
        poly=cv2.approxPolyDP(c,.04*cv2.arcLength(c,True),True)
        if len(poly)!=4 or not cv2.isContourConvex(poly): continue
        x,y,bw,bh=cv2.boundingRect(c)
        if .55 < bw/bh < 1.8 and a/(bw*bh)>.65:
            candidates.append((x+bw/2,y+bh/2,a))
    corners=[]
    for cx,cy in [(0,0),(w,0),(w,h),(0,h)]:
        options=[p for p in candidates if abs(p[0]-cx)<w*.28 and abs(p[1]-cy)<h*.22]
        if not options: raise ValueError('Thiếu mốc định vị. Chụp đủ bốn góc của mẫu OMR-1.')
        corners.append(min(options,key=lambda p:(p[0]-cx)**2+(p[1]-cy)**2)[:2])
    if len(set(corners))!=4: raise ValueError('Không xác định được bốn mốc riêng biệt.')
    transform=cv2.getPerspectiveTransform(np.float32(corners),np.float32(ANCHORS))
    normalized=cv2.warpPerspective(image,transform,(WIDTH,HEIGHT),borderValue=255)
    if np.percentile(normalized,90)-np.percentile(normalized,1)<70:
        raise ValueError('Ảnh thiếu tương phản. Hãy tăng ánh sáng và chụp lại.')
    sharpness=float(cv2.Laplacian(normalized,cv2.CV_64F).var())
    if sharpness<35: raise ValueError('Ảnh quá mờ để nhận dạng. Hãy chụp lại.')
    bits=''.join('1' if np.mean(normalized[98:107,203+i*24:212+i*24])<140 else '0' for i in range(24))
    if bits!=g['bits']: raise ValueError('Mã mẫu không khớp hoặc phiếu bị xoay/ngược. Chọn đúng mẫu và đặt đầu phiếu lên trên.')
    dark=cv2.adaptiveThreshold(normalized,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,41,12)/255
    yy,xx=np.ogrid[-6:7,-6:7]; mask=xx*xx+yy*yy<=36
    ay,ax=np.ogrid[-14:15,-14:15]; background_mask=(ax*ax+ay*ay>=144)&(ax*ax+ay*ay<=196)
    def level(p):
        x,y=p
        background=float(np.median(normalized[y-14:y+15,x-14:x+15][background_mask]))
        center=float(normalized[y-6:y+7,x-6:x+7][mask].mean())
        contrast=max(0.,(background-center)/max(background,1.))
        return max(contrast,float(dark[y-6:y+7,x-6:x+7][mask].mean()))
    values=[level(p) for p in marks(g)]
    baseline=float(np.percentile(values,30))
    cutoff=max(.30,baseline+.23)
    faint=max(.12,baseline+.10)
    def read(row, alphabet):
        scores=[level(p) for p in row]
        selected=[alphabet[i] for i,s in enumerate(scores) if s>=cutoff]
        uncertain=any(faint<s<cutoff for s in scores)
        state='uncertain' if uncertain else ('blank' if not selected else ('single' if len(selected)==1 else 'multiple'))
        return dict(value=''.join(selected),state=state,scores=[round(s,3) for s in scores])
    answers=[read(row,'ABCD') for row in g['answers']]
    digits={name:[read(row,'0123456789') for row in g[name]] for name in ['sbd','code']}
    result=dict(answers=answers,sbd=''.join(r['value'] if r['state']=='single' else '?' for r in digits['sbd']),
                code=''.join(r['value'] if r['state']=='single' else '?' for r in digits['code']),digits=digits,
                geometry=g,sharpness=round(sharpness,2),indicator='Tỷ lệ vùng tối trong ô, không phải xác suất đã hiệu chuẩn.',
                thresholds=dict(baseline=round(baseline,3),marked=round(cutoff,3),faint=round(faint,3)))
    ok,png=cv2.imencode('.png',normalized)
    if not ok: raise ValueError('Không lưu được ảnh đã căn chỉnh.')
    return result,png.tobytes()
