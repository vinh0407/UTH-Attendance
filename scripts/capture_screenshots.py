import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

def main():
    print(f"Saving screenshots to: {OUTPUT_DIR}")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        # ==========================================
        # 1. ADMIN DASHBOARD CAPTURES
        # ==========================================
        print("1. Logging in as Admin...")
        page.goto("http://127.0.0.1:8000/admin/login/?next=/admin-dashboard/")
        page.wait_for_load_state("networkidle")

        if page.locator('input[name="username"]').count() > 0:
            page.fill('input[name="username"]', "admin")
            page.fill('input[name="password"]', "admin123")
            page.click('input[type="submit"]')
            page.wait_for_load_state("networkidle")

        page.goto("http://127.0.0.1:8000/admin-dashboard/")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        print("Capturing 01_admin_dashboard_overview.png...")
        page.screenshot(path=os.path.join(OUTPUT_DIR, "01_admin_dashboard_overview.png"), full_page=False)

        # Tab 3: Grades Management & Audit Trail
        print("Switching to Tab 3 (Grades & Audit)...")
        page.evaluate("switchTab('tab-grades')")
        time.sleep(1.2)
        print("Capturing 02_admin_bulk_grades_and_audit.png...")
        page.screenshot(path=os.path.join(OUTPUT_DIR, "02_admin_bulk_grades_and_audit.png"), full_page=False)

        # Open Bulk Grade CSV modal
        print("Opening Bulk Grade CSV Modal...")
        page.evaluate("openBulkGradeModal()")
        time.sleep(1.0)
        print("Capturing 03_admin_bulk_grade_modal.png...")
        page.screenshot(path=os.path.join(OUTPUT_DIR, "03_admin_bulk_grade_modal.png"), full_page=False)
        page.evaluate("closeBulkGradeModal()")
        time.sleep(0.5)

        # ==========================================
        # 2. STUDENT PORTAL CAPTURES
        # ==========================================
        print("\n2. Logging in to Student Portal...")
        student_context = browser.new_context(
            viewport={"width": 1440, "height": 920},
            device_scale_factor=1.5,
        )
        s_page = student_context.new_page()
        s_page.goto("http://127.0.0.1:8000/student-portal/")
        s_page.wait_for_load_state("networkidle")

        # Fill student login form
        if s_page.locator("#loginStudentId").is_visible():
            s_page.fill("#loginStudentId", "2251120064")
            s_page.fill("#loginClassName", "CN22A")
            s_page.click("#loginSubmit")
            s_page.wait_for_selector("#portalShell:not([hidden])", timeout=10000)
            time.sleep(1.5)

        print("Capturing 04_portal_home.png...")
        s_page.screenshot(path=os.path.join(OUTPUT_DIR, "04_portal_home.png"), full_page=False)

        # Grades page with interactive calculator
        print("Navigating to #grades...")
        s_page.goto("http://127.0.0.1:8000/student-portal/#grades")
        time.sleep(1.2)
        print("Capturing 05_portal_grades_calculator.png...")
        s_page.screenshot(path=os.path.join(OUTPUT_DIR, "05_portal_grades_calculator.png"), full_page=False)

        # Leave requests page
        print("Navigating to #leaves...")
        s_page.goto("http://127.0.0.1:8000/student-portal/#leaves")
        time.sleep(1.2)
        print("Capturing 06_portal_leave_requests.png...")
        s_page.screenshot(path=os.path.join(OUTPUT_DIR, "06_portal_leave_requests.png"), full_page=False)

        # Attendance quota page
        print("Navigating to #attendance...")
        s_page.goto("http://127.0.0.1:8000/student-portal/#attendance")
        time.sleep(1.2)
        print("Capturing 07_portal_attendance_warnings.png...")
        s_page.screenshot(path=os.path.join(OUTPUT_DIR, "07_portal_attendance_warnings.png"), full_page=False)

        browser.close()
        print("\nAll 7 screenshots captured successfully!")

if __name__ == "__main__":
    main()
