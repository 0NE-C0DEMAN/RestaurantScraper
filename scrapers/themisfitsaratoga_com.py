"""
Scraper for The Misfit Saratoga (themisfitsaratoga.com)
Scrapes menu from HTML page
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup
import requests


RESTAURANT_NAME = "The Misfit Saratoga"
RESTAURANT_URL = "http://www.themisfitsaratoga.com/"

MENU_URL = "https://www.themisfitsaratoga.com/menu/"


def fetch_menu_html() -> Optional[str]:
    """Fetch menu HTML using requests"""
    print("  Fetching menu HTML...")
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'referer': 'https://www.themisfitsaratoga.com/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        cookies = {
            '_ga': 'GA1.1.814041966.1767721144',
            '_ga_W5V1FBJPZD': 'GS2.1.s1767757532$o2$g1$t1767757541$j51$l0$h0'
        }
        
        response = requests.get(MENU_URL, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu: {e}")
        return None


def extract_price(price_text: str) -> Optional[str]:
    """Extract and format price from text"""
    # Check for multi-price pattern like "$11.00/$42.00" (glass/bottle)
    multi_price_match = re.search(r'\$(\d+(?:\.\d{2})?)/\$(\d+(?:\.\d{2})?)', price_text)
    if multi_price_match:
        price1 = multi_price_match.group(1)
        price2 = multi_price_match.group(2)
        # For wine items, typically glass/bottle
        # Check if it's a wine section by context (we'll handle this in process_menu_item)
        return f"${price1}/${price2}"
    
    # Single price pattern like "$17.00" or "17.00"
    price_match = re.search(r'(\d+(?:\.\d{2})?)', price_text)
    if price_match:
        return f"${price_match.group(1)}"
    return None


def extract_all_prices(text: str) -> List[str]:
    """Extract all prices from text (for multi-price items)"""
    # Check for multi-price pattern first
    multi_price_match = re.search(r'\$(\d+(?:\.\d{2})?)/\$(\d+(?:\.\d{2})?)', text)
    if multi_price_match:
        return [f"${multi_price_match.group(1)}", f"${multi_price_match.group(2)}"]
    
    # Otherwise extract all prices
    prices = re.findall(r'(\d+(?:\.\d{2})?)', text)
    return [f"${p}" for p in prices if float(p) > 0]  # Filter out invalid prices


def extract_addons_from_text(text: str) -> str:
    """Extract addon information from text"""
    addons = []
    
    # Look for "Add X $Y" patterns
    add_pattern = r'Add\s+([A-Z][^$]+?)\s+\$?(\d+(?:\.\d{2})?)'
    add_matches = re.finditer(add_pattern, text, re.IGNORECASE)
    for match in add_matches:
        addon_name = match.group(1).strip()
        addon_price = match.group(2)
        if len(addon_name) < 100:
            addons.append(f"{addon_name} +${addon_price}")
    
    # Look for patterns like "+ X $Y" or "with X $Y"
    plus_pattern = r'[+\s]+([A-Z][^$]+?)\s+\$?(\d+(?:\.\d{2})?)'
    plus_matches = re.finditer(plus_pattern, text)
    for match in plus_matches:
        addon_name = match.group(1).strip()
        addon_price = match.group(2)
        if len(addon_name) < 100 and not any(addon_name in a for a in addons):
            addons.append(f"{addon_name} +${addon_price}")
    
    if addons:
        return "Add-ons: " + " / ".join(addons)
    return ""


def process_menu_item(item_elem, soup: BeautifulSoup, current_section: str) -> Optional[Dict]:
    """Process a single menu item"""
    # Extract item name
    title_elem = item_elem.find('h4', class_='offbeat-pli-title')
    if not title_elem:
        return None
    
    item_name = title_elem.get_text(strip=True)
    if not item_name:
        return None
    
    # Extract price
    price_elem = item_elem.find('span', class_='offbeat-pli-price')
    price = None
    if price_elem:
        price_text = price_elem.get_text(strip=True)
        # Check for multi-price pattern like "$11.00/$42.00" (glass/bottle for wine)
        multi_price_match = re.search(r'\$(\d+(?:\.\d{2})?)/\$(\d+(?:\.\d{2})?)', price_text)
        if multi_price_match:
            price1 = multi_price_match.group(1)
            price2 = multi_price_match.group(2)
            # Format as "Glass $X | Bottle $Y" for wine items
            # Check section to determine if it's wine (BUBBLES, WHITE, ROSÉ, RED)
            if current_section in ['BUBBLES', 'WHITE', 'ROSÉ', 'RED']:
                price = f"Glass ${price1} | Bottle ${price2}"
            else:
                # For other items, use generic format
                price = f"${price1} | ${price2}"
        else:
            # Single price
            price_match = re.search(r'(\d+(?:\.\d{2})?)', price_text)
            if price_match:
                price = f"${price_match.group(1)}"
    
    # Extract description
    desc_elem = item_elem.find('div', class_='offbeat-pli-desc')
    description = None
    if desc_elem:
        desc_para = desc_elem.find('p')
        if desc_para:
            description = desc_para.get_text(strip=True)
    
    # Check for add-ons in description
    addons_text = ""
    if description:
        addons_text = extract_addons_from_text(description)
        # Remove addon patterns from description if found
        if addons_text:
            # Clean up description by removing addon patterns
            description = re.sub(r'Add\s+[^$]+\s+\$?(\d+(?:\.\d{2})?)', '', description, flags=re.IGNORECASE)
            description = re.sub(r'[+\s]+([A-Z][^$]+?)\s+\$?(\d+(?:\.\d{2})?)', '', description)
            description = description.strip()
    
    # Check for multi-size pricing in description
    # Look for patterns like "Small $X | Large $Y" or "6\" $X | 12\" $Y"
    if description and not price:
        size_price_pattern = r'([A-Z][a-z]+|\d+"?)\s+\$(\d+(?:\.\d{2})?)\s*\|\s*([A-Z][a-z]+|\d+"?)\s+\$(\d+(?:\.\d{2})?)'
        size_match = re.search(size_price_pattern, description)
        if size_match:
            size1 = size_match.group(1)
            price1 = size_match.group(2)
            size2 = size_match.group(3)
            price2 = size_match.group(4)
            price = f"{size1} ${price1} | {size2} ${price2}"
            # Remove size/price pattern from description
            description = re.sub(size_price_pattern, '', description).strip()
    
    # If no price found, skip this item
    if not price:
        return None
    
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


def scrape_themisfit() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Fetch menu HTML
    print("\n[1] Fetching menu HTML...")
    html = fetch_menu_html()
    
    if not html:
        print("[ERROR] Failed to fetch menu HTML")
        return []
    
    print(f"[OK] Received {len(html)} characters")
    
    # Parse HTML
    print("\n[2] Parsing menu items...")
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all section titles
    section_titles = soup.find_all('h2', class_='edgtf-st-title')
    print(f"  Found {len(section_titles)} sections")
    
    # Find all menu items
    menu_items = soup.find_all('div', class_='offbeat-pricing-list-item')
    print(f"  Found {len(menu_items)} menu items")
    
    # Process each item and determine its section
    current_section = "Menu"
    
    for item_elem in menu_items:
        # Find the section this item belongs to
        # Look backwards for the nearest section title
        prev_section = None
        for section_title in section_titles:
            # Check if this section comes before the item
            if item_elem.find_previous('h2', class_='edgtf-st-title') == section_title:
                section_text = section_title.get_text(strip=True)
                if section_text:
                    current_section = section_text
                    break
        
        item = process_menu_item(item_elem, soup, current_section)
        if item:
            all_items.append(item)
    
    print(f"\n[OK] Extracted {len(all_items)} items")
    
    return all_items


if __name__ == "__main__":
    items = scrape_themisfit()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "themisfitsaratoga_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

