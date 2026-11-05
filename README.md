# Chấm Việt — chấm trắc nghiệm A–D

Ứng dụng hoạt động với backend, dữ liệu bền vững và OMR thật cho **mẫu OMR-1 do hệ thống tạo**. Trang học liệu `../index.html` được giữ nguyên. Không có điểm ngẫu nhiên hoặc nhận dạng giả trong ứng dụng.

## Chạy trong môi trường này

Từ `/workspace/B-i-4.-B-N-TRONG-M-Y-T-NH`:

```bash
bash omr/install.sh
/workspace/omr-clean-venv/bin/python -m uvicorn omr.app:app --host 0.0.0.0 --port 8000 --no-access-log
```

Script tạo venv riêng, cài phiên bản ghim, kiểm tra phụ thuộc và khởi tạo SQLite ngoài checkout. Poppler (`pdftoppm`), Tesseract và font DejaVu đã có trên máy này. Script tải mô hình tiếng Việt từ commit chính thức, kiểm tra SHA-256 trước khi dùng; không tắt TLS. Mạng cần PyPI, files.pythonhosted.org và raw.githubusercontent.com; không cần khóa AI hay token GitHub bổ sung.

Kiểm tra nội bộ: `curl --fail http://127.0.0.1:8000/api/health` phải trả `status: ok`. Đây là địa chỉ kiểm tra trong máy, không phải liên kết xem trước cho điện thoại.

Trên máy Linux khác: Python 3.12, `python3-venv`, `tesseract-ocr`, `poppler-utils`, `fonts-dejavu-core`; tạo venv và `pip install -r omr/requirements.txt`. Điều chỉnh đường dẫn tuyệt đối trong script nếu checkout ở nơi khác. Không cần Node hay bước build frontend. `.env.example` là tài liệu cấu hình, ứng dụng đọc biến môi trường thực; không tự nạp tệp `.env`.

## Quy trình sử dụng

1. Đăng ký giáo viên với email và mật khẩu ít nhất 10 ký tự. Chưa cài sẵn tài khoản hay dữ liệu học sinh thật.
2. Vào **Lớp học**, import CSV/XLSX, sửa từng dòng SBD và tên, kiểm tra rồi lưu. Tệp mẫu ở `samples/hoc-sinh.csv` hoặc tải trên giao diện. CSV UTF-8; XLSX nên lưu SBD dạng chuỗi hoặc định dạng `000000` để giữ số 0 đầu.
3. **Tạo bài kiểm tra**: khai báo môn/lớp/ngày, số câu, thang điểm, số chữ số SBD/mã đề và 2–4 cột. Tối đa 27 hàng mỗi cột, tối đa 100 câu.
4. Import DOCX/PDF/TXT/ảnh của đề và CSV/XLSX đáp án. Hệ thống giữ bản gốc và văn bản trích xuất. Mở bản gốc để kiểm tra hình, công thức, mã chương trình. Sửa nội dung và A–D qua các trường từng câu hoặc JSON nâng cao.
5. Kiểm tra bảng đáp án. Cần đủ câu 1…N cho mỗi mã, một đáp án A–D. Điểm riêng được khai báo cho **từng mã đề**, tổng bằng thang điểm; để trống điểm của cả mã để chia đều. Có thể lưu nháp thiếu đáp án, nhưng chưa thể chấm.
6. Đánh dấu đã đối chiếu và xác nhận rồi lưu. Mỗi lần nội dung đáp án/điểm/mẫu thay đổi và được xác nhận sẽ tạo phiên bản mới; không đổi điểm cũ.
7. Xem/in PDF A4 **100%, kích thước thực**, giữ đủ bốn mốc. Phiếu sạch được vẽ từ hình học, không dùng ảnh nền. Tô đủ SBD và mã đề, kể cả số 0 đầu.
8. **Quét**: chọn bài và lớp, mở camera sau hoặc tải PNG/JPEG/WebP. Chụp thủ công, đầy đủ phiếu, đầu phiếu hướng lên trên. Không tự động chụp hoặc tự tuyên bố đủ góc trước khi xử lý ảnh.
9. **Duyệt nhận dạng**: kiểm tra SBD, chọn/xác nhận rõ mã đề, xem ảnh đã căn chỉnh và phóng to từng câu. Máy đọc, chỉnh sửa của giáo viên và đáp án chính thức được giữ riêng. Ô trống, tô nhiều và ô mờ không bị ép thành một lựa chọn.
10. Xác nhận tất cả vùng cần kiểm tra rồi lưu điểm chính thức. Mặc định sai/trống/tô nhiều được 0 sau khi giáo viên duyệt; có thể chọn quy tắc buộc giải quyết tô nhiều. Mã đề không tồn tại hoặc SBD thiếu sẽ chặn lưu; lượt quét còn trong danh sách chờ.
11. SBD chưa có trong lớp cần ghép đúng hoặc xác nhận lưu chưa ghép; có thể ghép sau trong chi tiết kết quả. Bài trùng cần xem bài cũ rồi xác nhận thay thế; bài cũ được giữ trong lịch sử. Thử lại cùng lượt quét sau lỗi mạng không tạo kết quả thứ hai.
12. **Kết quả**: lọc theo bài/lớp/SBD/tên/mã/ngày/trạng thái, xem ảnh và lịch sử, xuất đúng các bài đang lọc sang CSV/XLSX/PDF; PDF cá nhân nằm ở chi tiết kết quả.
13. **Chấm lại**: sửa đáp án, xác nhận phiên bản mới, xem điểm cũ/mới rồi xác nhận áp dụng. Lịch sử giữ điểm và phiên bản trước đó. Nếu dữ liệu đổi sau bước xem trước thì phải xem lại.
14. **Thống kê**: chỉ dùng bài đã xác nhận, thống kê riêng từng mã đề, hiển thị số bài/phiên bản; có trung bình, trung vị, min/max, ngưỡng đạt, phân bố điểm, tỷ lệ đúng và tần suất A–D. Chưa có ánh xạ đảo câu để gộp các mã đề.

