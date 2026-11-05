import cv2
import numpy as np
import pytest
from omr.geometry import geometry,fixture,recognize

def encoded(img):return cv2.imencode('.png',img)[1].tobytes()

@pytest.mark.parametrize('condition',['clear','perspective','uneven','blank-multiple','faint'])
def test_labelled_synthetic(condition):
    g=geometry();answers=['A','B','C','D']*5
    if condition=='blank-multiple':answers[0]='';answers[1]='AB'
    img=fixture(g,answers)
    if condition=='perspective':
        matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[1000,0],[1000,1414],[0,1414]]),np.float32([[45,35],[950,70],[980,1380],[25,1330]]))
        img=cv2.warpPerspective(img,matrix,(1000,1414),borderValue=220)
    if condition=='uneven':img=(img.astype(float)*np.linspace(.55,1,1000)[None,:]).astype(np.uint8)
    if condition=='faint':
        x,y=g['answers'][0][0];cv2.circle(img,(x,y),7,210,-1)
    result,_=recognize(encoded(img),g)
    assert result['sbd']=='000001' and result['code']=='001'
    for i,(expected,actual) in enumerate(zip(answers,result['answers'])):
        if condition=='faint' and i==0:
            assert actual['state']=='uncertain'
        else:assert actual['value']==expected,(condition,i,actual)
    if condition=='blank-multiple':assert result['answers'][0]['state']=='blank' and result['answers'][1]['state']=='multiple'

@pytest.mark.parametrize('condition',['missing','blur','wrong-template','upside-down'])
def test_reject_bad_input(condition):
    g=geometry();img=fixture(g,['A']*20)
    if condition=='missing':img[:100,:100]=255
    if condition=='blur':img=cv2.GaussianBlur(img,(41,41),15)
    if condition=='upside-down':img=cv2.rotate(img,cv2.ROTATE_180)
    target=geometry(21) if condition=='wrong-template' else g
    with pytest.raises(ValueError):recognize(encoded(img),target)

def test_printed_pdf_geometry_and_recognition(tmp_path):
    import shutil,subprocess
    from omr.documents import sheet_pdf
    if not shutil.which('pdftoppm'):pytest.skip('Poppler is an optional PDF verification tool')
    g=geometry(4);pdf=tmp_path/'sheet.pdf';pdf.write_bytes(sheet_pdf(g,'Đề minh họa'))
    result=subprocess.run(['pdftoppm','-scale-to-x','1000','-scale-to-y','1414','-singlefile','-png',str(pdf),str(tmp_path/'printed')],capture_output=True,timeout=30)
    assert result.returncode==0
    img=cv2.imread(str(tmp_path/'printed.png'),cv2.IMREAD_GRAYSCALE)
    blank,_=recognize(encoded(img),g)
    assert all(r['state']=='blank' for r in blank['answers'])
    for row,a in zip(g['answers'],'ABCD'):
        x,y=row['ABCD'.index(a)];cv2.circle(img,(x,y),7,0,-1)
    for name,value in [('sbd','000001'),('code','001')]:
        for i,k in enumerate(value):cv2.circle(img,tuple(g[name][i][int(k)]),7,0,-1)
    read,_=recognize(encoded(img),g)
    assert [r['value'] for r in read['answers']]==list('ABCD')
    assert read['sbd']=='000001' and read['code']=='001'
