from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge', headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto('http://127.0.0.1:8000/admin/login/?next=/admin-dashboard/')
    page.fill('input[name="username"]', 'admin')
    page.fill('input[name="password"]', 'admin123')
    page.click('input[type="submit"]')
    page.wait_for_load_state('networkidle')
    page.goto('http://127.0.0.1:8000/admin-dashboard/')
    page.wait_for_load_state('networkidle')

    info_before = page.evaluate("document.querySelector('.app-main').offsetWidth")
    print('main width before:', info_before)

    page.evaluate("""() => {
        const style = document.createElement('style');
        style.textContent = `
            .app-shell { display: flex !important; min-height: 100vh; }
            .app-sidebar { width: 240px !important; flex-shrink: 0 !important; }
            .app-main { flex: 1 1 0% !important; min-width: 0 !important; width: auto !important; max-width: 1520px !important; }
        `;
        document.head.appendChild(style);
    }""")
    info_after = page.evaluate("document.querySelector('.app-main').offsetWidth")
    print('main width after:', info_after)
    page.screenshot(path="docs/screenshots/test_fixed_dashboard.png")
    b.close()
