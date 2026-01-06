"""Scraper for The Merc Saratoga restaurant menu"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import re
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
import time

RESTAURANT_NAME = "The Merc Saratoga"
RESTAURANT_URL = "https://www.themercsaratoga.com/"

MENU_URLS = [
    {
        "url": "https://www.themercsaratoga.com/brunch",
        "menu_name": "Brunch Menu",
        "menu_type": "Brunch"
    },
    {
        "url": "https://www.themercsaratoga.com/dinner",
        "menu_name": "Dinner Menu",
        "menu_type": "Dinner"
    },
    {
        "url": "https://www.themercsaratoga.com/cocktails",
        "menu_name": "Cocktails Menu",
        "menu_type": "Cocktails"
    },
    {
        "url": "https://www.themercsaratoga.com/beer-wine",
        "menu_name": "Beer & Wine Menu",
        "menu_type": "Beer & Wine"
    }
]

def fetch_menu_html(url: str) -> Optional[str]:
    """Fetch menu HTML using Playwright to get fully rendered content"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(2)  # Wait for any dynamic content
        html = page.content()
        browser.close()
        return html

def extract_price_from_text(text: str) -> Optional[str]:
    """Extract price(s) from text. Handles single price, multi-price (e.g., '7|10'), and add-ons."""
    # Pattern for prices: number at end of line or after item name
    # Handle multi-price like "7|10" or "7 | 10" (without $)
    multi_price_pattern = r'(\d+)\s*\|\s*(\d+)(?:\s|$)'
    multi_match = re.search(multi_price_pattern, text)
    if multi_match:
        price1 = multi_match.group(1)
        price2 = multi_match.group(2)
        return f"${price1} | ${price2}"
    
    # Single price - look for number at end of item name line
    # Pattern: item name followed by space(s) and number
    # Try multiple patterns
    patterns = [
        r'\s+(\d+)(?:\s|$)',  # Space(s) followed by number
        r'(\d+)(?:\s|$)',      # Number at end
        r'(\d+)',              # Any number
    ]
    
    for pattern in patterns:
        single_match = re.search(pattern, text)
        if single_match:
            price = single_match.group(1)
            # Make sure it's a reasonable price (between 1 and 1000)
            if 1 <= int(price) <= 1000:
                return f"${price}"
    
    return None

def extract_addons_from_text(text: str, item_name: str) -> str:
    """Extract add-on information from text"""
    addons = []
    
    # Look for "Add" patterns like "Add Fried Egg 3 | Bacon 3"
    add_pattern = r'ADD\s+(.+?)(?:\s|$)'
    add_matches = re.finditer(add_pattern, text, re.IGNORECASE)
    for match in add_matches:
        addon_text = match.group(1).strip()
        # Extract addon items with prices - pattern: "Item Name 3 | Item Name 3"
        addon_items = re.findall(r'([A-Za-z\s\']+?)\s+(\d+)(?:\s*\|\s*)?', addon_text)
        for item, price in addon_items:
            item_clean = item.strip()
            if item_clean:
                addons.append(f"{item_clean} +${price}")
    
    # Look for patterns like "Chicken 8 | Salmon 12" in salad add-ons
    if 'salad' in text.lower() or 'add' in text.lower():
        addon_pattern = r'([A-Za-z\s]+?)\s+(\d+)(?:\s*\|\s*([A-Za-z\s]+?)\s+(\d+))?'
        addon_matches = re.finditer(addon_pattern, text)
        for match in addon_matches:
            item1 = match.group(1).strip()
            price1 = match.group(2)
            # Make sure this isn't part of the main item name
            if item1.lower() not in item_name.lower() and len(item1) > 2:
                addons.append(f"{item1} +${price1}")
            if match.group(3):
                item2 = match.group(3).strip()
                price2 = match.group(4)
                if item2.lower() not in item_name.lower() and len(item2) > 2:
                    addons.append(f"{item2} +${price2}")
    
    if addons:
        return f"Add-ons: {' / '.join(addons)}"
    return ""

