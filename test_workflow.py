import io
import json
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from omr import store
from omr.app import app
from omr.geometry import geometry,fixture,recognize
from omr.domain import grade,validate_exam
from omr.documents import extract,parse_key,display_score,export_table,spreadsheet,sheet_pdf

H={'X-Requested-With':'ChamViet'}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('OMR_DATA_DIR',str(tmp_path/'data'));store.init()
    c=TestClient(app)
    response=c.post('/api/auth/register',json={'name':'Giáo viên','email':'teacher@example.com','password':'safe-test-password'},headers=H)
    assert response.status_code==200,response.text
    return c

def post(c,url,b): return c.post('/api'+url,json=b,headers=H)
def make_exam(c,**overrides):
    body=dict(name='Bài kiểm tra OMR',n=4,scale=10,keys={'001':['A','B','C','D'],'002':['D','C','B','A']},confirm=True)
    body.update(overrides); r=post(c,'/exams',body);assert r.status_code==200,r.text;return r.json()
def upload(c,e,answers=None,sbd='000001',code='001'):
    img=fixture(validate_exam(e)['geometry'],answers or ['A','B','C','D'],sbd,code)
    r=c.post('/api/scans/'+e['id'],files={'file':('labelled-synthetic.png',cv2.imencode('.png',img)[1].tobytes(),'image/png')},headers=H)
    assert r.status_code==200,r.text;return r.json()
def confirm(c,s,**overrides):
    b=dict(scan_id=s['id'],sbd=s['machine']['sbd'],code=s['machine']['code'],answers=[a['value'] for a in s['machine']['answers']],reviewed=True)
    b.update(overrides);return post(c,'/results',b)

def test_full_workflow_versioning_and_idempotency(client):
    c=client
    r=c.post('/api/import',files={'file':('key.csv',b'ma_de,cau,dap_an\n001,1,A\n001,2,B\n001,3,C\n001,4,D\n','text/csv')},headers=H)
    assert r.status_code==200 and not r.json()['errors']
    e=make_exam(c,original_files=[r.json()['file_id']]); assert e['active_version']==1
    pdf=c.get('/api/exams/'+e['id']+'/sheet.pdf');assert pdf.content.startswith(b'%PDF')
    s=upload(c,e); assert s['machine']['sbd']=='000001'
    assert confirm(c,s,reviewed=False).status_code==422
    saved=confirm(c,s); assert saved.status_code==200,saved.text
    result=saved.json();assert result['grade']['score']==10
    assert confirm(c,s).json()['id']==result['id']
    assert len(c.get('/api/results').json())==1
    s2=upload(c,e,['A','B','','AB']);duplicate=confirm(c,s2);assert duplicate.status_code==409
    assert c.get('/api/results').json()[0]['grade']['score']==10
    replaced=confirm(c,s2,replace_id=result['id'],replace_at=result['at']);assert replaced.status_code==200,replaced.text
    result=replaced.json();assert result['grade']['score']==5 and result['history'][0]['action']=='replace'
    assert c.get('/api/pending').json()==[]
    e['keys']['001']=['B','B','C','D'];e['confirm']=True
    e=post(c,'/exams',e).json();assert e['active_version']==2
    assert c.get('/api/results').json()[0]['grade']['score']==5
    preview=post(c,'/exams/'+e['id']+'/regrade',{}).json();assert preview['changes'][0]['new_score']==2.5
    applied=post(c,'/exams/'+e['id']+'/regrade',dict(confirm=True,fingerprint=preview['fingerprint']));assert applied.status_code==200
    result=c.get('/api/results').json()[0];assert result['grade']['score']==2.5 and result['version']==2
    assert result['history'][-1]['old_grade']['score']==5
    for kind in ('csv','xlsx','pdf'):
        r=post(c,'/export-selected/'+kind,{'ids':[result['id']]});assert r.status_code==200 and len(r.content)>100
    assert '000001' in c.get('/api/export/csv').content.decode('utf-8-sig')
    backup=c.get('/api/backup').json();assert backup['files'] and backup['results'] and backup['audit']
    # New client/session, same database: persistence is independent of browser state.
    other=TestClient(app);assert post(other,'/auth/login',dict(email='teacher@example.com',password='safe-test-password')).status_code==200
    assert other.get('/api/results').json()[0]['id']==result['id']

