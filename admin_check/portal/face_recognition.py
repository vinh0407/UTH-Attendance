"""
Face Recognition Module for Django Attendance System
Sử dụng InsightFace với model buffalo_l
"""

import cv2
import numpy as np
import pickle
import os
import json
import re
import warnings
import importlib.metadata
import ctypes
import tempfile
import threading
from .face_quality import assess_face, EmbeddingIndex
from django.conf import settings
warnings.filterwarnings("ignore", category=FutureWarning)

# Cấu hình
MODEL_NAME = 'buffalo_l'  # Hoặc 'buffalo_s' nếu muốn nhẹ hơn
THRESHOLD = 0.55  # Ngưỡng nhận diện

# Sử dụng database từ project gốc (đã có Thang và Viet)
# Có thể thay đổi thành đường dẫn riêng cho Django app
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATABASE_FILE = os.path.join(BASE_DIR, 'face_database.pkl')
MY_FACES_DIR = os.fspath(settings.STUDENT_DATA_DIR)  # Hồ sơ sinh viên + ảnh khuôn mặt

# Singleton pattern cho FaceAnalysis app
_face_app = None
_index_cache = None
_index_lock = threading.RLock()
_model_lock = threading.RLock()


def face_engine_status():
    """Return a safe, serialisable health snapshot for the registration UI."""
    try:
        from insightface.app import FaceAnalysis  # noqa: F401
    except Exception as exc:
        return {
            'available': False,
            'code': 'FACE_ENGINE_UNAVAILABLE',
            'message': 'InsightFace is not installed in the server environment.',
            'detail': str(exc),
        }
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
    except Exception:
        providers = []
    cuda_ready = _cuda_provider_usable(providers)
    dml_ready = 'DmlExecutionProvider' in providers
    runtime_package = None
    runtime_version = None
    for candidate in ('onnxruntime-directml', 'onnxruntime-gpu', 'onnxruntime'):
        try:
            runtime_version = importlib.metadata.version(candidate)
            runtime_package = candidate
            break
        except importlib.metadata.PackageNotFoundError:
            continue
    return {
        'available': True,
        'code': 'READY',
        'message': 'Face recognition is ready.',
        'provider': 'CUDAExecutionProvider' if cuda_ready else ('DmlExecutionProvider' if dml_ready else 'CPUExecutionProvider'),
        'insightface_version': importlib.metadata.version('insightface'),
        'onnxruntime_package': runtime_package,
        'onnxruntime_version': runtime_version,
    }


def _inference_providers():
    """Select CUDA when the installed ONNX Runtime exposes it, otherwise CPU."""
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
    except Exception:
        available = []
    if _cuda_provider_usable(available):
        return ['CUDAExecutionProvider', 'CPUExecutionProvider'], 0
    if 'DmlExecutionProvider' in available:
        return ['DmlExecutionProvider', 'CPUExecutionProvider'], 0
    return ['CPUExecutionProvider'], -1


def _cuda_provider_usable(available=None):
    """Return whether the CUDA provider DLL and its dependencies can load."""
    if available is None:
        try:
            import onnxruntime as ort
            available = ort.get_available_providers()
        except Exception:
            return False
    if 'CUDAExecutionProvider' not in available:
        return False
    try:
        import onnxruntime as ort
        provider_dll = os.path.join(os.path.dirname(ort.__file__), 'capi', 'onnxruntime_providers_cuda.dll')
        loader = getattr(ctypes, 'WinDLL', ctypes.CDLL)
        loader(provider_dll)
        return True
    except (OSError, ImportError):
        return False

def get_face_app():
    """Lấy instance FaceAnalysis (singleton để tránh load model nhiều lần)"""
    global _face_app
    with _model_lock:
        if _face_app is None:
            try:
                from insightface.app import FaceAnalysis
            except ImportError as exc:
                raise RuntimeError(
                    "InsightFace is not ready. Reinstall InsightFace and its AI dependencies before opening the camera."
                ) from exc
            providers, ctx_id = _inference_providers()
            print(f"Loading InsightFace model ({providers[0]})...")
            app = FaceAnalysis(name=MODEL_NAME, providers=providers, allowed_modules=['detection', 'recognition'])
            app.prepare(ctx_id=ctx_id, det_size=(640, 640))
            _face_app = app
            print("Model loaded successfully.")
    return _face_app


def load_database():
    """Đọc database embeddings từ file"""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'rb') as f:
            return pickle.load(f)
    return {}


