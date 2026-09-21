# Phân tích dự án tham chiếu và tích hợp vào UTH Attendance

Ngày thực hiện: 18/09/2026.

Nguồn tham chiếu: `C:\Users\ADMIN\Downloads\Attendance-system-with-face-main\Attendance-system-with-face-main`.

Đích tích hợp: `C:\VisualStudio\UTH-Attendance-main`.

## 1. Kết luận kiến trúc

Hai dự án cùng sử dụng InsightFace với `buffalo_l`. Giá trị đáng học từ dự án tham chiếu là cách tổ chức quy trình quanh AI: tích lũy nhiều lần nhận diện, kiểm tra ảnh đăng ký, báo cáo theo phiên và sửa kết quả có nhật ký. Không có cơ sở để khẳng định thay model hoặc chuyển toàn bộ Django sang FastAPI sẽ làm nhận diện chính xác hơn.

UTH mạnh hơn về nghiệp vụ trường học: lịch theo tiết, nhiều mức đi muộn, kiểm tra sai lớp, hoãn buổi, tổng hợp chuyên cần và điểm sinh viên. Các nghiệp vụ này được giữ lại.

### Các phần đã đọc và đối chiếu

| Khu vực tham chiếu | Mã nguồn chính | Nhận xét |
| --- | --- | --- |
| Kiến trúc chạy thật | `docker-compose.yml`, `ai/main.py` | Compose chạy Next.js, API trong `ai/` và PostgreSQL/pgvector. |
| AI | `ai/ai_service/recognition.py` | Dùng detector + recognizer; đăng ký yêu cầu đúng một mặt. So sánh cosine bằng vòng lặp NumPy. |
| Luồng điểm danh | `ai/routers/session/crud.py` | Kiểm tra ACTIVE, đối chiếu embedding của lớp, đếm hit, giữ ảnh có similarity cao nhất. |
| API và quyền | `ai/routers/session/router.py` | Một số thao tác có JWT nhưng chưa kiểm tra người dùng sở hữu phiên. Nhận diện không yêu cầu đăng nhập. |
| Realtime | `ai/routers/session/websockets.py` | Broadcast theo session, lưu kết nối trong bộ nhớ của một process. |
| Dữ liệu | `ai/routers/task/model.py`, `ai/routers/human/crud.py` | Có session, danh sách sinh viên, log nhận diện, audit và log mặt lạ. Có hàm tìm vector trong PostgreSQL. |
| Báo cáo | `frontend/app/reports/page.js` | Modal bắt buộc lý do sửa và lịch sử thay đổi có giá trị thực tế. Heatmap hiện dùng dữ liệu ngẫu nhiên. |
| Camera | `frontend/app/attendance/page.js` | Chụp frame, overlay bounding box, tiếp tục phiên đang hoạt động và nhận sự kiện realtime. |
| Đánh giá AI | `ai/test_level2_pipeline.py` | Có ý tưởng đo latency/FAR/FRR; cần sửa phương pháp đánh giá trước khi tin số liệu. |
| Backend khác | `backend/app/main.py` | Pipeline upload video chỉ giả lập hoàn tất; không phải pipeline AI đang chạy trong Compose. |

## 2. Điểm mạnh và giới hạn của dự án tham chiếu

### Những ý tưởng đáng áp dụng

1. **Xác nhận nhiều khung hình:** tránh ghi nhận ngay sau một kết quả đơn lẻ.
2. **Đăng ký một khuôn mặt:** tránh vô tình lấy người lớn nhất trong ảnh nhóm.
3. **Chỉ chạy module cần thiết:** detector và recognizer đủ cho điểm danh; không cần phân tích tuổi/giới tính.
4. **Nhật ký sửa điểm danh:** lưu người sửa, thời gian, lý do và kết quả cũ/mới.
5. **Theo dõi phiên liên tục:** giảng viên nhìn thấy kết quả mới mà không tải lại trang.
6. **Tách dịch vụ AI và nghiệp vụ:** giúp kiểm thử độc lập các quyết định chấp nhận/từ chối.

### Các chi tiết không nên sao chép nguyên trạng

