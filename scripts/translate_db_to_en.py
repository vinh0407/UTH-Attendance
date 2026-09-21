"""Update all database records from Vietnamese to professional English."""
import os
import sys
import django

sys.path.insert(0, os.path.abspath('admin_check'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from django.db import transaction
from portal.models import Student, Subject, ClassRoom, Schedule, AttendanceSession, AcademicTerm, AcademicPolicy, StudentAcademicProfile

TRANSLATIONS = {
    # Students
    'Sinh viên Demo': 'Demo Student',
    'Nguyễn An (Demo)': 'An Nguyen (Demo)',
    'Trần Bình (Demo)': 'Binh Tran (Demo)',
    'Lê Chi (Demo)': 'Chi Le (Demo)',
    'Phạm Duy (Demo)': 'Duy Pham (Demo)',

    # Subjects
    'Lập trình Web (Demo)': 'Web Programming (Demo)',
    'Cơ sở dữ liệu (Demo)': 'Database Systems (Demo)',
    'Mạng máy tính (Demo)': 'Computer Networks (Demo)',
    'Trí tuệ nhân tạo (Demo)': 'Artificial Intelligence (Demo)',
    'Công nghệ phần mềm (Demo)': 'Software Engineering (Demo)',
    'Lập trình Android (Demo)': 'Android Development (Demo)',
    'Thiết kế giao diện Web (Demo)': 'Web UI/UX Design (Demo)',
    'Phân tích dữ liệu (Demo)': 'Data Analysis (Demo)',
    'Trải nghiệm người dùng (Demo)': 'User Experience Design (Demo)',
    'Nhập môn lập trình (Demo)': 'Introduction to Programming (Demo)',
    'Toán rời rạc (Demo)': 'Discrete Mathematics (Demo)',
    'Cấu trúc dữ liệu (Demo)': 'Data Structures & Algorithms (Demo)',
    'Kỹ năng học đại học (Demo)': 'University Study Skills (Demo)',

    # Teachers
    'Giảng viên Demo': 'Demo Faculty Member',
    'TS. Trần Hoàng (Demo)': 'Dr. Tran Hoang (Demo)',
    'ThS. Minh Hà (Demo)': 'MSc. Minh Ha (Demo)',
    'TS. Hoàng Nam (Demo)': 'Dr. Hoang Nam (Demo)',
    'ThS. Thanh Mai (Demo)': 'MSc. Thanh Mai (Demo)',
    'ThS. Giảng viên cơ sở (Demo)': 'MSc. Core Faculty (Demo)',

    # Terms & Policies
    'Học kỳ Demo · 2026': 'Demo Semester · 2026',
    'Học kỳ 2 · 2025–2026 (Demo)': 'Semester 2 · 2025–2026 (Demo)',
    'Tiêu chí Demo · CNTT · Thang điểm 10': 'Demo Policy · IT Program · 10-Point Scale',
}

with transaction.atomic():
    # 1. Update Students
    for s in Student.objects.all():
        for vn, en in TRANSLATIONS.items():
            if vn in s.full_name:
                s.full_name = s.full_name.replace(vn, en)
                s.save(update_fields=['full_name'])
                print(f'Updated Student: {s.student_id} -> {s.full_name}')

    # 2. Update Subjects
    for sub in Subject.objects.all():
        updated = False
        for vn, en in TRANSLATIONS.items():
            if sub.name and vn in sub.name:
                sub.name = sub.name.replace(vn, en)
                updated = True
            if sub.teacher and vn in sub.teacher:
                sub.teacher = sub.teacher.replace(vn, en)
                updated = True
            if sub.teacher_department and 'Khoa Công nghệ thông tin' in sub.teacher_department:
                sub.teacher_department = 'Faculty of Information Technology (Demo)'
                updated = True
            if sub.teacher_office and 'Khu A' in sub.teacher_office:
                sub.teacher_office = 'Building A · Room 201 (Demo)'
                updated = True
            if sub.teacher_bio and 'Hồ sơ giảng viên' in sub.teacher_bio:
                sub.teacher_bio = 'Official faculty profile. Contact details are demonstration data for testing purposes.'
                updated = True
        if updated:
            sub.save()
            print(f'Updated Subject: {sub.code} -> {sub.name} (Teacher: {sub.teacher})')

    # 3. Update ClassRooms
    for c in ClassRoom.objects.all():
        for vn, en in TRANSLATIONS.items():
            if c.name and vn in c.name:
                c.name = c.name.replace(vn, en)
                c.save(update_fields=['name'])
                print(f'Updated ClassRoom: {c.class_id} -> {c.name}')

    # 4. Update Terms
    for t in AcademicTerm.objects.all():
        for vn, en in TRANSLATIONS.items():
            if t.name and vn in t.name:
                t.name = t.name.replace(vn, en)
                t.save(update_fields=['name'])
                print(f'Updated Term: {t.code} -> {t.name}')

    # 5. Update Policies
    for p in AcademicPolicy.objects.all():
        for vn, en in TRANSLATIONS.items():
            if p.name and vn in p.name:
                p.name = p.name.replace(vn, en)
                p.save(update_fields=['name'])
                print(f'Updated Policy: {p.name}')

print('Database translation to English finished successfully!')
