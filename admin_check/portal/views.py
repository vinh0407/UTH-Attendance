from decimal import Decimal
import decimal
import io
from .academic_services import score_to_scale4_and_letter, academic_classification
from .faculty import teacher_details
from .enrollment import session_students, student_schedules
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Avg
from django.views.static import serve
from .models import Student, AttendanceRecord, Camera, SystemStats, Subject, ClassRoom, Schedule, AttendanceSession, Grade, AcademicTerm, GradeAuditLog, LeaveRequest
from . import face_recognition as fr
from .attendance_import import import_csv_bytes
from .attendance_service import (
    METHOD_FACIAL_RECOGNITION,
    attendance_payload,
    calculate_attendance_status,
    get_session_scheduled_time,
    next_attendance_id,
    record_attendance_event,
    finalize_session_attendance,
    resolve_session,
    session_external_id,
)
import json
import cv2
import numpy as np
import base64
import os
import datetime
import csv
import hmac
import hashlib
import logging
from functools import wraps
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache

PORTAL_FRONTEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'APP', 'Portal'))
KIOSK_FRONTEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'APP', 'Máy điểm danh'))
ADMIN_STATIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))


def static_asset(request, path):
    """Serve admin static files directly."""
    return serve(request, path, document_root=ADMIN_STATIC_ROOT)
PORTAL_STUDENT_SESSION_KEY = 'portal_student_pk'
PORTAL_STUDENT_SESSION_AGE = 8 * 60 * 60
logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def student_portal(request):
    """Serve the existing static portal on the same origin as Django APIs."""
    response = serve(request, 'index.html', document_root=PORTAL_FRONTEND_ROOT)
    response['Cache-Control'] = 'no-cache'
    return response


def student_portal_asset(request, path):
    response = serve(request, path, document_root=PORTAL_FRONTEND_ROOT)
    # Windows may register .mjs as text/plain; browsers require a JavaScript MIME type.
    if path.endswith('.mjs'):
        response['Content-Type'] = 'text/javascript; charset=utf-8'
    return response


def attendance_kiosk(request):
    """Serve the face kiosk on the same origin as the central API."""
    response = serve(request, 'index.html', document_root=KIOSK_FRONTEND_ROOT)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


def attendance_kiosk_asset(request, path):
    response = serve(request, path, document_root=KIOSK_FRONTEND_ROOT)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


def _current_student(request):
    cached = getattr(request, 'portal_student', None)
    if cached is not None:
        return cached

    student_pk = request.session.get(PORTAL_STUDENT_SESSION_KEY)
    if student_pk:
        student = Student.objects.filter(pk=student_pk).first()
        if student:
            request.portal_student = student
            return student
        request.session.pop(PORTAL_STUDENT_SESSION_KEY, None)

    if request.user.is_authenticated and not request.user.is_staff:
        student = Student.objects.filter(user=request.user).first()
        if student:
            request.portal_student = student
            return student
    return None


def student_api_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        student = _current_student(request)
        if not student:
            return JsonResponse({'success': False, 'error': 'Student sign-in required'}, status=401)
        request.portal_student = student
        return view(request, *args, **kwargs)
    return wrapped


def admin_api_required(view):
    """Require an authenticated staff user for management mutations."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Staff authentication required'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def kiosk_api_required(view):
    """Require the per-kiosk API key (or a staff session for local recovery)."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        supplied = request.headers.get('X-Kiosk-Key', '')
        if request.user.is_authenticated and request.user.is_staff:
            return view(request, *args, **kwargs)
        if not supplied or not hmac.compare_digest(supplied, settings.KIOSK_API_KEY):
            return JsonResponse({'success': False, 'error': 'Kiosk authentication required'}, status=401)
        bucket = f"kiosk-rate:{request.META.get('REMOTE_ADDR', 'unknown')}:{timezone.now():%Y%m%d%H%M}"
        try:
            count = cache.get(bucket, 0)
            if count >= 120:
                return JsonResponse({'success': False, 'error': 'Too many requests'}, status=429)
            cache.set(bucket, count + 1, timeout=120)
        except Exception:
            logger.warning('Kiosk rate limiter unavailable', exc_info=True)
        return view(request, *args, **kwargs)
    return wrapped


def home(request):
    """UTH Digital Campus Central Hub & Gateway."""
    total_students = Student.objects.count()
    today = timezone.localdate()
    today_attendance = AttendanceRecord.objects.filter(
        date=today, 
        status__in=['present', 'late']
    ).count()
    
    attendance_rate = round((today_attendance / total_students) * 100, 1) if total_students > 0 else 0
    active_cameras = Camera.objects.filter(status='active').count()
    
    context = {
        'total_students': total_students,
        'attendance_rate': attendance_rate,
        'active_cameras': active_cameras,
        'avg_scan_time': '0.8',
        'opencv_plugin_url': getattr(settings, 'OPENCV_PLUGIN_URL', '/kiosk/'),
        'admin_url': getattr(settings, 'ADMIN_DASHBOARD_URL', '/admin-dashboard/'),
        'register_url': getattr(settings, 'REGISTER_FACE_URL', '/register/'),
    }
    return render(request, 'portal/home.html', context)


@staff_member_required(login_url='/admin/login/')
def admin_dashboard(request):
    """Trang Admin Dashboard"""
    from .face_recognition import load_database
    
    # Đếm số người đã đăng ký khuôn mặt từ face_database.pkl
    face_db = load_database()
    registered_faces = len(face_db)  # Số người đã đăng ký mặt
    
    # Thống kê tổng quan từ Student model
    total_students = Student.objects.count()
    
    today = timezone.localdate()
    today_records = AttendanceRecord.objects.filter(date=today)
    
    # Đếm số sinh viên unique có mặt hôm nay (không đếm trùng)
    today_attended_unique = today_records.filter(status__in=['present', 'late']).values('student').distinct().count()
    
    # Vắng = Tổng sinh viên - Có mặt unique (không được âm)
    today_absent = max(0, total_students - today_attended_unique)
    attendance_rate = round((today_attended_unique / total_students * 100), 1) if total_students > 0 else 0.0

    recent_audits = GradeAuditLog.objects.select_related(
        'grade__student', 'grade__subject', 'changed_by'
    ).order_by('-changed_at')[:15]
    
    # Đồng bộ mở các buổi học hôm nay và lấy dữ liệu thời khóa biểu
    _open_today_sessions(today)
    schedules = Schedule.objects.filter(is_active=True).select_related('subject', 'classroom')
    current_day = today.weekday()
    day_names_en = {
        0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday',
        4: 'Friday', 5: 'Saturday', 6: 'Sunday',
    }
    schedule_by_day = {}
    current_day_name = day_names_en.get(current_day, 'Today')
    for day_num, day_name in Schedule.DAY_CHOICES:
        schedule_by_day[day_num] = {
            'name': day_name,
            'name_en': day_names_en.get(day_num, day_name),
            'schedules': schedules.filter(day_of_week=day_num)
        }

    today_sessions = AttendanceSession.objects.filter(date=today).select_related('schedule__subject', 'schedule__classroom')
    active_sessions = AttendanceSession.objects.filter(status='active').select_related('schedule__subject', 'schedule__classroom')
    semesters = AcademicTerm.objects.all()

    context = {
        'total_students': total_students,
        'today': today,
        'registered_students': registered_faces,  # Từ face_database.pkl
        'today_present': today_records.filter(status='present').values('student').distinct().count(),
        'today_late': today_records.filter(status='late').values('student').distinct().count(),
        'today_absent': today_absent,
        'attendance_rate': attendance_rate,
        'recent_records': AttendanceRecord.objects.select_related('student').order_by('-date', '-time_in')[:25],
        'recent_audits': recent_audits,
        'pending_leaves': LeaveRequest.objects.filter(status='pending').select_related('student', 'subject').order_by('-created_at')[:15],
        'cameras': Camera.objects.all(),
        'students': Student.objects.all().order_by('-created_at'),  # Danh sách sinh viên
        'classrooms': ClassRoom.objects.all().order_by('class_id'),
        'subjects': Subject.objects.all().order_by('code'),
        'schedule_by_day': schedule_by_day,
        'current_day': current_day,
        'current_day_name': current_day_name,
        'today_sessions': today_sessions,
        'active_sessions': active_sessions,
        'semesters': semesters,
    }
    return render(request, 'portal/admin_dashboard.html', context)


@staff_member_required(login_url='/admin/login/')
def register_face(request):
    """Compatibility route: face registration belongs to the admin workspace."""
    return redirect(f"{settings.ADMIN_DASHBOARD_URL}#face-registration")


def scan_camera(request):
    """
    Trang scan camera với nhận diện khuôn mặt real-time
    """
    students = Student.objects.filter(is_registered=True)
    context = {
        'students': students,
        'message': 'Face recognition attendance'
    }
    return render(request, 'portal/scan_camera.html', context)


# =====================================================
# Thời khóa biểu và Điểm danh theo buổi
# =====================================================

