import asyncio
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import FastAPI,Request,Response,UploadFile,File,HTTPException,Depends
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from . import store
from .store import db,encode,decode
from .domain import validate_exam,grade
from .geometry import recognize
from .documents import extract,spreadsheet,sheet_pdf,export_table,display_score

PROCESSING=asyncio.Semaphore(2)

app=FastAPI(title='Chấm Việt',docs_url=None,redoc_url=None,openapi_url=None)
store.init()
STATIC=Path(__file__).parent/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex

def audit(c,owner,entity,data): c.execute('INSERT INTO audit(owner,entity,at,data) VALUES(?,?,?,?)',(owner,entity,now(),encode(data)))
def get(c,table,id,owner):
    row=c.execute(f'SELECT * FROM {table} WHERE id=? AND owner=?',(id,owner)).fetchone()
    if not row: raise HTTPException(404,'Không tìm thấy dữ liệu.')
    return decode(row)
def put(c,table,id,owner,data):
    c.execute(f'UPDATE {table} SET data=? WHERE id=? AND owner=?',(encode(data),id,owner))

def hash_password(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+':'+digest

def user(request:Request):
    token=request.cookies.get('omr_session','')
    with db() as c:
        row=c.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?',
                      (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not row: raise HTTPException(401,'Vui lòng đăng nhập.')
        return dict(id=row['id'],email=row['email'],name=row['name'])

@app.middleware('http')
async def security(request,call_next):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        if request.headers.get('x-requested-with')!='ChamViet': return JSONResponse({'detail':'Yêu cầu thiếu mã chống CSRF.'},403)
        origin=request.headers.get('origin')
        expected=os.environ.get('OMR_ORIGIN')
        if origin and origin.rstrip('/')!=(expected or str(request.base_url).rstrip('/')):
            return JSONResponse({'detail':'Nguồn yêu cầu không được phép.'},403)
        length=request.headers.get('content-length')
        if not length or not length.isdigit() or int(length)>17_000_000:
            return JSONResponse({'detail':'Yêu cầu phải có kích thước hợp lệ, tối đa 17 MB.'},413)
    if request.method in ('POST','PUT','PATCH','DELETE') and request.headers.get('content-type','').startswith('application/json'):
        try:
            if not isinstance(await request.json(),dict): raise ValueError()
        except (ValueError,TypeError): return JSONResponse({'detail':'Nội dung JSON phải là một đối tượng hợp lệ.'},422)
    try: response=await call_next(request)
    except (ValueError,TypeError,KeyError,OverflowError) as e:
        response=JSONResponse({'detail':str(e)[:400] or 'Dữ liệu không hợp lệ.'},422)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

@app.get('/')
def index(): return FileResponse(STATIC/'index.html')
@app.get('/api/health')
def health():
    with db() as c: c.execute('SELECT 1').fetchone()
    return dict(status='ok',schema=1)

@app.post('/api/auth/{action}')
async def auth(action:str,request:Request,response:Response):
    body=await request.json()
    if action not in ('register','login'): raise HTTPException(404)
    email=str(body.get('email','')).strip().lower(); password=str(body.get('password','')); name=str(body.get('name','')).strip()
    if not re.fullmatch(r'[^\s@]{1,100}@[^\s@]{1,150}\.[^\s@]{2,50}',email) or not 10<=len(password)<=128:
        raise ValueError('Email hợp lệ và mật khẩu từ 10–128 ký tự là bắt buộc.')
    identity=hashlib.sha256((email+'|'+(request.client.host if request.client else '')).encode()).hexdigest()
    with db() as c:
        attempt=c.execute('SELECT * FROM login_attempts WHERE identity=?',(identity,)).fetchone()
        if attempt and attempt['attempts']>=8 and time.time()-attempt['last']<900: raise HTTPException(429,'Thử lại sau 15 phút.')
        row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if action=='register':
            if not name or len(name)>120: raise ValueError('Cần tên giáo viên, tối đa 120 ký tự.')
            if row: raise HTTPException(409,'Không thể tạo tài khoản với email này.')
            id=uid(); c.execute('INSERT INTO users VALUES(?,?,?,?)',(id,email,hash_password(password),name))
        else:
            encoded=row['password'] if row else hash_password('dummy-password-123')
            valid=hmac.compare_digest(hash_password(password,encoded.split(':')[0]),encoded)
            if not row or not valid:
                count=attempt['attempts']+1 if attempt and time.time()-attempt['last']<900 else 1
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(identity,count,time.time())); c.commit()
                raise HTTPException(401,'Email hoặc mật khẩu không đúng.')
            id=row['id']; name=row['name']
        c.execute('DELETE FROM login_attempts WHERE identity=?',(identity,))
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        token=secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),id,time.time()+43200))
        response.set_cookie('omr_session',token,max_age=43200,httponly=True,samesite='strict',secure=os.environ.get('OMR_SECURE_COOKIE','0')=='1',path='/')
    return dict(id=id,email=email,name=name)

