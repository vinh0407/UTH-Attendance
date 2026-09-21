import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
import time
import os
import pickle

# ==========================================================
# CẤU HÌNH HỆ THỐNG (Đã tối ưu cho Laptop tầm trung)
# ==========================================================
# Sử dụng model 'buffalo_s' (Smal3l) thay vì 'buffalo_l' để nhẹ hơn
MODEL_NAME = 'buffalo_l' 
# Ngưỡng nhận diện (0.5 - 0.6 là ổn định)
THRESHOLD = 0.55
# Tỉ lệ thu nhỏ ảnh để xử lý (0.5 = 50%). 
# Giúp tăng tốc độ xử lý lên gấp 3-4 lần mà vẫn chính xác.
PROCESS_SCALE = 0.5
# Thư mục chứa dữ liệu khuôn mặt
FACES_FOLDER = "my_faces"
# File lưu database embedding
DATABASE_FILE = "face_database.pkl"
# Số ảnh cần chụp khi đăng ký
NUM_PHOTOS = 5

# Các góc độ cần chụp
POSE_INSTRUCTIONS = [
    "Nhìn THẲNG vào camera",
    "Quay mặt sang TRÁI một chút",
    "Quay mặt sang PHẢI một chút",
    "Ngẩng mặt LÊN một chút",
    "Cúi mặt XUỐNG một chút"
]

