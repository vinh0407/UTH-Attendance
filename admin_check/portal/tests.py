import datetime
import csv
import io
import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase, override_settings

from .attendance_service import calculate_attendance_status, finalize_session_attendance, record_attendance_event
from .attendance_import import import_csv_bytes
from .attendance_archive import archive_attendance_record
from .models import AcademicTerm, AttendanceRecord, AttendanceSession, ClassRoom, Grade, GradeAuditLog, LeaveRequest, Schedule, Student, Subject
from .student_attendance import student_course_attendance


class AttendanceTimingTests(SimpleTestCase):
    def test_spec_boundaries(self):
        scheduled = datetime.time(7, 30)
        cases = [
            ('07:29:00', 'ON_TIME'),
            ('07:30:00', 'ON_TIME'),
            ('07:31:00', 'LATE_LEVEL_1'),
            ('07:45:00', 'LATE_LEVEL_1'),
            ('07:45:59', 'LATE_LEVEL_1'),
            ('07:46:00', 'LATE_ONE_PERIOD'),
            ('08:29:00', 'LATE_ONE_PERIOD'),
            ('08:30:00', 'ABSENT_TWO_PERIODS'),
            ('09:30:00', 'ABSENT_TWO_PERIODS'),
            ('09:31:00', 'ABSENT'),
        ]
        for check_in, expected_code in cases:
            with self.subTest(check_in=check_in):
                result = calculate_attendance_status(scheduled, datetime.time.fromisoformat(check_in))
                self.assertEqual(result['attendance_code'], expected_code)


class AttendanceCsvIntegrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('audit-admin', is_staff=True, is_superuser=True)
        self.student = Student.objects.create(student_id='2251129999', full_name='CSV Student')
        classroom = ClassRoom.objects.create(class_id='CSV01', name='CSV Class')
        classroom.students.add(self.student)
        subject = Subject.objects.create(code='CSV101', name='CSV Integration')
        schedule = Schedule.objects.create(
            subject=subject,
            classroom=classroom,
            day_of_week=2,
            start_period=1,
            end_period=2,
            room='A203',
        )
        self.session = AttendanceSession.objects.create(
            schedule=schedule,
            external_session_id='SES-CSV-001',
            date=datetime.date(2026, 8, 26),
            status='completed',
        )

    def test_import_uses_shared_record_and_is_idempotent(self):
        csv_text = (
            'attendance_id,session_id,student_id,student_name,class_id,subject_id,subject_name,date,'
            'scheduled_time,check_in_time,late_minutes,status,attendance_code,attendance_label,'
            'attendance_periods,method,device_id\n'
            'ATT-20260826-9001,SES-CSV-001,2251129999,CSV Student,CSV01,CSV101,CSV Integration,'
            '2026-08-26,07:00:00,07:05:00,5,late,LATE_LEVEL_1,"TRỄ — LEVEL 1",0,'
            'FACIAL_RECOGNITION,KIOSK-A203\n'
        ).encode('utf-8')
        first = import_csv_bytes(csv_text, source='test.csv')
        second = import_csv_bytes(csv_text, source='test.csv')
        self.assertEqual(first.imported, 1)
        self.assertEqual(first.failed, [])
        self.assertEqual(second.duplicates, 1)
        record = self.student.attendance_records.get(session=self.session)
        self.assertEqual(record.attendance_id, 'ATT-20260826-9001')
        self.assertEqual(record.attendance_code, 'LATE_LEVEL_1')
        self.assertEqual(record.device_id, 'KIOSK-A203')

    def test_import_accepts_kiosk_uppercase_status_values(self):
        csv_text = (
            'attendance_id,session_id,student_id,student_name,subject_id,subject_name,date,'
            'scheduled_time,check_in_time,late_minutes,status,attendance_periods,method,device_id\n'
            'ATT-20260826-9002,SES-CSV-001,2251129999,CSV Student,CSV101,CSV Integration,'
            '2026-08-26,07:00:00,07:05:00,5,LATE_LEVEL_1,0,FACIAL_RECOGNITION,KIOSK-A203\n'
        ).encode('utf-8')
        result = import_csv_bytes(csv_text, source='kiosk.csv')
        self.assertEqual(result.imported, 1)

    def test_admin_can_create_class_and_postpone_session(self):
        client = Client(); client.force_login(self.admin)
        response = client.post('/api/classes/create/', data=json.dumps({
            'class_id': 'NEW01', 'name': 'New class', 'department': 'IT',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        response = client.post(
            f'/api/session/{self.session.id}/postpone/',
            data=json.dumps({'postponed_to': '2026-08-30', 'reason': 'Room maintenance'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'postponed')
        self.assertEqual(self.session.postponed_to, datetime.date(2026, 8, 30))
        self.assertTrue(AttendanceSession.objects.filter(schedule=self.session.schedule, date=datetime.date(2026, 8, 30), status='scheduled').exists())

    def test_admin_can_create_subject_and_assign_it_to_class(self):
        client = Client(); client.force_login(self.admin)
        response = client.post('/api/subjects/create/', data=json.dumps({
            'code': 'NEW101', 'name': 'New subject', 'teacher': 'Lecturer', 'credits': 3,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        subject_id = response.json()['data']['id']
        response = client.post('/api/schedules/create/', data=json.dumps({
            'subject_id': subject_id, 'classroom_id': self.session.schedule.classroom_id,
            'day_of_week': 4, 'start_period': 3, 'end_period': 4, 'room': 'B204',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Schedule.objects.filter(subject_id=subject_id, classroom_id=self.session.schedule.classroom_id).exists())

    def test_export_all_csv_has_consistent_rows(self):
        client = Client(); client.force_login(self.admin)
        response = client.get('/api/export/all.csv')
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(all(len(row) == len(rows[0]) for row in rows))

    def test_finalize_creates_absent_record_and_archives_csv(self):
        missing = Student.objects.create(student_id='2251128888', full_name='Missing Student')
        self.session.schedule.classroom.students.add(missing)
        self.session.status = 'active'
        self.session.save(update_fields=['status'])
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(ATTENDANCE_HISTORY_DIR=Path(temp_dir)):
            with self.captureOnCommitCallbacks(execute=True):
                created = finalize_session_attendance(self.session)
            self.assertEqual(created, 2)
            record = AttendanceRecord.objects.get(session=self.session, student=missing)
            self.assertEqual(record.status, 'absent')
            self.assertEqual(record.attendance_periods, 2)
            path = Path(temp_dir) / '26_08_2026' / 'CSV Integration' / 'attendance.csv'
            self.assertTrue(path.exists())
            self.assertIn('Missing Student', path.read_text(encoding='utf-8-sig'))

    def test_student_grades_and_subject_summary_are_scoped(self):
        user = User.objects.create_user('grade-user')
        self.student.user = user
        self.student.save(update_fields=['user'])
        Grade.objects.create(student=self.student, subject=self.session.schedule.subject, semester='2026-1', score='8.50')
        client = Client()
        client.force_login(user)
        grades = client.get('/api/student/me/grades/')
        summary = client.get('/api/student/me/subjects/summary/')
        self.assertEqual(grades.status_code, 200)
        self.assertEqual(grades.json()['data'][0]['score'], 8.5)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['data'][0]['subject_id'], 'CSV101')


class StudentPortalIdentityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('portal-admin', is_staff=True, is_superuser=True)
        self.student = Student.objects.create(
            student_id='2251120064',
            full_name='Portal Student',
            class_name='CN22A',
            email='student@uth.edu.vn',
        )
        self.other_student = Student.objects.create(
            student_id='2251120065',
            full_name='Other Student',
            class_name='CN22B',
        )
        self.classroom = ClassRoom.objects.create(class_id='CN22A', name='Mathematics')
        self.classroom.students.add(self.student)
        self.subject = Subject.objects.create(code='MATH101', name='Mathematics I')
        self.schedule = Schedule.objects.create(
            subject=self.subject,
            classroom=self.classroom,
            day_of_week=0,
            start_period=1,
            end_period=2,
            room='A101',
        )
        self.session = AttendanceSession.objects.create(
            schedule=self.schedule,
            external_session_id='SES-PORTAL-001',
            date=datetime.date(2026, 8, 24),
            status='completed',
        )
        AttendanceRecord.objects.create(
            attendance_id='ATT-PORTAL-001',
            session=self.session,
            student=self.student,
            date=self.session.date,
            status='present',
            attendance_code='ON_TIME',
            attendance_label='ON TIME',
        )
        AttendanceRecord.objects.create(
            attendance_id='ATT-PORTAL-002',
            session=self.session,
            student=self.other_student,
            date=self.session.date,
            status='absent',
            attendance_code='ABSENT',
            attendance_label='ABSENT',
        )

    def _login(self, client, class_name='CN22A'):
        return client.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'class_name': class_name,
        }), content_type='application/json')

    def test_student_can_sign_in_with_registered_id_and_class(self):
        client = Client()
        response = self._login(client, class_name='Mathematics')
        self.assertEqual(response.status_code, 200)
        dashboard = client.get('/api/student/me/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        data = dashboard.json()['data']
        self.assertEqual(data['profile']['student_id'], self.student.student_id)
        self.assertEqual(len(data['attendance']), 1)
        self.assertEqual(data['attendance'][0]['attendance_id'], 'ATT-PORTAL-001')
        self.assertEqual(data['schedule'][0]['subject_id'], 'MATH101')

    def test_wrong_class_returns_generic_error(self):
        client = Client()
        response = self._login(client, class_name='CN22B')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()['error'],
            'Student ID or class does not match an admin-registered student.',
        )
        self.assertEqual(client.get('/api/student/me/dashboard/').status_code, 401)

    def test_portal_identity_coexists_with_admin_session_and_logout(self):
        client = Client()
        client.force_login(self.admin)
        self.assertEqual(self._login(client).status_code, 200)
        self.assertEqual(client.get('/api/student/me/profile/').status_code, 200)
        self.assertEqual(client.post('/api/student/logout/', data='{}', content_type='application/json').status_code, 200)
        self.assertEqual(client.get('/api/student/me/profile/').status_code, 401)
        self.assertEqual(client.get('/admin-dashboard/').status_code, 200)


class StudentGradeComponentTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            student_id='2251128888',
            full_name='Grade Test Student',
            class_name='CN22A',
        )
        self.subject = Subject.objects.create(
            code='AND304',
            name='Lập trình Android',
            credits=3,
            weight_cc=0.10,
            weight_gk=0.30,
            weight_ck=0.60,
            bonus_method='DIRECT',
        )

    def test_grouped_grades_calculation_with_bonus(self):
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='ATTENDANCE', score='8.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='MIDTERM', score='7.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='FINAL', score='8.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='BONUS', score='0.50')

        client = Client()
        client.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'class_name': 'CN22A',
        }), content_type='application/json')

        response = client.get('/api/student/me/dashboard/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertIn('grouped_grades', data)
        group = next((g for g in data['grouped_grades'] if g['subject_id'] == 'AND304'), None)
        self.assertIsNotNone(group)
        self.assertEqual(group['cc'], 8.0)
        self.assertEqual(group['gk'], 7.0)
        self.assertEqual(group['ck'], 8.0)
        self.assertEqual(group['bonus'], 0.5)
        # 8*0.1 + 7*0.3 + 8*0.6 + 0.5 = 0.8 + 2.1 + 4.8 + 0.5 = 8.20
        self.assertEqual(group['calculated_total'], 8.20)

    def test_missing_component_grade_returns_none_for_missing_slot(self):
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='ATTENDANCE', score='9.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='MIDTERM', score='8.50')

        client = Client()
        client.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'class_name': 'CN22A',
        }), content_type='application/json')

        response = client.get('/api/student/me/dashboard/')
        self.assertEqual(response.status_code, 200)
        group = next((g for g in response.json()['data']['grouped_grades'] if g['subject_id'] == 'AND304'), None)
        self.assertIsNotNone(group)
        self.assertEqual(group['cc'], 9.0)
        self.assertEqual(group['gk'], 8.5)
        self.assertIsNone(group['ck'])
        self.assertIsNone(group['bonus'])

    def test_scale_4_and_letter_grade_conversion(self):
        # 8*0.1 + 7*0.3 + 8*0.6 + 0.5 = 8.20 -> B+ (3.5)
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='ATTENDANCE', score='8.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='MIDTERM', score='7.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='FINAL', score='8.00')
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='BONUS', score='0.50')

        client = Client()
        client.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'class_name': 'CN22A',
        }), content_type='application/json')

        response = client.get('/api/student/me/dashboard/')
        self.assertEqual(response.status_code, 200)
        group = next((g for g in response.json()['data']['grouped_grades'] if g['subject_id'] == 'AND304'), None)
        self.assertIsNotNone(group)
        self.assertEqual(group['letter_grade'], 'B+')
        self.assertEqual(group['gpa_scale_4'], 3.5)
        self.assertIn(group['rank'], ['Good', 'Khá giỏi'])
        self.assertEqual(response.json()['data']['cumulative_gpa_4'], 3.5)
        self.assertIn(response.json()['data']['academic_rank'], ['Very Good', 'Giỏi'])

    def test_student_password_login_and_change_password(self):
        client = Client()
        # Initial login using class_name fallback
        login_res = client.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'password': 'CN22A',
        }), content_type='application/json')
        self.assertEqual(login_res.status_code, 200)

        # Change password
        change_res = client.post('/api/student/me/change-password/', data=json.dumps({
            'old_password': 'CN22A',
            'new_password': 'securepassword123',
        }), content_type='application/json')
        self.assertEqual(change_res.status_code, 200)

        # Old password fails
        client2 = Client()
        fail_res = client2.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'password': 'CN22A',
        }), content_type='application/json')
        self.assertEqual(fail_res.status_code, 401)
        self.assertEqual(fail_res.json()['error'], 'Student ID or class does not match an admin-registered student.')

        # New password succeeds
        success_res = client2.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'password': 'securepassword123',
        }), content_type='application/json')
        self.assertEqual(success_res.status_code, 200)

    def test_admin_grade_update_creates_audit_log(self):
        admin_user = User.objects.create_user('grade_admin', is_staff=True)
        client = Client()
        client.force_login(admin_user)

        # Initial grade
        Grade.objects.create(student=self.student, subject=self.subject, semester='2026-1', assessment_type='FINAL', score='6.50')

        # Admin updates final score
        payload = {
            'student_id': self.student.student_id,
            'subject_id': self.subject.code,
            'semester': '2026-1',
            'assessment_type': 'FINAL',
            'score': 8.5,
            'reason': 'Chấm phúc khảo bài thi cuối kỳ'
        }
        response = client.post('/api/admin/grades/update/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        # Verify grade updated
        grade = Grade.objects.get(student=self.student, subject=self.subject, semester='2026-1', assessment_type='FINAL')
        self.assertEqual(float(grade.score), 8.5)

        # Verify audit log
        log = GradeAuditLog.objects.filter(grade=grade).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changed_by, admin_user)
        self.assertEqual(float(log.before_score), 6.5)
        self.assertEqual(float(log.after_score), 8.5)
        self.assertEqual(log.reason, 'Chấm phúc khảo bài thi cuối kỳ')

    def test_admin_dashboard_renders_with_enhanced_context(self):
        admin_user = User.objects.create_user('dash_staff', is_staff=True)
        client = Client()
        client.force_login(admin_user)

        response = client.get('/admin-dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_students', response.context)
        self.assertIn('attendance_rate', response.context)
        self.assertIn('subjects', response.context)
        self.assertIn('recent_audits', response.context)
        self.assertContains(response, 'UTH Operations')
        self.assertContains(response, 'GradeAuditLog')


class NewFeaturesIntegrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('feature_admin', is_staff=True, is_superuser=True)
        self.student = Student.objects.create(
            student_id='2251129999',
            full_name='Nguyen Van Test',
            class_name='CN22A',
        )
        self.classroom = ClassRoom.objects.create(class_id='CN22A', name='Mathematics')
        self.classroom.students.add(self.student)
        self.subject = Subject.objects.create(code='MATH101', name='Mathematics I', credits=3)
        self.term = AcademicTerm.objects.create(
            code='2026-1',
            name='Học kỳ 1 2026-2027',
            starts_on=datetime.date(2026, 8, 1),
            ends_on=datetime.date(2026, 12, 31),
        )
        self.schedule = Schedule.objects.create(
            subject=self.subject,
            classroom=self.classroom,
            semester=self.term,
            day_of_week=0,
            start_period=1,
            end_period=2,
            room='A101',
        )
        self.session = AttendanceSession.objects.create(
            schedule=self.schedule,
            external_session_id='SES-NEW-001',
            date=datetime.date(2026, 8, 24),
            status='completed',
        )
        AttendanceRecord.objects.create(
            attendance_id='ATT-NEW-001',
            session=self.session,
            student=self.student,
            date=self.session.date,
            status='present',
            attendance_code='ON_TIME',
            attendance_label='ON TIME',
        )

    def _login(self, client, class_name='CN22A'):
        return client.post('/api/student/login/', data=json.dumps({
            'student_id': self.student.student_id,
            'class_name': class_name,
        }), content_type='application/json')

    def test_student_leave_request_and_admin_approval_flow(self):
        client = Client()
        self._login(client, class_name='Mathematics')

        # Student submits leave request
        payload = {
            'date': '2026-08-24',
            'subject_id': self.subject.code,
            'reason': 'Nghỉ ốm có chỉ định bác sĩ',
            'evidence_url': 'https://example.com/giay-kham.jpg',
        }
        create_res = client.post('/api/student/me/leave-requests/create/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(create_res.status_code, 200)
        self.assertTrue(create_res.json()['success'])
        leave_id = create_res.json()['data']['id']

        # Student checks leave requests list
        list_res = client.get('/api/student/me/leave-requests/')
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(len(list_res.json()['data']), 1)
        self.assertEqual(list_res.json()['data'][0]['status'], 'pending')

        # Admin reviews and approves
        admin_client = Client()
        admin_client.force_login(self.admin)
        review_res = admin_client.post(f'/api/admin/leave-requests/{leave_id}/review/', data=json.dumps({
            'action': 'approve',
            'review_note': 'Đã duyệt đơn nghỉ bệnh hợp lệ.'
        }), content_type='application/json')
        self.assertEqual(review_res.status_code, 200)
        self.assertTrue(review_res.json()['success'])

        # Verify LeaveRequest model updated
        leave = LeaveRequest.objects.get(id=leave_id)
        self.assertEqual(leave.status, 'approved')
        self.assertEqual(leave.reviewed_by, self.admin)
        self.assertIsNotNone(leave.reviewed_at)

        # Verify AttendanceRecord updated to excused
        rec = AttendanceRecord.objects.get(student=self.student, session=self.session)
        self.assertEqual(rec.status, 'excused')
        self.assertEqual(rec.attendance_code, 'EXCUSED')

    def test_excused_absence_does_not_bar_student_from_exam(self):
        # Create completed sessions
        # 3 unexcused absences (ABSENCE_LIMIT = 3)
        sessions = []
        for i in range(1, 4):
            ses = AttendanceSession.objects.create(
                schedule=self.schedule,
                external_session_id=f'SES-ABS-{i}',
                date=datetime.date(2026, 8, 25 + i),
                status='completed',
            )
            AttendanceRecord.objects.create(
                attendance_id=f'ATT-ABS-{i}',
                session=ses,
                student=self.student,
                date=ses.date,
                status='absent',
                attendance_code='ABSENT',
            )
            sessions.append(ses)

        # 1 excused absence session
        ses_excused = AttendanceSession.objects.create(
            schedule=self.schedule,
            external_session_id='SES-EXC-1',
            date=datetime.date(2026, 8, 30),
            status='completed',
        )
        AttendanceRecord.objects.create(
            attendance_id='ATT-EXC-1',
            session=ses_excused,
            student=self.student,
            date=ses_excused.date,
            status='excused',
            attendance_code='EXCUSED',
        )

        res = student_course_attendance(self.student, datetime.date(2026, 9, 1))
        course = next(c for c in res['courses'] if c['subject_id'] == self.subject.code)
        self.assertEqual(course['absent_sessions'], 3)
        self.assertEqual(course['excused_sessions'], 1)
        # With 3 unexcused absences, still at warning, not failed (barred)
        self.assertEqual(course['attendance_outcome'], 'warning')
        self.assertEqual(course['danger_level'], 'warning')
        self.assertFalse(course['exam_prohibited'])

    def test_admin_grade_bulk_csv_import_and_template_export(self):
        admin_client = Client()
        admin_client.force_login(self.admin)

        # 1. Download CSV template
        tpl_res = admin_client.get(f'/api/admin/grades/template.csv?subject_code={self.subject.code}&semester=2026-1')
        self.assertEqual(tpl_res.status_code, 200)
        self.assertIn('attachment;', tpl_res.headers.get('Content-Disposition', ''))
        tpl_content = tpl_res.content.decode('utf-8-sig')
        self.assertIn('student_id', tpl_content)
        self.assertIn(self.student.student_id, tpl_content)

        # 2. Upload bulk grade CSV
        csv_content = (
            "student_id,full_name,class_name,subject_code,semester,cc,gk,ck,bonus,reason\n"
            f"{self.student.student_id},{self.student.full_name},CN22A,{self.subject.code},2026-1,9.0,8.5,9.5,1.0,Nhập điểm CSV\n"
        )
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        csv_file.name = 'bulk_grades.csv'
        import_res = admin_client.post('/api/admin/grades/import.csv', {'file': csv_file})
        self.assertEqual(import_res.status_code, 200)
        self.assertTrue(import_res.json()['success'])
        self.assertGreater(import_res.json()['updated_grades_count'], 0)

        # Verify Grade records
        cc = Grade.objects.get(student=self.student, subject=self.subject, semester='2026-1', assessment_type='ATTENDANCE')
        gk = Grade.objects.get(student=self.student, subject=self.subject, semester='2026-1', assessment_type='MIDTERM')
        ck = Grade.objects.get(student=self.student, subject=self.subject, semester='2026-1', assessment_type='FINAL')
        bonus = Grade.objects.get(student=self.student, subject=self.subject, semester='2026-1', assessment_type='BONUS')

        self.assertEqual(float(cc.score), 9.0)
        self.assertEqual(float(gk.score), 8.5)
        self.assertEqual(float(ck.score), 9.5)
        self.assertEqual(float(bonus.score), 1.0)

        # Verify GradeAuditLog created
        logs = GradeAuditLog.objects.filter(grade__student=self.student)
        self.assertGreaterEqual(logs.count(), 4)



