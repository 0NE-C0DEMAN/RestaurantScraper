"""
Scraper for The Whistling Kettle (thewhistlingkettle.com)
Scrapes menu from cafe.thewhistlingkettle.com/menu
Handles: multi-price, multi-size, and add-ons
Note: Prices may not be available in the HTML - will extract what's available
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time


RESTAURANT_NAME = "The Whistling Kettle"
RESTAURANT_URL = "https://www.thewhistlingkettle.com/"

MENU_URL = "https://cafe.thewhistlingkettle.com/menu"


def fetch_menu_html() -> Optional[str]:
    """Fetch menu HTML using Playwright"""
    print("  Loading page with Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set cookies
            page.context.add_cookies([
                {
                    'name': '_shopify_y',
                    'value': 'b27f8a39-e625-4d04-9898-7e7bb24a45e2',
                    'domain': '.thewhistlingkettle.com',
                    'path': '/'
                },
                {
                    'name': '_shopify_s',
                    'value': '9afb260b-7e96-4e9c-b70b-13a5caa73d45',
                    'domain': '.thewhistlingkettle.com',
                    'path': '/'
                }
            ])
            
            page.goto(MENU_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for content to load
            time.sleep(3)
            
            # Click through all tabs to load all content and collect items from each
            tabs = page.locator('button[role="tab"]').all()
            print(f"    Found {len(tabs)} tabs, clicking through to collect all content...")
            
            all_tab_htmls = []
            
            for i, tab in enumerate(tabs):
                try:
                    tab.click()
                    time.sleep(2)  # Wait for content to load
                    
                    # Get the tab text to identify the section
                    tab_text = tab.inner_text()
                    print(f"      Processing tab {i+1}/{len(tabs)}: {tab_text}")
                    
                    # Get the current HTML after clicking this tab
                    current_html = page.content()
                    all_tab_htmls.append((tab_text, current_html))
                    
                except Exception as e:
                    print(f"    [WARNING] Could not click tab {i+1}: {e}")
            
            # Use the last HTML (should have all content loaded)
            # But we'll process each tab's HTML separately
            html_content = all_tab_htmls[-1][1] if all_tab_htmls else page.content()
            
            browser.close()
            return html_content
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu: {e}")
        return None


def extract_price_from_text(text: str) -> Optional[str]:
    """Extract price from text"""
    # Look for price patterns
    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
    if price_match:
        return f"${price_match.group(1)}"
    return None


def extract_addons_from_text(text: str) -> str:
    """Extract addon information from text"""
    addons = []
    
    # Look for "add X" or "+ X" patterns
    add_pattern = r'(?:add|Add|\+)\s+([A-Z][^,\.]+?)(?:\s+\$(\d+(?:\.\d{2})?))?'
    add_matches = re.finditer(add_pattern, text, re.IGNORECASE)
    for match in add_matches:
        addon_name = match.group(1).strip()
        addon_price = match.group(2)
        if len(addon_name) < 100:
            if addon_price:
                addons.append(f"{addon_name} +${addon_price}")
            else:
                addons.append(addon_name)
    
    if addons:
        return "Add-ons: " + " / ".join(addons)
    return ""


def process_menu_item(li_elem, current_section: str) -> Optional[Dict]:
    """Process a single menu item from a li element"""
    # Extract item name from strong tag
    strong_elem = li_elem.find('strong')
    if not strong_elem:
        return None
    
    item_name = strong_elem.get_text(strip=True)
    if not item_name:
        return None
    
    # Extract description from p tag
    p_elem = li_elem.find('p')
    description = ""
    if p_elem:
        description = p_elem.get_text(strip=True)
    
    # Extract dietary info from div badges
    dietary_info = []
    badge_divs = li_elem.find_all('div', class_='inline-flex items-center rounded-full')
    for badge in badge_divs:
        badge_text = badge.get_text(strip=True)
        if badge_text and badge_text not in dietary_info:
            dietary_info.append(badge_text)
    
    # Combine description and dietary info
    if dietary_info:
        dietary_str = " (" + ", ".join(dietary_info) + ")"
        if description:
            full_description = description + dietary_str
        else:
            full_description = dietary_str
    else:
        full_description = description
    
    # Extract price (may not be available)
    price = None
    # Check if price is in the text
    all_text = li_elem.get_text(separator=' ', strip=True)
    price = extract_price_from_text(all_text)
    
    # If no price found, set to None (prices may not be displayed)
    if not price:
        price = None
    
    # Extract addons
    addons_text = extract_addons_from_text(all_text)
    if addons_text and full_description:
        full_description = f"{full_description}. {addons_text}"
    elif addons_text:
        full_description = addons_text
    
    return {
        "name": item_name,
        "description": full_description if full_description else None,
        "price": price,
        "section": current_section,
        "restaurant_name": RESTAURANT_NAME,
        "restaurant_url": RESTAURANT_URL,
        "menu_type": "Menu",
        "menu_name": current_section
    }


def scrape_whistlingkettle() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    print("\n[1] Fetching menu HTML with Playwright...")
    # Use Playwright to click through all tabs
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set cookies
            page.context.add_cookies([
                {
                    'name': '_shopify_y',
                    'value': 'b27f8a39-e625-4d04-9898-7e7bb24a45e2',
                    'domain': '.thewhistlingkettle.com',
                    'path': '/'
                },
                {
                    'name': '_shopify_s',
                    'value': '9afb260b-7e96-4e9c-b70b-13a5caa73d45',
                    'domain': '.thewhistlingkettle.com',
                    'path': '/'
                }
            ])
            
            page.goto(MENU_URL, wait_until="networkidle", timeout=60000)
            time.sleep(3)
            
            # Get all tabs
            tabs = page.locator('button[role="tab"]').all()
            print(f"[OK] Found {len(tabs)} tabs")
            
            # Process each tab - collect items as we go
            for i, tab in enumerate(tabs):
                try:
                    # Get the tab text (section name) before clicking
                    tab_text = tab.inner_text()
                    print(f"  Processing section: {tab_text}")
                    
                    # Click the tab
                    tab.click()
                    time.sleep(2)  # Wait for content to load
                    
                    # Wait for the tab panel to be visible
                    try:
                        page.wait_for_selector('div[role="tabpanel"]', timeout=5000)
                    except:
                        pass
                    
                    # Get the current HTML after clicking
                    current_html = page.content()
                    soup = BeautifulSoup(current_html, 'html.parser')
                    
                    # Find the active tab panel (should be visible now)
                    tab_panels = soup.find_all('div', role='tabpanel')
                    tab_panel = None
                    
                    # Find the panel that matches this tab
                    for panel in tab_panels:
                        # Check if this panel is associated with the current tab
                        aria_labelledby = panel.get('aria-labelledby', '')
                        if aria_labelledby:
                            # Find the button that matches
                            trigger_elem = soup.find('button', id=aria_labelledby)
                            if trigger_elem and trigger_elem.get_text(strip=True) == tab_text:
                                tab_panel = panel
                                break
                    
                    # If not found by aria-labelledby, try to find by data-state or just use the first visible one
                    if not tab_panel and tab_panels:
                        # Look for panel with data-state="active" or just use the first one
                        for panel in tab_panels:
                            # Check if panel has visible content
                            if panel.find('li'):
                                tab_panel = panel
                                break
                    
                    if tab_panel:
                        # Find all li elements in this tab panel
                        items = tab_panel.find_all('li')
                        print(f"    Found {len(items)} items in {tab_text}")
                        
                        for li_elem in items:
                            item = process_menu_item(li_elem, tab_text)
                            if item:
                                all_items.append(item)
                    else:
                        print(f"    [WARNING] No tab panel found for {tab_text}")
                        # Try to find items directly in the page
                        all_li = soup.find_all('li')
                        print(f"    Found {len(all_li)} list items on page")
                        for li_elem in all_li:
                            item = process_menu_item(li_elem, tab_text)
                            if item:
                                all_items.append(item)
                        
                except Exception as e:
                    print(f"  [ERROR] Failed to process tab {i+1}: {e}")
                    import traceback
                    traceback.print_exc()
            
            browser.close()
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu with Playwright: {e}")
        return []
    
    if not all_items:
        print("[WARNING] No items found, trying fallback method...")
        # Fallback: try to get HTML once
        html = fetch_menu_html()
        if html:
            soup = BeautifulSoup(html, 'html.parser')
    
            # Fallback processing if Playwright method didn't work
            all_li = soup.find_all('li')
            print(f"[OK] Found {len(all_li)} list items total")
            
            # Process all li elements
            processed_items = set()
            for li_elem in all_li:
                item = process_menu_item(li_elem, "Menu")
                if item:
                    desc_start = item['description'][:50] if item['description'] else ''
                    item_key = (item['name'], item['section'], desc_start)
                    if item_key not in processed_items:
                        processed_items.add(item_key)
                        all_items.append(item)
    
    print(f"\n[OK] Extracted {len(all_items)} items total")
    
    return all_items


if __name__ == "__main__":
    items = scrape_whistlingkettle()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "thewhistlingkettle_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