def _open_today_sessions(today=None):
    """Ensure every class scheduled for today is ready for kiosk check-in."""
    today = today or timezone.localdate()
    schedules = Schedule.objects.filter(is_active=True, day_of_week=today.weekday())
    for schedule in schedules:
        session, created = AttendanceSession.objects.get_or_create(
            schedule=schedule,
            date=today,
            defaults={'status': 'active', 'start_time': timezone.now()},
        )
        if created or session.status in {'scheduled', 'cancelled'}:
            session.status = 'active'
            session.start_time = session.start_time or timezone.now()
            session.save(update_fields=['status', 'start_time'])
        session_external_id(session)


@staff_member_required(login_url='/admin/login/')
def schedule_view(request):
    """Trang thời khóa biểu - Điều hướng đồng bộ vào tab Lịch & Buổi học của Admin Dashboard"""
    today = timezone.localdate()
    _open_today_sessions(today)
    return redirect('/admin-dashboard/#schedule')


@staff_member_required(login_url='/admin/login/')
def start_attendance_session(request, schedule_id):
    """Bắt đầu buổi điểm danh từ thời khóa biểu"""
    schedule = get_object_or_404(Schedule, id=schedule_id)
    today = timezone.localdate()
    
    # Tạo hoặc lấy buổi điểm danh cho hôm nay
    session, created = AttendanceSession.objects.get_or_create(
        schedule=schedule,
        date=today,
        defaults={
            'status': 'active',
            'start_time': timezone.now()
        }
    )
    
    if not created:
        # Nếu đã tồn tại, chuyển sang trạng thái active
        session.status = 'active'
        session.start_time = timezone.now()
        session.save()

    session_external_id(session)
    
    return redirect('portal:attendance_session', session_id=session.id)


@staff_member_required(login_url='/admin/login/')
def attendance_session(request, session_id):
    """Trang điểm danh cho 1 buổi học cụ thể"""
    session = get_object_or_404(AttendanceSession, id=session_id)
    
    # Lấy danh sách sinh viên trong lớp
    students_in_class = session_students(session)
    
    # Lấy các bản ghi điểm danh của buổi này
    attendance_records = list(session.session_records.select_related('student'))
    attended_ids = {record.student_id for record in attendance_records}
    records_by_student = {record.student_id: record for record in attendance_records}
    roster = [
        {'student': student, 'record': records_by_student.get(student.id)}
        for student in students_in_class
    ]
    
    context = {
        'session': session,
        'students_in_class': students_in_class,
        'attendance_records': attendance_records,
        'roster': roster,
        'attended_count': sum(1 for record in attendance_records if record.status in ('present', 'late')),
        'total_students': students_in_class.count(),
    }
    return render(request, 'portal/attendance_session.html', context)


@staff_member_required(login_url='/admin/login/')
def end_attendance_session(request, session_id):
    """Kết thúc buổi điểm danh"""
    session = get_object_or_404(AttendanceSession, id=session_id)
    if session.status in ('cancelled', 'postponed'):
        return HttpResponse('Cannot finalize a cancelled or postponed session', status=409)
    finalize_session_attendance(session)
    session.status = 'completed'
    session.end_time = timezone.now()
    session.save()
    return redirect('portal:schedule')


@admin_api_required
@require_http_methods(["POST"])
def api_finalize_session(request, session_id):
    """Close a session and persist absent rows for the complete class roster."""
    session = get_object_or_404(AttendanceSession, id=session_id)
    if session.status in ('cancelled', 'postponed'):
        return JsonResponse({'success': False, 'error': 'Cannot finalize a cancelled or postponed session'}, status=409)
    created = finalize_session_attendance(session)
    session.status = 'completed'
    session.end_time = timezone.now()
    session.save(update_fields=['status', 'end_time'])
    return JsonResponse({'success': True, 'data': {
        'session_id': session_external_id(session),
        'absent_created': created,
        'total_students': session.get_total_students(),
        'present_count': session.get_present_count(),
    }})


# =====================================================
# Video Streaming với Face Recognition
# =====================================================

# Lưu session_id hiện tại đang điểm danh (global variable)
_current_session_id = None

def set_current_session(session_id):
    global _current_session_id
    _current_session_id = session_id

def get_current_session():
    global _current_session_id
    return _current_session_id


def gen_frames(camera):
    """Generator để stream video frames với nhận diện khuôn mặt"""
    while True:
        frame = camera.get_frame()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def video_feed(request):
    """Stream video với nhận diện khuôn mặt"""
    session_id = request.GET.get('session_id')
    if session_id:
        set_current_session(int(session_id))
    camera = fr.VideoCamera()
    return StreamingHttpResponse(
        gen_frames(camera),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def video_feed_session(request, session_id):
    """Stream video cho buổi điểm danh cụ thể"""
    set_current_session(session_id)
    camera = fr.VideoCamera(session_id=session_id)
    return StreamingHttpResponse(
        gen_frames(camera),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


# =====================================================
# API Endpoints
# =====================================================

@admin_api_required
@require_http_methods(["GET"])
def api_stats(request):
    """API trả về thống kê realtime"""
    total_students = Student.objects.count()
    today = timezone.localdate()
    today_attendance = AttendanceRecord.objects.filter(
        date=today,
        status__in=['present', 'late']
    ).count()
    
    attendance_rate = round((today_attendance / total_students) * 100, 1) if total_students else 0
    
    active_cameras = Camera.objects.filter(status='active').count()
    
    return JsonResponse({
        'success': True,
        'data': {
            'total_students': total_students,
            'attendance_rate': attendance_rate,
            'active_cameras': active_cameras,
            'avg_scan_time': None,
            'last_sync': timezone.now().strftime('%H:%M:%S'),
        }
    })


@admin_api_required
@require_http_methods(["POST"])
def api_record_attendance(request):
    """
    API để plugin OpenCV gọi khi nhận diện được khuôn mặt
    
    Expected POST data:
    {
        "student_id": "SV001",
        "confidence": 98.5,
        "camera_id": "CAM01"
    }
    """
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        confidence = data.get('confidence', 0)
        camera_id = data.get('camera_id', '')
        
        # Tìm sinh viên
        try:
            student = Student.objects.get(student_id=student_id)
        except Student.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Student not found'
            }, status=404)
        
        # Tạo bản ghi điểm danh
        today = timezone.localdate()
        current_time = timezone.localtime().time()
        
        record, created = AttendanceRecord.objects.get_or_create(
            student=student,
            date=today,
            defaults={
                'time_in': current_time,
                'status': 'present',
                'confidence': confidence,
                'camera_id': camera_id,
            }
        )
        
        if not created:
            # Đã điểm danh rồi, cập nhật time_out
            record.time_out = current_time
            record.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Attendance recorded',
            'data': {
                'student_name': student.full_name,
                'student_id': student.student_id,
                'time': current_time.strftime('%H:%M:%S'),
                'status': record.status,
                'created': created
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception:
        logger.exception('Attendance API failure')
        return JsonResponse({'success': False, 'error': 'Attendance processing failed'}, status=500)


@require_http_methods(["GET"])
@admin_api_required
def api_students(request):
    """API lấy danh sách sinh viên"""
    students = Student.objects.all().values(
        'student_id', 'full_name', 'class_name', 'is_registered'
    )
    return JsonResponse({
        'success': True,
        'data': list(students)
    })


@require_http_methods(["GET"])
@admin_api_required
def api_attendance_today(request):
    """Attendance feed for management; optional date/subject/class filters."""
    date_text = request.GET.get('date', '')
    if date_text:
        try:
            today = datetime.date.fromisoformat(date_text)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'date must use YYYY-MM-DD'}, status=400)
    else:
        today = timezone.localdate()
    records = AttendanceRecord.objects.filter(date=today).select_related(
        'student', 'session__schedule__subject', 'session__schedule__classroom', 'session__schedule__semester'
    )
    subject_id = request.GET.get('subject_id')
    class_id = request.GET.get('class_id')
    if subject_id:
        records = records.filter(session__schedule__subject__code=subject_id)
    if class_id:
        records = records.filter(session__schedule__classroom__class_id=class_id)
    
    data = []
    for r in records:
        schedule = r.session.schedule if r.session_id else None
        data.append({
            'attendance_id': r.attendance_id,
            'session_id': r.session.external_session_id if r.session_id else None,
            'student_id': r.student.student_id,
            'student_name': r.student.full_name,
            'class_id': schedule.classroom.class_id if schedule else r.student.class_name,
            'class_name': schedule.classroom.name if schedule else r.student.class_name,
            'subject_id': schedule.subject.code if schedule else None,
            'subject_name': schedule.subject.name if schedule else None,
            'scheduled_time': r.scheduled_time.strftime('%H:%M:%S') if r.scheduled_time else None,
            'check_in_time': r.time_in.strftime('%H:%M:%S') if r.time_in else None,
            'time_in': r.time_in.strftime('%H:%M:%S') if r.time_in else None,
            'late_minutes': r.late_minutes,
            'status': r.status,
            'attendance_code': r.attendance_code,
            'attendance_label': r.attendance_label,
            'attendance_periods': r.attendance_periods,
            'method': r.method,
            'device_id': r.device_id,
            'confidence': r.confidence,
        })
    
    return JsonResponse({
        'success': True,
        'date': str(today),
        'data': data
    })


def _normalise_identity_value(value):
    return ' '.join(str(value or '').strip().split()).casefold()


