"""
Scraper for: https://www.fornobistro.com/
Uses requests to fetch HTML menu from SinglePlatform API and BeautifulSoup for parsing
Scrapes Dinner, Wine List, At the Bar, Happy Hour, and DZ At Home menus
"""

import json
import re
import requests
from pathlib import Path
from typing import Dict, List

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("Warning: beautifulsoup4 not installed.")


def scrape_fornobistro_menu(url: str) -> List[Dict]:
    """Scrape menu items from fornobistro.com"""
    all_items = []
    restaurant_name = "Forno Bistro"
    
    # Menu configurations: (menu_id(s), menu_name)
    # Wine List and Bar menu have multiple menu IDs
    menus = [
        (1292504, "Dinner"),
        ([4069785, 1814242, 1814243], "Wine List"),  # Multiple wine sections
        ([4629735, 4069785, 1814239, 1814242, 1814243, 5053857], "At the Bar"),  # Multiple bar sections
        (4017858, "Happy Hour"),
        (1292625, "DZ At Home"),
    ]
    
    print(f"Scraping: {url}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').rstrip('/').replace('/', '_').replace('.', '_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    if not BS4_AVAILABLE:
        print("ERROR: beautifulsoup4 is required for HTML parsing.")
        return []
    
    # Headers from curl command
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'referer': 'https://fornobistro.com/',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'iframe',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'cross-site',
        'sec-fetch-storage-access': 'active',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    try:
        for menu_config in menus:
            menu_id_or_ids = menu_config[0]
            menu_name = menu_config[1]
            
            # Handle multiple menu IDs (for Wine List and Bar menu)
            if isinstance(menu_id_or_ids, list):
                # Build URL with multiple display_menu parameters
                menu_ids_str = '&'.join([f'display_menu={menu_id}' for menu_id in menu_id_or_ids])
                menu_widget_url = f"https://places.singleplatform.com/forno-tuscano/menu_widget?api_key=ke09z8icq4xu8uiiccighy1bw&{menu_ids_str}&hide_cover_photo=true&hide_disclaimer=true&widget_background_color=rgba%280%2C%200%2C%200%2C%200%29"
            else:
                menu_widget_url = f"https://places.singleplatform.com/forno-tuscano/menu_widget?api_key=ke09z8icq4xu8uiiccighy1bw&display_menu={menu_id_or_ids}&hide_cover_photo=true&hide_disclaimer=true&widget_background_color=rgba%280%2C%200%2C%200%2C%200%29"
            
            print(f"Fetching {menu_name} Menu HTML...")
            response = requests.get(menu_widget_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            print(f"[OK] Received {menu_name} Menu HTML content\n")
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            print(f"Parsing menu items from {menu_name} Menu...")
            items = extract_menu_items_from_html(soup, menu_name, restaurant_name)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = url
                    item['menu_name'] = menu_name
                all_items.extend(items)
            
            print(f"[OK] Extracted {len(items)} items from {menu_name} Menu\n")
        
        print(f"[OK] Extracted {len(all_items)} total items from all menus\n")
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Deduplicate items based on name, description, price, and menu_type
    unique_items = []
    seen = set()
    for item in all_items:
        item_tuple = (item['name'], item['description'], item['price'], item['menu_type'], item['menu_name'])
        if item_tuple not in seen:
            unique_items.append(item)
            seen.add(item_tuple)
    
    # Save to JSON
    if unique_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(unique_items, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(unique_items)} unique items to: {output_json}")
    
    return unique_items


def extract_menu_items_from_html(soup: BeautifulSoup, menu_name: str = "Dinner", restaurant_name: str = "Forno Bistro") -> List[Dict]:
    """Extract menu items from HTML soup"""
    items = []
    
    # Find the menu section - look for h2 with menu name
    menu_headers = []
    
    if menu_name == 'Wine List' or menu_name == 'At the Bar' or menu_name == 'Happy Hour' or menu_name == 'DZ At Home':
        # For these menus, find all h2 with menu-title class (they may have multiple sections)
        menu_headers = soup.find_all('h2', class_='menu-title')
        if not menu_headers:
            print(f"  [WARNING] Could not find {menu_name} Menu headers")
            return []
        print(f"  Found {len(menu_headers)} {menu_name} Menu sections")
    else:
        patterns = [
            rf'{menu_name} Menu',
            rf'{menu_name}',
        ]
        
        menu_header = None
        for pattern in patterns:
            menu_header = soup.find('h2', class_='menu-title', string=re.compile(pattern, re.I))
            if menu_header:
                menu_headers = [menu_header]
                break
        
        if not menu_headers:
            print(f"  [WARNING] Could not find {menu_name} Menu header")
            return []
        
        print(f"  Found {menu_name} Menu section")
    
    # Find all menu containers
    menu_containers = []
    for menu_header in menu_headers:
        menu_container = menu_header.find_parent('div', class_='menu')
        if not menu_container:
            # Try to find the next menu div
            menu_container = menu_header.find_next('div', class_='menu')
        if menu_container and menu_container not in menu_containers:
            menu_containers.append(menu_container)
    
    if not menu_containers:
        print("  [WARNING] Could not find menu container(s)")
        return []
    
    # Find all sections within all menu containers
    all_sections = []
    for menu_container in menu_containers:
        sections = menu_container.find_all('div', class_='section')
        all_sections.extend(sections)
    
    print(f"  Found {len(all_sections)} sections in {menu_name} Menu")
    
    for section in all_sections:
        # Get section title
        section_title_elem = section.find('div', class_='title')
        if section_title_elem:
            section_title = section_title_elem.find('h3')
            if section_title:
                section_name = section_title.get_text(strip=True)
                print(f"  Processing section: {section_name}")
            else:
                section_name = "Menu"
        else:
            section_name = "Menu"
        
        # Get section-level add-ons (like "Add Chicken for $8, Fish for $15...")
        section_addons = ""
        section_desc_elems = section.find_all('div', class_='description')
        for desc_elem in section_desc_elems:
            classes = desc_elem.get('class', [])
            if 'text' in classes:
                desc_text = desc_elem.get_text(strip=True)
                if desc_text and ('Add' in desc_text or 'add' in desc_text):
                    section_addons = desc_text
                    break
        
        # Find all items in this section
        section_items = section.find_all('div', class_=re.compile(r'item'))
        
        for item_elem in section_items:
            # Must have item-title-row to be a real item
            item_title_row = item_elem.find('div', class_='item-title-row')
            if not item_title_row:
                continue
            
            # Get item name
            item_title_elem = item_elem.find('h4', class_='item-title')
            if not item_title_elem:
                continue
            
            item_name = item_title_elem.get_text(strip=True)
            
            # Get item description
            description = ""
            item_desc_elems = item_elem.find_all('div', class_='description')
            for desc_elem in item_desc_elems:
                classes = desc_elem.get('class', [])
                if 'text' in classes:
                    desc_text = desc_elem.get_text(strip=True)
                    if desc_text and desc_text.lower() not in ['small plates', 'small plate']:
                        description = desc_text
                        break
            
            # Extract item-level add-ons
            item_addons = []
            addon_divs = item_elem.find_all('div', class_='addon', recursive=True)
            for addon_div in addon_divs:
                parent_item = addon_div.find_parent('div', class_=re.compile(r'item'))
                if parent_item != item_elem:
                    continue
                
                title_span = addon_div.find('span', class_='title')
                if title_span:
                    title_li = title_span.find('li')
                    if title_li:
                        addon_title = title_li.get_text(strip=True)
                    else:
                        addon_title = title_span.get_text(strip=True)
                else:
                    continue
                
                price_span = addon_div.find('span', class_='price')
                if price_span:
                    price_li = price_span.find('li')
                    if price_li:
                        addon_price = price_li.get_text(strip=True)
                    else:
                        addon_price = price_span.get_text(strip=True)
                    
                    if addon_title and addon_price:
                        # Remove "Add" prefix if it's already in the title
                        addon_title_clean = addon_title.replace("Add ", "").strip()
                        item_addons.append(f"Add {addon_title_clean}: {addon_price}")
            
            # Get price - handle multiple prices (like Appetizer/Entrée)
            price = ""
            
            # First check for multiprice-group (items with multiple price options)
            # Make sure it's a direct child or descendant of this item, not from another item
            multiprice_group = item_elem.find('div', class_='multiprice-group')
            if multiprice_group:
                # Verify this multiprice-group belongs to this item by checking it's within the item's structure
                # and not in a sibling item
                parent_item = multiprice_group.find_parent('div', class_=re.compile(r'item'))
                if parent_item == item_elem:
                    multiprices = multiprice_group.find_all('div', class_='multiprice')
                    if multiprices:
                        prices = []
                        for mp in multiprices:
                            title_span = mp.find('span', class_='title')
                            price_span = mp.find('span', class_='price')
                            if title_span and price_span:
                                title_text = title_span.get_text(strip=True)
                                price_text = price_span.get_text(strip=True)
                                if title_text and price_text:
                                    prices.append(f"{title_text} {price_text}")
                        if prices:
                            price = " / ".join(prices)
            
            # If no multiprice, check for regular price
            if not price:
                price_elem = item_elem.find('span', class_='price')
                if price_elem:
                    # Make sure this price belongs to this item (not from item-title-row of another item)
                    price_parent = price_elem.find_parent('div', class_=re.compile(r'item'))
                    if price_parent == item_elem or price_elem.find_parent('div', class_='item-title-row'):
                        price = price_elem.get_text(strip=True)
            
            # Handle M.P. (Market Price) - normalize variations
            if price and ('M.P.' in price or 'M. P.' in price or price.strip() == 'M.P' or price.strip() == 'M. P'):
                price = "M.P."
            
            # Append section-level add-ons to description if applicable
            if section_addons and not item_addons:
                if description:
                    description = f"{description} | {section_addons}"
                else:
                    description = section_addons
            
            # Append item-level add-ons to description
            if item_addons:
                if description:
                    description = f"{description} | {' | '.join(item_addons)}"
                else:
                    description = ' | '.join(item_addons)
            
            # Skip items without prices (unless it's a wine menu or similar)
            if not price and menu_name not in ['Wine List', 'At the Bar', 'Happy Hour']:
                continue
            
            items.append({
                'name': item_name,
                'description': description,
                'price': price,
                'menu_type': section_name,
                'restaurant_name': restaurant_name,
                'restaurant_url': "https://www.fornobistro.com/",
                'menu_name': menu_name
            })
    
    return items


if __name__ == '__main__':
    url = "https://www.fornobistro.com/"
    scrape_fornobistro_menu(url)