def test_tenant_permissions_and_csrf(client):
    c=client;e=make_exam(c);s=upload(c,e);r=confirm(c,s).json()
    stranger=TestClient(app)
    assert post(stranger,'/auth/register',dict(name='Khác',email='other@example.com',password='other-password-123')).status_code==200
    for path in ['/exams/'+e['id']+'/sheet.pdf','/files/'+s['aligned_file'],'/scans/'+s['id']]:assert stranger.get('/api'+path).status_code==404
    assert stranger.get('/api/results').json()==[]
    assert post(stranger,'/results',dict(scan_id=s['id'])).status_code==404
    assert post(stranger,'/export-selected/csv',dict(ids=[r['id']])).status_code==422
    assert post(stranger,'/exams',dict(e,confirm=True)).status_code==404
    assert c.post('/api/classes',json={}).status_code==403
    assert c.post('/api/classes',json={},headers=dict(H,Origin='https://evil.example')).status_code==403
    assert TestClient(app).get('/api/files/'+s['aligned_file']).status_code==401

def test_unknown_code_class_and_draft(client):
    c=client;draft=make_exam(c,confirm=False)
    assert c.post('/api/scans/'+draft['id'],files={'file':('x.png',b'x')},headers=H).status_code==422
    e=make_exam(c);s=upload(c,e,code='999')
    assert confirm(c,s).status_code==422
    assert confirm(c,s,code='002').json()['grade']['score']==0
    students=[dict(sbd='000002',name='Học sinh')]
    cls=post(c,'/classes',dict(name='11A1',students=students)).json()
    assert post(c,'/classes',dict(name='Trùng',students=students*2)).status_code==422
    s=upload(c,e,sbd='000003')
    assert confirm(c,s,class_id=cls['id']).status_code==422
    assert confirm(c,s,class_id=cls['id'],unknown_student_confirmed=True).status_code==200

def test_rounding_and_input_validation():
    assert display_score(2.675)=='2.68'
    assert grade(['A','','AB','C'],['A','B','C','D'],[2.5]*4)==dict(score=2.5,display='2.50',correct=1,wrong=1,blank=1,invalid=1,details=[dict(number=i+1,answer=a,key=k,state=s,weight=2.5) for i,(a,k,s) in enumerate(zip(['A','','AB','C'],['A','B','C','D'],['correct','blank','invalid','wrong']))])
    assert parse_key([['001','1','A'],['001','1','B']])['errors']
    assert parse_key([['001','1','AB']])['errors']
    for override in [dict(keys={'001':['A']}),dict(weights=[1]*4),dict(scale=float('nan')),dict(keys={'001':['A','B','C','AB']})]:
        with pytest.raises(ValueError):validate_exam(dict({'name':'Exam','n':4,'keys':{'001':['A']*4}},**override))

def test_imports_and_spreadsheet_safety():
    from openpyxl import Workbook
    from docx import Document
    doc=Document();doc.add_paragraph('Câu 1. Nội dung A. Một B. Hai C. Ba D. Bốn');out=io.BytesIO();doc.save(out)
    parsed=extract(out.getvalue(),'exam.docx');assert parsed['questions'][0]['choices']['D']=='Bốn'
    parsed=extract(b'Cau\n[DAP_AN]\nma_de,cau,dap_an\n001,1,A','test.txt');assert parsed['key']['items'][0]['code']=='001'
    wb=Workbook();ws=wb.active;ws.append(['sbd','ho_ten']);ws.append([1,'Nguyễn An']);ws['A2'].number_format='000000';out=io.BytesIO();wb.save(out)
    assert spreadsheet(out.getvalue(),'.xlsx')[1][0]=='000001'
    content=export_table([['SBD','Tên'],['000001','=HYPERLINK("evil")']],'xlsx')
    from openpyxl import load_workbook
    row=list(load_workbook(io.BytesIO(content)).active.rows)[1]
    assert row[0].value=='000001' and row[1].data_type!='f'
    with pytest.raises(ValueError):extract(b'not a pdf','x.pdf')