## Định dạng import

Đáp án CSV/XLSX (sheet đầu tiên, cột theo đúng thứ tự):

```csv
ma_de,cau,dap_an,diem
001,1,A,2.5
001,2,B,2.5
001,3,C,2.5
001,4,D,2.5
```

Số 0 đầu mã đề bắt buộc khớp cấu hình mẫu. CSV nhận dấu phẩy, chấm phẩy hoặc tab. Không nhận ô công thức trong XLSX. CSV xuất có BOM UTF-8; các giá trị có thể bị diễn giải thành công thức được vô hiệu hóa. XLSX xuất giữ SBD là chuỗi.

Đề: `Câu 1. Nội dung ... A. ... B. ... C. ... D. ...` hoặc mỗi phương án một dòng. Tệp mẫu `samples/de-va-dap-an.txt` chứa đề và khối `[DAP_AN]` cuối tệp; DOCX/PDF có văn bản cũng nhận khối này. Hai tệp riêng vẫn dùng được. Không đoán đáp án từ nội dung đề.

OCR chạy **tại máy chủ**, không gửi tài liệu tới dịch vụ ngoài. Ảnh OCR và PDF scan vẫn cần đối chiếu toàn bộ. PDF tối đa 100 trang; tối đa 10 trang cần OCR trong một lần nhập. Trang chưa đọc được được liệt kê để nhập riêng, không bỏ qua im lặng. Tệp gốc và cảnh báo trích xuất luôn có trước bước giáo viên xác nhận. Ảnh/công thức nhúng không được tái dựng vào mô hình câu hỏi; xem bản gốc.

## Kiến trúc và dữ liệu

- Frontend: HTML/CSS/JavaScript thuần, tiếng Việt, ưu tiên điện thoại, không cần CDN.
- FastAPI cùng origin, cookie HttpOnly/SameSite, kiểm tra CSRF và nguồn yêu cầu, mật khẩu scrypt với salt riêng. Mỗi thao tác backend kiểm tra chủ sở hữu.
- SQLite, giao dịch khi lưu/chấm lại, ràng buộc duy nhất `(exam_id,sbd)` và `scan_id`. JSON cho cấu hình có phiên bản; BLOB cho tệp/ảnh riêng tư, không nằm trong static hay Git.
- OpenCV: tìm bốn mốc, biến đổi phối cảnh, kiểm tra mã hình học có checksum, đo mức tối trong lòng ô kết hợp tương phản nền cục bộ, phân loại trống/một/nhiều/chưa chắc chắn. Đây là thuật toán chưa hiệu chuẩn thực địa, không phải xác suất chính xác.
- Một nguồn tọa độ (`geometry.py`) cho cả PDF, bộ nhận dạng, mẫu và phép thử. Mã nhận diện mẫu OMR-1 được in và mã hóa trên phiếu; không tự đọc mẫu bất kỳ.
- `store.py` chứa migration v1 idempotent và bảng `schema_version`. Các bảng: users, sessions, exams (câu hỏi, mã đề, phiên bản đáp án, mẫu), classes (học sinh), files (tài liệu và ảnh), scan_sessions (phiên quét), scans (máy đọc, ảnh), results (duyệt, điểm, lịch sử), audit. Dữ liệu theo tài khoản ở mọi bảng nội dung.
- Phiên quét và các lượt quét được lưu bền vững, nhưng bộ đếm nhanh hiển thị chỉ tính trong lần mở trình duyệt. Đóng trình duyệt không mất lượt quét/điểm; có thể tiếp tục duyệt trong danh sách chờ.
- Dữ liệu mặc định: `/workspace/omr-data/omr.sqlite3`; đặt `OMR_DATA_DIR` để thay đổi. Thư mục quyền 700, tệp 600. Thời gian lưu UTC, giao diện và xuất bảng điểm dùng giờ Việt Nam. Điểm tính Decimal, chỉ làm tròn HALF_UP 2 chữ số khi hiển thị/xuất.
- Giới hạn upload 15 MB, ảnh tối đa 25 triệu điểm ảnh, XLSX/DOCX kiểm tra dung lượng giải nén. Không ghi body, mật khẩu hay ảnh vào log. Giới hạn 8 lần đăng nhập lỗi/15 phút trên email và IP; triển khai công khai cần thêm giới hạn truy cập/tạo tài khoản tại reverse proxy.

