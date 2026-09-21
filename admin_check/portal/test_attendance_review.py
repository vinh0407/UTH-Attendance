import csv
import datetime as dt
import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import AttendanceRecord, AttendanceSession, ClassRoom, Schedule, Student, Subject


class AttendanceReviewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('reviewer', is_staff=True)
        self.student = Student.objects.create(student_id='REVIEW1', full_name='Review Student')
        classroom = ClassRoom.objects.create(class_id='REVIEW', name='Review Class')
        classroom.students.add(self.student)
        subject = Subject.objects.create(code='RV', name='Review Subject')
        schedule = Schedule.objects.create(subject=subject, classroom=classroom,
                                          day_of_week=0, start_period=1, end_period=3)
        self.session = AttendanceSession.objects.create(schedule=schedule, date=timezone.localdate(), status='completed')
        self.url = f'/api/session/{self.session.pk}/review/{self.student.pk}/'
        self.client.force_login(self.staff)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        override = override_settings(ATTENDANCE_HISTORY_DIR=self.root)
        override.enable()
        self.addCleanup(override.disable)

    def change(self, **overrides):
        data = {'outcome': 'checked_in', 'check_in_time': '07:20', 'reason': 'Camera unavailable'}
        data.update(overrides)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, json.dumps(data), content_type='application/json')

    def test_manual_recovery_uses_timing_and_records_actor_and_reason(self):
        response = self.change()
        self.assertEqual(response.status_code, 200)
        record = AttendanceRecord.objects.get()
        self.assertEqual(record.attendance_code, 'LATE_ONE_PERIOD')
        self.assertEqual(record.attendance_periods, 1)
        self.assertEqual(record.method, 'MANUAL_REVIEW')
        audit = record.audit_logs.get()
        self.assertEqual(audit.changed_by, self.staff)
        self.assertEqual(audit.reason, 'Camera unavailable')
        self.assertEqual(audit.before, {})
        self.assertEqual(audit.after['attendance_code'], 'LATE_ONE_PERIOD')

    def test_correction_updates_existing_csv_and_keeps_audit_history(self):
        self.assertEqual(self.change().status_code, 200)
        self.assertEqual(self.change(outcome='absent', check_in_time='', reason='Wrong student selected').status_code, 200)
        record = AttendanceRecord.objects.get()
        self.assertEqual(record.attendance_code, 'ABSENT')
        self.assertIsNone(record.time_in)
        self.assertEqual(record.attendance_periods, 3)
        self.assertEqual(record.audit_logs.count(), 2)
        archive = next(self.root.rglob('attendance.csv'))
        with archive.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'ABSENT')

    def test_requires_nonempty_reason_and_valid_time(self):
        self.assertEqual(self.change(reason='  ').status_code, 400)
        self.assertEqual(self.change(check_in_time='bad').status_code, 400)
        self.assertEqual(self.change(check_in_time='07:00+07:00').status_code, 400)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_kiosk_and_students_cannot_edit(self):
        self.client.logout()
        self.assertEqual(self.change().status_code, 403)
        user = User.objects.create_user('student')
        self.client.force_login(user)
        self.assertEqual(self.change().status_code, 403)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_student_must_belong_to_session(self):
        self.session.schedule.classroom.students.clear()
        self.assertEqual(self.change().status_code, 404)

    def test_csrf_is_enforced_for_corrections(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.staff)
        self.assertEqual(self.change().status_code, 403)

    def test_report_includes_actual_audit_and_similarity(self):
        self.assertEqual(self.change().status_code, 200)
        report = self.client.get(f'/api/session/{self.session.pk}/review/').json()['data']
        self.assertEqual(report['summary']['checked_in'], 1)
        self.assertEqual(report['students'][0]['audit'][0]['reason'], 'Camera unavailable')
        self.assertIsNone(report['students'][0]['similarity'])

    def test_registration_returns_quality_failure_reason(self):
        from unittest.mock import patch
        import base64
        import cv2
        import numpy as np
        encoded = base64.b64encode(cv2.imencode('.png', np.zeros((80, 80, 3), np.uint8))[1]).decode()
        with patch('portal.face_recognition.face_engine_status', return_value={'available': True}), patch(
                'portal.face_recognition.register_face', return_value=(False, 'Keep exactly one face in each registration image.')):
            response = self.client.post('/api/register-face/', json.dumps({
                'student_id': 'NEW', 'name': 'New', 'images': [encoded],
            }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('one face', response.json()['error'])
        self.assertFalse(Student.objects.filter(student_id='NEW').exists())