# ==========================================================
# 1. KHỞI TẠO MODEL
# ==========================================================
print("Đang tải model AI... Vui lòng đợi chút...")
# providers=['CUDAExecutionProvider'] chạy bằng GPU (nhanh hơn)
# Nếu không có GPU thì đổi thành ['CPUExecutionProvider']
app = FaceAnalysis(name=MODEL_NAME, providers=['CUDAExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))
print("Tải model thành công!")

# ==========================================================
# 2. HÀM ĐĂNG KÝ KHUÔN MẶT MỚI
# ==========================================================
def register_face():
    """Đăng ký khuôn mặt mới với nhiều góc độ"""
    print("\n" + "="*50)
    print("       ĐĂNG KÝ KHUÔN MẶT MỚI")
    print("="*50)
    
    # Nhập tên
    name = input("\nNhập tên của bạn: ").strip()
    if not name:
        print("[Lỗi] Tên không được để trống!")
        return
    
    # Tạo thư mục cho người này
    person_folder = os.path.join(FACES_FOLDER, name.lower())
    if os.path.exists(person_folder):
        overwrite = input(f"[Cảnh báo] '{name}' đã tồn tại. Ghi đè? (y/n): ").lower()
        if overwrite != 'y':
            print("Đã hủy đăng ký.")
            return
        # Xóa ảnh cũ
        for f in os.listdir(person_folder):
            os.remove(os.path.join(person_folder, f))
    else:
        os.makedirs(person_folder)
    
    # Mở camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    print("\n📷 Camera đã mở!")
    print("Nhấn SPACE để chụp | Nhấn Q để hủy\n")
    
    photos_taken = 0
    embeddings_list = []  # Lưu embeddings trực tiếp
    
    while photos_taken < NUM_PHOTOS:
        ret, frame = cap.read()
        if not ret:
            break
        
        display = frame.copy()
        
        # Phát hiện khuôn mặt
        faces = app.get(frame)
        face_detected = len(faces) > 0
        
        # Vẽ khung khuôn mặt
        if face_detected:
            box = faces[0].bbox.astype(int)
            cv2.rectangle(display, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 3)
        
        # Hiển thị hướng dẫn
        instruction = POSE_INSTRUCTIONS[photos_taken]
        cv2.putText(display, f"Anh {photos_taken + 1}/{NUM_PHOTOS}: {instruction}", 
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        # Trạng thái
        status = "OK - Nhan SPACE de chup" if face_detected else "Khong thay mat - Di chuyen vao khung"
        color = (0, 255, 0) if face_detected else (0, 0, 255)
        cv2.putText(display, status, (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Hiển thị tên
        cv2.putText(display, f"Dang ky: {name}", (10, 120), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        cv2.imshow('Dang ky khuon mat - SPACE: Chup | Q: Huy', display)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            print("\n❌ Đã hủy đăng ký!")
            cap.release()
            cv2.destroyAllWindows()
            # Xóa thư mục nếu chưa có ảnh
            if photos_taken == 0:
                os.rmdir(person_folder)
            return
        
        elif key == ord(' ') and face_detected:
            # Lấy embedding trực tiếp từ face đã detect
            face = faces[0]
            embeddings_list.append(face.embedding)
            
            # Lưu ảnh thumbnail để xem lại (128x128)
            box = face.bbox.astype(int)
            h, w = frame.shape[:2]
            pad_x = int((box[2] - box[0]) * 0.3)
            pad_y = int((box[3] - box[1]) * 0.3)
            x1 = max(0, box[0] - pad_x)
            y1 = max(0, box[1] - pad_y)
            x2 = min(w, box[2] + pad_x)
            y2 = min(h, box[3] + pad_y)
            face_crop = frame[y1:y2, x1:x2]
            face_crop = cv2.resize(face_crop, (128, 128))
            
            photo_path = os.path.join(person_folder, f"{photos_taken + 1}.jpg")
            cv2.imwrite(photo_path, face_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            photos_taken += 1
            print(f"✅ Đã chụp ảnh {photos_taken}/{NUM_PHOTOS}: {instruction}")
            time.sleep(0.5)
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Lưu embeddings vào database
    save_embeddings_to_database(name, embeddings_list)
    
    print(f"\n🎉 Đăng ký thành công cho '{name}' với {NUM_PHOTOS} ảnh!")
    print(f"📁 Ảnh thumbnail lưu tại: {person_folder}")

# ==========================================================
# 2B. HÀM ĐĂNG KÝ TỪ ẢNH CÓ SẴN
# ==========================================================
def register_from_images():
    """Đăng ký khuôn mặt từ ảnh có sẵn (hỗ trợ mọi kích thước)"""
    print("\n" + "="*50)
    print("   ĐĂNG KÝ TỪ ẢNH CÓ SẴN")
    print("="*50)
    
    name = input("\nNhập tên người cần đăng ký: ").strip()
    if not name:
        print("[Lỗi] Tên không được để trống!")
        return
    
    print("\nNhập đường dẫn các ảnh (mỗi ảnh 1 dòng, nhập 'done' khi xong):")
    print("Ví dụ: C:\\Users\\Thang\\anh1.jpg")
    print("Hoặc kéo thả file ảnh vào đây\n")
    
    image_paths = []
    while True:
        path = input(f"Ảnh {len(image_paths) + 1}: ").strip().strip('"')
        if path.lower() == 'done':
            break
        if path:
            image_paths.append(path)
    
    if not image_paths:
        print("[Lỗi] Chưa có ảnh nào!")
        return
    
    # Tạo thư mục
    person_folder = os.path.join(FACES_FOLDER, name.lower())
    if not os.path.exists(person_folder):
        os.makedirs(person_folder)
    
    embeddings_list = []
    success_count = 0
    
    for i, img_path in enumerate(image_paths):
        img = cv2.imread(img_path)
        if img is None:
            print(f"❌ Không đọc được: {img_path}")
            continue
        
        # Resize nếu ảnh quá lớn (giữ tỉ lệ)
        h, w = img.shape[:2]
        max_size = 1280
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            print(f"  📐 Đã resize từ {w}x{h} → {img.shape[1]}x{img.shape[0]}")
        
        # Phát hiện khuôn mặt
        faces = app.get(img)
        
        if len(faces) == 0:
            print(f"❌ Không tìm thấy khuôn mặt trong: {os.path.basename(img_path)}")
            continue
        
        if len(faces) > 1:
            print(f"⚠️ Có {len(faces)} khuôn mặt, chọn khuôn mặt lớn nhất")
            # Chọn khuôn mặt lớn nhất
            faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)
        
        face = faces[0]
        embeddings_list.append(face.embedding)
        
        # Lưu thumbnail
        box = face.bbox.astype(int)
        pad_x = int((box[2] - box[0]) * 0.3)
        pad_y = int((box[3] - box[1]) * 0.3)
        x1 = max(0, box[0] - pad_x)
        y1 = max(0, box[1] - pad_y)
        x2 = min(img.shape[1], box[2] + pad_x)
        y2 = min(img.shape[0], box[3] + pad_y)
        face_crop = img[y1:y2, x1:x2]
        face_crop = cv2.resize(face_crop, (128, 128))
        
        thumb_path = os.path.join(person_folder, f"{success_count + 1}.jpg")
        cv2.imwrite(thumb_path, face_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        success_count += 1
        print(f"✅ Ảnh {success_count}: OK - {os.path.basename(img_path)}")
    
    if embeddings_list:
        save_embeddings_to_database(name, embeddings_list)
        print(f"\n🎉 Đăng ký thành công '{name}' với {success_count} ảnh!")
    else:
        print("\n❌ Không có ảnh nào hợp lệ!")

# ==========================================================
# 3. HÀM LƯU/ĐỌC DATABASE EMBEDDING
# ==========================================================
def save_embeddings_to_database(name, embeddings):
    """Lưu embeddings vào file database"""
    database = load_database()
    database[name.capitalize()] = embeddings
    
    with open(DATABASE_FILE, 'wb') as f:
        pickle.dump(database, f)
    print(f"💾 Đã lưu {len(embeddings)} embedding vào database")

def load_database():
    """Đọc database từ file"""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'rb') as f:
            return pickle.load(f)
    return {}

# ==========================================================
# 4. HÀM TẠO DATABASE (HỖ TRỢ NHIỀU ẢNH)
# ==========================================================
def create_database():
    """Tạo database từ file embedding đã lưu"""
    print("--- Đang khởi tạo dữ liệu khuôn mặt ---")
    
    database = load_database()
    
    if database:
        for name, embeddings in database.items():
            print(f"[OK] Đã tải {len(embeddings)} ảnh của: {name}")
    else:
        print("[Info] Chưa có dữ liệu. Hãy đăng ký khuôn mặt trước!")
    
    return database

# ==========================================================
# 5. HÀM SO SÁNH KHUÔN MẶT (HỖ TRỢ NHIỀU ẢNH)
# ==========================================================
def compare_face(current_embedding, known_faces_db):
    """So sánh khuôn mặt với database, trả về tên và độ chính xác cao nhất"""
    best_name = "Unknown"
    best_score = 0.0
    
    for db_name, embeddings_list in known_faces_db.items():
        # So sánh với tất cả ảnh của người này, lấy điểm cao nhất
        for db_embedding in embeddings_list:
            sim = np.dot(current_embedding, db_embedding) / (
                np.linalg.norm(current_embedding) * np.linalg.norm(db_embedding)
            )
            
            if sim > best_score:
                best_score = sim
                if sim > THRESHOLD:
                    best_name = db_name
    
    return best_name, best_score

# ==========================================================
# 6. CHƯƠNG TRÌNH CHÍNH - CAMERA
# ==========================================================
def run_camera():
    """Nhận diện khuôn mặt qua camera"""
    # Load dữ liệu
    known_faces_db = create_database()
    if not known_faces_db:
        print("Không có dữ liệu khuôn mặt nào. Hãy đăng ký trước!")
        return

    # Mở Camera
    cap = cv2.VideoCapture(0)
    
    # Cài đặt độ phân giải camera (Tùy chọn)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("\nĐang mở camera... Nhấn 'q' để thoát.")
    
    prev_frame_time = 0
    new_frame_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # --- TỐI ƯU HÓA: RESIZE ẢNH ĐỂ XỬ LÝ ---
        # Thu nhỏ ảnh đầu vào để AI tính toán nhanh hơn
        small_frame = cv2.resize(frame, (0, 0), fx=PROCESS_SCALE, fy=PROCESS_SCALE)
        
        # AI phát hiện và mã hóa khuôn mặt trên ảnh nhỏ
        faces = app.get(small_frame)

        # Copy frame gốc để vẽ giao diện (giữ nguyên độ nét)
        display_frame = frame.copy()

        for face in faces:
            # --- XỬ LÝ TỌA ĐỘ ---
            # Vì AI soi trên ảnh nhỏ (50%), nên tọa độ nhận được phải nhân 2 (chia 0.5) 
            # để vẽ đúng lên ảnh gốc
            box = (face.bbox / PROCESS_SCALE).astype(int)
            
            # So sánh khuôn mặt với database (hỗ trợ nhiều ảnh)
            name, max_score = compare_face(face.embedding, known_faces_db)
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)

            # --- VẼ GIAO DIỆN ---
            x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
            
            # Vẽ khung chữ nhật bo góc (đơn giản hóa bằng rectangle thường)
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
            
            # Vẽ tên và độ chính xác
            label = f"{name} ({max_score:.0%})"
            
            # Tạo nền đen cho chữ dễ đọc
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(display_frame, (x1, y1 - 25), (x1 + w, y1), color, -1)
            cv2.putText(display_frame, label, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # --- TÍNH FPS (Frame Per Second) ---
        new_frame_time = time.time()
        fps = 1 / (new_frame_time - prev_frame_time)
        prev_frame_time = new_frame_time
        
        cv2.putText(display_frame, f"FPS: {int(fps)}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

        # Hiển thị
        cv2.imshow('Face Recognition - Thang (Nhan Q de thoat)', display_frame)

        # Thoát khi nhấn 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

# ==========================================================
# 4. HÀM TEST VỚI ẢNH TĨNH
# ==========================================================
def test_with_image(image_path):
    """Test nhận diện khuôn mặt với một ảnh tĩnh"""
    # Load dữ liệu
    known_faces_db = create_database()
    if not known_faces_db:
        print("Không có dữ liệu khuôn mặt nào. Hãy kiểm tra lại file ảnh!")
        return
    
    # Đọc ảnh test
    img = cv2.imread(image_path)
    if img is None:
        print(f"[Lỗi] Không đọc được ảnh: {image_path}")
        return
    
    print(f"\n--- Đang phân tích ảnh: {image_path} ---")
    
    # Phát hiện khuôn mặt
    faces = app.get(img)
    print(f"Tìm thấy {len(faces)} khuôn mặt trong ảnh!")
    
    # Copy ảnh để vẽ
    display_img = img.copy()
    
    for i, face in enumerate(faces):
        box = face.bbox.astype(int)
        
        # So sánh khuôn mặt với database (hỗ trợ nhiều ảnh)
        name, max_score = compare_face(face.embedding, known_faces_db)
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        
        # Vẽ khung và tên
        x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
        cv2.rectangle(display_img, (x1, y1), (x2, y2), color, 3)
        
        label = f"{name} ({max_score:.0%})"
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        cv2.rectangle(display_img, (x1, y1 - 35), (x1 + w, y1), color, -1)
        cv2.putText(display_img, label, (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        print(f"  Khuôn mặt {i+1}: {name} - Độ chính xác: {max_score:.1%}")
    
    # Lưu ảnh kết quả
    output_path = "test_result.jpg"
    cv2.imwrite(output_path, display_img)
    print(f"\n✅ Đã lưu kết quả vào: {output_path}")
    
    # Hiển thị ảnh
    cv2.imshow('Test Result - Nhan phim bat ky de dong', display_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Nếu có tham số, test với ảnh
        test_with_image(sys.argv[1])
    else:
        # Hiển thị menu
        print("\n" + "="*50)
        print("   HỆ THỐNG NHẬN DIỆN KHUÔN MẶT")
        print("="*50)
        print("1. Đăng ký khuôn mặt (chụp qua Camera)")
        print("2. Đăng ký từ ảnh có sẵn")
        print("3. Nhận diện qua Camera")
        print("4. Test với ảnh")
        print("="*50)
        
        choice = input("Chọn chức năng (1/2/3/4): ").strip()
        
        if choice == "1":
            register_face()
        elif choice == "2":
            register_from_images()
        elif choice == "3":
            run_camera()
        elif choice == "4":
            img_path = input("Nhập đường dẫn ảnh: ").strip().strip('"')
            if img_path:
                test_with_image(img_path)
            else:
                print("[Đường dẫn không hợp lệ!]")
        else:
            print("Lựa chọn không hợp lệ!")