- `hit_count >= 5` là tích lũy theo phiên, chưa có cửa sổ thời gian, chưa tách thiết bị và chưa kiểm tra frame trùng. Năm lần gửi lại cùng ảnh có thể đủ điều kiện.
- README mô tả lọc `det_score < 0.6`, nhưng luồng `recognize_faces` đang chạy chưa có điều kiện lọc này. Không coi mô tả README là chức năng đã được chứng minh.
- `RecognizedHuman` trong schema phản hồi chưa khai báo `hit_count` mặc dù CRUD trả trường này.
- PostgreSQL có pgvector và có hàm tìm kiếm cosine, nhưng pipeline phiên vẫn tải embedding rồi so bằng vòng lặp Python. Chưa thể khẳng định đang tận dụng chỉ mục vector ở luồng chính.
- Endpoint nhận diện và WebSocket không xác thực. Các thao tác sửa/đóng/xóa/báo cáo phiên có chỗ chưa ràng buộc chủ sở hữu; đường dẫn sửa nhận `session_id` nhưng CRUD chỉ dùng ID bản ghi.
- Lưu mọi khuôn mặt lạ theo từng frame có thể tăng dung lượng rất nhanh; chưa thấy cơ chế giới hạn/tự xóa đi kèm.
- Một số sự kiện WebSocket được phát trước khi transaction commit; UI có thể thấy kết quả chưa lưu thành công. Bộ quản lý kết nối trong RAM không tự broadcast qua nhiều worker.
- Heatmap dùng `Math.random()` nên không phản ánh chuyên cần thực tế.
- Script FAR/FRR chỉ kiểm tra có nhận ra bất kỳ ai hay không, chưa kiểm tra đúng danh tính. Yêu cầu API lỗi bị bỏ qua ở phần đếm sai nhưng tổng ảnh vẫn có thể được dùng làm mẫu số.
- “Check-in/check-out” chủ yếu thể hiện qua ghi chú phiên; chưa tương đương quy trình kiểm tra giờ ra/vào và quy tắc tiết học của UTH.
- Không tìm thấy mô hình liveness/anti-spoofing trong pipeline đang chạy. Temporal voting không chống được mọi ảnh/video giả mạo.

## 3. Những phần đã tích hợp

### A. Pipeline chất lượng và so khớp

File: `admin_check/portal/face_quality.py`, `face_recognition.py`.

- Từ chối ảnh đăng ký có nhiều hơn một khuôn mặt trước khi ghi ảnh/embedding.
- Kiểm tra điểm detector, kích thước mặt, mặt bị cắt khỏi khung, độ sáng và độ nét.
- Trả thông báo cụ thể để người đứng trước kiosk điều chỉnh; lỗi đăng ký cũng trả nguyên nhân chất lượng.
- Chuẩn hóa embedding một lần, so sánh bằng phép nhân ma trận NumPy.
- Cache chỉ mục theo đường dẫn, mtime, kích thước và inode file. File được thay thế sẽ làm mới cache.
- Nhiều mẫu của cùng một sinh viên được gộp theo danh tính trước khi so vị trí thứ nhất/thứ hai.
- Nếu hai sinh viên có điểm quá gần nhau, trả `AMBIGUOUS_MATCH` thay vì chọn đại người đứng đầu.
- Bỏ qua vector zero/NaN khi tạo chỉ mục.
- Giữ nguyên kích thước ảnh đầu vào cho kiểm tra chất lượng và bounding box; InsightFace tự resize theo cấu hình detector.
- Chỉ giữ `detection` và `recognition` trong model hoạt động. Có khóa tránh khởi tạo model đồng thời trong cùng process.

Đây là cải tiến cách ra quyết định và tổ chức tính toán. Chưa có benchmark độ chính xác hoặc tốc độ trên tập ảnh sinh viên thực tế; không công bố phần trăm cải thiện.

### B. Xác nhận nhiều khung hình trên server

File: `recognition_service.py`, `recognition_views.py`; model `RecognitionWindow`.

