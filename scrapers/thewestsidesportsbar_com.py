"""
Scraper for The West Side Sports Bar & Grill (thewestsidesportsbar.com)
Scrapes menu from HTML pages (breakfast and lunch/dinner)
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup
import requests


RESTAURANT_NAME = "The West Side Sports Bar & Grill"
RESTAURANT_URL = "http://www.thewestsidesportsbar.com/"

BREAKFAST_URL = "http://www.thewestsidesportsbar.com/breakfast"
LUNCH_DINNER_URL = "http://www.thewestsidesportsbar.com/lunchdinner"


def fetch_menu_html(url: str, referer: str = None) -> Optional[str]:
    """Fetch menu HTML using requests"""
    try:
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        if referer:
            headers['Referer'] = referer
        
        cookies = {
            'crumb': 'BSErl27akSbcZGMwNmJmZTAyNjIwNjRhYWQzNjVkMGQ5NTAxYWY4',
            'ss_cvr': '766c6169-0136-42a1-bb89-e93bef2749f2|1767761875355|1767761875355|1767761875355|1',
            'ss_cvt': '1767761875355'
        }
        
        response = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu: {e}")
        return None


def extract_price_from_text(text: str) -> Optional[str]:
    """Extract price from text - prices are in parentheses like (8), (13), (16/18/18)"""
    # Look for price patterns in parentheses
    # Single price: (8), (13.50)
    # Multi-price: (16/18/18), (7/9)
    # Multi-size: Cup (7) or Bowl (9), Ten for 19 or Twenty for 33
    
    # First check for multi-size patterns like "Cup (7) or Bowl (9)"
    multi_size_pattern = r'(\w+)\s*\((\d+(?:\.\d{2})?)\)\s+or\s+(\w+)\s*\((\d+(?:\.\d{2})?)\)'
    multi_size_match = re.search(multi_size_pattern, text, re.IGNORECASE)
    if multi_size_match:
        size1 = multi_size_match.group(1)
        price1 = multi_size_match.group(2)
        size2 = multi_size_match.group(3)
        price2 = multi_size_match.group(4)
        return f"{size1} ${price1} | {size2} ${price2}"
    
    # Check for patterns like "Ten for 19 or Twenty for 33"
    count_price_pattern = r'(\w+)\s+for\s+(\d+)\s+or\s+(\w+)\s+for\s+(\d+)'
    count_price_match = re.search(count_price_pattern, text, re.IGNORECASE)
    if count_price_match:
        count1 = count_price_match.group(1)
        price1 = count_price_match.group(2)
        count2 = count_price_match.group(3)
        price2 = count_price_match.group(4)
        return f"{count1} ${price1} | {count2} ${price2}"
    
    # Check for multi-price pattern like (16/18/18) or (7/9)
    multi_price_pattern = r'\((\d+(?:\.\d{2})?)(?:/(\d+(?:\.\d{2})?))+\)'
    multi_price_match = re.search(multi_price_pattern, text)
    if multi_price_match:
        prices = re.findall(r'(\d+(?:\.\d{2})?)', text[multi_price_match.start():multi_price_match.end()])
        if len(prices) > 1:
            # Check if there are labels before the prices (like chicken/steak/shrimp)
            before_text = text[:multi_price_match.start()].strip()
            # Look for item name that might indicate what the prices are for
            item_name = before_text.split(':')[-1].strip() if ':' in before_text else ''
            item_lower = item_name.lower()
            if 'chicken' in item_lower and 'steak' in item_lower and 'shrimp' in item_lower:
                return f"Chicken ${prices[0]} | Steak ${prices[1]} | Shrimp ${prices[2] if len(prices) > 2 else prices[1]}"
            elif 'chicken' in item_lower and 'steak' in item_lower:
                return f"Chicken ${prices[0]} | Steak ${prices[1]}"
            elif len(prices) == 3:
                # Three prices - likely chicken, steak, shrimp
                return f"Chicken ${prices[0]} | Steak ${prices[1]} | Shrimp ${prices[2]}"
            elif len(prices) == 2:
                # Two prices - could be different sizes or options
                return f"${prices[0]} | ${prices[1]}"
            return " | ".join([f"${p}" for p in prices])
    
    # Single price in parentheses - find the LAST price (usually the main price)
    # Sometimes there are multiple prices like "(2) served with ... (8)" - we want the last one
    all_prices = list(re.finditer(r'\((\d+(?:\.\d{2})?)\)', text))
    if all_prices:
        # Use the last price found (usually the main item price)
        last_price = all_prices[-1]
        return f"${last_price.group(1)}"
    
    return None


def extract_addons_from_text(text: str) -> str:
    """Extract addon information from text"""
    addons = []
    
    # Look for "Add X (Y)" patterns
    add_pattern = r'Add\s+([^\(]+?)\s*\((\d+(?:\.\d{2})?)\)'
    add_matches = re.finditer(add_pattern, text, re.IGNORECASE)
    for match in add_matches:
        addon_name = match.group(1).strip()
        addon_price = match.group(2)
        if len(addon_name) < 100:
            addons.append(f"{addon_name} +${addon_price}")
    
    if addons:
        return "Add-ons: " + " / ".join(addons)
    return ""


def process_menu_item(para_elem, soup: BeautifulSoup, current_section: str) -> Optional[Dict]:
    """Process a single menu item from a paragraph element"""
    text = para_elem.get_text(strip=True)
    if not text:
        return None
    
    # Skip if it's just an addon line (starts with "Add" and has price)
    if re.match(r'^Add\s+.*\(\d+\)', text, re.IGNORECASE):
        return None
    
    # Skip if it's a section header (h3) or just descriptive text without prices
    if para_elem.name == 'h3':
        return None
    
    # Extract item name - usually in <strong> tags
    strong_elem = para_elem.find('strong')
    item_name = None
    if strong_elem:
        item_name = strong_elem.get_text(strip=True)
        # Remove the name from the text to get description
        text = text.replace(item_name, '', 1).strip()
    else:
        # If no strong tag, try to extract name from beginning of text
        # Look for pattern like "Item Name: description (price)"
        name_match = re.match(r'^([^:\(]+?):\s*(.+)$', text)
        if name_match:
            item_name = name_match.group(1).strip()
            text = name_match.group(2).strip()
        else:
            # Try to find name before first price
            price_match = re.search(r'\((\d+)', text)
            if price_match:
                item_name = text[:price_match.start()].strip()
                text = text[price_match.start():].strip()
            else:
                return None
    
    if not item_name:
        return None
    
    # Extract price
    price = extract_price_from_text(text)
    if not price:
        return None
    
    # Remove price from text to get description
    # Remove price patterns from text
    text = re.sub(r'\((\d+(?:\.\d{2})?)(?:/(\d+(?:\.\d{2})?))*\)', '', text)
    text = re.sub(r'\w+\s+for\s+\d+\s+or\s+\w+\s+for\s+\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\w+\s*\(\d+\)\s+or\s+\w+\s*\(\d+\)', '', text, flags=re.IGNORECASE)
    text = text.strip()
    
    # Clean up description
    description = text
    if description:
        # Remove trailing colons, commas, etc.
        description = re.sub(r'^[:\s,]+', '', description)
        description = re.sub(r'[:\s,]+$', '', description)
    
    # Extract addons from italic text (usually in <em> tags) - but only if they're in the same paragraph
    # Addons in separate paragraphs will be handled by the main loop
    addons_text = ""
    em_elem = para_elem.find('em')
    if em_elem:
        em_text = em_elem.get_text(strip=True)
        # Only extract if it's NOT a standalone addon line (those are handled separately)
        if not re.match(r'^Add\s+.*\(\d+\)', em_text, re.IGNORECASE):
            addons_text = extract_addons_from_text(em_text)
    
    # Combine description and addons
    if description and addons_text:
        full_description = f"{description}. {addons_text}"
    elif addons_text:
        full_description = addons_text
    else:
        full_description = description
    
    return {
        "name": item_name,
        "description": full_description,
        "price": price,
        "section": current_section,
        "restaurant_name": RESTAURANT_NAME,
        "restaurant_url": RESTAURANT_URL,
        "menu_type": "Menu",
        "menu_name": current_section
    }


def scrape_menu_page(url: str, menu_type: str, referer: str = None) -> List[Dict]:
    """Scrape a single menu page"""
    print(f"\n  Fetching {menu_type} menu...")
    html = fetch_menu_html(url, referer)
    
    if not html:
        print(f"  [ERROR] Failed to fetch {menu_type} menu")
        return []
    
    print(f"  [OK] Received {len(html)} characters")
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main content area
    content_div = soup.find('div', class_='sqs-html-content')
    if not content_div:
        print(f"  [ERROR] Could not find menu content")
        return []
    
    all_items = []
    current_section = menu_type
    
    # Find the main h1 title to determine the menu type
    h1_elem = content_div.find('h1')
    if h1_elem:
        h1_text = h1_elem.get_text(strip=True)
        if h1_text:
            current_section = h1_text
    
    # Find all h3 (section headers) and p (menu items)
    elements = content_div.find_all(['h3', 'p'])
    
    i = 0
    while i < len(elements):
        elem = elements[i]
        
        if elem.name == 'h3':
            # This is a section header
            section_text = elem.get_text(strip=True)
            # Skip h3 that are just time/date info (like "SERVED SATURDAY AND SUNDAY...")
            if (section_text and 
                len(section_text) < 100 and 
                not any(word in section_text.upper() for word in ['SERVED', 'ONLY', 'FROM', 'TO', 'AM', 'PM', 'AVAILABLE AFTER'])):
                current_section = section_text
        elif elem.name == 'p':
            # This might be a menu item
            # Check if it's an addon line (will be attached to previous item or next item)
            if elem.find('em'):
                em_text = elem.find('em').get_text(strip=True)
                # If it's an addon line, attach it to the previous item if it exists
                if re.match(r'^Add\s+.*\(\d+\)', em_text, re.IGNORECASE):
                    if all_items:
                        # Add this addon to the last item's description
                        addon_text = extract_addons_from_text(em_text)
                        if addon_text and addon_text not in all_items[-1]['description']:
                            last_item = all_items[-1]
                            if last_item['description']:
                                last_item['description'] = f"{last_item['description']}. {addon_text}"
                            else:
                                last_item['description'] = addon_text
                    # Skip this paragraph - it's just an addon, not a menu item
                    i += 1
                    continue
            
            # Skip if it's just a list of addon items without a main item name
            text = elem.get_text(strip=True)
            if not elem.find('strong') and not re.search(r'\((\d+)', text):
                # No strong tag and no price - likely just descriptive text
                i += 1
                continue
            
            # Skip if it's just a side/item list without prices (like "Sausage, bacon, Canadian bacon (4)")
            # These should be addons, not separate items
            if not elem.find('strong') and re.search(r'^[^:]+,\s+[^:]+\(\d+\)$', text):
                # Looks like a list of addon items - attach to previous item if it exists
                if all_items:
                    addon_text = extract_addons_from_text(text)
                    if addon_text:
                        last_item = all_items[-1]
                        if last_item['description']:
                            last_item['description'] = f"{last_item['description']}. {addon_text}"
                        else:
                            last_item['description'] = addon_text
                i += 1
                continue
            
            item = process_menu_item(elem, soup, current_section)
            if item:
                # Check if next element is an addon and include it (only once)
                if i + 1 < len(elements):
                    next_elem = elements[i + 1]
                    if next_elem.name == 'p' and next_elem.find('em'):
                        em_text = next_elem.find('em').get_text(strip=True)
                        if re.match(r'^Add\s+.*\(\d+\)', em_text, re.IGNORECASE):
                            addon_text = extract_addons_from_text(em_text)
                            if addon_text and addon_text not in item['description']:
                                if item['description']:
                                    item['description'] = f"{item['description']}. {addon_text}"
                                else:
                                    item['description'] = addon_text
                
                all_items.append(item)
        
        i += 1
    
    print(f"  [OK] Extracted {len(all_items)} items from {menu_type}")
    
    return all_items


def scrape_westside() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Scrape breakfast menu
    breakfast_items = scrape_menu_page(BREAKFAST_URL, "Breakfast")
    all_items.extend(breakfast_items)
    
    # Scrape lunch & dinner menu
    lunch_dinner_items = scrape_menu_page(LUNCH_DINNER_URL, "Lunch & Dinner", BREAKFAST_URL)
    all_items.extend(lunch_dinner_items)
    
    print(f"\n[OK] Extracted {len(all_items)} items total")
    
    return all_items


if __name__ == "__main__":
    items = scrape_westside()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "thewestsidesportsbar_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

