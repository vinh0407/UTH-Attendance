"""Extend only the labelled local demo with registration, reviews and classmates."""
import datetime as dt
from django.db import transaction
from django.utils import timezone
from portal.models import (Student, Subject, ClassRoom, Schedule, Grade, AcademicTerm,
    AcademicPolicy, StudentAcademicProfile, TermAssessment, CourseOffering)

with transaction.atomic():
    student=Student.objects.get(student_id='2251120064',full_name='Sinh viên Demo',class_name='CN22A')
    room=ClassRoom.objects.get(class_id='CN22A')
    term=AcademicTerm.objects.get(code='DEMO-2026')
    today=timezone.localdate()
    policy,_=AcademicPolicy.objects.get_or_create(name='Tiêu chí Demo · CNTT · Thang điểm 10',defaults={'is_demo':True,'min_scholarship_average':8,'min_scholarship_credits':12,'min_conduct_score':80,'graduation_credits':120,'min_graduation_average':5,'max_term_credits':24})
    StudentAcademicProfile.objects.get_or_create(student=student,defaults={'policy':policy,'english_certified':None,'physical_education_completed':True,'defense_completed':True,'financial_clearance':None})
    TermAssessment.objects.get_or_create(student=student,semester=term,defaults={'conduct_score':85})
    for i,name in enumerate(['Nguyễn An (Demo)','Trần Bình (Demo)','Lê Chi (Demo)','Phạm Duy (Demo)'],2):
        peer,_=Student.objects.get_or_create(student_id=f'DEMO-SV{i:02}',defaults={'full_name':name,'class_name':'CN22A'})
        room.students.add(peer)
    for i,(code,name,credits,day,period,teacher) in enumerate([
        ('DEMO-AND304','Lập trình Android (Demo)',3,1,1,'TS. Trần Hoàng (Demo)'),
        ('DEMO-WEB301','Thiết kế giao diện Web (Demo)',3,2,1,'ThS. Minh Hà (Demo)'),
        ('DEMO-DATA302','Phân tích dữ liệu (Demo)',3,2,6,'TS. Hoàng Nam (Demo)'),
        ('DEMO-UX303','Trải nghiệm người dùng (Demo)',3,3,1,'ThS. Thanh Mai (Demo)'),
    ],1):
        subject,_=Subject.objects.get_or_create(code=code,defaults={'name':name,'credits':credits,'teacher':teacher,'weight_cc':0.10,'weight_gk':0.30,'weight_ck':0.60,'bonus_method':'DIRECT'})
        section,_=ClassRoom.objects.get_or_create(class_id=f'DEMO-LHP{i:02}',defaults={'name':name})
        schedule,_=Schedule.objects.get_or_create(subject=subject,classroom=section,semester=term,day_of_week=(today.weekday()+day)%7,start_period=period,end_period=period+2,defaults={'room':f'B.{200+i}'})
        CourseOffering.objects.get_or_create(schedule=schedule,defaults={'capacity':35,'opens_on':today-dt.timedelta(days=7),'closes_on':today+dt.timedelta(days=14),'is_open':True})

    # Component grades for current semester
    and_subject = Subject.objects.get(code='DEMO-AND304')
    Grade.objects.get_or_create(student=student, subject=and_subject, semester=term.code, assessment_type='ATTENDANCE', defaults={'score': 8.00})
    Grade.objects.get_or_create(student=student, subject=and_subject, semester=term.code, assessment_type='MIDTERM', defaults={'score': 7.00})
    Grade.objects.get_or_create(student=student, subject=and_subject, semester=term.code, assessment_type='FINAL', defaults={'score': 8.00})
    Grade.objects.get_or_create(student=student, subject=and_subject, semester=term.code, assessment_type='BONUS', defaults={'score': 0.50})

    web_subject = Subject.objects.get(code='DEMO-WEB301')
    Grade.objects.get_or_create(student=student, subject=web_subject, semester=term.code, assessment_type='ATTENDANCE', defaults={'score': 9.00})
    Grade.objects.get_or_create(student=student, subject=web_subject, semester=term.code, assessment_type='MIDTERM', defaults={'score': 8.50})
    Grade.objects.get_or_create(student=student, subject=web_subject, semester=term.code, assessment_type='BONUS', defaults={'score': 0.50})

    previous,_=AcademicTerm.objects.get_or_create(code='DEMO-2025-2',defaults={'name':'Học kỳ 2 · 2025–2026 (Demo)','starts_on':dt.date(2026,1,1),'ends_on':dt.date(2026,6,30)})
    for i,name in enumerate(['Nhập môn lập trình (Demo)','Toán rời rạc (Demo)','Cấu trúc dữ liệu (Demo)','Kỹ năng học đại học (Demo)'],1):
        subject,_=Subject.objects.get_or_create(code=f'DEMO-BASE{i}',defaults={'name':name,'credits':3,'teacher':'ThS. Giảng viên cơ sở (Demo)'})
        Grade.objects.get_or_create(student=student,subject=subject,semester=previous.code,assessment_type='TOTAL',defaults={'score':8+i/10})
    TermAssessment.objects.get_or_create(student=student,semester=previous,defaults={'conduct_score':90})
    for subject in Subject.objects.filter(code__startswith='DEMO'):
        subject.teacher_email=subject.code.lower()+'@lecturer.example.test'
        subject.teacher_phone='0000 000 '+str(subject.pk).zfill(3)
        subject.teacher_department='Khoa Công nghệ thông tin (Demo)'
        subject.teacher_office='Khu A · Phòng 201 (Demo)'
        subject.teacher_bio='Hồ sơ giảng viên minh họa. Email và số điện thoại chỉ là dữ liệu demo, không dùng để liên hệ thực tế.'
        subject.save(update_fields=['teacher_email','teacher_phone','teacher_department','teacher_office','teacher_bio'])
    print('Academic demo ready: offerings, component grades, configurable review, faculty contacts.')