@app.get('/api/me')
def me(u=Depends(user)): return u
@app.post('/api/logout')
def logout(request:Request,response:Response,u=Depends(user)):
    with db() as c: c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('omr_session','').encode()).hexdigest(),))
    response.delete_cookie('omr_session'); return {'ok':True}

@app.get('/api/exams')
def exams(u=Depends(user)):
    with db() as c: return [decode(r) for r in c.execute('SELECT data FROM exams WHERE owner=? ORDER BY rowid DESC',(u['id'],))]

@app.post('/api/exams')
async def save_exam(request:Request,u=Depends(user)):
    b=await request.json(); confirmed=bool(b.get('confirm')); config=validate_exam(b,strict=confirmed); id=b.get('id') or uid()
    with db() as c:
        old=get(c,'exams',id,u['id']) if b.get('id') else None
        if old and b.get('updated')!=old['updated']: raise HTTPException(409,'Bài kiểm tra đã thay đổi. Tải lại trước khi sửa.')
        revisions=old.get('revisions',[]) if old else []
        confirmed=bool(b.get('confirm'))
        current=next((r for r in revisions if r['version']==(old or {}).get('active_version')),None)
        changed=current is None or any(current[k]!=config[k] for k in ('geometry','keys','weights','scale','questions','multiple_rule'))
        # JSON round-trip normalizes geometry tuples before equality comparison.
        if current: changed=any(current.get(k)!=json.loads(encode(config[k])) for k in config)
        if confirmed and changed:
            version=len(revisions)+1
            revisions.append(dict(version=version,at=now(),**config))
        else: version=old.get('active_version') if old else None
        if not confirmed and (not current or changed): version=None
        if b.get('status') in ('grading','done') and version is None: raise ValueError('Cần xác nhận đáp án trước khi chấm hoặc hoàn tất.')
        data={k:str(b.get(k,''))[:200] for k in ('name','subject','grade','class_name','date','duration','school')}
        data.update(dict(id=id,n=config['geometry']['n'],scale=config['scale'],keys=config['keys'],weights=config['weights'],code_weights=config['code_weights'],questions=config['questions'],
                         sbd_digits=config['geometry']['sbd_digits'],code_digits=config['geometry']['code_digits'],columns=config['geometry']['columns'],
                         multiple_rule=config['multiple_rule'],revisions=revisions,active_version=version,
                         status=b.get('status') if b.get('status') in ('done','grading') else ('ready' if version else 'draft'),
                         updated=now(),archived=bool(b.get('archived',False)),original_files=b.get('original_files',[])))
        for file_id in data['original_files']:
            if not c.execute('SELECT 1 FROM files WHERE id=? AND owner=?',(file_id,u['id'])).fetchone(): raise ValueError('Tệp gốc không hợp lệ.')
        if old: put(c,'exams',id,u['id'],data)
        else: c.execute('INSERT INTO exams VALUES(?,?,?)',(id,u['id'],encode(data)))
        audit(c,u['id'],id,dict(action='exam_saved',version=version))
    return data

