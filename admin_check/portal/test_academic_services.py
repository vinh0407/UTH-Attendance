import datetime as dt
import json
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone
from .models import (AcademicTerm, AcademicPolicy, StudentAcademicProfile, TermAssessment,
    CourseOffering, CourseRegistration, Student, Subject, Schedule, ClassRoom, Grade,
    AttendanceSession, AttendanceRecord)
from .academic_services import register_course, cancel_registration, academic_review
from .enrollment import student_schedules, session_students

class AcademicServicesTests(TestCase):
    def setUp(self):
        self.today=timezone.localdate()
        self.term=AcademicTerm.objects.create(code='TEST',name='Test term',starts_on=self.today-dt.timedelta(days=30),ends_on=self.today+dt.timedelta(days=120))
        self.user=User.objects.create_user('academic-student')
        self.student=Student.objects.create(user=self.user,student_id='ACA01',full_name='Student One',class_name='HOME')
        self.room=ClassRoom.objects.create(class_id='HOME',name='Home class')
        self.room.students.add(self.student)
        self.other=Student.objects.create(student_id='ACA02',full_name='Classmate',email='private@example.test')
        self.room.students.add(self.other)
        self.subject=Subject.objects.create(code='NEW101',name='New course',credits=3,teacher='Teacher',teacher_email='teacher@example.test',teacher_phone='0000000000')
        self.section=ClassRoom.objects.create(class_id='SECTION',name='Course section')
        self.schedule=Schedule.objects.create(subject=self.subject,classroom=self.section,semester=self.term,day_of_week=5,start_period=1,end_period=3)
        self.offering=CourseOffering.objects.create(schedule=self.schedule,capacity=1,opens_on=self.today-dt.timedelta(days=1),closes_on=self.today+dt.timedelta(days=10))
        self.client.force_login(self.user)
        self.policy=AcademicPolicy.objects.create(name='Demo criteria',is_demo=True,min_scholarship_average=8,min_scholarship_credits=3,min_conduct_score=80,graduation_credits=3,min_graduation_average=5)
        self.profile=StudentAcademicProfile.objects.create(student=self.student,policy=self.policy,english_certified=True,physical_education_completed=True,defense_completed=True,financial_clearance=True)
        TermAssessment.objects.create(student=self.student,semester=self.term,conduct_score=90)

    def test_register_persists_updates_schedule_and_attendance_roster(self):
        registration=register_course(self.student,self.offering.pk)
        self.assertEqual(registration.status,'registered')
        self.assertIn(self.schedule,list(student_schedules(self.student)))
        session=AttendanceSession.objects.create(schedule=self.schedule,date=self.today)
        self.assertTrue(session_students(session).filter(pk=self.student.pk).exists())
        self.assertFalse(self.section.students.filter(pk=self.student.pk).exists())
        self.assertEqual(register_course(self.student,self.offering.pk).pk,registration.pk)
        with self.assertRaisesMessage(ValueError,'hết chỗ'): register_course(self.other,self.offering.pk)

    def test_cancel_releases_seat_and_cannot_cancel_another_students_registration(self):
        registration=register_course(self.student,self.offering.pk)
        with self.assertRaises(ValueError): cancel_registration(self.other,registration.pk)
        cancel_registration(self.student,registration.pk)
        self.assertFalse(student_schedules(self.student).filter(pk=self.schedule.pk).exists())
        self.assertEqual(register_course(self.other,self.offering.pk).status,'registered')

    def test_deadline_conflict_and_prerequisites_enforced(self):
        self.offering.closes_on=self.today-dt.timedelta(days=1);self.offering.save()
        with self.assertRaisesMessage(ValueError,'thời gian'):register_course(self.student,self.offering.pk)
        self.offering.closes_on=self.today+dt.timedelta(days=1);self.offering.save()
        pre=Subject.objects.create(code='PRE',name='Prerequisite')
        self.offering.prerequisites.add(pre)
        with self.assertRaisesMessage(ValueError,'tiên quyết'):register_course(self.student,self.offering.pk)
        Grade.objects.create(student=self.student,subject=pre,semester='OLD',assessment_type='TOTAL',score=8)
        Schedule.objects.create(subject=pre,classroom=self.room,semester=self.term,day_of_week=5,start_period=3,end_period=5)
        with self.assertRaisesMessage(ValueError,'trùng lịch'):register_course(self.student,self.offering.pk)

    def test_cannot_cancel_after_attendance_exists(self):
        registration=register_course(self.student,self.offering.pk)
        session=AttendanceSession.objects.create(schedule=self.schedule,date=self.today,status='completed')
        AttendanceRecord.objects.create(student=self.student,session=session,date=self.today,status='present')
        with self.assertRaisesMessage(ValueError,'điểm danh'):cancel_registration(self.student,registration.pk)

    def test_directory_does_not_expose_contact_grades_or_unrelated_class(self):
        result=self.client.get('/api/student/me/classmates/',{'class_id':self.room.pk})
        self.assertEqual(result.status_code,200)
        rows=result.json()['data']['students']
        self.assertEqual(len(rows),2)
        self.assertEqual(set(rows[0]),{'student_id','full_name','class_name'})
        self.assertEqual(self.client.get('/api/student/me/classmates/',{'class_id':self.section.pk}).status_code,403)
        self.assertEqual(Client().get('/api/student/me/academics/').status_code,401)

    def test_review_uses_final_weighted_grades_and_marks_missing_information(self):
        register_course(self.student,self.offering.pk)
        Grade.objects.create(student=self.student,subject=self.subject,semester=self.term.code,assessment_type='MIDTERM',score=10)
        result=academic_review(self.student,self.term.code)
        self.assertEqual(result['scholarship']['status'],'incomplete')
        Grade.objects.create(student=self.student,subject=self.subject,semester=self.term.code,assessment_type='TOTAL',score=9)
        result=academic_review(self.student,self.term.code)
        self.assertEqual(result['scholarship']['status'],'eligible')
        self.assertEqual(result['graduation']['status'],'eligible')
        self.assertTrue(result['policy']['is_demo'])
        self.profile.english_certified=None;self.profile.save()
        self.assertEqual(academic_review(self.student,self.term.code)['graduation']['status'],'incomplete')

    def test_absence_failure_prevents_credit_and_scholarship(self):
        register_course(self.student,self.offering.pk)
        Grade.objects.create(student=self.student,subject=self.subject,semester=self.term.code,assessment_type='TOTAL',score=9)
        for i in range(4):
            day=self.today-dt.timedelta(days=i+1)
            session=AttendanceSession.objects.create(schedule=self.schedule,date=day,status='completed')
            AttendanceRecord.objects.create(student=self.student,session=session,date=day,status='absent')
        result=academic_review(self.student,self.term.code)
        self.assertEqual(result['scholarship']['status'],'not_eligible')
        self.assertEqual(result['graduation']['earned_credits'],0)

    def test_no_policy_is_not_an_automatic_approval(self):
        result=academic_review(self.other,self.term.code)
        self.assertEqual(result['scholarship']['status'],'unconfigured')
        self.assertEqual(result['graduation']['status'],'unconfigured')

    def test_registration_api_rejects_spoofed_student_identity(self):
        response=self.client.post('/api/student/me/registrations/',data=json.dumps({'offering_id':self.offering.pk,'student_id':self.other.pk}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        self.assertTrue(CourseRegistration.objects.filter(student=self.student,offering=self.offering).exists())
        self.assertFalse(CourseRegistration.objects.filter(student=self.other).exists())
        payload=self.client.get('/api/student/me/academics/').json()['data']
        self.assertEqual(payload['enrolled_credits_by_semester'][self.term.code],3)

    def test_weighted_average_and_retakes_never_duplicate_earned_credits(self):
        register_course(self.student,self.offering.pk)
        Grade.objects.create(student=self.student,subject=self.subject,semester=self.term.code,assessment_type='TOTAL',score=9)
        Grade.objects.create(student=self.student,subject=self.subject,semester='OLD',assessment_type='TOTAL',score=6)
        small=Subject.objects.create(code='ONE',name='One credit',credits=1)
        Grade.objects.create(student=self.student,subject=small,semester=self.term.code,assessment_type='TOTAL',score=5)
        result=academic_review(self.student,self.term.code)
        self.assertEqual(result['scholarship']['average'],8)
        self.assertEqual(result['graduation']['average'],8)
        self.assertEqual(result['graduation']['earned_credits'],4)

    def test_credit_limit_and_duplicate_subject_section(self):
        self.policy.max_term_credits=2;self.policy.save()
        with self.assertRaisesMessage(ValueError,'tín chỉ'):register_course(self.student,self.offering.pk)
        self.policy.max_term_credits=24;self.policy.save()
        Schedule.objects.create(subject=self.subject,classroom=self.room,semester=self.term,day_of_week=1,start_period=1,end_period=3)
        with self.assertRaisesMessage(ValueError,'môn này'):register_course(self.student,self.offering.pk)

    def test_registration_requires_csrf_and_cancelled_students_lose_directory_access(self):
        protected=Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        response=protected.post('/api/student/me/registrations/',data=json.dumps({'offering_id':self.offering.pk}),content_type='application/json')
        self.assertEqual(response.status_code,403)
        registration=register_course(self.student,self.offering.pk)
        self.assertEqual(self.client.get('/api/student/me/classmates/',{'class_id':self.section.pk}).status_code,200)
        cancel_registration(self.student,registration.pk)
        self.assertEqual(self.client.get('/api/student/me/classmates/',{'class_id':self.section.pk}).status_code,403)
