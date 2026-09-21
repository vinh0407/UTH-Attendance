"""Seed only the explicitly labelled local demo student; never touch real students.
Run: python admin_check/manage.py shell -c "exec(open('tools/seed_student_quota_demo.py', encoding='utf-8-sig').read())"
"""
import datetime as dt
from django.db import transaction
from django.utils import timezone
from portal.models import AcademicTerm, AttendanceRecord, AttendanceSession, ClassRoom, Grade, Schedule, Student, Subject
from portal.attendance_service import get_session_scheduled_time

with transaction.atomic():
    student = Student.objects.get(student_id='2251120064', full_name='Sinh viên Demo', class_name='CN22A')
    room = ClassRoom.objects.get(class_id='CN22A')
    today = timezone.localdate()
    term, _ = AcademicTerm.objects.get_or_create(code='DEMO-2026', defaults={'name':'Học kỳ Demo · 2026', 'starts_on':today-dt.timedelta(days=120), 'ends_on':today+dt.timedelta(days=120)})
    names = ['Lập trình Web (Demo)', 'Cơ sở dữ liệu (Demo)', 'Mạng máy tính (Demo)', 'Trí tuệ nhân tạo (Demo)', 'Công nghệ phần mềm (Demo)']
    for i, name in enumerate(names):
        subject, _ = Subject.objects.get_or_create(code=f'DEMO{i+1}', defaults={'name':name, 'teacher':'Giảng viên Demo'})
        schedule = Schedule.objects.filter(subject=subject, classroom=room).first()
        if schedule is None:
            schedule = Schedule.objects.create(subject=subject, classroom=room, semester=term, day_of_week=(today.weekday()+1)%7, start_period=1 if i==3 else 6, end_period=3 if i==3 else 8, room=f'A.{301+i}')
        else:
            schedule.semester = term
            schedule.save(update_fields=['semester'])
        for n in range(1,5):
            day = today-dt.timedelta(days=(today.weekday()-schedule.day_of_week)%7+7*n)
            session, _ = AttendanceSession.objects.get_or_create(schedule=schedule, date=day, defaults={'status':'completed'})
            scheduled = get_session_scheduled_time(session)
            absent = n <= i
            AttendanceRecord.objects.update_or_create(student=student, session=session, defaults={
                'date':day, 'status':'absent' if absent else 'present', 'attendance_code':'ABSENT' if absent else 'ON_TIME',
                'time_in':None if absent else scheduled, 'scheduled_time':scheduled,
                'attendance_periods':schedule.end_period-schedule.start_period+1 if absent else 0,
                'notes':'DEMO: synthetic attendance for absence allowance testing',
            })
        Grade.objects.get_or_create(student=student,subject=subject,semester=term.code,assessment_type='MIDTERM',defaults={'score':8})
    print('Demo ready: five courses with 3/3, 2/3, 1/3, 0/3 warning, 0/3 failed.')
