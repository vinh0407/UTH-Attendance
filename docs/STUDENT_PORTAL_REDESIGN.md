# Trang sinh viên: phân tích và phiên bản responsive

Cập nhật mới: [Chuyên cần theo học kỳ, tối đa 3 buổi nghỉ](STUDENT_ATTENDANCE_QUOTA.md) thay quy tắc cũ tính theo tiết.

## Kết quả phân tích trang cũ

- Sidebar desktop che nội dung trên điện thoại; bảng và bố cục thiếu khả năng thích ứng với màn hình nhỏ.
- Điều hướng có các mục chưa triển khai, nhiều nhãn tiếng Anh không đồng nhất.
- Tổng quan chưa ưu tiên rõ buổi học tiếp theo, lịch hôm nay và tình trạng chuyên cần.
- Lịch chỉ dựa vào thứ lặp lại, chưa phản ánh phiên học đã hủy hoặc chuyển ngày.
- Lỗi tải dữ liệu và trạng thái đăng nhập chưa được thể hiện đầy đủ; luồng làm mới có thể đọc event.currentTarget sau await.

## Phiên bản đã triển khai

Giữ Django và frontend HTML/CSS/JavaScript hiện có. Giao diện tiếng Việt, màu xanh UTH, dùng biểu tượng và logo nội bộ, không thêm framework hay dịch vụ ngoài.

- Desktop: sidebar cố định, tổng quan hai cột, bảng dữ liệu dễ đối chiếu.
- Mobile: điều hướng dưới gồm 5 mục, nội dung một cột, bảng điểm và điểm danh chuyển thành thẻ. Tablet tự thích ứng.
- Tổng quan: lớp đang diễn ra hoặc sắp tới, lịch hôm nay, chuyên cần, cảnh báo điều kiện dự thi và lịch sử gần đây.
- Lịch học: chọn ngày/cả tuần hiện tại; hiển thị hủy, hoãn, ngày chuyển và lý do từ phiên học thực tế.
- Chuyên cần: tìm kiếm không dấu theo tên/mã môn, lọc trạng thái, xem thêm từng 20 bản ghi.
- Bảng điểm: lọc học kỳ; học phần hiển thị điều kiện dự thi do backend tính.
- Hồ sơ: thông tin sinh viên, trạng thái đăng ký khuôn mặt, giao diện sáng/tối và đăng xuất.
- Có trạng thái trống, đang tải, lỗi làm mới, hết phiên; lỗi đăng xuất giữ nguyên phiên để người dùng thử lại.
- Dữ liệu cá nhân không được lưu vào localStorage; chỉ lưu lựa chọn giao diện. Mọi nội dung đưa vào HTML được escape.

## Mã nguồn

- APP/Portal/index.html và styles.css: cấu trúc và giao diện.
- APP/Portal/app.js: đăng nhập, điều hướng, tải dữ liệu và trạng thái ứng dụng.
- APP/Portal/portal-render.mjs: trình bày dữ liệu API.
- APP/Portal/portal-utils.mjs: thời gian, tìm kiếm và định dạng.
- admin_check/portal/student_schedule.py: hợp nhất lịch tuần với phiên học thực tế, giới hạn đúng lớp của sinh viên.
- admin_check/portal/views.py: bổ sung schedule_week; trả MIME JavaScript chính xác cho module trên Windows.

Mở qua Django tại /student-portal/. Không mở index.html trực tiếp vì ứng dụng cần API cùng origin và cookie phiên đăng nhập.

## Kiểm chứng

- python admin_check/manage.py test portal --noinput: 45 kiểm thử đạt.
- node tools/test_portal_utils.mjs: lớp đang học, thời gian kết thúc, hủy/hoãn, tuần qua ngày Chủ nhật, tìm không dấu, escape HTML.
- python -u tools/check_student_portal.py: kiểm thử Edge ở 320, 390, 768, 1024, 1440 px; các màn hình không tràn ngang; đăng nhập/đăng xuất, lọc, cảnh báo học phần, hủy lịch, chọn ngày, trạng thái trống, lỗi mạng, hết phiên, lưu giao diện tối.
- Ảnh trước/sau trong .impeccable/review/student-*.png. Dữ liệu trong ảnh được tạo trong SQLite tạm để kiểm thử, không thêm vào cơ sở dữ liệu sử dụng thật.

## Phạm vi và việc nên làm tiếp

- Đăng nhập hiện vẫn theo cơ chế mã sinh viên + lớp của hệ thống cũ. Cần chuyển sang mật khẩu hoặc SSO trước khi mở cho người dùng trên Internet; giao diện mới không thay đổi cơ chế xác thực này.
- Lịch tuần hiện tại; chưa có lịch học kỳ, thông báo đẩy hay xin phép vắng.
- Tỷ lệ có mặt tính từ các bản ghi đã có kết quả, không suy đoán những buổi chưa điểm danh. Quy tắc hiện tại: nghỉ 3 buổi cảnh báo, buổi thứ 4 rớt môn trong học kỳ.
- Nút Làm mới lấy dữ liệu mới nhất; trang cũng tự đồng bộ mỗi 30 giây khi đang mở. API trả toàn bộ lịch sử, việc xem thêm hiện phân trang tại trình duyệt; cần phân trang phía máy chủ khi dữ liệu lớn.
- Chưa triển khai lên máy chủ công khai.
