import datetime as dt
from django.contrib.auth.models import User
from django.test import TestCase
from .models import AcademicTerm, AttendanceRecord, AttendanceSession, ClassRoom, Schedule, Student, Subject
from .student_attendance import student_course_attendance

class StudentAbsenceQuotaTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(student_id='QUOTA01', full_name='Quota Student')
        self.room = ClassRoom.objects.create(class_id='QUOTA', name='Quota')
        self.room.students.add(self.student)
        self.term = AcademicTerm.objects.create(code='2026-1', name='HK1 2026', starts_on=dt.date(2026,8,1), ends_on=dt.date(2026,12,31))
        self.subject = Subject.objects.create(code='Q101', name='Quota course')
        self.schedule = Schedule.objects.create(subject=self.subject,classroom=self.room,semester=self.term,day_of_week=0,start_period=1,end_period=3)

    def absence(self, n, schedule=None, status='completed', attendance='absent'):
        session=AttendanceSession.objects.create(schedule=schedule or self.schedule,date=dt.date(2026,9,n),status=status)
        return AttendanceRecord.objects.create(student=self.student,session=session,date=session.date,status=attendance,attendance_code='ABSENT',attendance_periods=3)

    def course(self):
        result=student_course_attendance(self.student, dt.date(2026,9,18))
        return next(c for c in result['courses'] if c['semester']=='2026-1')

    def test_each_absent_session_uses_one_allowance_not_three_periods(self):
        self.assertEqual(self.course()['remaining_absences'],3)
        self.absence(1)
        self.assertEqual(self.course()['remaining_absences'],2)
        self.absence(2)
        self.assertEqual(self.course()['remaining_absences'],1)
        self.absence(3)
        course=self.course()
        self.assertEqual(course['remaining_absences'],0)
        self.assertEqual(course['attendance_outcome'],'warning')
        self.assertFalse(course['exam_prohibited'])
        self.assertEqual(len(student_course_attendance(self.student, dt.date(2026,9,18))['notifications']),1)
        self.absence(4)
        course=self.course()
        self.assertEqual(course['attendance_outcome'],'failed')
        self.assertTrue(course['exam_prohibited'])
        self.assertEqual(course['remaining_absences'],0)

    def test_correction_restores_allowance_and_removes_warning(self):
        rows=[self.absence(n) for n in range(1,5)]
        for row in rows[:2]:
            row.status='present'; row.save()
        self.assertEqual(self.course()['remaining_absences'],1)
        self.assertEqual(self.course()['attendance_outcome'],'eligible')
        self.assertEqual(student_course_attendance(self.student,dt.date(2026,9,18))['notifications'],[])

    def test_unfinished_cancelled_postponed_and_late_do_not_consume_allowance(self):
        for n,status in enumerate(['scheduled','active','cancelled','postponed'],1):
            self.absence(n,status=status)
        self.absence(5,attendance='late')
        self.assertEqual(self.course()['remaining_absences'],3)

    def test_same_subject_in_other_term_is_separate(self):
        other=AcademicTerm.objects.create(code='2025-2',name='Old term',starts_on=dt.date(2025,1,1),ends_on=dt.date(2025,6,30))
        schedule=Schedule.objects.create(subject=self.subject,classroom=self.room,semester=other,day_of_week=0,start_period=1,end_period=3,is_active=False)
        for n in range(1,5): self.absence(n,schedule=schedule)
        self.assertEqual(self.course()['remaining_absences'],3)
        self.assertEqual(student_course_attendance(self.student,dt.date(2026,9,18))['selected_semester'],'2026-1')

    def test_student_cannot_see_another_students_course(self):
        outsider=Student.objects.create(student_id='OTHER',full_name='Other')
        self.assertEqual(student_course_attendance(outsider,dt.date(2026,9,18))['courses'],[])

    def test_dashboard_and_summary_use_the_same_rule(self):
        user=User.objects.create_user('quota-user')
        self.student.user=user; self.student.save()
        self.client.force_login(user)
        for n in range(1,5): self.absence(n)
        payload=self.client.get('/api/student/me/dashboard/').json()['data']
        self.assertEqual(payload['course_attendance'][0]['attendance_outcome'],'failed')
        self.assertEqual(payload['subjects'][0]['attendance_outcome'],'failed')
        summary=self.client.get('/api/student/me/subjects/summary/').json()['data']
        self.assertEqual(summary[0]['attendance_outcome'],'failed')

    def test_unassigned_history_does_not_fail_a_student_across_unknown_terms(self):
        self.schedule.semester = None
        self.schedule.save()
        for n in range(1,5): self.absence(n)
        result = student_course_attendance(self.student, dt.date(2026,9,18))
        self.assertEqual(result['courses'][0]['attendance_outcome'], 'unassigned')
        self.assertIsNone(result['courses'][0]['remaining_absences'])
        self.assertEqual(result['notifications'], [])

    def test_finalizing_fourth_missed_class_automatically_fails_course(self):
        for n in range(1,4): self.absence(n)
        session = AttendanceSession.objects.create(schedule=self.schedule, date=dt.date(2026,9,4), status='active')
        staff = User.objects.create_user('quota-staff', is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(f'/api/session/{session.pk}/finalize/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.course()['attendance_outcome'], 'failed')
        self.client.post(f'/api/session/{session.pk}/finalize/')
        self.assertEqual(self.course()['absent_sessions'], 4)

    def test_cannot_finalize_cancelled_session_to_consume_allowance(self):
        session = AttendanceSession.objects.create(schedule=self.schedule, date=dt.date(2026,9,4), status='cancelled')
        staff = User.objects.create_user('quota-staff', is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(f'/api/session/{session.pk}/finalize/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.course()['absent_sessions'], 0)
