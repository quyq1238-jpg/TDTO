# Kết quả kiểm thử — 05/11/2026 (giờ Việt Nam)

Đây là kết quả chạy trong môi trường đám mây hiện tại, không phải chứng nhận độ chính xác thực địa hay xác nhận đã triển khai HTTPS công khai.

| Kiểm tra | Kết quả quan sát |
|---|---|
| Cài mới bằng `bash omr/install.sh` trong venv độc lập | Thành công; `pip check` không có xung đột |
| Chạy lại script thiết lập | Thành công, tái sử dụng gói và kiểm tra checksum mô hình |
| Bộ pytest | **20 passed**, không skipped/xfailed; lần cuối 16,08 giây |
| JavaScript `node --check` | Đạt |
| Máy chủ Uvicorn và CSDL SQLite | Khởi động thành công, API hoạt động |
| Chromium máy tính | Đăng ký → import đề/đáp án chung → xác nhận → upload ảnh → OMR thật → duyệt → lưu 10,00 điểm → chi tiết → XLSX |
| Chromium chiều rộng 390 px | Không tràn ngang, có điều hướng di động và thẻ kết quả |
| JavaScript trong luồng trình duyệt | Không ghi nhận lỗi pageerror |
| Mất phản hồi lưu điểm | Mô phỏng: backend đã lưu, chặn phản hồi; thử lại trả đúng bài đã lưu, tổng vẫn một kết quả |
| Camera | Kiểm tra trạng thái không có thiết bị; mô phỏng NotAllowedError, có hướng dẫn quyền và tải ảnh |
| GitHub | Đọc `origin HEAD` thành công qua xác thực sẵn có; không cần token bổ sung |
| Trang học liệu cũ | `git diff --exit-code -- index.html` đạt, không thay đổi |

## Nội dung 20 kiểm thử

- 5 điều kiện ảnh tổng hợp có nhãn: rõ, phối cảnh, ánh sáng không đều, bỏ trống/tô hai, ô mờ. Tổng **5 ảnh, 100 vị trí câu**, 99 giá trị có nhãn cần đọc khớp và 1 ô mờ được đưa vào trạng thái chưa chắc chắn. SBD/mã đề ở cả 5 ảnh được kiểm tra (45 chữ số). Không suy rộng các con số này thành độ chính xác ảnh điện thoại.
- 4 điều kiện phải từ chối: thiếu mốc, quá mờ, sai mã mẫu, phiếu ngược đầu.
- 1 kiểm tra phiếu PDF thực: kết xuất PDF do ứng dụng tạo bằng Poppler, kiểm tra 4 ô trống, sau đó tô tại tọa độ mẫu và đọc A/B/C/D, SBD `000001`, mã `001`.
- 1 luồng tích hợp từ import tới lưu điểm, chống gửi lại, thay thế có xác nhận, giữ ảnh/lịch sử, phiên bản đáp án, xem trước và xác nhận chấm lại, xuất CSV/XLSX/PDF, sao lưu và đăng nhập lại để đọc dữ liệu bền vững.
- 1 kiểm tra hai tài khoản: không đọc/sửa/tải/xuất được dữ liệu của nhau; yêu cầu thiếu CSRF hoặc sai origin bị từ chối.
- 1 kiểm tra bản nháp, mã đề không tồn tại, SBD chưa có trong lớp, trùng học sinh.
- 1 kiểm tra tính điểm đúng/sai/trống/tô nhiều, làm tròn HALF_UP và đầu vào không hợp lệ.
- 1 kiểm tra DOCX, tệp chung đề/đáp án, XLSX giữ số 0, xuất an toàn trước công thức, PDF giả bị từ chối.
- 1 kiểm tra xác nhận/mật khẩu khi xóa tài khoản và dữ liệu ảnh.
- 1 kiểm tra lưu nháp thiếu đáp án, chặn xác nhận nháp lỗi, điểm riêng cho từng mã đề và điểm tạm tính qua backend.
- 1 kiểm tra sao lưu/phục hồi SQLite, dữ liệu nguyên vẹn, không ghi đè bản sao cũ.
- 1 kiểm tra OCR tiếng Việt thực sự trên ảnh chữ và PDF chỉ chứa ảnh, kiểm tra tách câu/phương án và cảnh báo OCR.
- 1 kiểm tra hai yêu cầu lưu cùng lúc: cùng một ID kết quả, một hàng kết quả và một phiên quét.

## Giới hạn còn lại

- Chưa thử camera trên điện thoại vật lý; kiểm thử Chromium không thay thế kiểm tra Android/iOS, quyền camera, lấy nét hay đèn thiết bị thật.
- Chưa có ảnh giấy thật đã in, viết/tô/tẩy và nhãn chuẩn đa thiết bị. Chưa đo precision/recall hay hiệu chuẩn chỉ báo OMR. Mẫu tổng hợp không mô phỏng đầy đủ bóng, mép gấp, nhiễu và mực bút thực tế.
- Chỉ OMR-1, đầu phiếu hướng lên; không hỗ trợ mẫu tùy ý, tự chụp, đúng/sai, nhiều đáp án đúng hoặc trả lời ngắn.
- OCR vẫn có lỗi; không khôi phục hình, công thức hoặc bố cục như bản gốc. PDF tối đa 10 trang OCR mỗi tệp, trang chưa đọc cần nhập riêng.
- Chưa triển khai tên miền/TLS, cấu hình sao lưu ngoài máy hay dịch vụ giám sát. README có hướng dẫn triển khai và phục hồi; chưa xác minh một bản môi trường mới sau Publish.
- Mã nguồn ứng dụng nằm trong `omr/`. Việc lưu mã nguồn trên GitHub và Publish snapshot môi trường là hai thao tác riêng; cấu hình và snapshot môi trường cần người dùng xem, lưu và Publish qua giao diện môi trường.

Kịch bản trình duyệt có thể chạy lại bằng Python có Playwright và Chromium cài sẵn, với backend ở cổng 8000:

```bash
/workspace/omr-venv/bin/python omr/tests/browser_smoke.py
```

Kịch bản dùng tài khoản thử mới và xóa tài khoản khi hoàn tất; không nhập dữ liệu học sinh thật. Kết quả và ảnh tổng hợp trong `samples/` được ghi nhãn rõ.
