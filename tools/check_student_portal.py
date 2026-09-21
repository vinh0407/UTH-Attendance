"""Exercise the real student portal with an isolated SQLite DB and fake records."""
import datetime as dt
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'admin_check'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')


def main():
    with tempfile.TemporaryDirectory(prefix='uth-student-ui-') as directory:
        from django.conf import settings
        settings.DATABASES['default']['NAME'] = str(Path(directory) / 'db.sqlite3')
        settings.DEBUG = True
        settings.SESSION_COOKIE_SECURE = settings.CSRF_COOKIE_SECURE = False
        settings.ALLOWED_HOSTS = ['127.0.0.1', 'testserver']
        import django
        django.setup()
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.utils import timezone
        from portal.models import Student, ClassRoom, Schedule, Subject, AttendanceSession, AttendanceRecord, Grade, AcademicTerm, AcademicPolicy, StudentAcademicProfile, TermAssessment, CourseOffering
        call_command('migrate', verbosity=0)
        today = timezone.localdate()
        term = AcademicTerm.objects.create(code='2026-1', name='Học kỳ 1 · 2026', starts_on=today-dt.timedelta(days=90), ends_on=today+dt.timedelta(days=90))
        student = Student.objects.create(student_id='2251120064', full_name='Nguyễn Minh Anh',
                                         class_name='CN22A', email='anh.demo@example.test', is_registered=True)
        Student.objects.create(student_id='EMPTY01', full_name='Sinh viên mới', class_name='CN22B')
        room = ClassRoom.objects.create(class_id='CN22A', name='Công nghệ thông tin 22A')
        room.students.add(student)
        classmate = Student.objects.create(student_id='CLASSMATE01', full_name='Bạn học Demo', class_name='CN22A', email='private@example.test')
        room.students.add(classmate)
        policy = AcademicPolicy.objects.create(name='Tiêu chí demo', min_scholarship_credits=3)
        StudentAcademicProfile.objects.create(student=student, policy=policy, english_certified=True, physical_education_completed=True)
        TermAssessment.objects.create(student=student, semester=term, conduct_score=85)
        elective = Subject.objects.create(code='ELECT01', name='Thiết kế giao diện', credits=3, teacher='ThS. Giảng viên Demo', teacher_email='lecturer@example.test', teacher_phone='0000 000 001', teacher_department='Khoa Công nghệ thông tin', teacher_office='A.201')
        elective_class = ClassRoom.objects.create(class_id='UI01', name='Lớp Thiết kế giao diện')
        elective_schedule = Schedule.objects.create(subject=elective, classroom=elective_class, semester=term, day_of_week=(today.weekday()+2)%7, start_period=1, end_period=3, room='B.201')
        CourseOffering.objects.create(schedule=elective_schedule, capacity=30, opens_on=today-dt.timedelta(days=7), closes_on=today+dt.timedelta(days=7))
        titles = ['Lập trình ứng dụng Web', 'Cơ sở dữ liệu', 'Mạng máy tính', 'Trí tuệ nhân tạo']
        for i, title in enumerate(titles):
            subject = Subject.objects.create(code=f'IT{201+i}', name=title, teacher=['ThS. Lê Hoàng Nam', 'TS. Trần Thu Hà'][i % 2])
            schedule = Schedule.objects.create(subject=subject, classroom=room, semester=term, day_of_week=today.weekday() if i < 2 else (today.weekday()+1)%7,
                                                start_period=1 if i % 2 == 0 else 6, end_period=3 if i % 2 == 0 else 8, room=f'A.{301+i}')
            if i == 1:
                AttendanceSession.objects.create(schedule=schedule, date=today, status='cancelled')
            for n in range(4):
                session = AttendanceSession.objects.create(schedule=schedule, date=today-dt.timedelta(days=7*(n+1)), status='completed')
                absent = (i == 1 and n == 1) or (i == 2 and n < 3) or i == 3
                late = i == 1 and n == 0
                AttendanceRecord.objects.create(student=student, session=session, date=session.date, attendance_id=f'UI-{i}-{n}',
                    time_in=None if absent else dt.time(7, 20 if late else 0), scheduled_time=dt.time(7),
                    status='absent' if absent else 'late' if late else 'present', attendance_code='ABSENT' if absent else 'LATE_ONE_PERIOD' if late else 'ON_TIME',
                    attendance_periods=3 if absent else 1 if late else 0, late_minutes=20 if late else 0)
            Grade.objects.create(student=student, subject=subject, semester='2026-1', assessment_type='MIDTERM', score=8+i*.25)
            Grade.objects.create(student=student, subject=subject, semester='2026-1', assessment_type='TOTAL', score=7.8+i*.3)
        old_term = AcademicTerm.objects.create(code='2025-2', name='Học kỳ cũ', starts_on=today-dt.timedelta(days=300), ends_on=today-dt.timedelta(days=120))
        old_schedule = Schedule.objects.create(subject=Subject.objects.get(code='IT201'), classroom=room, semester=old_term, day_of_week=0, start_period=1, end_period=3, is_active=False)
        for n in range(4):
            day = today-dt.timedelta(days=180+n*7)
            session = AttendanceSession.objects.create(schedule=old_schedule, date=day, status='completed')
            AttendanceRecord.objects.create(student=student, session=session, date=day, status='absent', attendance_code='ABSENT', attendance_periods=3)
        fourth_record_id = AttendanceRecord.objects.get(student=student, session__schedule__subject__code='IT203', status='present').pk
        def change_fourth_record(absent):
            # Playwright's sync API runs an event loop; keep Django writes on a worker.
            def update():
                from django.db import connections
                try:
                    AttendanceRecord.objects.filter(pk=fourth_record_id).update(status='absent' if absent else 'present', attendance_code='ABSENT' if absent else 'ON_TIME', attendance_periods=3 if absent else 0)
                finally:
                    connections.close_all()
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(update).result()
        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *_args):
                pass
        server = make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()), handler_class=QuietHandler)
        origin = f'http://127.0.0.1:{server.server_port}'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        output = ROOT / '.impeccable' / 'review'
        output.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright, expect
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1050})
                page.emulate_media(reduced_motion='reduce')
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.on('console', lambda msg: print('BROWSER:', msg.text, flush=True) if msg.type == 'error' else None)
                page.goto(origin+'/student-portal/')
                page.wait_for_load_state('networkidle')
                page.locator('#loginStudentId').fill('2251120064')
                page.locator('#loginClassName').fill('CN22A')
                page.locator('#loginSubmit').click()
                expect(page.locator('#portalShell')).to_be_visible()
                if '--baseline' in sys.argv:
                    page.screenshot(path=str(output/'student-before-desktop.png'), full_page=True)
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.screenshot(path=str(output/'student-before-mobile.png'), full_page=True)
                else:
                    expect(page.get_by_role('heading', name='Lịch học hôm nay')).to_be_visible()
                    page.locator('.side-nav [data-route="registration"]').click()
                    expect(page.locator('#offeringList')).to_contain_text('Thiết kế giao diện')
                    page.locator('#offeringList details summary').click()
                    expect(page.locator('#offeringList')).to_contain_text('lecturer@example.test')
                    page.get_by_role('button', name='Đăng ký học phần', exact=True).click()
                    expect(page.get_by_role('button', name='Hủy đăng ký', exact=True)).to_be_visible()
                    page.evaluate("location.hash='schedule'")
                    expect(page.locator('#weeklySchedule')).to_contain_text('Thiết kế giao diện')
                    page.evaluate("location.hash='registration'")
                    page.get_by_role('button', name='Hủy đăng ký', exact=True).click()
                    expect(page.get_by_role('button', name='Đăng ký học phần', exact=True)).to_be_visible()
                    page.evaluate("location.hash='scholarship'")
                    expect(page.locator('#scholarshipReview')).to_contain_text('tham khảo')
                    page.evaluate("location.hash='graduation'")
                    expect(page.locator('#graduationReview')).to_contain_text('Tín chỉ tích lũy')
                    page.evaluate("location.hash='classmates'")
                    expect(page.locator('#classmatesList')).to_contain_text('Bạn học Demo')
                    expect(page.locator('#classmatesList')).not_to_contain_text('private@example.test')
                    page.get_by_role('button', name='Xem hồ sơ Bạn học Demo').click()
                    expect(page.locator('#classmateDialog')).to_be_visible()
                    expect(page.locator('#classmateDialog')).to_contain_text('CLASSMATE01')
                    page.get_by_role('button', name='Đóng hồ sơ').click()
                    page.evaluate("location.hash='home'")
                    expect(page.locator('#portalShell')).to_contain_text('Nguyễn Minh Anh')
                    expect(page.locator('#todaySchedule')).to_contain_text('Đã hủy')
                    page.screenshot(path=str(output/'student-desktop.png'), full_page=True)
                    page.locator('.side-nav [data-route="attendance"]').click()
                    expect(page.locator('#attendanceCourses .quota-card')).to_have_count(4)
                    for code, remaining in [('IT201', 3), ('IT202', 2), ('IT203', 0), ('IT204', 0)]:
                        expect(page.locator(f'#attendanceCourses [data-subject="{code}"] .quota-ring')).to_contain_text(f'{remaining}/3')
                    expect(page.locator('#attendanceCourses [data-subject="IT203"]')).to_contain_text('Hết lượt nghỉ')
                    expect(page.locator('#attendanceCourses [data-subject="IT204"]')).to_contain_text('Rớt môn')
                    expect(page.locator('#attendanceNotifications')).to_contain_text('Vắng thêm 1 buổi')
                    expect(page.locator('#attendanceNotifications')).to_contain_text('rớt')
                    page.screenshot(path=str(output/'student-quota-desktop.png'))
                    page.get_by_label('Học kỳ chuyên cần').select_option('2025-2')
                    expect(page.locator('#attendanceCourses .quota-card')).to_have_count(1)
                    expect(page.locator('#attendanceCourses')).to_contain_text('Rớt môn')
                    expect(page.locator('#attendanceRows tr')).to_have_count(4)
                    page.get_by_label('Học kỳ chuyên cần').select_option('2026-1')
                    expect(page.locator('#attendanceCourses [data-subject="IT201"] .quota-ring')).to_contain_text('3/3')
                    change_fourth_record(True)
                    expect(page.locator('#attendanceCourses [data-subject="IT203"]')).to_contain_text('Rớt môn', timeout=35000)
                    change_fourth_record(False)
                    page.get_by_role('button', name='Làm mới dữ liệu').click()
                    expect(page.locator('#attendanceCourses [data-subject="IT203"]')).to_contain_text('Hết lượt nghỉ')
                    page.get_by_label('Trạng thái điểm danh').select_option('absent')
                    expect(page.locator('#attendanceRows tr')).to_have_count(8)
                    page.get_by_label('Tìm môn học').fill('không có môn này')
                    expect(page.locator('#attendanceRows')).to_contain_text('Không tìm thấy')
                    page.get_by_label('Tìm môn học').fill('')
                    page.get_by_label('Trạng thái điểm danh').select_option('all')
                    for width in (320, 390, 768, 1024, 1440):
                        page.set_viewport_size({'width': width, 'height': 900})
                        page.evaluate("location.hash='home'")
                        expect(page.locator('#page-home')).to_be_visible()
                        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), width
                        if width == 390:
                            page.screenshot(path=str(output/'student-mobile.png'), full_page=True)
                            page.screenshot(path=str(output/'student-mobile-viewport.png'))
                        navigation = '.bottom-nav' if width < 900 else '.side-nav'
                        for route in ('schedule', 'grades', 'attendance', 'profile'):
                            page.locator(f'{navigation} [data-route="{route}"]').click()
                            expect(page.locator('#page-'+route)).to_be_visible()
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), (width, route)
                        for route in ('registration', 'scholarship', 'graduation', 'classmates'):
                            page.evaluate(f"location.hash='{route}'")
                            expect(page.locator('#page-'+route)).to_be_visible()
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), (width, route)
                            if width == 390:
                                page.screenshot(path=str(output/('student-mobile-'+route+'.png')))
                        if width == 390:
                            page.locator('.bottom-nav [data-route="attendance"]').click()
                            page.screenshot(path=str(output/'student-mobile-attendance.png'), full_page=True)
                            page.screenshot(path=str(output/'student-quota-mobile.png'))
                    page.evaluate("location.hash='home'")
                    page.get_by_role('button', name='Làm mới dữ liệu').click()
                    expect(page.locator('#refreshButton')).to_be_enabled()
                    page.route('**/api/student/me/dashboard/', lambda route: route.fulfill(status=503, json={'error': 'Offline'}))
                    page.get_by_role('button', name='Làm mới dữ liệu').click()
                    expect(page.locator('#syncStatus')).to_contain_text('chưa cập nhật')
                    expect(page.locator('#portalShell')).to_contain_text('Nguyễn Minh Anh')
                    page.unroute('**/api/student/me/dashboard/')
                    page.evaluate("location.hash='subjects'")
                    expect(page.locator('#subjectCards')).to_contain_text('Rớt môn')
                    page.evaluate("location.hash='schedule'")
                    page.get_by_role('button', name='Hôm nay', exact=True).click()
                    expect(page.locator('#weeklySchedule')).to_contain_text('Đã hủy')
                    expect(page.locator('#weeklySchedule .card')).to_have_count(1)
                    page.evaluate("location.hash='profile'")
                    page.get_by_role('button', name='Chuyển giao diện tối').click()
                    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                    page.evaluate("location.hash='attendance'")
                    expect(page.locator('#page-attendance')).to_be_visible()
                    page.screenshot(path=str(output/'student-quota-dark.png'))
                    page.evaluate("location.hash='profile'")
                    page.reload()
                    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                    page.get_by_role('button', name='Chuyển giao diện sáng').click()
                    page.route('**/api/student/logout/', lambda route: route.fulfill(status=503, json={'error': 'Offline'}))
                    page.get_by_role('button', name='Đăng xuất', exact=True).click()
                    expect(page.locator('#toast')).to_contain_text('Chưa thể đăng xuất')
                    expect(page.locator('#portalShell')).to_be_visible()
                    page.unroute('**/api/student/logout/')
                    page.get_by_role('button', name='Đăng xuất', exact=True).click()
                    expect(page.locator('#authGate')).to_be_visible()
                    page.reload()
                    expect(page.locator('#authGate')).to_be_visible()
                    expect(page.locator('#portalShell')).not_to_be_visible()
                    page.locator('#loginStudentId').fill('EMPTY01')
                    page.locator('#loginClassName').fill('CN22B')
                    page.locator('#loginSubmit').click()
                    expect(page.locator('#portalShell')).to_contain_text('Sinh viên mới')
                    expect(page.locator('#portalShell')).not_to_contain_text('Nguyễn Minh Anh')
                    page.evaluate("location.hash='home'")
                    expect(page.locator('#todaySchedule')).to_contain_text('Không có lịch học')
                    page.screenshot(path=str(output/'student-empty.png'), full_page=True)
                    page.route('**/api/student/me/dashboard/', lambda route: route.fulfill(status=401, json={'error': 'Expired'}))
                    page.get_by_role('button', name='Làm mới dữ liệu').click()
                    expect(page.locator('#authGate')).to_be_visible()
                    expect(page.locator('#loginError')).to_contain_text('hết hạn')
                    expect(page.locator('#portalShell')).not_to_be_visible()
                    assert not errors, errors
                    print('PASS: student login/logout, real data, filters, empty/error states, theme persistence and 5 responsive widths.', flush=True)
                browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()
            from django.db import connections
            connections.close_all()


if __name__ == '__main__':
    main()