def test_delete_only_own_data(client):
    e=make_exam(client);s=upload(client,e);confirm(client,s)
    assert client.request('DELETE','/api/account',json={'password':'wrong','confirm':'XÓA DỮ LIỆU'},headers=H).status_code==422
    r=client.request('DELETE','/api/account',json={'password':'safe-test-password','confirm':'XÓA DỮ LIỆU'},headers=H)
    assert r.status_code==200,r.text
    assert client.get('/api/me').status_code==401
    with store.db() as c:assert c.execute('SELECT count(*) FROM files').fetchone()[0]==0

def test_incomplete_draft_and_per_code_weights(client):
    draft=make_exam(client,confirm=False,keys={'001':['','','','']})
    assert draft['active_version'] is None
    assert post(client,'/exams',dict(draft,confirm=True)).status_code==422
    e=make_exam(client,code_weights={'001':[1,2,3,4],'002':[4,3,2,1]})
    s=upload(client,e,['A','','',''])
    assert confirm(client,s).json()['grade']['score']==1
    s2=upload(client,e,['D','','',''],sbd='000002',code='002')
    assert confirm(client,s2).json()['grade']['score']==4
    assert post(client,'/scans/'+s2['id']+'/preview',dict(code='002',answers=['D','','',''])).json()['display']=='4.00'
    assert client.post('/api/exams',json=[],headers=H).status_code==422

def test_backup_restore_integrity(tmp_path):
    import sqlite3
    from omr.backup import backup
    source=tmp_path/'source.db';target=tmp_path/'backup.db';restored=tmp_path/'restored.db'
    with sqlite3.connect(source) as c:c.execute('CREATE TABLE example(value TEXT)');c.execute('INSERT INTO example VALUES(?)',('000001',))
    backup(source,target);backup(target,restored)
    with sqlite3.connect(restored) as c:assert c.execute('SELECT value FROM example').fetchone()[0]=='000001'
    with pytest.raises(FileExistsError):backup(source,target)

def test_local_vietnamese_ocr_image_and_scanned_pdf():
    import shutil
    from pathlib import Path
    from PIL import Image,ImageDraw,ImageFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    if not shutil.which('tesseract') or not Path('/workspace/omr-ocr/vie.traineddata').is_file():pytest.skip('Vietnamese OCR model is optional outside the configured cloud environment')
    image=Image.new('RGB',(1400,800),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',42)
    for i,text in enumerate(['Câu 1. Thiết bị nào xử lý lệnh?','A. CPU','B. Màn hình','C. Bàn phím','D. Chuột']):draw.text((60,50+100*i),text,font=font,fill='black')
    out=io.BytesIO();image.save(out,format='PNG')
    result=extract(out.getvalue(),'ocr.png');assert len(result['questions'])==1 and result['questions'][0]['choices']['A']=='CPU'
    if shutil.which('pdftoppm'):
        pdf=io.BytesIO();c=canvas.Canvas(pdf,pagesize=(700,400));c.drawImage(ImageReader(image),0,0,700,400);c.showPage();c.save()
        scanned=extract(pdf.getvalue(),'scan.pdf');assert len(scanned['questions'])==1 and any('OCR' in w for w in scanned['warnings'])

def test_concurrent_same_scan_is_one_result(client):
    from concurrent.futures import ThreadPoolExecutor
    e=make_exam(client);s=upload(client,e)
    def save(_):
        other=TestClient(app);other.cookies.update(client.cookies);return confirm(other,s)
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(save,range(2)))
    assert all(r.status_code==200 for r in responses)
    assert responses[0].json()['id']==responses[1].json()['id']
    assert len(client.get('/api/results').json())==1
    with store.db() as c:
        assert c.execute('SELECT count(*) FROM scan_sessions').fetchone()[0]==1