## Sao lưu và phục hồi

Giáo viên có thể tải bản JSON của riêng tài khoản qua **Cài đặt**; bản đó gồm ảnh và lịch sử. Chưa có chức năng nhập lại JSON trong giao diện.

Quản trị viên sao lưu toàn bộ SQLite bằng backup API của SQLite (gồm BLOB ảnh, tài khoản và lịch sử):

```bash
/workspace/omr-clean-venv/bin/python -m omr.backup backup /workspace/omr-data/omr.sqlite3 /workspace/backup-2026-11-05.sqlite3
```

Đích phải chưa tồn tại. Đặt lịch hằng ngày, mã hóa và chuyển bản sao sang nơi lưu trữ riêng có kiểm soát quyền truy cập. Snapshot môi trường phát triển không thay thế sao lưu dữ liệu học sinh.

Để phục hồi: dừng dịch vụ, giữ nguyên thư mục dữ liệu cũ làm bản dự phòng, tạo thư mục dữ liệu mới quyền 700 rồi:

```bash
/workspace/omr-clean-venv/bin/python -m omr.backup restore /workspace/backup-2026-11-05.sqlite3 /workspace/omr-restored/omr.sqlite3
```

Đặt `OMR_DATA_DIR=/workspace/omr-restored`, khởi động lại, kiểm tra đăng nhập/kết quả/ảnh. Công cụ kiểm tra toàn vẹn và không ghi đè CSDL đang có. Các bản sao chứa dữ liệu cá nhân; quản trị viên cần chính sách lưu/xóa bản sao phù hợp. Xóa tài khoản trong giao diện yêu cầu mật khẩu và xác nhận, xóa dữ liệu hoạt động của tài khoản; bản sao ngoài ứng dụng cần xử lý riêng.

## Triển khai HTTPS

Chưa triển khai lên tên miền công khai. Camera điện thoại cần HTTPS; máy tính có thể thử qua loopback. Ví dụ máy Linux đã có DNS và Caddy:

```caddyfile
cham.example.edu.vn {
    request_body { max_size 17MB }
    reverse_proxy 127.0.0.1:8000
}
```

Chạy backend bằng tài khoản riêng, ổ đĩa bền vững, `OMR_SECURE_COOKIE=1`, `OMR_ORIGIN=https://cham.example.edu.vn`, `OMR_DATA_DIR=/srv/cham-viet/data` và bind `127.0.0.1`. Dùng systemd hoặc bộ quản lý tiến trình để khởi động lại; một worker phù hợp phiên bản SQLite này. Giữ TLS, đặt giới hạn CPU/bộ nhớ/thời gian và rate limit ở proxy. Backend không cung cấp CORS cho origin ngoài. Không đưa mật khẩu hoặc khóa vào frontend. Bản v1 chưa có xác minh email, quên mật khẩu, quản trị trường hoặc chia sẻ dữ liệu giữa giáo viên.

## Kiểm thử và giới hạn

```bash
/workspace/omr-clean-venv/bin/python -m pytest omr/tests -q
node --check omr/static/app.js
```

`TEST_RESULTS.md` ghi kết quả thực tế và giới hạn. `tests/browser_smoke.py` là kiểm thử tùy chọn với Playwright/Chromium đã có trong máy này; chạy bằng Python runtime có Playwright, với backend đang hoạt động. Kịch bản tạo rồi xóa tài khoản thử, dùng ảnh có nhãn, mô phỏng mất phản hồi khi lưu và từ chối camera. Không thay thế kiểm thử camera trên điện thoại thật.

Mẫu trong `samples/` ghi rõ minh họa/tổng hợp. Sinh lại bằng `python -m omr.samples.generate` từ gốc kho mã (chỉ khi chủ ý cập nhật mẫu).

**Chưa nghiệm thu thực địa:** chưa có bộ ảnh điện thoại thật và nhãn chuẩn đủ lớn, chưa đánh giá quét giấy đã in dưới nhiều ánh sáng/thiết bị; chưa có hiệu chuẩn ngưỡng OMR. Các ảnh thiếu mốc/mờ/sai mẫu bị từ chối; một số ảnh chất lượng kém vẫn có thể bị đọc sai. Giáo viên phải duyệt từng bài. Không hỗ trợ mẫu tùy ý, tự chụp, nhiều đáp án đúng, dạng đúng/sai hoặc trả lời ngắn. OCR và phân tích DOCX/PDF không bảo toàn hình/công thức, nên đối chiếu bản gốc là bắt buộc.

Mô hình OCR tiếng Việt: [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd), Apache-2.0. Mô hình được cài ngoài kho mã tại `/workspace/omr-ocr/`; SHA-256 được ghim trong `install.sh`.