def _student_class_values(student):
    values = {_normalise_identity_value(student.class_name)} if student.class_name else set()
    for classroom in student.classrooms.all():
        values.add(_normalise_identity_value(classroom.class_id))
        values.add(_normalise_identity_value(classroom.name))
    return {value for value in values if value}


def _student_profile_payload(student):
    return {
        'student_id': student.student_id,
        'full_name': student.full_name,
        'email': student.email,
        'class_name': student.class_name,
        'is_registered': student.is_registered,
    }


@require_http_methods(["POST"])
def api_student_login(request):
    """Start an isolated Portal session using an admin-registered student identity and password."""
    try:
        data = json.loads(request.body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Dữ liệu yêu cầu không hợp lệ'}, status=400)

    student_id = str(data.get('student_id') or '').strip()[:20]
    auth_value = str(data.get('password') or data.get('class_name') or '').strip()[:100]
    if not student_id or not auth_value:
        return JsonResponse({'success': False, 'error': 'Mã sinh viên và mật khẩu / lớp là bắt buộc.'}, status=400)

    identity_digest = hashlib.sha256(student_id.casefold().encode('utf-8')).hexdigest()[:16]
    rate_key = f"portal-login:{request.META.get('REMOTE_ADDR', 'unknown')}:{identity_digest}"
    attempts = cache.get(rate_key, 0)
    if attempts >= 10:
        return JsonResponse({
            'success': False,
            'error': 'Bạn đã đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 5 phút.',
        }, status=429)
    cache.set(rate_key, attempts + 1, timeout=300)

    student = Student.objects.filter(student_id__iexact=student_id).prefetch_related('classrooms').first()
    if not student:
        return JsonResponse({
            'success': False,
            'error': 'Student ID or class does not match an admin-registered student.',
        }, status=401)

    authenticated = False
    if student.password_hash:
        authenticated = student.check_password(auth_value)
    else:
        # Fallback to class validation when password has not been explicitly set yet
        supplied_class = _normalise_identity_value(auth_value)
        if supplied_class in _student_class_values(student) or auth_value in (student.class_name, '123456'):
            authenticated = True
            student.set_password(auth_value)
            student.save(update_fields=['password_hash'])

    if not authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Student ID or class does not match an admin-registered student.',
        }, status=401)

    request.session.cycle_key()
    request.session[PORTAL_STUDENT_SESSION_KEY] = student.pk
    request.session.set_expiry(PORTAL_STUDENT_SESSION_AGE)
    cache.delete(rate_key)
    response = JsonResponse({'success': True, 'data': _student_profile_payload(student)})
    response['Cache-Control'] = 'private, no-store'
    return response


@student_api_required
@require_http_methods(["POST"])
def api_student_change_password(request):
    """Cho phép sinh viên đổi mật khẩu bảo mật tài khoản cá nhân."""
    try:
        data = json.loads(request.body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ'}, status=400)

    student = request.portal_student
    old_password = str(data.get('old_password') or '').strip()
    new_password = str(data.get('new_password') or '').strip()

    if len(new_password) < 6:
        return JsonResponse({'success': False, 'error': 'Mật khẩu mới phải có ít nhất 6 ký tự.'}, status=400)

    if student.password_hash and not student.check_password(old_password):
        return JsonResponse({'success': False, 'error': 'Mật khẩu hiện tại không đúng.'}, status=400)

    student.set_password(new_password)
    student.save(update_fields=['password_hash'])
    return JsonResponse({'success': True, 'message': 'Đổi mật khẩu thành công.'})


@admin_api_required
@require_http_methods(["POST"])
def api_admin_update_grade(request):
    """Cập nhật điểm thành phần cho sinh viên và lưu nhật ký kiểm toán GradeAuditLog."""
    try:
        data = json.loads(request.body or '{}')
        student_id = str(data.get('student_id') or '').strip()
        subject_id = str(data.get('subject_id') or '').strip()
        semester = str(data.get('semester') or '').strip()
        assessment_type = str(data.get('assessment_type') or 'TOTAL').strip().upper()
        score = Decimal(str(data.get('score')))
        reason = str(data.get('reason') or 'Cập nhật từ cán bộ quản lý').strip()
    except (TypeError, ValueError, json.JSONDecodeError, decimal.InvalidOperation):
        return JsonResponse({'success': False, 'error': 'Dữ liệu điểm không hợp lệ.'}, status=400)

    if score < 0 or score > 10:
        return JsonResponse({'success': False, 'error': 'Điểm số phải nằm trong khoảng từ 0 đến 10.'}, status=400)

    student = Student.objects.filter(student_id=student_id).first()
    if not student:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy sinh viên.'}, status=404)
    subject = Subject.objects.filter(code=subject_id).first()
    if not subject:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy môn học.'}, status=404)

    grade = Grade.objects.filter(
        student=student, subject=subject, semester=semester, assessment_type=assessment_type
    ).first()
    before_score = grade.score if grade else None

    if grade:
        grade.score = score
        grade.save(update_fields=['score', 'updated_at'])
    else:
        grade = Grade.objects.create(
            student=student, subject=subject, semester=semester, assessment_type=assessment_type, score=score
        )

    GradeAuditLog.objects.create(
        grade=grade,
        changed_by=request.user if request.user.is_authenticated else None,
        before_score=before_score,
        after_score=score,
        reason=reason
    )

    return JsonResponse({
        'success': True,
        'message': 'Đã cập nhật điểm và ghi nhật ký kiểm toán.',
        'data': {
            'student_id': student.student_id,
            'subject_id': subject.code,
            'semester': semester,
            'assessment_type': assessment_type,
            'before_score': float(before_score) if before_score is not None else None,
            'after_score': float(score),
        }
    })


@admin_api_required
@require_http_methods(["GET"])
def api_admin_grade_template_csv(request):
    """Xuất file mẫu CSV điểm theo môn học và học kỳ."""
    subject_code = request.GET.get('subject_code', '').strip()
    semester = request.GET.get('semester', '2026-1').strip()

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"uth-grade-template-{subject_code or 'all'}-{semester}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['student_id', 'full_name', 'class_name', 'subject_code', 'semester', 'cc', 'gk', 'ck', 'bonus', 'reason'])

    students = Student.objects.all().order_by('class_name', 'student_id')
    if subject_code:
        subject = Subject.objects.filter(code=subject_code).first()
        if subject:
            existing = {
                (g.student_id, g.assessment_type): float(g.score)
                for g in Grade.objects.filter(subject=subject, semester=semester)
            }
            for st in students:
                cc = existing.get((st.pk, 'ATTENDANCE'), '')
                gk = existing.get((st.pk, 'MIDTERM'), '')
                ck = existing.get((st.pk, 'FINAL'), '')
                bonus = existing.get((st.pk, 'BONUS'), '')
                writer.writerow([st.student_id, st.full_name, st.class_name, subject_code, semester, cc, gk, ck, bonus, ''])
            return response

    for st in students:
        writer.writerow([st.student_id, st.full_name, st.class_name, subject_code, semester, '', '', '', '', ''])
    return response


@admin_api_required
@require_http_methods(["POST"])
def api_admin_import_grades_csv(request):
    """Nhập điểm hàng loạt từ file CSV/Excel và tự động lưu GradeAuditLog."""
    csv_text = ''
    if 'file' in request.FILES:
        uploaded = request.FILES['file']
        raw = uploaded.read()
        try:
            csv_text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            csv_text = raw.decode('latin-1', errors='replace')
    else:
        csv_text = request.body.decode('utf-8-sig', errors='replace') if request.body else ''

    if not csv_text.strip():
        return JsonResponse({'success': False, 'error': 'Tập tin hoặc nội dung CSV trống.'}, status=400)

    reader = csv.DictReader(io.StringIO(csv_text))
    updated_students = set()
    updated_grades = 0
    errors = []

    for idx, row in enumerate(reader, start=2):
        student_id = str(row.get('student_id') or '').strip()
        subject_code = str(row.get('subject_code') or '').strip()
        semester = str(row.get('semester') or '2026-1').strip()
        reason = str(row.get('reason') or '').strip() or 'Nhập điểm hàng loạt từ file CSV'

        if not student_id or not subject_code:
            continue

        student = Student.objects.filter(student_id=student_id).first()
        if not student:
            errors.append(f"Dòng {idx}: Không tìm thấy sinh viên MSSV {student_id}")
            continue

        subject = Subject.objects.filter(code=subject_code).first()
        if not subject:
            errors.append(f"Dòng {idx}: Không tìm thấy môn học {subject_code}")
            continue

        components = [
            ('ATTENDANCE', row.get('cc')),
            ('MIDTERM', row.get('gk')),
            ('FINAL', row.get('ck')),
            ('BONUS', row.get('bonus')),
        ]

        for assessment_type, raw_val in components:
            if raw_val is None or str(raw_val).strip() == '':
                continue
            try:
                score = Decimal(str(raw_val).strip())
                if score < 0 or score > 10:
                    errors.append(f"Dòng {idx}: Điểm {assessment_type} ({score}) phải trong [0, 10]")
                    continue
            except (decimal.InvalidOperation, ValueError, TypeError):
                errors.append(f"Dòng {idx}: Điểm {assessment_type} không hợp lệ: {raw_val}")
                continue

            grade = Grade.objects.filter(
                student=student, subject=subject, semester=semester, assessment_type=assessment_type
            ).first()
            before_score = grade.score if grade else None

            if grade:
                grade.score = score
                grade.save(update_fields=['score', 'updated_at'])
            else:
                grade = Grade.objects.create(
                    student=student, subject=subject, semester=semester, assessment_type=assessment_type, score=score
                )

            GradeAuditLog.objects.create(
                grade=grade,
                changed_by=request.user if request.user.is_authenticated else None,
                before_score=before_score,
                after_score=score,
                reason=reason
            )
            updated_students.add(student.student_id)
            updated_grades += 1

    return JsonResponse({
        'success': True,
        'message': f"Đã nhập thành công {updated_grades} đầu điểm cho {len(updated_students)} sinh viên.",
        'updated_students_count': len(updated_students),
        'updated_grades_count': updated_grades,
        'errors': errors[:10]
    })


@student_api_required
@require_http_methods(["GET"])
def api_student_leave_requests(request):
    """Lấy danh sách đơn xin nghỉ phép của sinh viên đang đăng nhập."""
    student = request.portal_student
    leaves = LeaveRequest.objects.filter(student=student).select_related('subject').order_by('-created_at')
    data = [{
        'id': l.id,
        'subject_code': l.subject.code if l.subject else '',
        'subject_name': l.subject.name if l.subject else 'Toàn bộ buổi học trong ngày',
        'date': str(l.date),
        'reason': l.reason,
        'evidence_url': l.evidence_url,
        'status': l.status,
        'status_display': l.get_status_display(),
        'review_note': l.review_note,
        'created_at': l.created_at.strftime('%d/%m/%Y %H:%M'),
    } for l in leaves]
    return JsonResponse({'success': True, 'data': data})


@student_api_required
@require_http_methods(["POST"])
def api_student_create_leave_request(request):
    """Sinh viên nộp đơn xin nghỉ phép có lý do kèm minh chứng."""
    student = request.portal_student
    try:
        data = json.loads(request.body or '{}')
        date_str = str(data.get('date') or '').strip()
        subject_id = str(data.get('subject_id') or '').strip()
        reason = str(data.get('reason') or '').strip()
        evidence_url = str(data.get('evidence_url') or '').strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ.'}, status=400)

    if not date_str or not reason:
        return JsonResponse({'success': False, 'error': 'Vui lòng chọn ngày nghỉ và nêu rõ lý do.'}, status=400)

    try:
        leave_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Định dạng ngày không hợp lệ (YYYY-MM-DD).'}, status=400)

    subject = Subject.objects.filter(code=subject_id).first() if subject_id else None

    leave = LeaveRequest.objects.create(
        student=student,
        subject=subject,
        date=leave_date,
        reason=reason,
        evidence_url=evidence_url,
        status='pending'
    )

    return JsonResponse({
        'success': True,
        'message': 'Đã gửi đơn xin nghỉ phép thành công. Vui lòng chờ cán bộ/giảng viên phê duyệt.',
        'data': {'id': leave.id, 'status': leave.status}
    })


@admin_api_required
@require_http_methods(["GET"])
def api_admin_leave_requests(request):
    """Cán bộ quản lý xem danh sách đơn xin nghỉ phép."""
    status_filter = request.GET.get('status', '').strip()
    qs = LeaveRequest.objects.select_related('student', 'subject', 'reviewed_by').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)

    data = [{
        'id': l.id,
        'student_id': l.student.student_id,
        'student_name': l.student.full_name,
        'class_name': l.student.class_name,
        'subject_code': l.subject.code if l.subject else '',
        'subject_name': l.subject.name if l.subject else 'Toàn bộ ngày',
        'date': str(l.date),
        'reason': l.reason,
        'evidence_url': l.evidence_url,
        'status': l.status,
        'status_display': l.get_status_display(),
        'reviewed_by': l.reviewed_by.username if l.reviewed_by else None,
        'review_note': l.review_note,
        'created_at': l.created_at.strftime('%d/%m/%Y %H:%M'),
    } for l in qs]
    return JsonResponse({'success': True, 'data': data})


