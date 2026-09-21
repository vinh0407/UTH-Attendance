"""Browser smoke test with a temporary DB; never uses real student records.

Run: python tools/check_attendance_ui.py
Requires playwright and an installed Microsoft Edge browser.
"""
import os
import sys
import tempfile
import threading
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'admin_check'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')


def main():
    with tempfile.TemporaryDirectory(prefix='uth-ui-') as temporary:
        from django.conf import settings
        settings.DATABASES['default']['NAME'] = str(Path(temporary) / 'test.sqlite3')
        settings.ATTENDANCE_HISTORY_DIR = Path(temporary) / 'archive'
        settings.DEBUG = True
        settings.SESSION_COOKIE_SECURE = False
        settings.CSRF_COOKIE_SECURE = False
        settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth.models import User
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.wsgi import get_wsgi_application
        from django.test import Client
        from django.utils import timezone
        from portal.models import AttendanceSession, ClassRoom, Schedule, Student, Subject
        call_command('migrate', verbosity=0)
        staff = User.objects.create_user('ui-reviewer', is_staff=True)
        student = Student.objects.create(student_id='UI-001', full_name='Demo Student')
        classroom = ClassRoom.objects.create(class_id='UI-CLASS', name='Demo class')
        classroom.students.add(student)
        subject = Subject.objects.create(code='UI101', name='Software Engineering')
        schedule = Schedule.objects.create(subject=subject, classroom=classroom,
                                          day_of_week=timezone.localdate().weekday(), start_period=1, end_period=3, room='A203')
        session = AttendanceSession.objects.create(schedule=schedule, date=timezone.localdate(), status='active')
        client = Client()
        client.force_login(staff)

        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *_args):
                pass

        server = make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()), handler_class=QuietHandler)
        origin = f'http://127.0.0.1:{server.server_port}'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        from playwright.sync_api import sync_playwright, expect
        output = ROOT / '.impeccable' / 'review'
        output.mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True, args=[
                    '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
                ])
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, permissions=['camera'])
                context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': client.cookies[settings.SESSION_COOKIE_NAME].value, 'url': origin}])
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'{origin}/session/{session.pk}/')
                page.wait_for_load_state('networkidle')
                expect(page.get_by_role('button', name='Correct attendance for Demo Student')).to_be_visible()
                assert page.locator('.app-main').bounding_box()['width'] > 1000
                page.screenshot(path=str(output / 'attendance-before-edit.png'), full_page=True)
                print('Review page loaded', flush=True)
                page.get_by_role('button', name='Correct attendance for Demo Student').click()
                page.get_by_label('Actual arrival time (local time)').fill('07:20:00')
                page.get_by_label('Reason for correction').fill('Camera unavailable; lecturer confirmed arrival.')
                page.get_by_role('button', name='Save correction').click()
                expect(page.locator('#review-dialog')).not_to_be_visible()
                expect(page.locator('#review-rows')).to_contain_text('LATE — 1 PERIOD')
                page.get_by_text('1 correction(s)', exact=True).click()
                expect(page.locator('#review-rows')).to_contain_text('ui-reviewer')
                page.screenshot(path=str(output / 'attendance-review-desktop.png'), full_page=True)
                for width in (320, 768, 1024):
                    page.set_viewport_size({'width': width, 'height': 900})
                    page.get_by_role('button', name='Correct attendance for Demo Student').click()
                    expect(page.get_by_label('Reason for correction')).to_be_visible()
                    box = page.locator('#review-dialog').bounding_box()
                    assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, box
                    page.screenshot(path=str(output / f'attendance-review-{width}.png'), full_page=True)
                    page.keyboard.press('Escape')
                    expect(page.locator('#review-dialog')).not_to_be_visible()
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.get_by_role('button', name='Correct attendance for Demo Student').click()
                page.get_by_label('Attendance', exact=True).select_option('absent')
                expect(page.get_by_label('Actual arrival time (local time)')).to_be_disabled()
                page.get_by_label('Reason for correction').fill('Review correction test')
                page.get_by_role('button', name='Save correction').click()
                expect(page.locator('#review-rows')).to_contain_text('2 correction(s)')
                archive = next((Path(temporary) / 'archive').rglob('attendance.csv'))
                assert 'ABSENT' in archive.read_text(encoding='utf-8-sig')

                # Only the AI response is simulated; the kiosk page and session APIs are real.
                def verifying(route):
                    route.fulfill(json={'success': True, 'data': {'recognized': [{
                        'name': 'Demo Student', 'status': 'verifying', 'bbox': [100, 60, 300, 270],
                        'verification': {'hits': 2, 'required': 3},
                    }]}})
                page.route('**/api/recognize-face/', verifying)
                page.goto(f'{origin}/kiosk/?session_id={session.pk}')
                expect(page.locator('#state-label')).to_have_text('VERIFYING', timeout=20000)
                expect(page.locator('#state-copy')).to_contain_text('2 of 3')
                expect(page.locator('#student-result')).not_to_be_visible()
                page.screenshot(path=str(output / 'kiosk-verifying.png'), full_page=True)
                assert not errors, errors
                browser.close()
            print('PASS: real correction API, audit history, CSV callback, responsive dialog, kiosk verifying state; no JavaScript errors.')
            print(f'Screenshots: {output}')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            from django.db import connections
            connections.close_all()


if __name__ == '__main__':
    main()