@app.get('/api/exams/{id}/sheet.pdf')
def sheet(id:str,u=Depends(user)):
    with db() as c: e=get(c,'exams',id,u['id'])
    g=validate_exam(e,strict=False)['geometry']
    return Response(sheet_pdf(g,e['name'],e.get('school',''),e.get('subject','')),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="phieu-omr.pdf"'})

@app.post('/api/import')
async def import_document(file:UploadFile=File(...),u=Depends(user)):
    data=await file.read(15_000_001)
    if len(data)>15_000_000: raise ValueError('Tệp vượt quá 15 MB.')
    try:
        async with PROCESSING: parsed=await run_in_threadpool(extract,data,file.filename or '')
    except (ValueError,TypeError): raise
    except Exception as e: raise ValueError('Không trích xuất được tệp. Bản gốc chưa được nhập; hãy kiểm tra định dạng hoặc nhập thủ công.') from e
    file_id=uid(); name=Path(file.filename or 'original').name[:180]
    mime={'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}.get(Path(name).suffix.lower(),'application/octet-stream')
    with db() as c: c.execute('INSERT INTO files VALUES(?,?,?,?,?)',(file_id,u['id'],name,mime,data))
    return dict(file_id=file_id,filename=name,**parsed)

@app.get('/api/files/{id}')
def file_get(id:str,download:bool=False,u=Depends(user)):
    with db() as c: row=c.execute('SELECT * FROM files WHERE id=? AND owner=?',(id,u['id'])).fetchone()
    if not row: raise HTTPException(404,'Không tìm thấy tệp.')
    # Fixed ASCII filename avoids response header injection; originals remain private.
    return Response(row['content'],media_type=row['mime'],headers={'Content-Disposition':('attachment' if download or row['mime']=='application/octet-stream' else 'inline')+'; filename="tai-lieu'+Path(row['name']).suffix.lower().replace('"','')+'"'})

@app.get('/api/classes')
def classes(u=Depends(user)):
    with db() as c: return [decode(r) for r in c.execute('SELECT data FROM classes WHERE owner=?',(u['id'],))]

@app.post('/api/classes/parse')
async def parse_class(file:UploadFile=File(...),u=Depends(user)):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ('.xlsx','.csv'): raise ValueError('Danh sách phải là CSV hoặc XLSX.')
    data=await file.read(15_000_001)
    if len(data)>15_000_000: raise ValueError('Tệp quá lớn.')
    rows=spreadsheet(data,suffix); students=[]
    for i,r in enumerate(rows):
        if not any(r): continue
        if i==0 and r[0].lower() in ('sbd','so_bao_danh','số báo danh'): continue
        students.append(dict(sbd=str(r[0]).strip(),name=str(r[1]).strip() if len(r)>1 else '',class_name=str(r[2]).strip() if len(r)>2 else ''))
    return dict(students=students)

@app.post('/api/classes')
async def save_class(request:Request,u=Depends(user)):
    b=await request.json(); name=str(b.get('name','')).strip(); students=b.get('students',[])
    if not name or len(name)>120 or len(students)>3000: raise ValueError('Tên lớp bắt buộc, tối đa 3.000 học sinh.')
    seen=set(); clean=[]
    for s in students:
        code=str(s.get('sbd','')).strip(); student_name=str(s.get('name','')).strip()
        if not code.isascii() or not code.isdigit() or len(code)>10 or not student_name or len(student_name)>120 or code in seen:
            raise ValueError(f'SBD {code}: trùng mã, thiếu tên hoặc mã không hợp lệ. Giữ nguyên số 0 đầu.')
        seen.add(code); clean.append(dict(sbd=code,name=student_name,class_name=name))
    id=b.get('id') or uid(); data=dict(id=id,name=name,students=clean,updated=now())
    with db() as c:
        if b.get('id'): get(c,'classes',id,u['id']); put(c,'classes',id,u['id'],data)
        else: c.execute('INSERT INTO classes VALUES(?,?,?)',(id,u['id'],encode(data)))
    return data

@app.get('/api/class-template.csv')
def class_template(u=Depends(user)):
    return Response('sbd,ho_ten,lop\r\n000001,Nguyễn Văn An,11A1\r\n'.encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="mau-lop.csv"'})

@app.post('/api/scans/{exam_id}')
async def scan(exam_id:str,session_id:str='',file:UploadFile=File(...),u=Depends(user)):
    with db() as c:
        exam=get(c,'exams',exam_id,u['id'])
        if not exam.get('active_version') or exam['archived']: raise ValueError('Bài kiểm tra phải có đáp án đã xác nhận và chưa lưu trữ.')
        revision=next(r for r in exam['revisions'] if r['version']==exam['active_version'])
        if session_id:
            session=get(c,'scan_sessions',session_id,u['id'])
            if session['exam_id']!=exam_id: raise ValueError('Phiên quét không thuộc bài kiểm tra này.')
    raw=await file.read(15_000_001)
    try:
        async with PROCESSING: result,normalized=await run_in_threadpool(recognize,raw,revision['geometry'])
    except ValueError: raise
    except Exception as e: raise ValueError('Không xử lý được ảnh. Hãy chụp lại.') from e
    id=uid(); original=uid(); aligned=uid();create_session=not session_id;session_id=session_id or uid()
    data=dict(id=id,session_id=session_id,exam_id=exam_id,version=revision['version'],machine=result,original_file=original,aligned_file=aligned,at=now())
    with db() as c:
        if create_session: c.execute('INSERT INTO scan_sessions VALUES(?,?,?,?)',(session_id,u['id'],exam_id,encode(dict(id=session_id,exam_id=exam_id,at=now()))))
        for file_id,name,mime,content in [(original,'bai-goc','application/octet-stream',raw),(aligned,'phieu.png','image/png',normalized)]:
            c.execute('INSERT INTO files VALUES(?,?,?,?,?)',(file_id,u['id'],name,mime,content))
        c.execute('INSERT INTO scans VALUES(?,?,?,?)',(id,u['id'],exam_id,encode(data)))
    return data

@app.get('/api/scans/{id}')
def get_scan(id:str,u=Depends(user)):
    with db() as c: return get(c,'scans',id,u['id'])

def build_result(c,b,u,scan,exam,revision):
    sbd=str(b.get('sbd','')); code=str(b.get('code','')); answers=b.get('answers',[])
    if not sbd.isascii() or not sbd.isdigit() or len(sbd)!=revision['geometry']['sbd_digits']:
        raise ValueError('Cần SBD đủ chữ số. Bài vẫn được giữ ở lượt quét chờ xử lý.')
    if code not in revision['keys']: raise ValueError('Mã đề không tồn tại. Chọn mã đúng, không dùng mã mặc định.')
    if len(answers)!=len(revision['weights']) or any(not isinstance(a,str) or len(a)>4 or len(set(a))!=len(a) or any(ch not in 'ABCD' for ch in a) for a in answers):
        raise ValueError('Kết quả câu trả lời không hợp lệ.')
    if not b.get('reviewed'): raise ValueError('Giáo viên phải duyệt mọi vùng chưa chắc chắn trước khi xác nhận điểm.')
    if revision['multiple_rule']=='review' and any(len(a)>1 for a in answers): raise ValueError('Quy tắc hiện tại yêu cầu xử lý tất cả câu tô nhiều trước khi lưu.')
    class_id=b.get('class_id') or None; student=None
    if class_id:
        cls=get(c,'classes',class_id,u['id']); student=next((s for s in cls['students'] if s['sbd']==sbd),None)
        if not student and not b.get('unknown_student_confirmed'): raise ValueError('SBD không có trong lớp. Ghép đúng học sinh hoặc xác nhận lưu chưa ghép.')
    machine=scan['machine']; changes=[]
    for field,new,old in [('sbd',sbd,machine['sbd']),('code',code,machine['code'])]+[(str(i+1),a,r['value']) for i,(a,r) in enumerate(zip(answers,machine['answers']))]:
        if new!=old: changes.append(dict(field=field,old=old,new=new,at=now(),by=u['id'],by_name=u['name']))
    return dict(sbd=sbd,code=code,answers=answers,class_id=class_id,name=(student or {}).get('name',''),class_name=(student or {}).get('class_name',''),
                version=revision['version'],grade=grade(answers,revision['keys'][code],revision.get('code_weights',{}).get(code,revision['weights'])),corrections=changes,status='confirmed',by=u['id'],at=now())

@app.post('/api/results')
async def save_result(request:Request,u=Depends(user)):
    b=await request.json()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        scan=get(c,'scans',str(b.get('scan_id','')),u['id']); exam=get(c,'exams',scan['exam_id'],u['id'])
        existing=c.execute('SELECT data FROM results WHERE scan_id=? AND owner=?',(scan['id'],u['id'])).fetchone()
        if existing: return decode(existing)
        revision=next(r for r in exam['revisions'] if r['version']==scan['version'])
        if exam['active_version']!=scan['version']: raise HTTPException(409,'Đáp án đã đổi sau lượt quét này. Quét lại theo phiên bản đang áp dụng.')
        data=build_result(c,b,u,scan,exam,revision)
        duplicate=c.execute('SELECT * FROM results WHERE exam_id=? AND sbd=?',(exam['id'],data['sbd'])).fetchone()
        if duplicate:
            previous=decode(duplicate)
            if b.get('replace_id')!=previous['id'] or b.get('replace_at')!=previous['at']:
                raise HTTPException(409,dict(message='Trùng SBD. Xem bài cũ trước khi xác nhận thay thế.',existing=previous))
            history=previous.get('history',[])+[dict(action='replace',at=now(),by=u['id'],by_name=u['name'],previous={k:v for k,v in previous.items() if k!='history'})]
            id=previous['id']; data.update(id=id,exam_id=exam['id'],scan_id=scan['id'],history=history)
            c.execute('UPDATE results SET scan_id=?,data=? WHERE id=? AND owner=?',(scan['id'],encode(data),id,u['id']))
        else:
            id=uid(); data.update(id=id,exam_id=exam['id'],scan_id=scan['id'],history=[])
            c.execute('INSERT INTO results VALUES(?,?,?,?,?,?)',(id,u['id'],exam['id'],data['sbd'],scan['id'],encode(data)))
        exam['status']='grading'; put(c,'exams',exam['id'],u['id'],exam)
        audit(c,u['id'],id,dict(action='result_confirmed',version=revision['version'],corrections=data['corrections']))
    return data

@app.get('/api/results')
def results(exam_id:str='',u=Depends(user)):
    with db() as c:
        if exam_id: get(c,'exams',exam_id,u['id'])
        return [decode(r) for r in c.execute('SELECT data FROM results WHERE owner=? AND (?="" OR exam_id=?) ORDER BY rowid DESC',(u['id'],exam_id,exam_id))]

@app.get('/api/pending')
def pending(u=Depends(user)):
    with db() as c:
        results=[decode(r) for r in c.execute('SELECT data FROM results WHERE owner=?',(u['id'],))]
        used={r['scan_id'] for r in results}
        for r in results:
            used.update(h['previous']['scan_id'] for h in r.get('history',[]) if h.get('action')=='replace')
        return [decode(r) for r in c.execute('SELECT data FROM scans WHERE owner=? ORDER BY rowid DESC',(u['id'],)) if decode(r)['id'] not in used]

@app.post('/api/exams/{id}/regrade')
async def regrade(id:str,request:Request,u=Depends(user)):
    b=await request.json()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        exam=get(c,'exams',id,u['id']); version=exam['active_version']
        if not version: raise ValueError('Cần đáp án phiên bản mới đã xác nhận.')
        rev=next(r for r in exam['revisions'] if r['version']==version)
        rows=c.execute('SELECT * FROM results WHERE owner=? AND exam_id=?',(u['id'],id)).fetchall()
        changes=[]; updates=[]
        for row in rows:
            old=decode(row)
            if old['code'] not in rev['keys'] or len(old['answers'])!=len(rev['weights']): raise ValueError('Phiên bản mới không tương thích mã đề hoặc số câu đã chấm.')
            new=grade(old['answers'],rev['keys'][old['code']],rev.get('code_weights',{}).get(old['code'],rev['weights']))
            changes.append(dict(id=old['id'],sbd=old['sbd'],old_score=old['grade']['score'],new_score=new['score'],old_display=display_score(old['grade']['score']),new_display=display_score(new['score']),old_version=old['version'],new_version=version))
            history=old.get('history',[])+[dict(action='regrade',at=now(),by=u['id'],by_name=u['name'],old_grade=old['grade'],old_version=old['version'],new_grade=new,new_version=version)]
            updates.append(dict(old,grade=new,version=version,history=history,at=now()))
        fingerprint=hashlib.sha256(encode([dict(changes=changes,versions=[decode(r)['at'] for r in rows])]).encode()).hexdigest()
        if b.get('confirm'):
            if b.get('fingerprint')!=fingerprint: raise HTTPException(409,'Dữ liệu đã đổi. Xem lại ảnh hưởng trước khi chấm lại.')
            for data in updates: put(c,'results',data['id'],u['id'],data)
            audit(c,u['id'],id,dict(action='regrade',changes=changes))
        return dict(changes=changes,fingerprint=fingerprint,applied=bool(b.get('confirm')))

@app.get('/api/export/{kind}')
def export(kind:str,exam_id:str='',class_id:str='',code:str='',sbd:str='',result_id:str='',u=Depends(user)):
    if kind not in ('csv','xlsx','pdf'): raise HTTPException(404)
    rows=results(exam_id,u)
    rows=[r for r in rows if (not class_id or r['class_id']==class_id) and (not code or r['code']==code) and (not sbd or sbd in r['sbd']) and (not result_id or r['id']==result_id)]
    if not rows: raise ValueError('Không có kết quả để xuất.')
    table=[['STT','SBD','Họ tên','Lớp','Mã đề','Đúng','Sai','Trống','Không hợp lệ','Điểm','Trạng thái','Thời gian','Phiên bản','Đáp án học sinh']]
    for i,r in enumerate(rows,1):
        g=r['grade']; table.append([i,r['sbd'],r['name'],r['class_name'],r['code'],g['correct'],g['wrong'],g['blank'],g['invalid'],display_score(g['score']),'Đã xác nhận' if r['status']=='confirmed' else r['status'],datetime.fromisoformat(r['at']).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),r['version'],';'.join(a or '_' for a in r['answers'])])
    mime={'csv':'text/csv','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pdf':'application/pdf'}[kind]
    return Response(export_table(table,kind),media_type=mime,headers={'Content-Disposition':f'attachment; filename="ket-qua.{kind}"'})

@app.get('/api/backup')
def backup(u=Depends(user)):
    # Teacher-scoped logical backup, including private originals and audit history.
    import base64
    out=dict(format='ChamViet-1',at=now())
    with db() as c:
        for table in ('exams','classes','scan_sessions','scans','results'):
            out[table]=[dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE owner=?',(u['id'],))]
        out['files']=[dict(id=r['id'],name=r['name'],mime=r['mime'],content=base64.b64encode(r['content']).decode()) for r in c.execute('SELECT * FROM files WHERE owner=?',(u['id'],))]
        out['audit']=[dict(r) for r in c.execute('SELECT * FROM audit WHERE owner=?',(u['id'],))]
    return Response(encode(out),media_type='application/json',headers={'Content-Disposition':'attachment; filename="sao-luu-rieng-tu.json"'})

@app.delete('/api/account')
async def delete_account(request:Request,response:Response,u=Depends(user)):
    b=await request.json()
    with db() as c:
        row=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()
        if b.get('confirm')!='XÓA DỮ LIỆU' or not hmac.compare_digest(hash_password(str(b.get('password','')),row['password'].split(':')[0]),row['password']):
            raise ValueError('Cần mật khẩu và cụm xác nhận XÓA DỮ LIỆU.')
        # Delete dependents in dependency order before removing the account.
        for table in ('results','scans','scan_sessions','exams','classes','files','audit'): c.execute(f'DELETE FROM {table} WHERE owner=?',(u['id'],))
        c.execute('DELETE FROM users WHERE id=?',(u['id'],))
    response.delete_cookie('omr_session'); return dict(ok=True)

@app.post('/api/export-selected/{kind}')
async def export_selected(kind:str,request:Request,u=Depends(user)):
    if kind not in ('csv','xlsx','pdf'): raise HTTPException(404)
    b=await request.json(); ids=b.get('ids',[])
    if not isinstance(ids,list) or len(ids)>10000: raise ValueError('Danh sách kết quả không hợp lệ.')
    wanted=set(ids)
    with db() as c:
        rows=[decode(r) for r in c.execute('SELECT data FROM results WHERE owner=? ORDER BY rowid',(u['id'],)) if decode(r)['id'] in wanted]
    if len(rows)!=len(wanted) or not rows: raise ValueError('Không tìm thấy đủ kết quả được chọn.')
    table=[['STT','SBD','Họ tên','Lớp','Mã đề','Đúng','Sai','Trống','Không hợp lệ','Điểm','Trạng thái','Thời gian','Phiên bản','Đáp án học sinh']]
    for i,r in enumerate(rows,1):
        g=r['grade']; table.append([i,r['sbd'],r['name'],r['class_name'],r['code'],g['correct'],g['wrong'],g['blank'],g['invalid'],display_score(g['score']),'Đã xác nhận' if r['status']=='confirmed' else r['status'],datetime.fromisoformat(r['at']).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),r['version'],';'.join(a or '_' for a in r['answers'])])
    mime={'csv':'text/csv','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pdf':'application/pdf'}[kind]
    return Response(export_table(table,kind),media_type=mime,headers={'Content-Disposition':f'attachment; filename="ket-qua.{kind}"'})

@app.post('/api/results/{id}/match')
async def match_student(id:str,request:Request,u=Depends(user)):
    b=await request.json()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        result=get(c,'results',id,u['id']); cls=get(c,'classes',b.get('class_id',''),u['id'])
        student=next((s for s in cls['students'] if s['sbd']==result['sbd']),None)
        if not student: raise ValueError('Không có SBD này trong lớp đã chọn. Sửa danh sách lớp trước.')
        result['history'].append(dict(action='match_student',at=now(),by=u['id'],by_name=u['name'],old=dict(name=result['name'],class_id=result['class_id']),new=student))
        result.update(name=student['name'],class_id=cls['id'],class_name=cls['name'],at=now())
        put(c,'results',id,u['id'],result); audit(c,u['id'],id,dict(action='match_student',class_id=cls['id']))
    return result


@app.post('/api/scans/{id}/preview')
async def preview_score(id:str,request:Request,u=Depends(user)):
    b=await request.json()
    with db() as c:
        scan=get(c,'scans',id,u['id']);exam=get(c,'exams',scan['exam_id'],u['id'])
    rev=next(r for r in exam['revisions'] if r['version']==scan['version'])
    code=b.get('code','');answers=b.get('answers',[])
    if code not in rev['keys'] or not isinstance(answers,list) or any(not isinstance(a,str) or len(a)>4 or any(ch not in 'ABCD' for ch in a) for a in answers): raise ValueError('Chọn mã đề và đáp án hợp lệ.')
    return grade(answers,rev['keys'][code],rev.get('code_weights',{}).get(code,rev['weights']))
