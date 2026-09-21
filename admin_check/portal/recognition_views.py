import base64
import binascii
import hashlib
import json
import logging

import cv2
import numpy as np
from django.db import OperationalError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import face_recognition as fr
from .attendance_service import attendance_payload, resolve_session, session_external_id
from .models import AttendanceSession
from .recognition_service import process_recognition
from .views import kiosk_api_required

logger = logging.getLogger(__name__)


@csrf_exempt
@kiosk_api_required
@require_POST
def recognize(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object')
        image = data.get('image')
        if not isinstance(image, str) or not image:
            raise ValueError('A camera image is required')
        if len(image) > 6 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'Image is too large'}, status=413)
        session = resolve_session(data.get('session_id'))
        if not session or session.status != 'active' or session.date != timezone.localdate():
            return JsonResponse({'success': False, 'error': 'Cần có một buổi học đang diễn ra trong hôm nay.'}, status=409)
        device_id = data.get('device_id', 'KIOSK-LOCAL')
        if not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 80:
            raise ValueError('Mã thiết bị Kiosk phải từ 1 đến 80 ký tự.')
        raw = base64.b64decode(image.split(',', 1)[-1], validate=True)
        if not raw:
            raise ValueError('Hình ảnh không hợp lệ.')
        frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0] * frame.shape[1] > 12_000_000:
            raise ValueError('Hình ảnh không hợp lệ hoặc kích thước vượt quá 12MP.')
    except AttendanceSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy buổi điểm danh.'}, status=404)
    except (ValueError, TypeError, binascii.Error, cv2.error) as e:
        return JsonResponse({'success': False, 'error': str(e) or 'Dữ liệu hình ảnh hoặc yêu cầu không hợp lệ.'}, status=400)
    try:
        results = fr.recognize_frame(frame)
        faces, canonical = process_recognition(session, results, device_id.strip(), hashlib.sha256(raw).hexdigest())
        payload = {'success': True, 'data': {'faces_detected': len(results), 'recognized': faces,
                                            'timestamp': timezone.localtime().strftime('%H:%M:%S')}}
        if canonical:
            student, record, created = canonical
            payload.update(student={'student_id': student.student_id, 'full_name': student.full_name},
                           session={'session_id': session_external_id(session),
                                    'subject_id': session.schedule.subject.code,
                                    'subject_name': session.schedule.subject.name,
                                    'scheduled_time': record.scheduled_time.isoformat()},
                           attendance=attendance_payload(record, already_checked_in=not created))
        return JsonResponse(payload)
    except ValueError as error:
        return JsonResponse({'success': False, 'error': str(error)}, status=409)
    except OperationalError:
        return JsonResponse({'success': False, 'error': 'Máy chủ đang bận xử lý điểm danh. Vui lòng thử lại.'}, status=503)
    except Exception:
        logger.exception('Face recognition failed')
        return JsonResponse({'success': False, 'error': 'Dịch vụ nhận diện khuôn mặt tạm thời gián đoạn. Vui lòng thử lại.'}, status=503)
