# Chuyên cần theo học kỳ và giới hạn 3 buổi nghỉ

Quy tắc đã được xác nhận: 1 lượt là 1 buổi vắng, tối đa 3 lượt cho mỗi môn trong mỗi học kỳ.

| Buổi vắng đã chốt | Vòng tròn | Trạng thái |
| --- | --- | --- |
| 0 | 3/3, đầy màu | Còn 3 lượt |
| 1 | 2/3, màu phủ 2/3 | Còn 2 lượt |
| 2 | 1/3, màu phủ 1/3 | Còn 1 lượt |
| 3 | 0/3, không còn màu | Cảnh báo hết lượt; chưa rớt |
| 4 trở lên | 0/3 | Rớt môn do chuyên cần |

## Nguồn dữ liệu và hành vi

- AcademicTerm lưu mã/tên/ngày bắt đầu/ngày kết thúc; Schedule liên kết học kỳ. Quản lý học kỳ trong Django Admin và chọn học kỳ khi tạo lịch ở trang quản lý.
- student_attendance.py tính kết quả trên máy chủ theo sinh viên + môn + học kỳ, dựa trên các AttendanceRecord thuộc AttendanceSession đã completed.
- Không tự coi một buổi tương lai hoặc đang diễn ra là vắng. Giảng viên kết thúc phiên bằng luồng hiện có để ghi nhận những sinh viên không có mặt.
- Buổi hủy, hoãn, chưa chốt và bản ghi đi muộn không trừ lượt. API kết thúc buổi học từ chối phiên đã hủy/hoãn.
- Không suy đoán học kỳ cho dữ liệu cũ. Lịch chưa phân kỳ hiện —/3 và yêu cầu gắn học kỳ; không tự kết luận rớt từ lịch sử chưa phân kỳ.
- Kết quả là dữ liệu dẫn xuất từ các bản ghi điểm danh lưu trong cơ sở dữ liệu. Không ghi đè điểm số do giảng viên nhập. Màn hình Bảng điểm có cột Chuyên cần riêng; Học phần và Tổng quan dùng cùng kết quả từ backend.
- Khi giảng viên sửa điểm danh, kết quả và thông báo tự tính lại; không giữ trạng thái rớt sai sau khi dữ liệu được sửa.
- Thông báo nằm trong trang Chuyên cần, không gửi email/SMS hay push. Trang tự tải lại dữ liệu mỗi 30 giây khi đang mở, hoặc khi quay lại tab; nút Làm mới cập nhật ngay.
- Lọc học kỳ áp dụng cho cả thẻ môn và lịch sử điểm danh. Không cộng lượt nghỉ của môn học lại ở kỳ trước.

## Demo local

Tài khoản 2251120064 / CN22A, tên Sinh viên Demo, có 5 môn minh họa lần lượt 3/3, 2/3, 1/3, 0/3 cảnh báo, 0/3 rớt. Tất cả môn đều mang tên Demo và không phải kết quả học tập thật.

Seeder tools/seed_student_quota_demo.py chỉ chạy khi khớp chính xác hồ sơ demo. Đã sao lưu SQLite trước migration 0010.

## Kiểm thử

- 54 kiểm thử Django: mốc 0–4, tính theo buổi thay vì tiết, sửa sai, cách ly sinh viên/học kỳ, chưa phân kỳ, hủy/hoãn, kết thúc buổi thứ tư và kết thúc lặp lại.
- Kiểm thử Edge: vòng tròn, thông báo, đổi học kỳ, tự cập nhật trạng thái khi dữ liệu đổi, lọc lịch sử, giao diện tối và 5 độ rộng 320–1440 px.
- Ảnh: .impeccable/review/student-quota-desktop.png, student-quota-mobile.png, student-quota-dark.png.