def process_menu_item(item_paragraphs: List, soup: BeautifulSoup, current_section: str) -> Optional[Dict]:
    """Process menu item from list of paragraphs"""
    if not item_paragraphs:
        return None
    
    # First paragraph contains item name and possibly price
    first_p = item_paragraphs[0]
    item_name_elem = first_p.find('strong')
    if not item_name_elem:
        return None
    
    item_name = item_name_elem.get_text(strip=True)
    if not item_name or len(item_name) < 2:
        return None
    
    # Get text from first paragraph to extract price
    first_p_text = first_p.get_text(strip=True)
    price = extract_price_from_text(first_p_text)
    
    # Remove price from item name if it's there
    if price:
        price_num = price.replace('$', '').replace(' | ', '|')
        item_name = re.sub(r'\s+' + re.escape(price_num) + r'(?:\s|$)', '', item_name).strip()
    
    # Collect description from following paragraphs
    description_parts = []
    for p in item_paragraphs[1:]:
        p_text = p.get_text(strip=True)
        if not p_text:
            continue
        
        # Check if this is an add-on line
        if re.match(r'ADD\s+', p_text, re.IGNORECASE):
            continue  # Will handle add-ons separately
        
        # Check if it's a price-only line
        if re.match(r'^\d+$', p_text):
            continue
        
        # Check if it's emphasis (usually description)
        em_tag = p.find('em')
        if em_tag:
            desc_text = em_tag.get_text(strip=True)
            if desc_text and not re.match(r'^\d+$', desc_text):
                description_parts.append(desc_text)
        else:
            # Regular paragraph text
            if p_text and not re.match(r'^\d+$', p_text) and '$' not in p_text:
                description_parts.append(p_text)
    
    description = ' '.join(description_parts).strip() if description_parts else None
    
    # Extract add-ons from all paragraphs
    all_text = ' '.join([p.get_text(strip=True) for p in item_paragraphs])
    addons_text = extract_addons_from_text(all_text, item_name)
    
    # Combine description and addons
    full_description = description
    if addons_text:
        if full_description:
            full_description = f"{full_description}. {addons_text}"
        else:
            full_description = addons_text
    
    # Only return item if it has a name and price
    if not item_name or not price:
        return None
    
    return {
        "name": item_name,
        "description": full_description,
        "price": price,
        "section": current_section,
        "restaurant_name": RESTAURANT_NAME,
        "restaurant_url": RESTAURANT_URL,
        "menu_type": current_section,
        "menu_name": current_section
    }

def parse_menu_html(html: str, menu_name: str, menu_type: str) -> List[Dict]:
    """Parse menu HTML and extract menu items"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find main content
    main = soup.find('main') or soup.find('article')
    if not main:
        return all_items
    
    # Find all section headers (h2)
    sections = main.find_all(['h1', 'h2', 'h3'])
    current_section = "Menu"
    
    for i, section in enumerate(sections):
        section_text = section.get_text(strip=True)
        # Skip main menu title
        if 'MENU' in section_text.upper() and len(section_text) < 20:
            continue
        
        # Update current section
        if section_text and len(section_text) < 50:
            current_section = section_text
        
        # Find items in this section
        # Get the parent container of the section
        section_parent = section.parent
        if not section_parent:
            continue
        
        # Find all paragraphs in this section (until next section)
        next_section = None
        if i + 1 < len(sections):
            next_section = sections[i + 1]
        
        # Get all elements between this section and next
        current_elem = section.find_next_sibling()
        item_paragraphs = []
        
        while current_elem:
            # Stop if we hit the next section
            if next_section and current_elem == next_section:
                break
            
            if current_elem.name == 'p':
                strong_tag = current_elem.find('strong')
                if strong_tag:
                    item_text = strong_tag.get_text(strip=True)
                    # Check if this is a new item (has strong tag with substantial text)
                    # Exclude common non-item text
                    if (item_text and len(item_text) > 2 and 
                        not item_text.upper().startswith('ADD') and
                        item_text.upper() not in ['ALL', 'FOR AGES', 'ALL DISHES'] and
                        not item_text.startswith('(') and
                        'MENU' not in item_text.upper()):
                        # Process previous item if we have one
                        if item_paragraphs:
                            item = process_menu_item(item_paragraphs, soup, current_section)
                            if item:
                                item['menu_type'] = menu_type
                                item['menu_name'] = menu_name
                                all_items.append(item)
                        
                        # Start new item
                        item_paragraphs = [current_elem]
                    else:
                        # Continuation of current item (like "ADD" lines)
                        if item_paragraphs:
                            item_paragraphs.append(current_elem)
                else:
                    # Continuation paragraph (no strong tag) - description or other text
                    if item_paragraphs:
                        item_paragraphs.append(current_elem)
            
            current_elem = current_elem.find_next_sibling()
        
        # Process last item in section
        if item_paragraphs:
            item = process_menu_item(item_paragraphs, soup, current_section)
            if item:
                item['menu_type'] = menu_type
                item['menu_name'] = menu_name
                all_items.append(item)
    
    return all_items

def scrape_merc() -> List[Dict]:
    """Main scraping function"""
    all_items = []
    
    for menu_info in MENU_URLS:
        print(f"\n[INFO] Scraping {menu_info['menu_name']}...")
        url = menu_info['url']
        menu_name = menu_info['menu_name']
        menu_type = menu_info['menu_type']
        
        try:
            html = fetch_menu_html(url)
            if not html:
                print(f"  [ERROR] Failed to fetch HTML for {menu_name}")
                continue
            
            items = parse_menu_html(html, menu_name, menu_type)
            print(f"  [OK] Extracted {len(items)} items")
            all_items.extend(items)
            
        except Exception as e:
            print(f"  [ERROR] Error scraping {menu_name}: {e}")
            continue
    
    return all_items

if __name__ == "__main__":
    print(f"[INFO] Starting scraper for {RESTAURANT_NAME}...")
    items = scrape_merc()
    
    # Save to JSON
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "themercsaratoga_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Scraped {len(items)} items total")
    print(f"[OK] Saved to {output_file}")

