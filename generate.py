"""Run from repository root: python -m omr.samples.generate."""
import json
from pathlib import Path
import cv2
from omr.geometry import geometry,fixture
from omr.documents import sheet_pdf

out=Path(__file__).parent
g=geometry(4)
(out/'phieu-4-cau.pdf').write_bytes(sheet_pdf(g,'MINH HỌA · 4 câu','DỮ LIỆU THỬ','Tin học'))
(out/'hinh-hoc-4-cau.json').write_text(json.dumps(g,ensure_ascii=False,indent=2),encoding='utf-8')
image=fixture(g,['A','B','C','D'])
cv2.putText(image,'SYNTHETIC TEST - NOT A REAL SUBMISSION',(120,560),cv2.FONT_HERSHEY_SIMPLEX,.6,0,1)
cv2.imwrite(str(out/'phieu-tong-hop-co-nhan.png'),image)
(out/'nhan-chuan.json').write_text(json.dumps(dict(synthetic=True,sbd='000001',code='001',answers=['A','B','C','D']),indent=2),encoding='utf-8')
print('Đã tạo mẫu PDF, hình học, ảnh tổng hợp và nhãn chuẩn; không phải bài thật.')
