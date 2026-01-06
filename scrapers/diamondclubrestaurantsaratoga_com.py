"""
Scraper for Diamond Club Restaurant (diamondclubrestaurantsaratoga.com)
Scrapes menu from the menu page with multiple sections: Starters, Soup & Salad, Table Fare, Entree, Desserts, Kids Menu
"""

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pathlib import Path


def fetch_menu_html(url: str) -> Optional[str]:
    """Download menu HTML from the menu page"""
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "cookie": "_ga=GA1.1.92898778.1767685482; _ga_LCD8MKN18L=GS2.1.s1767685482^$o1^$g1^$t1767686033^$j37^$l0^$h0^",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://www.diamondclubrestaurantsaratoga.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return None


def extract_price_from_name(name_text: str) -> tuple[str, str]:
    """Extract price and clean name from item name text"""
    # Pattern: "ITEM NAME $XX V" or "ITEM NAME $XX GF" etc.
    # Extract price
    price_match = re.search(r'\$(\d+(?:\.\d+)?)', name_text)
    price = price_match.group(0) if price_match else ""
    
    # Clean name - remove price and dietary labels (V, GF, GFV, etc.)
    name = name_text
    if price_match:
        # Remove everything from the price onwards
        name = name[:price_match.start()].strip()
    
    # Remove trailing dietary labels that might remain
    name = re.sub(r'\s+(V|GF|GFV)$', '', name, flags=re.IGNORECASE)
    name = name.strip()
    
    return name, price


def extract_addons(text: str) -> List[str]:
    """Extract add-on information from text"""
    addons = []
    
    # Pattern: "Add X $Y" or "Add X $Y.XX"
    addon_patterns = [
        r'Add\s+([^$]+?)\s+\$(\d+(?:\.\d+)?)',
        r'Add\s+([^$]+?)\s*\$(\d+(?:\.\d+)?)',
    ]
    
    for pattern in addon_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            addon_name = match.group(1).strip()
            addon_price = match.group(2)
            addons.append(f"{addon_name} +${addon_price}")
    
    return addons


