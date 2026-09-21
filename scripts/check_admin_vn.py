import asyncio
from playwright.async_api import async_playwright
import re

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        await page.goto('http://127.0.0.1:8000/admin/login/')
        await page.fill('input[name="username"]', 'admin')
        await page.fill('input[name="password"]', 'admin123')
        await page.click('input[type="submit"]')
        await page.wait_for_load_state('networkidle')
        await page.goto('http://127.0.0.1:8000/admin-dashboard/')
        await page.wait_for_load_state('networkidle')
        
        # Check text in all tabs
        tabs = ['tab-live', 'tab-students', 'tab-grades', 'tab-schedule', 'tab-face-reg']
        out = []
        for tab in tabs:
            btn = await page.query_selector(f'.dash-nav-link[data-tab="{tab}"]')
            if btn:
                await btn.click()
                await asyncio.sleep(0.5)
            content = await page.inner_text('body')
            vn_matches = [line.strip() for line in content.split('\n') if re.search(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]', line)]
            out.append(f'=== Tab {tab}: {len(vn_matches)} Vietnamese lines ===')
            for line in vn_matches:
                out.append(f'   {line}')
                
        with open('scripts/vn_output.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
        print('Wrote scripts/vn_output.txt successfully!')
        await browser.close()

asyncio.run(main())
