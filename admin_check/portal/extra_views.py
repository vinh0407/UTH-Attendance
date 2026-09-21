"""
Extra API views for testing and synchronization.
"""
import json
import base64
import os
import pickle
import cv2
import numpy as np

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings

from .models import Student, AttendanceRecord
from . import face_recognition as fr
from .attendance_service import METHOD_FACIAL_RECOGNITION, calculate_attendance_status, next_attendance_id
from .views import kiosk_api_required, admin_api_required


@admin_api_required
@require_http_methods(["POST"])
def api_test_image(request):
    """
    API test nhan dien khuon mat tu anh upload.
    POST /api/test-image/ voi multipart form-data field 'image'
    hoac JSON body {'image_base64': '...'}.
    Tu dong ghi diem danh neu nhan dien duoc.
    """
    try:
        frame = None

        # Uu tien file upload
        if request.FILES.get('image'):
            img_file = request.FILES['image']
            if img_file.size > 4 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': 'Image exceeds 4 MB limit'}, status=413)
            img_data = img_file.read()
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}
            img_b64 = data.get('image_base64') or data.get('image', '')
            if img_b64:
                if ',' in img_b64:
                    img_b64 = img_b64.split(',')[1]
                if len(img_b64) > 6 * 1024 * 1024:
                    return JsonResponse({'success': False, 'error': 'Image exceeds 4 MB limit'}, status=413)
                img_data = base64.b64decode(img_b64, validate=True)
                nparr = np.frombuffer(img_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({
                'success': False,
                'error': 'Unable to read the image. Upload an image using the "image" field.'
            }, status=400)

        # Nhan dien khuon mat
        results = fr.recognize_face(frame)
        recognized = []
        attendance_results = []
        device_id = str(request.POST.get('device_id') or 'TEST-API')[:80]

        for r in results:
            name = r['name']
            conf = r['confidence']
            recognized.append({
                'name': name,
                'confidence': round(conf, 1),
                'bbox': r['bbox']
            })

            if name != 'Unknown':
                try:
                    student = Student.objects.filter(full_name=name).first()
                    if student:
                        current_time = timezone.now()
                        current_time = timezone.now()
                        timing = calculate_attendance_status(current_time.time(), current_time)
                        existing = AttendanceRecord.objects.filter(student=student, date=current_time.date(), session=None).first()
                        record, created = AttendanceRecord.objects.update_or_create(
                            student=student,
                            date=current_time.date(),
                            session=None,
                            defaults={
                                'attendance_id': existing.attendance_id if existing and existing.attendance_id else next_attendance_id(current_time.date()),
                                'time_in': current_time.time(),
                                'status': timing['status'],
                                'confidence': conf / 100.0,
                                'scheduled_time': current_time.time(),
                                'late_minutes': timing['late_minutes'],
                                'attendance_code': timing['attendance_code'],
                                'attendance_label': timing['attendance_label'],
                                'attendance_periods': timing['attendance_periods'],
                                'method': METHOD_FACIAL_RECOGNITION,
                                'device_id': device_id,
                            }
                        )
                        attendance_results.append({
                            'student_id': student.student_id,
                            'student_name': student.full_name,
                            'class_name': student.class_name,
                            'time': current_time.strftime('%H:%M:%S'),
                            'confidence': round(conf, 1),
                            'status': record.status,
                            'is_new': created,
                            'attendance_id': record.attendance_id,
                            'attendance_code': record.attendance_code,
                            'attendance_label': record.attendance_label,
                            'late_minutes': record.late_minutes,
                            'attendance_periods': record.attendance_periods,
                        })
                    else:
                        attendance_results.append({
                            'student_name': name,
                            'error': 'Student is not in the database. Run GET /api/sync-faces/ first.'
                        })
                except Exception as e:
                    attendance_results.append({'student_name': name, 'error': str(e)})

        return JsonResponse({
            'success': True,
            'faces_detected': len(results),
            'faces_recognized': len([r for r in results if r['name'] != 'Unknown']),
            'recognized': recognized,
            'attendance': attendance_results,
        })

    except Exception:
        return JsonResponse({'success': False, 'error': 'Image processing failed'}, status=500)


@admin_api_required
@require_http_methods(["GET"])
def api_sync_faces(request):
    """
    API dong bo face_database.pkl -> Django Student DB.
    GET /api/sync-faces/
    """
    try:
        # Duong dan: BASE_DIR = admin_check/, cha no la thu muc goc project
        project_root = os.path.dirname(str(settings.BASE_DIR))
        db_file = os.path.join(project_root, 'face_database.pkl')

        if not os.path.exists(db_file):
            return JsonResponse({
                'success': False,
                'error': 'face_database.pkl was not found.',
            }, status=404)

        with open(db_file, 'rb') as f:
            face_db = pickle.load(f)

        created_list = []
        updated_list = []

        # Tinh toan student_id tiep theo
        existing_ids = set(Student.objects.values_list('student_id', flat=True))
        sv_numbers = []
        for sid in existing_ids:
            try:
                sv_numbers.append(int(sid.replace('SV', '')))
            except Exception:
                pass
        next_num = max(sv_numbers) + 1 if sv_numbers else 1

        for name, embeddings in face_db.items():
            student = Student.objects.filter(full_name=name).first()
            if student:
                if not student.is_registered:
                    student.is_registered = True
                    student.save()
                updated_list.append({'name': name, 'student_id': student.student_id})
            else:
                new_id = f'SV{next_num:03d}'
                while Student.objects.filter(student_id=new_id).exists():
                    next_num += 1
                    new_id = f'SV{next_num:03d}'
                student = Student.objects.create(
                    student_id=new_id,
                    full_name=name,
                    class_name='CNTT01',
                    is_registered=True,
                )
                created_list.append({'name': name, 'student_id': new_id})
                next_num += 1

        return JsonResponse({
            'success': True,
            'message': f'Synchronization complete: {len(created_list)} created, {len(updated_list)} updated.',
            'created': created_list,
            'updated': updated_list,
            'total_students': Student.objects.count(),
            'face_db_count': len(face_db),
        })

    except Exception:
        return JsonResponse({'success': False, 'error': 'Face synchronization failed'}, status=500)