def parse_menu_items(html: str) -> List[Dict]:
    """Parse menu items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all tab content sections
    tab_contents = soup.find_all('div', class_='tab-content')
    
    for tab in tab_contents:
        # Get section name
        section_header = tab.find('h2')
        if not section_header:
            continue
        
        section_name = section_header.get_text(strip=True)
        
        # Check for section-wide add-ons (like "Add Grilled Chicken, Salmon, or Steak $9")
        # This typically appears in the "Soup & Salad" section
        section_addon_text = None
        section_text = tab.get_text()
        # Look for add-on notes that apply to the whole section (usually in a <p> tag)
        section_addon_match = re.search(r'Add\s+(Grilled Chicken|Salmon|Steak|Chicken|Salmon|Steak)[^$]*\$(\d+)', section_text, re.IGNORECASE)
        if section_addon_match:
            section_addon_text = section_addon_match.group(0)
        
        # Find all list items in this section
        list_items = tab.find_all('li')
        
        for li in list_items:
            # Find strong tags (item names with prices)
            strong_tags = li.find_all('strong')
            
            if not strong_tags:
                continue
            
            # First strong tag contains the item name and price
            name_strong = strong_tags[0]
            name_text = name_strong.get_text(strip=True)
            
            # Extract name and price
            item_name, item_price = extract_price_from_name(name_text)
            
            if not item_name or not item_price:
                continue
            
            # Get full text of the list item
            full_text = li.get_text(separator=' ', strip=True)
            
            # Get description - everything after the item name and price
            # Remove the name and price from the full text
            description = full_text
            # Remove item name
            description = re.sub(re.escape(item_name), '', description, flags=re.IGNORECASE)
            # Remove price
            description = re.sub(re.escape(item_price), '', description)
            # Remove dietary labels
            description = re.sub(r'\b(V|GF|GFV)\b', '', description, flags=re.IGNORECASE)
            description = description.strip()
            
            # Extract add-ons from the full item text
            addons = []
            
            # Pattern 1: "Add X $Y" in the description
            addon_matches = re.finditer(r'Add\s+([^$]+?)\s+\$(\d+(?:\.\d+)?)', full_text, re.IGNORECASE)
            for match in addon_matches:
                addon_name = match.group(1).strip()
                addon_price = match.group(2)
                addons.append(f"{addon_name} +${addon_price}")
            
            # Pattern 2: Check for standalone prices in other strong tags (like "$1.50" for cheese)
            for strong in strong_tags[1:]:
                strong_text = strong.get_text(strip=True)
                # If it's just a price, it's likely an add-on
                if re.match(r'^\$[\d.]+$', strong_text):
                    # Look for context before this strong tag in the parent li
                    li_text_before_strong = ""
                    for sibling in strong.previous_siblings:
                        if isinstance(sibling, str):
                            li_text_before_strong = sibling.strip() + " " + li_text_before_strong
                        elif hasattr(sibling, 'get_text'):
                            li_text_before_strong = sibling.get_text(strip=True) + " " + li_text_before_strong
                    
                    # Try to find add-on name in previous text
                    addon_match = re.search(r'(Add|with)\s+([^$]+?)\s*$', li_text_before_strong, re.IGNORECASE)
                    if addon_match:
                        addon_name = addon_match.group(2).strip()
                        addons.append(f"{addon_name} +{strong_text}")
            
            # Apply section-wide add-ons only to relevant items (salads in Soup & Salad section)
            if section_addon_text and section_name == "Soup & Salad" and "SALAD" in item_name.upper():
                section_addons = extract_addons(section_addon_text)
                addons.extend(section_addons)
            
            # Remove duplicates from addons
            seen = set()
            unique_addons = []
            for addon in addons:
                if addon not in seen:
                    seen.add(addon)
                    unique_addons.append(addon)
            addons = unique_addons
            
            # Remove add-on text from description to avoid duplication
            if addons:
                for addon in addons:
                    # Extract the addon pattern from the addon string
                    addon_name_part = addon.split(' +')[0].strip()
                    addon_price_part = addon.split(' +')[1] if ' +' in addon else ""
                    # Remove "Add X $Y" patterns from description
                    description = re.sub(rf'Add\s+{re.escape(addon_name_part)}\s+\{addon_price_part}', '', description, flags=re.IGNORECASE)
                    description = re.sub(rf'Add\s+{re.escape(addon_name_part)}\s+\${addon_price_part}', '', description, flags=re.IGNORECASE)
            
            # Clean up description
            description = re.sub(r'\s+', ' ', description).strip()
            # Remove trailing punctuation
            description = re.sub(r'[.\s]+$', '', description)
            
            # Append add-ons to description if any
            if addons:
                addon_text = " / ".join(addons)
                if description:
                    description = f"{description}. Add-ons: {addon_text}"
                else:
                    description = f"Add-ons: {addon_text}"
            
            item = {
                "name": item_name,
                "description": description if description else None,
                "price": item_price,
                "section": section_name,
                "restaurant_name": "Diamond Club Restaurant",
                "restaurant_url": "https://www.diamondclubrestaurantsaratoga.com/",
                "menu_type": "Main Menu",
                "menu_name": "Main Menu"
            }
            
            all_items.append(item)
    
    return all_items


def scrape_diamondclub() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print("Scraping Diamond Club Restaurant (diamondclubrestaurantsaratoga.com)")
    print("=" * 60)
    
    menu_url = "https://www.diamondclubrestaurantsaratoga.com/menu/"
    
    print(f"\n[1] Downloading menu HTML...")
    html = fetch_menu_html(menu_url)
    
    if not html:
        print("[ERROR] Failed to download menu HTML")
        return []
    
    print(f"[OK] Downloaded {len(html)} characters")
    
    print(f"\n[2] Parsing menu items...")
    items = parse_menu_items(html)
    
    print(f"[OK] Extracted {len(items)} items")
    
    # Save to JSON
    output_path = Path("output/diamondclubrestaurantsaratoga_com.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_path}")
    
    return items


if __name__ == "__main__":
    scrape_diamondclub()

