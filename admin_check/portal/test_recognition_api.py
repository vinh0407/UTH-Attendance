import base64
import datetime as dt
import json
from unittest.mock import patch

import cv2
import numpy as np
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import AttendanceRecord, AttendanceSession, ClassRoom, Schedule, Student, Subject


@override_settings(FACE_CONFIRMATION_MIN_INTERVAL_SECONDS=0)
class RecognitionApiTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(student_id='AI001', full_name='AI Student')
        classroom = ClassRoom.objects.create(class_id='AI', name='AI Class')
        classroom.students.add(self.student)
        subject = Subject.objects.create(code='AI', name='AI')
        schedule = Schedule.objects.create(subject=subject, classroom=classroom,
                                          day_of_week=0, start_period=1, end_period=3)
        self.session = AttendanceSession.objects.create(schedule=schedule, date=timezone.localdate(), status='active')
        self.face = {'name': 'AI001', 'confidence': 90., 'bbox': [10, 10, 100, 100],
                     'quality': {'ok': True, 'code': 'OK', 'message': 'Accepted'}}
        self.frame_number = 0

    def scan(self, faces=None, device='TEST', frame=None):
        self.frame_number += 1
        image = np.full((120, 120, 3), self.frame_number if frame is None else frame, np.uint8)
        encoded = base64.b64encode(cv2.imencode('.jpg', image)[1]).decode()
        with patch('portal.face_recognition.recognize_frame', return_value=[self.face] if faces is None else faces):
            return self.client.post('/api/recognize-face/', json.dumps({
                'image': encoded, 'session_id': self.session.pk, 'device_id': device,
            }), content_type='application/json', HTTP_X_KIOSK_KEY='development-kiosk-key-change-before-deployment')

    def test_three_frames_required_then_duplicate_keeps_first_check_in(self):
        first = self.scan()
        self.assertEqual(first.status_code, 200)
        self.assertFalse(AttendanceRecord.objects.exists())
        self.assertEqual(first.json()['data']['recognized'][0]['status'], 'verifying')
        self.scan()
        self.assertFalse(AttendanceRecord.objects.exists())
        confirmed = self.scan()
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        self.assertTrue(confirmed.json()['attendance']['attendance_id'])
        record = AttendanceRecord.objects.get()
        duplicate = self.scan()
        self.assertTrue(duplicate.json()['attendance']['already_checked_in'])
        self.assertEqual(AttendanceRecord.objects.get().time_in, record.time_in)

    def test_multiple_faces_never_write_attendance(self):
        response = self.scan([self.face, self.face])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_same_image_replay_does_not_confirm(self):
        for _ in range(5):
            self.scan(frame=77)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_devices_cannot_combine_confirmation_frames(self):
        self.scan(device='A')
        self.scan(device='A')
        self.scan(device='B')
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_empty_frame_resets_confirmation(self):
        self.scan(); self.scan(); self.scan([]); self.scan()
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_expired_window_starts_over(self):
        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now):
            self.scan(); self.scan()
        with patch('django.utils.timezone.now', return_value=now + dt.timedelta(seconds=11)):
            self.scan()
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_wrong_class_does_not_write(self):
        self.session.schedule.classroom.students.clear()
        for _ in range(3):
            response = self.scan()
        self.assertEqual(response.json()['data']['recognized'][0]['status'], 'wrong_class')
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_old_active_session_is_rejected(self):
        self.session.date -= dt.timedelta(days=1)
        self.session.save()
        self.assertEqual(self.scan().status_code, 409)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_non_object_json_returns_validation_error(self):
        response = self.client.post('/api/recognize-face/', '[]', content_type='application/json',
                                   HTTP_X_KIOSK_KEY='development-kiosk-key-change-before-deployment')
        self.assertEqual(response.status_code, 400)

    def test_identity_switch_restarts_confirmation(self):
        other = Student.objects.create(student_id='AI002', full_name='Other Student')
        self.session.schedule.classroom.students.add(other)
        self.scan(); self.scan()
        self.face = {**self.face, 'name': 'AI002'}
        response = self.scan()
        self.assertFalse(AttendanceRecord.objects.exists())
        self.assertEqual(response.json()['data']['recognized'][0]['verification']['hits'], 1)

    @override_settings(FACE_CONFIRMATION_MIN_INTERVAL_SECONDS=0.4)
    def test_burst_requests_do_not_satisfy_confirmation(self):
        with patch('django.utils.timezone.now', return_value=timezone.now()):
            for _ in range(5):
                self.scan()
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_kiosk_cannot_bypass_confirmation_through_manual_endpoints(self):
        for url in ('/api/record-attendance/', '/api/session/record/', '/api/test-image/'):
            response = self.client.post(url, '{}', content_type='application/json',
                                        HTTP_X_KIOSK_KEY='development-kiosk-key-change-before-deployment')
            self.assertEqual(response.status_code, 403)

    def test_allocating_ids_without_inserting_cannot_collide(self):
        from .attendance_service import next_attendance_id
        self.assertNotEqual(next_attendance_id(self.session.date), next_attendance_id(self.session.date))

    def test_first_confirmed_frame_time_prevents_verification_delay_penalty(self):
        start = timezone.make_aware(dt.datetime.combine(self.session.date, dt.time(7, 15, 59)))
        for seconds in (0, 1, 3):
            with patch('django.utils.timezone.now', return_value=start + dt.timedelta(seconds=seconds)):
                self.scan()
        record = AttendanceRecord.objects.get()
        self.assertEqual(record.time_in, dt.time(7, 15, 59))
        self.assertEqual(record.attendance_code, 'LATE_LEVEL_1')
