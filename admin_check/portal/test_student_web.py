import datetime as dt
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from .models import AttendanceSession, ClassRoom, Schedule, Student, Subject


class StudentWebScheduleTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('student-web')
        self.student = Student.objects.create(user=user, student_id='WEB01', full_name='Web Student')
        self.room = ClassRoom.objects.create(class_id='WEB', name='Web Class')
        self.room.students.add(self.student)
        subject = Subject.objects.create(code='WEB101', name='Web Development')
        self.schedule = Schedule.objects.create(subject=subject, classroom=self.room,
                                               day_of_week=0, start_period=1, end_period=3)
        self.client.force_login(user)

    def dashboard(self, day):
        with patch('portal.views.timezone.localdate', return_value=day):
            return self.client.get('/api/student/me/dashboard/').json()['data']

    def test_today_reports_cancellation_instead_of_regular_class(self):
        day = dt.date(2026, 9, 14)
        AttendanceSession.objects.create(schedule=self.schedule, date=day, status='cancelled')
        data = self.dashboard(day)
        self.assertEqual(data['schedule_today'][0].get('session_status'), 'cancelled')

    def test_browser_modules_have_javascript_content_type(self):
        response = self.client.get('/student-portal/portal-render.mjs')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/javascript'))
        response.close()

    def test_rescheduled_class_appears_on_its_actual_day(self):
        monday, tuesday = dt.date(2026, 9, 14), dt.date(2026, 9, 15)
        AttendanceSession.objects.create(schedule=self.schedule, date=monday, status='postponed', postponed_to=tuesday)
        AttendanceSession.objects.create(schedule=self.schedule, date=tuesday, status='scheduled')
        data = self.dashboard(tuesday)
        self.assertEqual(len(data['schedule_today']), 1)
        self.assertEqual(data['schedule_today'][0]['date'], '2026-09-15')
        self.assertEqual(len(data['schedule_week']), 2)

    def test_week_never_contains_another_students_class(self):
        other = ClassRoom.objects.create(class_id='OTHER', name='Other class')
        other_schedule = Schedule.objects.create(subject=self.schedule.subject, classroom=other,
                                                day_of_week=0, start_period=1, end_period=3)
        AttendanceSession.objects.create(schedule=other_schedule, date=dt.date(2026, 9, 14), status='active')
        data = self.dashboard(dt.date(2026, 9, 14))
        self.assertIn('schedule_week', data)
        self.assertEqual({item['class_id'] for item in data['schedule_week']}, {'WEB'})
