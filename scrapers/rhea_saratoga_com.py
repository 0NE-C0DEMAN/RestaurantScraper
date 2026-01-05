"""
Scraper for Rhea Saratoga (rhea-saratoga.com)
"""
import json
import re
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup

# Get the project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

def fetch_menu_html(url: str, referer: str = None) -> str:
    """Fetch menu HTML from a URL"""
    headers = {
        "Referer": referer or "https://www.rhea-saratoga.com/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def parse_menu_items(soup: BeautifulSoup, menu_name: str, menu_type: str) -> List[Dict]:
    """Parse menu items from HTML"""
    items = []
    
    # Find all h2 headings (section headers)
    sections = soup.find_all('h2', class_='vc_custom_heading')
    
    current_section = "Menu"
    
    # Process each section
    for section_h2 in sections:
        section_name = section_h2.get_text(strip=True)
        if not section_name or len(section_name) < 2:
            continue
        
        current_section = section_name
        
        # Find all menu items after this h2, before next h2
        current = section_h2
        while current:
            current = current.find_next_sibling()
            if not current:
                break
            
            # Stop at next h2 (next section)
            if current.name == 'h2' or (hasattr(current, 'find') and current.find('h2', class_='vc_custom_heading')):
                break
            
            # Look for menu items in this element
            menu_divs = current.find_all('div', class_='db-restaurant-menu')
            
            for menu_div in menu_divs:
                # Get item name
                name_span = menu_div.find('span', class_='db-restaurant-menu-name-with-price')
                if not name_span:
                    continue
                
                # Extract name - it's the text in the span, but we need to remove the label if present
                name_text = name_span.get_text(strip=True)
                # Remove any warning labels
                label = name_span.find('span', class_='db-restaurant-menu-label')
                if label:
                    name_text = name_text.replace(label.get_text(strip=True), '').strip()
                
                item_name = name_text
                
                # Get price
                price_span = menu_div.find('span', class_='db-restaurant-menu-price')
                price = ""
                if price_span:
                    price_text = price_span.get_text(strip=True)
                    # Price might be just a number, format it
                    price_text = price_text.replace('&nbsp;', ' ').strip()
                    if price_text:
                        # Check if it already has $, if not add it
                        if not price_text.startswith('$'):
                            # Try to extract number
                            price_match = re.search(r'(\d+(?:\.\d+)?)', price_text)
                            if price_match:
                                price = f"${price_match.group(1)}"
                            else:
                                price = price_text
                        else:
                            price = price_text
                
                # Get description
                desc_div = menu_div.find('div', class_='db-restaurant-menu-description')
                description = ""
                if desc_div:
                    # Get all text, but clean up nested divs
                    desc_text = desc_div.get_text(separator=' ', strip=True)
                    # Remove page/section markers
                    desc_text = re.sub(r'Page \d+', '', desc_text, flags=re.IGNORECASE)
                    description = desc_text.strip()
                
                # Skip if no price and no description
                if not price and not description:
                    continue
                
                items.append({
                    "name": item_name,
                    "description": description if description else None,
                    "price": price if price else "",
                    "section": current_section,
                    "restaurant_name": "Rhea",
                    "restaurant_url": "https://www.rhea-saratoga.com/",
                    "menu_type": menu_type,
                    "menu_name": menu_name
                })
    
    # If no sections found with h2, try finding menu items directly
    if not items:
        menu_divs = soup.find_all('div', class_='db-restaurant-menu')
        for menu_div in menu_divs:
            name_span = menu_div.find('span', class_='db-restaurant-menu-name-with-price')
            if not name_span:
                continue
            
            name_text = name_span.get_text(strip=True)
            label = name_span.find('span', class_='db-restaurant-menu-label')
            if label:
                name_text = name_text.replace(label.get_text(strip=True), '').strip()
            
            item_name = name_text
            
            price_span = menu_div.find('span', class_='db-restaurant-menu-price')
            price = ""
            if price_span:
                price_text = price_span.get_text(strip=True).replace('&nbsp;', ' ').strip()
                if price_text:
                    price_match = re.search(r'(\d+(?:\.\d+)?)', price_text)
                    if price_match:
                        price = f"${price_match.group(1)}"
            
            desc_div = menu_div.find('div', class_='db-restaurant-menu-description')
            description = ""
            if desc_div:
                description = desc_div.get_text(separator=' ', strip=True)
                description = re.sub(r'Page \d+', '', description, flags=re.IGNORECASE).strip()
            
            if not price and not description:
                continue
            
            items.append({
                "name": item_name,
                "description": description if description else None,
                "price": price if price else "",
                "section": "Menu",
                "restaurant_name": "Rhea",
                "restaurant_url": "https://www.rhea-saratoga.com/",
                "menu_type": menu_type,
                "menu_name": menu_name
            })
    
    return items

def scrape_rhea_saratoga() -> List[Dict]:
    """Scrape menu from Rhea Saratoga website"""
    print("=" * 60)
    print("Scraping Rhea Saratoga (rhea-saratoga.com)")
    print("=" * 60)
    
    all_items = []
    
    # Menu URLs
    menus = [
        {
            "url": "https://www.rhea-saratoga.com/menu/",
            "referer": "https://www.rhea-saratoga.com/menu/drink-menu/",
            "name": "Dinner Menu",
            "type": "Dinner"
        },
        {
            "url": "https://www.rhea-saratoga.com/menu/drink-menu/",
            "referer": "https://www.rhea-saratoga.com/menu/",
            "name": "Drink Menu",
            "type": "Drinks"
        },
        {
            "url": "https://www.rhea-saratoga.com/menu/happy-hour-menu/",
            "referer": "https://www.rhea-saratoga.com/menu/drink-menu/",
            "name": "Happy Hour Menu",
            "type": "Happy Hour"
        }
    ]
    
    for menu_info in menus:
        print(f"\n[{menu_info['name'].upper()}]")
        print(f"  Downloading HTML from: {menu_info['url']}")
        
        try:
            html_content = fetch_menu_html(menu_info['url'], menu_info['referer'])
            print(f"  [OK] Downloaded {len(html_content)} characters")
        except Exception as e:
            print(f"  [ERROR] Failed to download: {e}")
            continue
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract items
        print(f"  Extracting menu items...")
        items = parse_menu_items(soup, menu_info['name'], menu_info['type'])
        all_items.extend(items)
        print(f"  [OK] Extracted {len(items)} items")
    
    # Filter out items with no price and no description
    filtered_items = []
    for item in all_items:
        if item.get('price') or item.get('description'):
            filtered_items.append(item)
    
    print(f"\n[SUMMARY] Total items: {len(filtered_items)} (filtered {len(all_items) - len(filtered_items)} items)")
    all_items = filtered_items
    
    # Save to JSON
    output_file = OUTPUT_DIR / "rhea_saratoga_com.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved {len(all_items)} items to {output_file}")
    
    # Show sample items
    if all_items:
        print(f"\n[4] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            price_str = item.get('price', 'N/A')
            section = item.get('section', 'Menu')
            print(f"  {i}. {item.get('name', 'N/A')} - {price_str} ({section})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items

if __name__ == "__main__":
    scrape_rhea_saratoga()