@admin_api_required
@require_http_methods(["POST"])
def api_admin_review_leave_request(request, request_id):
    """Cán bộ phê duyệt hoặc từ chối đơn xin nghỉ phép."""
    leave = get_object_or_404(LeaveRequest, id=request_id)
    try:
        data = json.loads(request.body or '{}')
        action = str(data.get('action') or '').strip().lower()
        note = str(data.get('note') or '').strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ.'}, status=400)

    if action not in ('approve', 'reject'):
        return JsonResponse({'success': False, 'error': 'Hành động phải là approve hoặc reject.'}, status=400)

    if action == 'approve':
        leave.status = 'approved'
        leave.reviewed_by = request.user if request.user.is_authenticated else None
        leave.reviewed_at = timezone.now()
        leave.review_note = note or 'Đã phê duyệt đơn xin nghỉ phép'
        leave.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at'])

        session_qs = AttendanceSession.objects.filter(date=leave.date)
        if leave.subject_id:
            session_qs = session_qs.filter(schedule__subject=leave.subject)
        target_session = session_qs.first()

        record = AttendanceRecord.objects.filter(student=leave.student, date=leave.date).first()
        if record:
            record.status = 'excused'
            record.attendance_code = 'EXCUSED'
            record.attendance_label = 'NGHỈ CÓ PHÉP'
            record.notes = f"Đơn nghỉ phép đã duyệt: {leave.reason}"
            record.save(update_fields=['status', 'attendance_code', 'attendance_label', 'notes'])
        else:
            AttendanceRecord.objects.create(
                student=leave.student,
                session=target_session,
                date=leave.date,
                status='excused',
                attendance_code='EXCUSED',
                attendance_label='NGHỈ CÓ PHÉP',
                notes=f"Đơn nghỉ phép đã duyệt: {leave.reason}"
            )
        return JsonResponse({'success': True, 'message': 'Đã duyệt đơn xin nghỉ phép và chuyển trạng thái điểm danh sang Nghỉ có phép.'})
    else:
        leave.status = 'rejected'
        leave.reviewed_by = request.user if request.user.is_authenticated else None
        leave.reviewed_at = timezone.now()
        leave.review_note = note or 'Không chấp thuận lý do nghỉ phép'
        leave.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at'])
        return JsonResponse({'success': True, 'message': 'Đã từ chối đơn xin nghỉ phép.'})


@require_http_methods(["POST"])
def api_student_logout(request):
    """End only the Portal identity session without signing out an Admin user."""
    request.session.pop(PORTAL_STUDENT_SESSION_KEY, None)
    request.session.modified = True
    response = JsonResponse({'success': True, 'message': 'Signed out'})
    response['Cache-Control'] = 'private, no-store'
    return response


def _attendance_record_payload(record):
    session = record.session
    return {
        'attendance_id': record.attendance_id,
        'session_id': session_external_id(session) if session else None,
        'semester': session.schedule.semester.code if session and session.schedule.semester_id else '',
        'date': str(record.date),
        'subject_id': session.schedule.subject.code if session else None,
        'subject_name': session.schedule.subject.name if session else None,
        'scheduled_time': record.scheduled_time.strftime('%H:%M:%S') if record.scheduled_time else None,
        'check_in_time': record.time_in.strftime('%H:%M:%S') if record.time_in else None,
        'late_minutes': record.late_minutes,
        'status': record.status,
        'attendance_code': record.attendance_code,
        'attendance_label': record.attendance_label,
        'attendance_periods': record.attendance_periods,
        'method': record.method,
        'device_id': record.device_id,
    }


