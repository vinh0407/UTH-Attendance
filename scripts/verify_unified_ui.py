import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("1. Checking Home Gateway...")
        await page.goto("http://127.0.0.1:8000/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)
        os.makedirs("docs/screenshots", exist_ok=True)
        await page.screenshot(path="docs/screenshots/unified_home.png", full_page=False)
        print("Saved docs/screenshots/unified_home.png")

        print("2. Logging into Admin Dashboard...")
        await page.goto("http://127.0.0.1:8000/admin/login/")
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin123")
        await page.click('input[type="submit"]')
        await page.wait_for_load_state("networkidle")

        print("3. Navigating to Admin Dashboard...")
        await page.goto("http://127.0.0.1:8000/admin-dashboard/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)
        await page.screenshot(path="docs/screenshots/unified_admin_live.png", full_page=False)
        print("Saved docs/screenshots/unified_admin_live.png")

        print("4. Testing Schedule tab navigation...")
        await page.click('.dash-nav-link[data-tab="tab-schedule"]')
        await asyncio.sleep(1)
        await page.screenshot(path="docs/screenshots/unified_admin_schedule.png", full_page=False)
        print("Saved docs/screenshots/unified_admin_schedule.png")

        print("5. Testing Mobile Drawer Navigation...")
        mobile_context = await browser.new_context(viewport={"width": 414, "height": 896})
        mobile_page = await mobile_context.new_page()
        # Transfer cookies or login on mobile
        await mobile_page.goto("http://127.0.0.1:8000/admin/login/")
        await mobile_page.fill('input[name="username"]', "admin")
        await mobile_page.fill('input[name="password"]', "admin123")
        await mobile_page.click('input[type="submit"]')
        await mobile_page.goto("http://127.0.0.1:8000/admin-dashboard/")
        await mobile_page.wait_for_load_state("networkidle")
        await mobile_page.click('#mobileMenuBtn')
        await asyncio.sleep(0.5)
        await mobile_page.screenshot(path="docs/screenshots/unified_admin_mobile_drawer.png", full_page=False)
        print("Saved docs/screenshots/unified_admin_mobile_drawer.png")

        print("6. Checking Student Portal...")
        page2 = await context.new_page()
        await page2.goto("http://127.0.0.1:8000/student-portal/")
        await page2.fill('#loginStudentId', "2251120064")
        await page2.fill('#loginClassName', "CN22A")
        await page2.click('#loginSubmit')
        await page2.wait_for_selector('#portalShell:not([hidden])', timeout=5000)
        await asyncio.sleep(1)
        await page2.screenshot(path="docs/screenshots/unified_student_portal_check.png", full_page=False)
        print("Saved docs/screenshots/unified_student_portal_check.png")

        await browser.close()
        print("All UI verification complete!")

if __name__ == "__main__":
    asyncio.run(main())
