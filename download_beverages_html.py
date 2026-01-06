from playwright.sync_api import sync_playwright
import pathlib

pathlib.Path("temp").mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    print("Loading page...")
    page.goto('https://www.hideawaysaratoga.com/beverages', wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(2000)
    html = page.content()
    browser.close()
    
    with open('temp/beverages_html.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Saved {len(html)} characters to temp/beverages_html.html')