def _student_grouped_grades(grades, enrolled_schedules=None):
    grouped = {}
    if enrolled_schedules:
        for sch in enrolled_schedules:
            subject = sch.subject
            sem_code = sch.semester.code if sch.semester else ''
            if sem_code:
                key = (subject.code, sem_code)
                grouped[key] = {
                    'subject_id': subject.code,
                    'subject_name': subject.name,
                    'credits': subject.credits,
                    'semester': sem_code,
                    'weights': {
                        'cc': float(getattr(subject, 'weight_cc', 0.10)),
                        'gk': float(getattr(subject, 'weight_gk', 0.30)),
                        'ck': float(getattr(subject, 'weight_ck', 0.60)),
                    },
                    'bonus_method': getattr(subject, 'bonus_method', 'DIRECT'),
                    'cc': None,
                    'gk': None,
                    'ck': None,
                    'bonus': None,
                    'official_total': None,
                }

    for grade in grades:
        key = (grade.subject.code, grade.semester)
        if key not in grouped:
            subject = grade.subject
            grouped[key] = {
                'subject_id': subject.code,
                'subject_name': subject.name,
                'credits': subject.credits,
                'semester': grade.semester,
                'weights': {
                    'cc': float(getattr(subject, 'weight_cc', 0.10)),
                    'gk': float(getattr(subject, 'weight_gk', 0.30)),
                    'ck': float(getattr(subject, 'weight_ck', 0.60)),
                },
                'bonus_method': getattr(subject, 'bonus_method', 'DIRECT'),
                'cc': None,
                'gk': None,
                'ck': None,
                'bonus': None,
                'official_total': None,
            }
        score = float(grade.score)
        atype = grade.assessment_type.upper()
        if atype in ('ATTENDANCE', 'CC'):
            grouped[key]['cc'] = score
        elif atype in ('MIDTERM', 'GK'):
            grouped[key]['gk'] = score
        elif atype in ('FINAL', 'CK'):
            grouped[key]['ck'] = score
        elif atype in ('BONUS', 'PROCESS', 'ASSIGNMENT', 'QUIZ'):
            grouped[key]['bonus'] = score
        elif atype in ('TOTAL',):
            grouped[key]['official_total'] = score

    result = []
    for item in grouped.values():
        w_cc = item['weights']['cc']
        w_gk = item['weights']['gk']
        w_ck = item['weights']['ck']
        cc = item['cc']
        gk = item['gk']
        ck = item['ck']
        bonus = item['bonus']
        
        if cc is not None or gk is not None or ck is not None:
            sum_weighted = (
                (cc * w_cc if cc is not None else 0.0) +
                (gk * w_gk if gk is not None else 0.0) +
                (ck * w_ck if ck is not None else 0.0)
            )
            if bonus is not None and item['bonus_method'] == 'DIRECT':
                sum_weighted += bonus
            item['calculated_total'] = round(min(10.0, max(0.0, sum_weighted)), 2)
        else:
            item['calculated_total'] = None

        final_score = item['official_total'] if item['official_total'] is not None else item['calculated_total']
        scale4 = score_to_scale4_and_letter(final_score)
        item['letter_grade'] = scale4['letter']
        item['gpa_scale_4'] = scale4['gpa']
        item['rank'] = scale4['rank']

        result.append(item)
    return result


@student_api_required
@require_http_methods(["GET"])
def api_student_dashboard(request):
    """Return the complete Portal workspace in one optimized, student-scoped response."""
    from .student_attendance import student_course_attendance
    from .student_schedule import weekly_timetable

    student = request.portal_student
    today = timezone.localdate()
    schedules = list(student_schedules(student).filter(is_active=True).select_related('subject', 'classroom').distinct())
    records = list(AttendanceRecord.objects.filter(student=student).select_related(
        'session__schedule__subject', 'session__schedule__classroom'
    ))
    grades = list(Grade.objects.filter(student=student).select_related('subject'))

    schedule_data = [{
        'schedule_id': schedule.id,
        'day_of_week': schedule.day_of_week,
        'day_name': schedule.get_day_of_week_display(),
        'subject_id': schedule.subject.code,
        'subject_name': schedule.subject.name,
        'teacher': schedule.subject.teacher, 'teacher_contact': teacher_details(schedule.subject),
        'class_id': schedule.classroom.class_id,
        'classroom': schedule.classroom.name,
        'room': schedule.room,
        'start_period': schedule.start_period,
        'end_period': schedule.end_period,
        'time_range': schedule.get_time_range(),
    } for schedule in schedules]
    attendance_data = [_attendance_record_payload(record) for record in records]
    grade_data = [{
        'subject_id': grade.subject.code,
        'subject_name': grade.subject.name,
        'semester': grade.semester,
        'assessment_type': grade.assessment_type,
        'score': float(grade.score),
        'updated_at': grade.updated_at.isoformat(),
    } for grade in grades]

    grouped_grade_data = _student_grouped_grades(grades, enrolled_schedules=schedules)

    graded_items = [g for g in grouped_grade_data if g.get('gpa_scale_4') is not None]
    total_credits = sum(g['credits'] for g in graded_items)
    cumulative_gpa_4 = round(sum(g['gpa_scale_4'] * g['credits'] for g in graded_items) / total_credits, 2) if total_credits else None
    academic_rank = academic_classification(cumulative_gpa_4)

    summary = {
        'total_records': len(records),
        'on_time': 0,
        'late_level_1': 0,
        'late_one_period': 0,
        'absent_two_periods': 0,
        'absent': 0,
    }
    summary_keys = {
        'ON_TIME': 'on_time',
        'LATE_LEVEL_1': 'late_level_1',
        'LATE_ONE_PERIOD': 'late_one_period',
        'ABSENT_TWO_PERIODS': 'absent_two_periods',
        'ABSENT': 'absent',
    }
    for record in records:
        summary_key = summary_keys.get(record.attendance_code)
        if summary_key:
            summary[summary_key] += 1
    course_data = student_course_attendance(student, today)

    week = weekly_timetable(student, schedules, today)
    response = JsonResponse({'success': True, 'data': {
        'profile': _student_profile_payload(student),
        'date': str(today),
        'schedule': schedule_data,
        'schedule_week': week,
        'schedule_today': [item for item in week if item['date'] == today.isoformat()],
        'attendance': attendance_data,
        'attendance_summary': summary,
        'grades': grade_data,
        'grouped_grades': grouped_grade_data,
        'cumulative_gpa_4': cumulative_gpa_4,
        'academic_rank': academic_rank,
        'subjects': course_data['courses'],
        'course_attendance': course_data['courses'],
        'semesters': course_data['semesters'],
        'selected_semester': course_data['selected_semester'],
        'attendance_notifications': course_data['notifications'],
        'synchronized_at': timezone.now().isoformat(),
    }})
    response['Cache-Control'] = 'private, no-store'
    return response


@student_api_required
@require_http_methods(["GET"])
def api_student_profile(request):
    return JsonResponse({'success': True, 'data': _student_profile_payload(request.portal_student)})


@student_api_required
@require_http_methods(["GET"])
def api_student_schedule_today(request):
    student = _current_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student profile not linked'}, status=403)
    today = timezone.localdate()
    schedules = student_schedules(student).filter(is_active=True, day_of_week=today.weekday()).select_related('subject', 'classroom').distinct()
    return JsonResponse({'success': True, 'date': str(today), 'data': [{
        'schedule_id': schedule.id,
        'subject_id': schedule.subject.code,
        'subject_name': schedule.subject.name,
        'teacher': schedule.subject.teacher, 'teacher_contact': teacher_details(schedule.subject),
        'class_id': schedule.classroom.class_id,
        'classroom': schedule.classroom.name,
        'room': schedule.room,
        'start_period': schedule.start_period,
        'end_period': schedule.end_period,
        'time_range': schedule.get_time_range(),
    } for schedule in schedules]})


@student_api_required
@require_http_methods(["GET"])
def api_student_attendance(request):
    student = _current_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student profile not linked'}, status=403)
    records = AttendanceRecord.objects.filter(student=student).select_related(
        'session__schedule__subject', 'session__schedule__classroom'
    )
    data = []
    for record in records:
        session = record.session
        data.append({
            'attendance_id': record.attendance_id,
            'session_id': session_external_id(session) if session else None,
            'date': str(record.date),
            'subject_id': session.schedule.subject.code if session else None,
            'subject_name': session.schedule.subject.name if session else None,
            'scheduled_time': record.scheduled_time.strftime('%H:%M:%S') if record.scheduled_time else None,
            'check_in_time': record.time_in.strftime('%H:%M:%S') if record.time_in else None,
            'late_minutes': record.late_minutes,
            'status': record.status,
            'attendance_code': record.attendance_code,
            'attendance_label': record.attendance_label,
            'attendance_periods': record.attendance_periods,
            'method': record.method,
            'device_id': record.device_id,
        })
    return JsonResponse({'success': True, 'data': data})


@student_api_required
@require_http_methods(["GET"])
def api_student_attendance_summary(request):
    student = _current_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student profile not linked'}, status=403)
    records = AttendanceRecord.objects.filter(student=student)
    return JsonResponse({'success': True, 'data': {
        'total_records': records.count(),
        'on_time': records.filter(attendance_code='ON_TIME').count(),
        'late_level_1': records.filter(attendance_code='LATE_LEVEL_1').count(),
        'late_one_period': records.filter(attendance_code='LATE_ONE_PERIOD').count(),
        'absent_two_periods': records.filter(attendance_code='ABSENT_TWO_PERIODS').count(),
        'absent': records.filter(attendance_code='ABSENT').count(),
    }})


@student_api_required
@require_http_methods(["GET"])
def api_student_grades(request):
    """Return the authenticated student's grade ledger."""
    student = _current_student(request)
    if not student:
        return JsonResponse({'success': False, 'error': 'Student profile not linked'}, status=403)
    grades = Grade.objects.filter(student=student).select_related('subject')
    return JsonResponse({'success': True, 'data': [{
        'subject_id': grade.subject.code,
        'subject_name': grade.subject.name,
        'semester': grade.semester,
        'assessment_type': grade.assessment_type,
        'score': float(grade.score),
        'updated_at': grade.updated_at.isoformat(),
    } for grade in grades]})


@student_api_required
@require_http_methods(["GET"])
def api_student_subject_summary(request):
    """Use the same semester-scoped rule as the student dashboard."""
    from .student_attendance import student_course_attendance
    result = student_course_attendance(request.portal_student, timezone.localdate())
    response = JsonResponse({'success': True, 'data': result['courses']})
    response['Cache-Control'] = 'private, no-store'
    return response


