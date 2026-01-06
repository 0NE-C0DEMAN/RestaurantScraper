"""
Scraper for Sweet Mimi's Cafe & Bakery (sweetmimiscafe.com)
Scrapes menu from multiple pages: Cafe Menus, Specials Menus, Baked Goods, and Specialty Cakes
"""

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pathlib import Path


def fetch_menu_html(url: str, referer: str) -> Optional[str]:
    """Download menu HTML from a page"""
    headers = {
        "Referer": referer,
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return None


def format_price(price_text: str) -> str:
    """Format price text to handle multiple prices and sizes"""
    if not price_text:
        return ""
    
    price_text = price_text.strip()
    
    # Handle multiple prices separated by comma (e.g., "9.50, 18.25")
    if ',' in price_text:
        prices = [p.strip() for p in price_text.split(',')]
        formatted_prices = []
        for price in prices:
            # Extract numeric price
            price_match = re.search(r'([\d.]+)', price)
            if price_match:
                formatted_prices.append(f"${price_match.group(1)}")
        if len(formatted_prices) > 1:
            return " | ".join(formatted_prices)
        elif formatted_prices:
            return formatted_prices[0]
    
    # Handle "OR" patterns (e.g., "WHOLE 6 OR HALF 3")
    if ' OR ' in price_text.upper():
        parts = re.split(r'\s+OR\s+', price_text, flags=re.IGNORECASE)
        formatted_parts = []
        for part in parts:
            part = part.strip()
            # Look for size and price pattern
            size_price_match = re.search(r'([A-Z\s]+?)\s*([\d.]+)', part, re.IGNORECASE)
            if size_price_match:
                size = size_price_match.group(1).strip()
                price = size_price_match.group(2)
                formatted_parts.append(f"{size} ${price}")
            else:
                # Just price
                price_match = re.search(r'([\d.]+)', part)
                if price_match:
                    formatted_parts.append(f"${price_match.group(1)}")
        if formatted_parts:
            return " | ".join(formatted_parts)
    
    # Handle "for two X, for one Y" patterns
    for_two_match = re.search(r'for two\s+([\d.]+)', price_text, re.IGNORECASE)
    for_one_match = re.search(r'for one\s+([\d.]+)', price_text, re.IGNORECASE)
    if for_two_match and for_one_match:
        return f"For Two ${for_two_match.group(1)} | For One ${for_one_match.group(1)}"
    
    # Single price - extract numeric value
    price_match = re.search(r'([\d.]+)', price_text)
    if price_match:
        return f"${price_match.group(1)}"
    
    return price_text


def extract_addons(text: str) -> List[str]:
    """Extract add-on information from text"""
    addons = []
    
    # Pattern: (Add X +Y) or (Add X +Y.XX)
    addon_pattern = r'\(Add\s+([^+)]+?)\s*\+([\d.]+)\)'
    matches = re.findall(addon_pattern, text, re.IGNORECASE)
    for addon_name, price in matches:
        # Fix common typos like "+150" -> "+1.50"
        if len(price) == 3 and price.startswith('1'):
            price = f"{price[0]}.{price[1:]}"
        addons.append(f"{addon_name.strip()} +${price}")
    
    # Pattern: Add X +Y (without parentheses) - but not "Add one" in "for one"
    addon_pattern2 = r'(?<!for\s)(?<!Serving\s)Add\s+([^+]+?)\s*\+([\d.]+)'
    matches2 = re.findall(addon_pattern2, text, re.IGNORECASE)
    for addon_name, price in matches2:
        # Fix common typos
        if len(price) == 3 and price.startswith('1'):
            price = f"{price[0]}.{price[1:]}"
        addon_text = f"{addon_name.strip()} +${price}"
        if addon_text not in addons:
            addons.append(addon_text)
    
    return addons


def parse_menu_items(soup: BeautifulSoup, menu_name: str, menu_type: str) -> List[Dict]:
    """Parse menu items from HTML"""
    items = []
    current_section = None
    
    # Find the main content area (usually in divs with class containing "rte" or "body-size")
    content_divs = soup.find_all('div', class_=lambda x: x and ('rte' in str(x) or 'body-size' in str(x)))  # pyright: ignore[reportArgumentType]
    
    for content_div in content_divs:
        # Process all child elements in order
        for element in content_div.children:
            if not hasattr(element, 'name'):
                continue
            
            if element.name == 'h3':
                # New section
                current_section = element.get_text(strip=True)
                continue
            
            elif element.name == 'p':
                # Process paragraph - may contain one or more items
                text = element.get_text(separator=' ', strip=True)
                if not text or len(text) < 3:
                    continue
                
                # Find all strong tags in this paragraph
                strong_tags = element.find_all('strong')
                
                if not strong_tags:
                    continue
                
                # Process each strong tag as a potential item
                # Get full paragraph text first for better price matching
                full_para_text = element.get_text(separator=' ', strip=True)
                
                for i, strong in enumerate(strong_tags):
                    item_name = strong.get_text(strip=True)
                    
                    # Skip if too short or just a number
                    if len(item_name) < 3 or item_name.replace('.', '').isdigit():
                        continue
                    
                    # Check if price is in the same strong tag
                    name_price_match = re.match(r'^(.+?)\s+([\d.,\s]+)$', item_name)
                    if name_price_match:
                        item_name = name_price_match.group(1).strip()
                        price_text = name_price_match.group(2).strip()
                    else:
                        # Check if next strong tag is a price
                        if i + 1 < len(strong_tags):
                            next_strong = strong_tags[i + 1]
                            next_text = next_strong.get_text(strip=True)
                            # Check if it's just a price
                            if re.match(r'^[\d.,\s]+$', next_text):
                                price_text = next_text
                                # Skip the next strong tag in next iteration
                                i += 1
                            else:
                                price_text = ""
                        else:
                            price_text = ""
                    
                    # Get description - text after this strong tag until next strong tag or end of paragraph
                    description_parts = []
                    current = strong.next_sibling
                    next_strong_index = i + 1 if i + 1 < len(strong_tags) else None
                    
                    while current:
                        if hasattr(current, 'name'):
                            if current.name == 'strong':
                                # If this is the next strong tag and it's a price, skip it
                                if next_strong_index and current == strong_tags[next_strong_index]:
                                    # Check if it's just a price
                                    if re.match(r'^[\d.,\s]+$', current.get_text(strip=True)):
                                        break
                                else:
                                    break
                            description_parts.append(current.get_text(strip=True))
                        else:
                            text = str(current).strip()
                            if text:
                                description_parts.append(text)
                        current = current.next_sibling
                    
                    description = ' '.join(description_parts).strip()
                    
                    # Clean up description - remove <br/> artifacts and extra spaces
                    description = description.replace('<br/>', ' ').replace('<br>', ' ')
                    description = re.sub(r'\s+', ' ', description).strip()
                    
                    # Use full paragraph text for better matching (remove item name)
                    search_text = full_para_text.replace(item_name, '', 1).strip()
                    
                    # Pattern: "(1) X, (2) Y, or (3) Z" - e.g., "(1) egg 4.75, (2) 7.75, or (3) 10"
                    if not price_text:
                        # Match pattern: (1) egg 4.75, (2) 7.75, or (3) 10
                        # Search in both description and full paragraph text
                        search_texts = [search_text, description, full_para_text]
                        for search_txt in search_texts:
                            multi_price_pattern1 = r'\((\d+)\)\s*(?:egg\s+)?([\d.]+)'
                            matches1 = re.findall(multi_price_pattern1, search_txt)
                            if len(matches1) >= 2:  # At least 2 prices
                                price_parts = []
                                for match in matches1:
                                    size = f"({match[0]})"
                                    price = match[1]
                                    price_parts.append(f"{size} ${price}")
                                if price_parts:
                                    price_text = " | ".join(price_parts)
                                    # Remove price info from description
                                    description = re.sub(r'\(\d+\)\s*(?:egg\s+)?[\d.]+\s*,?\s*(?:or\s*)?', '', description, flags=re.IGNORECASE)
                                    break
                    
                    # Pattern: "Full stack (3) X, short stack (2) Y, solo (1) Z"
                    if not price_text:
                        # Search in both description and full paragraph text
                        search_texts = [search_text, description, full_para_text]
                        for search_txt in search_texts:
                            multi_price_pattern2 = r'(Full stack|short stack|solo)\s*\((\d+)\)\s*([\d.]+)'
                            matches2 = re.findall(multi_price_pattern2, search_txt, re.IGNORECASE)
                            if matches2:
                                price_parts = []
                                for match in matches2:
                                    size = f"{match[0].title()} ({match[1]})"
                                    price = match[2]
                                    price_parts.append(f"{size} ${price}")
                                if price_parts:
                                    price_text = " | ".join(price_parts)
                                    # Remove price info from description
                                    for match in matches2:
                                        pattern = rf'{re.escape(match[0])}\s*\(\d+\)\s*[\d.]+\s*,?\s*'
                                        description = re.sub(pattern, '', description, flags=re.IGNORECASE)
                                    break
                    
                    # Pattern: "Serving for two X, for one Y"
                    if not price_text:
                        # Search in both description and full paragraph text
                        search_texts = [search_text, description, full_para_text]
                        for search_txt in search_texts:
                            for_two_match = re.search(r'Serving\s+for\s+two\s+(\d+)', search_txt, re.IGNORECASE)
                            for_one_match = re.search(r'for\s+one\s+([\d.]+)', search_txt, re.IGNORECASE)
                            if for_two_match and for_one_match:
                                price_text = f"For Two ${for_two_match.group(1)} | For One ${for_one_match.group(1)}"
                                description = re.sub(r'Serving\s+for\s+two\s+\d+\s*,?\s*for\s+one\s+[\d.]+', '', description, flags=re.IGNORECASE)
                                break
                    
                    # Pattern: "WHOLE X OR HALF Y" - check in item name first
                    if not price_text and 'OR HALF' in item_name.upper():
                        whole_half_match = re.search(r'WHOLE\s+(\d+)\s+OR\s+HALF\s+(\d+)', item_name, re.IGNORECASE)
                        if whole_half_match:
                            price_text = f"Whole ${whole_half_match.group(1)} | Half ${whole_half_match.group(2)}"
                            # Update item name to remove price
                            item_name = re.sub(r'\s+WHOLE\s+\d+\s+OR\s+HALF\s+\d+', '', item_name, flags=re.IGNORECASE)
                    
                    # Extract add-ons
                    addons = extract_addons(description)
                    
                    # Clean up description
                    if addons:
                        for addon in addons:
                            addon_name = addon.split(' +')[0]
                            description = re.sub(rf'\(Add\s+{re.escape(addon_name)}\s*\+[\d.]+\)', '', description, flags=re.IGNORECASE)
                            description = re.sub(rf'Add\s+{re.escape(addon_name)}\s*\+[\d.]+', '', description, flags=re.IGNORECASE)
                        description = re.sub(r'\s+', ' ', description).strip()
                    
                    # Format price
                    formatted_price = format_price(price_text) if price_text else ""
                    
                    # Skip if no price and no description
                    if not formatted_price and not description:
                        continue
                    
                    # Add add-ons to description if present
                    if addons:
                        addons_text = " / ".join(addons)
                        if description:
                            description = f"{description}. Add-ons: {addons_text}"
                        else:
                            description = f"Add-ons: {addons_text}"
                    
                    items.append({
                        "name": item_name,
                        "description": description if description else None,
                        "price": formatted_price,
                        "section": current_section or menu_name,
                        "restaurant_name": "Sweet Mimi's Cafe & Bakery",
                        "restaurant_url": "https://sweetmimiscafe.com/",
                        "menu_type": menu_type,
                        "menu_name": menu_name
                    })
            
            elif element.name == 'h5':
                # Sometimes items are in h5 tags (like in baked goods)
                strong = element.find('strong')
                if strong:
                    item_text = strong.get_text(strip=True)
                    
                    # Extract name and price
                    name_price_match = re.match(r'^(.+?)\s+\$?([\d.,\s]+)$', item_text)
                    if name_price_match:
                        item_name = name_price_match.group(1).strip()
                        price_text = name_price_match.group(2).strip()
                        
                        formatted_price = format_price(price_text)
                        
                        if formatted_price:
                            items.append({
                                "name": item_name,
                                "description": None,
                                "price": formatted_price,
                                "section": current_section or menu_name,
                                "restaurant_name": "Sweet Mimi's Cafe & Bakery",
                                "restaurant_url": "https://sweetmimiscafe.com/",
                                "menu_type": menu_type,
                                "menu_name": menu_name
                            })
    
    return items


def scrape_sweetmimiscafe() -> List[Dict]:
    """Main scraping function for Sweet Mimi's Cafe"""
    print("=" * 60)
    print("Scraping Sweet Mimi's Cafe & Bakery (sweetmimiscafe.com)")
    print("=" * 60)
    
    menus = [
        {
            "name": "Cafe Menus",
            "url": "https://sweetmimiscafe.com/pages/cafe-menus",
            "referer": "https://sweetmimiscafe.com/pages/specials-menus",
            "type": "Cafe Menu"
        },
        {
            "name": "Specials Menus",
            "url": "https://sweetmimiscafe.com/pages/specials-menus",
            "referer": "https://sweetmimiscafe.com/pages/cafe-menus",
            "type": "Specials"
        },
        {
            "name": "Baked Goods",
            "url": "https://sweetmimiscafe.com/pages/baked-goods",
            "referer": "https://sweetmimiscafe.com/pages/baked-goods",
            "type": "Baked Goods"
        },
        {
            "name": "Specialty Cakes",
            "url": "https://sweetmimiscafe.com/pages/specialty-cakes",
            "referer": "https://sweetmimiscafe.com/pages/baked-goods",
            "type": "Specialty Cakes"
        }
    ]
    
    all_items = []
    
    for menu in menus:
        print(f"\n[1] Downloading {menu['name']}...")
        html_content = fetch_menu_html(menu['url'], menu['referer'])
        
        if not html_content:
            print(f"  [ERROR] Failed to download {menu['name']}")
            continue
        
        print(f"  [OK] Downloaded {len(html_content)} characters")
        
        print(f"\n[2] Parsing {menu['name']}...")
        soup = BeautifulSoup(html_content, 'html.parser')
        items = parse_menu_items(soup, menu['name'], menu['type'])
        
        print(f"  [OK] Extracted {len(items)} items from {menu['name']}")
        all_items.extend(items)
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    return all_items


if __name__ == "__main__":
    items = scrape_sweetmimiscafe()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "sweetmimiscafe_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