- Mặc định cần **3 frame khác nhau trong 10 giây**, khoảng cách tối thiểu **0,4 giây** giữa hai frame được tính.
- Lưu tiến độ theo **buổi học + thiết bị + danh tính** trong database, không chỉ trong bộ nhớ một worker.
- Reset khi không có mặt, có nhiều mặt, ảnh không đạt chất lượng, sai lớp, đổi danh tính hoặc hết cửa sổ xác minh.
- Hash byte ảnh ngăn cùng một ảnh đóng góp nhiều lần trong một cửa sổ. Đây chỉ là chống lặp chính xác, không phải chống giả mạo.
- Chỉ chấp nhận buổi đang hoạt động trong ngày hiện tại.
- Backend không ghi điểm danh khi có nhiều người, phù hợp hướng dẫn một người của kiosk.
- Thời gian điểm danh dùng frame hợp lệ đầu tiên của chuỗi được xác nhận để thời gian chờ AI không làm sinh viên bị tính muộn hơn.
- Sau khi xác nhận, vẫn dùng `record_attendance_event` để tính đi muộn, chống trùng và ghi CSV.
- Trả trạng thái `verifying` và tiến độ; kiosk chưa hiển thị “đã điểm danh” khi đang xác minh.
- Ba API cũ `/api/record-attendance/`, `/api/session/record/`, `/api/test-image/` yêu cầu staff và CSRF; khóa kiosk không còn được dùng để bỏ qua xác minh. Các ứng dụng thiết bị cũ cần chuyển sang `/api/recognize-face/`.
- Mã điểm danh mới dùng tiền tố ngày + 24 ký tự ngẫu nhiên từ UUID, tránh cơ chế đọc max rồi cộng một. Mã cũ và CSV đã nhập vẫn được giữ.

### C. Sửa điểm danh và lịch sử thay đổi

File: `attendance_review.py`, `review_views.py`; model `AttendanceAuditLog`.

- Trong trang buổi học, bấm **Correct** ở hàng sinh viên.
- Chọn có đến lớp và nhập giờ đến thực tế, hoặc chọn vắng cả buổi.
- Server tính lại trạng thái/tiết vắng theo quy tắc UTH; không cho client tự chọn mã `ON_TIME` bất chấp giờ đến.
- Bắt buộc lý do 1–500 ký tự, quyền staff và CSRF hợp lệ.
- Ràng buộc sinh viên thuộc lớp của buổi học; từ chối buổi đã hủy hoặc hoãn.
- Lưu actor, thời gian, lý do, snapshot trước và sau trong cùng transaction.
- Gắn phương thức `MANUAL_REVIEW`, không giả làm kết quả AI.
- Xây dựng lại CSV của ngày/môn từ database sau khi commit; thay file qua file tạm để bản lưu phản ánh kết quả đã sửa.
- Nhật ký được đọc trong giao diện; không có API sửa/xóa nhật ký. Đây chưa phải kho lưu trữ bất biến: xóa bản ghi cha bằng công cụ quản trị/database vẫn có thể xóa log theo cascade.
- API quản trị cũ vẫn tồn tại để tương thích. Nhật ký mới bao phủ luồng **Correct**; không tuyên bố mọi thao tác trực tiếp trong Django Admin/SQL đều được audit.

### D. Giao diện và cập nhật trực tiếp

- Danh sách buổi học lấy dữ liệu thật mỗi 5 giây, có nút Refresh và thông báo lỗi.
- Tạm ngừng polling khi tab ẩn hoặc đang mở hộp thoại sửa; dữ liệu không đổi không dựng lại bảng.
- Có giờ đến, độ trễ, tiết vắng, thiết bị, similarity, phương thức và lịch sử sửa.
- Similarity là điểm cosine, không phải xác suất AI đúng.
- Dùng native dialog, nhãn cho input, hỗ trợ Escape/Tab và không chèn tên/lý do bằng HTML.
- Sửa xung đột sidebar cố định/grid trong phạm vi trang buổi học để nội dung không bị ép thành một cột hẹp.
- Chọn polling thay WebSocket để hoạt động ngay với Django hiện tại, không thêm Channels/Redis chỉ cho việc cập nhật danh sách.

## 4. Cấu hình và cách sử dụng

Các mặc định trong `attendance_system/settings.py`:

| Cấu hình | Giá trị |
| --- | --- |
| `FACE_SIMILARITY_THRESHOLD` | 0.55; biến môi trường `UTH_FACE_THRESHOLD` |
| `FACE_MATCH_MARGIN` | 0.04; biến môi trường `UTH_FACE_MATCH_MARGIN` |
| `FACE_MIN_DETECTION_SCORE` | 0.6 |
| `FACE_MIN_SIZE` | 60 px trên ảnh gửi tới server |
| `FACE_MIN_SHARPNESS` | 35, phương sai Laplacian |
| `FACE_CONFIRMATION_FRAMES` | 3 |
| `FACE_CONFIRMATION_WINDOW_SECONDS` | 10 |
| `FACE_CONFIRMATION_MIN_INTERVAL_SECONDS` | 0.4 |

Các ngưỡng chất lượng là điểm khởi đầu, cần hiệu chỉnh bằng camera và ánh sáng thực tế. Không tự động hạ threshold để tăng số lượt nhận diện.

```powershell
python admin_check/manage.py migrate
$env:DJANGO_DEBUG = '1'
python admin_check/manage.py runserver 127.0.0.1:8000
```

Mở `/kiosk/?session_id=<ID>` để điểm danh; mở `/session/<ID>/` bằng tài khoản staff để xem và sửa kết quả. Đăng ký khuôn mặt tiếp tục qua trang quản trị hiện có. Cần tạo tài khoản bằng `createsuperuser` nếu dùng database mới.

## 5. Kiểm chứng và giới hạn

- Kết quả sau tích hợp: **41/41 bài kiểm thử đạt**, Django system check không có lỗi, không còn model thay đổi chưa có migration. Đã áp dụng migration `0008` và `0009` tại dự án đích.
- Browser smoke test đạt trên Edge; ảnh kiểm chứng nằm trong `.impeccable/review/`. Không phát hiện lỗi JavaScript trong các luồng đã kiểm tra.
- Có kiểm thử unit/integration cho chất lượng, danh tính gần nhau, nhiều mẫu cùng người, cache làm mới, temporal voting, ảnh lặp, burst request, đổi thiết bị/danh tính, hết hạn, sai lớp, buổi cũ, JSON lỗi, phân quyền, CSRF, tính giờ và cập nhật CSV/audit.
- `tools/check_attendance_ui.py` dùng database tạm và dữ liệu giả; chạy giao diện thật trên Edge, gọi API sửa thật, xác minh CSV, kiểm tra dialog ở 320/768/1024/1440 px. Chỉ phản hồi AI cho phần kiosk được giả lập để kiểm tra trạng thái giao diện.
- Smoke test model thật trên máy dùng DirectML: detector/recognizer tải được và ảnh trống trả về không có khuôn mặt. Không thay thế kiểm thử nhận diện người thật.
- Chưa triển khai nhận diện cả lớp cùng lúc, check-out theo quy tắc mới, lưu ảnh bằng chứng/mặt lạ, WebSocket đa worker, PostgreSQL/pgvector hay Docker. Đây là các hướng mở rộng có chi phí và yêu cầu khác, không cần thiết cho nhóm tính năng đã chọn.
- Chưa có liveness/anti-spoofing, chưa chứng minh FAR/FRR trên dữ liệu thực.
- SQLite vẫn có giới hạn ghi đồng thời; API nhận diện trả 503 khi gặp xung đột khóa để kiosk thử lại. Khóa row có hiệu lực đầy đủ trên PostgreSQL; chưa chạy load test PostgreSQL.
- Lưu embedding pickle và khóa kiosk mặc định của dự án cũ vẫn cần được thay/hardening trước triển khai rộng. Chỉ dùng file pickle tin cậy. Cơ chế đăng nhập sinh viên bằng mã/lớp chưa được thay trong đợt này.
- CSV là bản sao của database; lỗi ghi sau commit được ghi log. Chưa có hàng đợi retry hoặc đồng bộ file liên tiến trình cho nhiều worker ghi cùng archive.
- Bản sao mã nguồn trước thay đổi: `C:\VisualStudio\UTH-Attendance-backup-20260918-002706.zip`.

Chạy kiểm tra:

```powershell
python admin_check/manage.py check
python admin_check/manage.py makemigrations --check --dry-run
python admin_check/manage.py test portal --noinput
node --check admin_check/static/js/session-review.js
node --check "APP/Máy điểm danh/kiosk.js"
# Kiểm thử trình duyệt: cần gói playwright và Microsoft Edge
python tools/check_attendance_ui.py
```