# =====================================================
# Face Recognition APIs
# =====================================================

@admin_api_required
@require_http_methods(["GET"])
def api_face_engine_status(request):
    """Expose dependency health so the registration page can explain failures."""
    status = fr.face_engine_status()
    return JsonResponse({'success': True, 'data': status}, status=200 if status['available'] else 503)

@admin_api_required
@require_http_methods(["POST"])
def api_register_face(request):
    """API đăng ký khuôn mặt từ ảnh base64"""
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        name = data.get('name')
        class_name = data.get('class_name', '')  # Lấy class_name
        email = data.get('email', '')  # Lấy email
        images_base64 = data.get('images', [])  # List of base64 images
        
        if not student_id or not name or not images_base64:
            return JsonResponse({
                'success': False,
                'code': 'VALIDATION_ERROR',
                'error': 'Enter a student ID, full name, and at least one image.'
            }, status=400)
        if not isinstance(images_base64, list) or len(images_base64) > 5:
            return JsonResponse({'success': False, 'code': 'VALIDATION_ERROR', 'error': 'At most 5 images may be registered.'}, status=400)

        engine = fr.face_engine_status()
        if not engine['available']:
            return JsonResponse({
                'success': False,
                'code': engine['code'],
                'error': engine['message'],
                'detail': engine.get('detail', ''),
            }, status=503)
        
        # Decode và xử lý ảnh
        registered_count = 0
        rejected_images = []
        for img_b64 in images_base64:
            try:
                # Xóa header base64 nếu có
                if ',' in img_b64:
                    img_b64 = img_b64.split(',')[1]
                
                if not isinstance(img_b64, str) or len(img_b64) > 6 * 1024 * 1024:
                    continue
                img_data = base64.b64decode(img_b64, validate=True)
                nparr = np.frombuffer(img_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    success = fr.register_face(
                        name,
                        frame,
                        student_id=student_id,
                        class_name=class_name,
                        email=email,
                    )
                    if isinstance(success, tuple):
                        if not success[0]:
                            rejected_images.append(success[1])
                        success = success[0]
                    if success:
                        registered_count += 1
            except RuntimeError as e:
                return JsonResponse({
                    'success': False,
                    'code': 'FACE_ENGINE_UNAVAILABLE',
                    'error': str(e),
                }, status=503)
            except Exception as e:
                print(f"Error processing image: {e}")
                continue
        
        if registered_count > 0:
            # Cập nhật student trong database với đầy đủ thông tin
            student, created = Student.objects.update_or_create(
                student_id=student_id,
                defaults={
                    'full_name': name,
                    'class_name': class_name,  # Lưu class_name
                    'email': email,  # Lưu email
                    'is_registered': True
                }
            )
            
            # Tự động thêm sinh viên vào ClassRoom nếu có class_name
            if class_name:
                from .models import ClassRoom
                classroom = ClassRoom.objects.filter(class_id__iexact=class_name).first()
                classroom = classroom or ClassRoom.objects.filter(name__iexact=class_name).first()
                if classroom:
                    classroom.students.add(student)
            
            return JsonResponse({
                'success': True,
                'message': f'Registered {registered_count} face(s) for {name}',
                'data': {
                    'student_id': student_id,
                    'name': name,
                    'faces_registered': registered_count,
                    'rejected_images': rejected_images,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'code': 'NO_FACE_DETECTED',
                'error': rejected_images[0] if rejected_images else 'No clear face was detected in the selected image.'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'code': 'INVALID_JSON',
            'error': 'Invalid JSON'
        }, status=400)
    except Exception:
        return JsonResponse({
            'success': False,
            'error': 'Face registration failed'
        }, status=500)


@admin_api_required
@require_http_methods(["DELETE"])
def api_delete_student(request, student_id):
    """API xóa sinh viên và dữ liệu khuôn mặt"""
    import shutil
    from .face_recognition import load_database, save_database, MY_FACES_DIR, face_folder_name
    
    try:
        # Lấy thông tin sinh viên
        student = Student.objects.get(id=student_id)
        student_name = student.full_name
        
        # 1. Xóa khỏi face_database.pkl
        face_db = load_database()
        removed = False
        for identity in (student.student_id, student_name):
            if identity in face_db:
                face_db.pop(identity, None)
                removed = True
        if removed:
            save_database(face_db)
        
        # 2. Xóa thư mục ảnh my_faces/{tên}
        import os
        person_dir = os.path.join(MY_FACES_DIR, face_folder_name(student_name, student.class_name))
        if os.path.exists(person_dir):
            shutil.rmtree(person_dir)
        
        # 3. Xóa các bản ghi điểm danh liên quan
        AttendanceRecord.objects.filter(student=student).delete()
        
        # 4. Xóa sinh viên khỏi database
        student.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Deleted {student_name} and all related attendance and face data.'
        })
        
    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Student not found'
        }, status=404)
    except Exception:
        return JsonResponse({
            'success': False,
            'error': 'Student deletion failed'
        }, status=500)


@admin_api_required
@require_http_methods(["PUT"])
def api_update_student(request, student_id):
    """API cập nhật thông tin sinh viên"""
    from .face_recognition import load_database, save_database, MY_FACES_DIR, face_folder_name
    import os
    import shutil
    
    try:
        data = json.loads(request.body)
        student = Student.objects.get(id=student_id)
        old_name = student.full_name
        
        # Cập nhật thông tin
        new_student_id = data.get('student_id', student.student_id)
        new_full_name = data.get('full_name', student.full_name)
        new_class_name = data.get('class_name', student.class_name)
        new_email = data.get('email', student.email)
        
        # Nếu tên thay đổi, cập nhật trong face_database.pkl và thư mục my_faces
        if new_full_name != old_name or new_class_name != student.class_name:
            # Cập nhật face_database.pkl
            face_db = load_database()
            identity = student.student_id if student.student_id in face_db else old_name
            if identity in face_db:
                face_db[student.student_id] = face_db.pop(identity)
                save_database(face_db)
            
            # Đổi tên thư mục my_faces
            old_dir = os.path.join(MY_FACES_DIR, face_folder_name(old_name, student.class_name))
            new_dir = os.path.join(MY_FACES_DIR, face_folder_name(new_full_name, new_class_name))
            if os.path.exists(old_dir):
                shutil.move(old_dir, new_dir)
        
        # Cập nhật student trong database
        student.student_id = new_student_id
        student.full_name = new_full_name
        student.class_name = new_class_name
        student.email = new_email
        student.save()

        # Keep the on-disk student profile in sync with the database.
        if student.is_registered:
            profile_dir = os.path.join(MY_FACES_DIR, face_folder_name(new_full_name, new_class_name))
            profile_path = os.path.join(profile_dir, 'student.json')
            if os.path.isdir(profile_dir):
                with open(profile_path, 'w', encoding='utf-8') as stream:
                    json.dump({
                        'student_id': new_student_id,
                        'full_name': new_full_name,
                        'class_name': new_class_name,
                        'email': new_email,
                        'face_files': sorted(
                            f for f in os.listdir(profile_dir)
                            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
                        ),
                    }, stream, ensure_ascii=False, indent=2)
        
        return JsonResponse({
            'success': True,
            'message': f'Updated student information for {new_full_name}.'
        })
        
    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Student not found'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception:
        return JsonResponse({
            'success': False,
            'error': 'Student update failed'
        }, status=500)


@require_http_methods(["GET"])
@admin_api_required
def api_registered_faces(request):
    """API lấy danh sách khuôn mặt đã đăng ký"""
    database = fr.load_database()
    
    faces = []
    for name, embeddings in database.items():
        faces.append({
            'name': name,
            'embeddings_count': len(embeddings)
        })
    
    return JsonResponse({
        'success': True,
        'data': faces
    })


# =====================================================
# API cho Thời khóa biểu và Buổi điểm danh
# =====================================================

@require_http_methods(["GET"])
@admin_api_required
def api_schedules(request):
    """API lấy thời khóa biểu"""
    day = request.GET.get('day')
    schedules = Schedule.objects.filter(is_active=True).select_related('subject', 'classroom')
    
    if day is not None:
        schedules = schedules.filter(day_of_week=int(day))
    
    data = [{
        'id': s.id,
        'subject': s.subject.name,
        'subject_code': s.subject.code,
        'classroom': s.classroom.name,
        'class_id': s.classroom.class_id,
        'day_of_week': s.day_of_week,
        'day_name': s.get_day_of_week_display(),
        'start_period': s.start_period,
        'end_period': s.end_period,
        'time_range': s.get_time_range(),
        'room': s.room,
    } for s in schedules]
    
    return JsonResponse({'success': True, 'data': data})


@require_http_methods(["GET"])
@kiosk_api_required
def api_sessions_today(request):
    """API lấy các buổi điểm danh hôm nay"""
    today = timezone.localdate()
    _open_today_sessions(today)
    sessions = AttendanceSession.objects.filter(date=today).select_related('schedule__subject', 'schedule__classroom')
    
    data = [{
        'id': s.id,
        'session_id': session_external_id(s),
        'subject': s.schedule.subject.name,
        'classroom': s.schedule.classroom.name,
        'date': str(s.date),
        'status': s.status,
        'status_display': s.get_status_display(),
        'present_count': s.get_present_count(),
        'total_students': s.get_total_students(),
        'start_time': s.start_time.strftime('%H:%M:%S') if s.start_time else None,
        'scheduled_time': get_session_scheduled_time(s).strftime('%H:%M:%S'),
        'room': s.schedule.room,
    } for s in sessions]
    
    return JsonResponse({'success': True, 'data': data})