def save_database(database):
    """Lưu database embeddings vào file"""
    directory = os.path.dirname(DATABASE_FILE) or '.'
    fd, temp_path = tempfile.mkstemp(prefix='.face_database-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            pickle.dump(database, stream, protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, DATABASE_FILE)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _safe_component(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '').strip())
    return value.rstrip('. ') or 'Unknown'


def face_folder_name(name, class_name=''):
    return _safe_component(f"{name}_{class_name}" if class_name else name)


def register_face(name, image, student_id='', class_name='', email=''):
    """
    Đăng ký khuôn mặt mới từ ảnh
    Args:
        name: Tên người
        image: numpy array (BGR image từ OpenCV)
    Returns:
        (success: bool, message: str)
    """
    app = get_face_app()
    faces = app.get(image)
    
    if len(faces) == 0:
        return False, "No face was detected in the image"
    
    if len(faces) > 1:
        return False, 'Keep exactly one face in each registration image.'
    quality = assess_face(image, faces[0])
    if not quality['ok']:
        return False, quality['message']
    
    embedding = faces[0].embedding
    
    # Lưu hồ sơ vào APP/Dữ liệu/Sinh viên trường/{Tên}_{Lớp}
    folder_name = face_folder_name(name, class_name)
    person_dir = os.path.join(MY_FACES_DIR, folder_name)
    os.makedirs(person_dir, exist_ok=True)
    
    # Đếm số ảnh hiện có để đặt tên file
    existing_images = [f for f in os.listdir(person_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
    img_index = len(existing_images) + 1
    img_path = os.path.join(person_dir, 'face.png' if img_index == 1 else f'face_{img_index:02d}.png')
    # cv2.imwrite cannot reliably create files in Unicode Windows paths.
    # Encode first, then write bytes through Python so Vietnamese student
    # names and class labels are preserved on disk.
    success, encoded = cv2.imencode('.png', image)
    if not success:
        return False, "Unable to encode the face image"
    with open(img_path, 'wb') as stream:
        stream.write(encoded.tobytes())

    metadata = {
        'student_id': str(student_id or ''),
        'full_name': str(name or ''),
        'class_name': str(class_name or ''),
        'email': str(email or ''),
        'face_files': sorted(f for f in os.listdir(person_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))),
    }
    with open(os.path.join(person_dir, 'student.json'), 'w', encoding='utf-8') as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
    
    # Lưu vào database
    database = load_database()
    identity = str(student_id or '').strip() or name
    if identity in database:
        database[identity].append(embedding)
    else:
        database[identity] = [embedding]
    
    save_database(database)
    return True, f"Face registered successfully for {name}"


def _embedding_index():
    global _index_cache
    with _index_lock:
        try:
            stat = os.stat(DATABASE_FILE)
            signature = (DATABASE_FILE, stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except FileNotFoundError:
            signature = (DATABASE_FILE, None)
        if _index_cache is None or _index_cache[0] != signature:
            _index_cache = (signature, EmbeddingIndex(load_database()))
        return _index_cache[1]


def recognize_face(image):
    """Return every detected face, including quality feedback for rejected faces."""
    faces = get_face_app().get(image)
    index = _embedding_index()
    results = []
    for face in faces:
        quality = assess_face(image, face)
        name, score = 'Unknown', 0.0
        if quality['ok']:
            name, score, code = index.match(
                face.embedding, settings.FACE_SIMILARITY_THRESHOLD, settings.FACE_MATCH_MARGIN,
            )
            if code != 'OK':
                quality = {
                    'ok': False, 'code': code,
                    'message': ('Match is too close to another student. Try a clearer angle.'
                                if code == 'AMBIGUOUS_MATCH' else 'Face is not recognized. Contact your lecturer.'),
                }
        results.append({'name': name, 'confidence': float(score * 100),
                        'bbox': face.bbox.astype(int).tolist(), 'quality': quality})
    return results


def recognize_frame(frame, scale=0.5):
    """Keep coordinates/quality in original pixels; InsightFace resizes internally."""
    return recognize_face(frame)


def draw_results(frame, results):
    """
    Vẽ kết quả nhận diện lên frame
    Args:
        frame: numpy array (BGR image)
        results: list từ recognize_frame()
    Returns:
        frame với annotations
    """
    for result in results:
        x1, y1, x2, y2 = result['bbox']
        name = result['name']
        conf = result['confidence']
        
        # Màu: xanh nếu nhận diện được, đỏ nếu Unknown
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        
        # Vẽ khung
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Vẽ label
        label = f"{name} ({conf:.0f}%)"
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - 25), (x1 + w, y1), color, -1)
        cv2.putText(frame, label, (x1, y1 - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return frame


# Hàm ghi nhận điểm danh vào Django database
def record_attendance_to_db(name, confidence, session_id=None):
    """
    Ghi nhận điểm danh vào database Django
    Args:
        name: Tên sinh viên
        confidence: Độ tin cậy
        session_id: ID buổi điểm danh (optional)
    """
    try:
        # Import Django models
        import django
        import os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
        if not django.apps.apps.ready:
            django.setup()
        
        from django.utils import timezone
        from portal.models import Student, AttendanceRecord, AttendanceSession
        from portal.attendance_service import (
            METHOD_FACIAL_RECOGNITION, calculate_attendance_status,
            get_session_scheduled_time, next_attendance_id,
        )
        
        student = Student.objects.filter(student_id=name).first() or Student.objects.filter(full_name=name).first()
        if not student:
            print(f"Student not found: {name}")
            return False
        
        current_time = timezone.now()
        
        if session_id:
            # Điểm danh theo buổi
            try:
                session = AttendanceSession.objects.get(id=session_id)
                now_time = current_time.time()
                timing = calculate_attendance_status(get_session_scheduled_time(session), now_time)
                record, created = AttendanceRecord.objects.get_or_create(
                    session=session,
                    student=student,
                    date=current_time.date(),
                    defaults={
                        'attendance_id': next_attendance_id(current_time.date()),
                        'time_in': now_time,
                        'status': timing['status'],
                        'scheduled_time': get_session_scheduled_time(session),
                        'late_minutes': timing['late_minutes'],
                        'attendance_code': timing['attendance_code'],
                        'attendance_label': timing['attendance_label'],
                        'attendance_periods': timing['attendance_periods'],
                        'method': METHOD_FACIAL_RECOGNITION,
                        'confidence': confidence,
                    }
                )
                if created:
                    print(f"{name} checked in for session #{session_id} at {current_time.strftime('%H:%M:%S')}")
                return True
            except AttendanceSession.DoesNotExist:
                print(f"Attendance session not found: {session_id}")
                return False
        else:
            # Điểm danh chung (không theo buổi)
            record, created = AttendanceRecord.objects.get_or_create(
                student=student,
                date=current_time.date(),
                session=None,
                defaults={
                    'attendance_id': next_attendance_id(current_time.date()),
                    'time_in': current_time.time(),
                    'status': 'present',
                    'attendance_code': 'ON_TIME',
                    'attendance_label': 'ON TIME',
                    'method': METHOD_FACIAL_RECOGNITION,
                    'confidence': confidence,
                }
            )
            if created:
                print(f"{name} checked in at {current_time.strftime('%H:%M:%S')}")
            return True
            
    except Exception as e:
        print(f"Attendance recording error: {e}")
        return False


class VideoCamera:
    """Class để stream video từ camera với hỗ trợ điểm danh theo buổi"""
    
    def __init__(self, camera_id=0, session_id=None, device_id='SERVER-CAMERA'):
        self.video = cv2.VideoCapture(camera_id)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.session_id = session_id
        self.device_id = device_id
        self.recognized_names = set()  # Lưu tên đã điểm danh để tránh trùng
    
    def __del__(self):
        if self.video.isOpened():
            self.video.release()
    
    def get_frame(self, recognize=True):
        """
        Lấy frame từ camera
        Args:
            recognize: có nhận diện khuôn mặt không
        Returns:
            JPEG encoded bytes
        """
        ret, frame = self.video.read()
        if not ret:
            return None
        
        if recognize:
            results = recognize_frame(frame)
            
            # Tự động ghi nhận điểm danh
            for result in results:
                name = result['name']
                conf = result['confidence']
                
                if name != "Unknown" and name not in self.recognized_names:
                    # Ghi nhận điểm danh
                    success = record_attendance_to_db(name, conf / 100.0, self.session_id)
                    if success:
                        self.recognized_names.add(name)
            
            frame = draw_results(frame, results)
        
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()
    
    def get_frame_with_results(self):
        """
        Lấy frame và kết quả nhận diện
        Returns:
            (JPEG bytes, results list)
        """
        ret, frame = self.video.read()
        if not ret:
            return None, []
        
        results = recognize_frame(frame)
        annotated_frame = draw_results(frame.copy(), results)
        
        ret, jpeg = cv2.imencode('.jpg', annotated_frame)
        return jpeg.tobytes(), results