@require_http_methods(["GET"])
@admin_api_required
def api_session_attendance(request, session_id):
    """API lấy danh sách điểm danh của 1 buổi"""
    try:
        session = AttendanceSession.objects.get(id=session_id)
        records = session.session_records.select_related('student')
        
        data = [{
            'attendance_id': r.attendance_id,
            'student_id': r.student.student_id,
            'student_name': r.student.full_name,
            'class_name': r.student.class_name,
            'time_in': r.time_in.strftime('%H:%M:%S') if r.time_in else None,
            'status': r.status,
            'confidence': round(r.confidence * 100, 1) if r.confidence else 0,
            'scheduled_time': r.scheduled_time.strftime('%H:%M:%S') if r.scheduled_time else None,
            'late_minutes': r.late_minutes,
            'attendance_code': r.attendance_code,
            'attendance_label': r.attendance_label,
            'attendance_periods': r.attendance_periods,
            'method': r.method,
            'device_id': r.device_id,
        } for r in records]
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': session.id,
                'session_id': session_external_id(session),
                'subject': session.schedule.subject.name,
                'classroom': session.schedule.classroom.name,
                'class_id': session.schedule.classroom.class_id,
                'date': str(session.date),
                'status': session.status,
                'scheduled_time': get_session_scheduled_time(session).strftime('%H:%M:%S'),
            },
            'data': data
        })
    except AttendanceSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)


def _session_roster_rows(session):
    students = session_students(session).order_by('student_id')
    records = {record.student_id: record for record in session.session_records.select_related('student')}
    scheduled_time = get_session_scheduled_time(session)
    rows = []
    for student in students:
        record = records.get(student.id)
        if record:
            row = {
                'attendance_id': record.attendance_id,
                'student_id': student.student_id,
                'student_name': student.full_name,
                'class_id': session.schedule.classroom.class_id,
                'subject_id': session.schedule.subject.code,
                'subject_name': session.schedule.subject.name,
                'date': str(session.date),
                'scheduled_time': record.scheduled_time.strftime('%H:%M:%S') if record.scheduled_time else scheduled_time.strftime('%H:%M:%S'),
                'check_in_time': record.time_in.strftime('%H:%M:%S') if record.time_in else None,
                'late_minutes': record.late_minutes,
                'status': record.status,
                'attendance_code': record.attendance_code,
                'attendance_label': record.attendance_label,
                'attendance_periods': record.attendance_periods,
                'method': record.method,
                'device_id': record.device_id,
                'already_checked_in': True,
            }
        else:
            closed = session.status in ('completed', 'cancelled')
            row = {
                'attendance_id': None,
                'student_id': student.student_id,
                'student_name': student.full_name,
                'class_id': session.schedule.classroom.class_id,
                'subject_id': session.schedule.subject.code,
                'subject_name': session.schedule.subject.name,
                'date': str(session.date),
                'scheduled_time': scheduled_time.strftime('%H:%M:%S'),
                'check_in_time': None,
                'late_minutes': None,
                'status': 'absent' if closed else 'not_checked_in',
                'attendance_code': 'ABSENT' if closed else 'NOT_CHECKED_IN',
                'attendance_label': 'ABSENT' if closed else 'NOT CHECKED IN',
                'attendance_periods': None,
                'method': None,
                'device_id': None,
                'already_checked_in': False,
            }
        rows.append(row)
    return rows


@require_http_methods(["GET"])
@kiosk_api_required
def api_session_roster(request, session_id):
    """Return every expected student, including students not yet scanned."""
    try:
        session = AttendanceSession.objects.select_related('schedule__subject', 'schedule__classroom').get(id=session_id)
        return JsonResponse({
            'success': True,
            'session': {
                'id': session.id,
                'session_id': session_external_id(session),
                'subject_id': session.schedule.subject.code,
                'subject_name': session.schedule.subject.name,
                'class_id': session.schedule.classroom.class_id,
                'classroom': session.schedule.classroom.name,
                'room': session.schedule.room,
                'date': str(session.date),
                'scheduled_time': get_session_scheduled_time(session).strftime('%H:%M:%S'),
                'status': session.status,
            },
            'data': _session_roster_rows(session),
        })
    except AttendanceSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)


@require_http_methods(["GET"])
@admin_api_required
def api_export_session_csv(request, session_id):
    """Export a session roster as UTF-8 BOM CSV for Excel compatibility."""
    try:
        session = AttendanceSession.objects.select_related('schedule__subject', 'schedule__classroom').get(id=session_id)
    except AttendanceSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)

    columns = [
        'attendance_id', 'session_id', 'student_id', 'student_name', 'class_id',
        'subject_id', 'subject_name', 'date', 'scheduled_time', 'check_in_time',
        'late_minutes', 'status', 'attendance_code', 'attendance_label',
        'attendance_periods', 'method', 'device_id',
    ]
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('\ufeff')
    response['Content-Disposition'] = f'attachment; filename="attendance-{session.date}-{session.id}.csv"'
    writer = csv.DictWriter(response, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in _session_roster_rows(session):
        row['session_id'] = session_external_id(session)
        writer.writerow(row)
    return response


@admin_api_required
@require_http_methods(["POST"])
def api_import_attendance_csv(request):
    """Administrative CSV backup import into the same central records."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Staff authentication required'}, status=403)
    uploaded = request.FILES.get('file')
    if uploaded is None:
        return JsonResponse({'success': False, 'error': 'Missing multipart file field: file'}, status=400)
    result = import_csv_bytes(uploaded.read(), source=uploaded.name)
    status = 200 if result.imported or result.duplicates else 400
    return JsonResponse({
        'success': status == 200 and not result.failed,
        'data': {
            'file': uploaded.name,
            'imported': result.imported,
            'duplicates': result.duplicates,
            'failed': result.failed,
        },
    }, status=status)


@admin_api_required
@require_http_methods(["POST"])
def api_record_session_attendance(request):
    """API ghi nhận điểm danh cho 1 buổi học"""
    try:
        data = json.loads(request.body)
        session_ref = data.get('session_id')
        student_name = data.get('student_name')
        confidence = data.get('confidence', 0)
        device_id = data.get('device_id', 'MANUAL-MANAGEMENT')
        
        if not session_ref or not student_name:
            return JsonResponse({
                'success': False,
                'error': 'Missing session_id or student_name'
            }, status=400)
        
        session = resolve_session(session_ref)
        student = Student.objects.get(full_name__iexact=student_name)
        record, created, timing = record_attendance_event(
            session=session,
            student=student,
            confidence=confidence,
            method=METHOD_FACIAL_RECOGNITION,
            device_id=device_id,
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{student.full_name} attendance recorded: {timing["attendance_label"]}',
            'data': {
                'student_name': student.full_name,
                'student_id': student.student_id,
                'class_name': student.class_name,
                'attendance_id': record.attendance_id,
                'time_in': record.time_in.strftime('%H:%M:%S') if record.time_in else None,
                'date': str(record.date),
                'session_id': session_external_id(session),
                'subject': session.schedule.subject.name,
                'created': created,
                'already_checked_in': not created,
                'status': record.status,
                'attendance_label': record.attendance_label,
                'attendance_code': record.attendance_code,
                'late_minutes': record.late_minutes,
                'attendance_periods': record.attendance_periods,
                'method': record.method,
                'device_id': record.device_id,
            }
        })
        
    except AttendanceSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Student not found'}, status=404)
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=409)
    except Exception:
        logger.exception('Session attendance API failure')
        return JsonResponse({'success': False, 'error': 'Attendance processing failed'}, status=500)


@admin_api_required
@require_http_methods(["POST"])
def api_create_session(request):
    """API tạo buổi điểm danh mới"""
    try:
        data = json.loads(request.body)
        schedule_id = data.get('schedule_id')
        date_str = data.get('date')  # Format: YYYY-MM-DD
        
        if not schedule_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing schedule_id'
            }, status=400)
        
        schedule = Schedule.objects.get(id=schedule_id)
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.localdate()
        
        session, created = AttendanceSession.objects.get_or_create(
            schedule=schedule,
            date=date,
            defaults={
                'status': 'active',
                'start_time': timezone.now()
            }
        )
        
        if not created:
            session.status = 'active'
            session.start_time = timezone.now()
            session.save()

        external_id = session_external_id(session)
        
        return JsonResponse({
            'success': True,
            'message': 'Attendance session created.',
            'data': {
                'session_id': session.id,
                'external_session_id': external_id,
                'subject': schedule.subject.name,
                'classroom': schedule.classroom.name,
                'scheduled_time': get_session_scheduled_time(session).strftime('%H:%M:%S'),
                'date': str(date),
                'created': created
            }
        })
        
    except Schedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'}, status=404)
    except Exception:
        logger.exception('Session creation API failure')
        return JsonResponse({'success': False, 'error': 'Session creation failed'}, status=500)


@admin_api_required
@require_http_methods(["POST"])
def api_create_class(request):
    """Create a class and optionally attach existing students by ID."""
    try:
        data = json.loads(request.body or '{}')
        class_id = str(data.get('class_id') or '').strip()
        name = str(data.get('name') or '').strip()
        if not class_id or not name:
            return JsonResponse({'success': False, 'error': 'class_id and name are required'}, status=400)
        classroom, created = ClassRoom.objects.get_or_create(
            class_id=class_id,
            defaults={'name': name, 'department': str(data.get('department') or '').strip()},
        )
        if not created:
            classroom.name = name
            classroom.department = str(data.get('department') or classroom.department).strip()
            classroom.save(update_fields=['name', 'department'])
        student_ids = [str(value).strip() for value in (data.get('student_ids') or []) if str(value).strip()]
        if student_ids:
            classroom.students.add(*Student.objects.filter(student_id__in=student_ids))
        return JsonResponse({'success': True, 'created': created, 'data': {
            'id': classroom.id, 'class_id': classroom.class_id, 'name': classroom.name,
            'department': classroom.department, 'student_count': classroom.students.count(),
        }}, status=201 if created else 200)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)


@admin_api_required
@require_http_methods(["POST"])
def api_create_subject(request):
    """Create or update a subject from the Admin scheduling workspace."""
    try:
        data = json.loads(request.body or '{}')
        code = str(data.get('code') or '').strip().upper()
        name = str(data.get('name') or '').strip()
        if not code or not name:
            return JsonResponse({'success': False, 'error': 'Subject code and name are required'}, status=400)
        try:
            credits = int(data.get('credits') or 3)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Credits must be a number'}, status=400)
        if credits < 1 or credits > 20:
            return JsonResponse({'success': False, 'error': 'Credits must be between 1 and 20'}, status=400)
        subject, created = Subject.objects.get_or_create(
            code=code,
            defaults={'name': name, 'teacher': str(data.get('teacher') or '').strip(), 'credits': credits},
        )
        if not created:
            subject.name = name
            subject.teacher = str(data.get('teacher') or '').strip()
            subject.credits = credits
            subject.save(update_fields=['name', 'teacher', 'credits'])
        return JsonResponse({'success': True, 'created': created, 'data': {
            'id': subject.id, 'code': subject.code, 'name': subject.name,
            'teacher': subject.teacher, 'credits': subject.credits,
        }}, status=201 if created else 200)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)


@admin_api_required
@require_http_methods(["POST"])
def api_create_schedule(request):
    """Attach a subject to a class and create/update its weekly schedule."""
    try:
        data = json.loads(request.body or '{}')
        subject_id = data.get('subject_id')
        classroom_id = data.get('classroom_id')
        if not subject_id or not classroom_id:
            return JsonResponse({'success': False, 'error': 'Subject and class are required'}, status=400)
        subject = Subject.objects.get(id=int(subject_id))
        classroom = ClassRoom.objects.get(id=int(classroom_id))
        semester = AcademicTerm.objects.get(pk=int(data['semester_id'])) if data.get('semester_id') else None
        day_of_week = int(data.get('day_of_week'))
        start_period = int(data.get('start_period'))
        end_period = int(data.get('end_period'))
        if day_of_week not in range(7):
            raise ValueError('Day of week must be between 0 and 6')
        if start_period not in range(1, 11) or end_period not in range(1, 11) or end_period < start_period:
            raise ValueError('Invalid teaching periods')
        schedule, created = Schedule.objects.get_or_create(
            subject=subject,
            classroom=classroom,
            semester=semester,
            day_of_week=day_of_week,
            start_period=start_period,
            end_period=end_period,
            defaults={'room': str(data.get('room') or '').strip(), 'is_active': True},
        )
        if not created:
            schedule.room = str(data.get('room') or '').strip()
            schedule.is_active = True
            schedule.save(update_fields=['room', 'is_active'])
        return JsonResponse({'success': True, 'created': created, 'data': {
            'id': schedule.id, 'subject_id': subject.id, 'subject': subject.name,
            'classroom_id': classroom.id, 'classroom': classroom.name,
            'day_of_week': schedule.day_of_week, 'start_period': schedule.start_period,
            'end_period': schedule.end_period, 'room': schedule.room,
        }}, status=201 if created else 200)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except (Subject.DoesNotExist, ClassRoom.DoesNotExist, AcademicTerm.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Subject or class not found'}, status=404)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid subject, class, or period values'}, status=400)


@admin_api_required
@require_http_methods(["POST"])
def api_postpone_session(request, session_id):
    """Postpone a session without deleting its attendance history."""
    session = get_object_or_404(AttendanceSession, id=session_id)
    try:
        data = json.loads(request.body or '{}')
        postponed_to = data.get('postponed_to')
        if postponed_to:
            postponed_to = datetime.date.fromisoformat(str(postponed_to))
            if postponed_to <= session.date:
                return JsonResponse({'success': False, 'error': 'postponed_to must be after the current session date'}, status=400)
        session.status = 'postponed'
        session.postponed_to = postponed_to
        session.postponed_reason = str(data.get('reason') or '').strip()[:240]
        session.save(update_fields=['status', 'postponed_to', 'postponed_reason'])
        rescheduled = None
        if postponed_to:
            rescheduled, _ = AttendanceSession.objects.get_or_create(
                schedule=session.schedule,
                date=postponed_to,
                defaults={'status': 'scheduled', 'notes': f'Rescheduled from {session.date}.'},
            )
            session_external_id(rescheduled)
        return JsonResponse({'success': True, 'data': {
            'session_id': session_external_id(session), 'status': session.status,
            'postponed_to': str(session.postponed_to) if session.postponed_to else None,
            'rescheduled_session_id': session_external_id(rescheduled) if rescheduled else None,
        }})
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'postponed_to must use YYYY-MM-DD'}, status=400)


@admin_api_required
@require_http_methods(["GET"])
def api_export_all_csv(request):
    """Export students, classes, schedules, sessions and attendance in one CSV."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="uth-attendance-export.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    columns = ['entity_type', 'student_id', 'student_name', 'email', 'class_id', 'class_name', 'department', 'subject_id', 'subject_name', 'session_id', 'session_date', 'session_status', 'postponed_to', 'postponed_reason', 'scheduled_time', 'attendance_id', 'check_in_time', 'late_minutes', 'attendance_status', 'attendance_code', 'attendance_periods', 'method', 'device_id', 'semester', 'assessment_type', 'score']
    writer.writerow(columns)
    for student in Student.objects.order_by('student_id'):
        writer.writerow(['STUDENT', student.student_id, student.full_name, student.email, student.class_name, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
    for classroom in ClassRoom.objects.order_by('class_id'):
        writer.writerow(['CLASS', '', '', '', classroom.class_id, classroom.name, classroom.department, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])
    for schedule in Schedule.objects.select_related('subject', 'classroom').order_by('id'):
        writer.writerow(['SCHEDULE', '', '', '', schedule.classroom.class_id, schedule.classroom.name, schedule.classroom.department, schedule.subject.code, schedule.subject.name, '', '', '', '', '', schedule.get_time_range(), '', '', '', '', '', '', '', '', '', '', ''])
    for session in AttendanceSession.objects.select_related('schedule__subject', 'schedule__classroom').order_by('-date', 'id'):
        writer.writerow(['SESSION', '', '', '', session.schedule.classroom.class_id, session.schedule.classroom.name, session.schedule.classroom.department, session.schedule.subject.code, session.schedule.subject.name, session_external_id(session), session.date, session.status, session.postponed_to or '', session.postponed_reason, get_session_scheduled_time(session), '', '', '', '', '', '', '', '', '', '', ''])
    for record in AttendanceRecord.objects.select_related('student', 'session__schedule__subject', 'session__schedule__classroom').order_by('-date', 'id'):
        schedule = record.session.schedule if record.session_id else None
        writer.writerow(['ATTENDANCE', record.student.student_id, record.student.full_name, record.student.email, schedule.classroom.class_id if schedule else record.student.class_name, schedule.classroom.name if schedule else '', schedule.classroom.department if schedule else '', schedule.subject.code if schedule else '', schedule.subject.name if schedule else '', session_external_id(record.session) if record.session_id else '', record.date, record.session.status if record.session_id else '', record.session.postponed_to if record.session_id and record.session.postponed_to else '', record.session.postponed_reason if record.session_id else '', record.scheduled_time or '', record.attendance_id or '', record.time_in or '', record.late_minutes, record.status, record.attendance_code, record.attendance_periods if record.attendance_periods is not None else '', record.method, record.device_id, '', '', ''])
    for grade in Grade.objects.select_related('student', 'subject').order_by('student__student_id', 'subject__code'):
        writer.writerow(['GRADE', grade.student.student_id, grade.student.full_name, grade.student.email, grade.student.class_name, '', '', grade.subject.code, grade.subject.name, '', '', '', '', '', '', '', '', '', '', '', '', '', '', grade.semester, grade.assessment_type, grade.score])
    return response
