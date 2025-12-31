"""
Scraper for: https://bocabistro.com/
Uses requests to fetch HTML menu and BeautifulSoup for parsing
Scrapes both Lunch and Dinner menus
All code consolidated in a single file
"""

import json
import sys
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


def scrape_bocabistro_menu(url: str) -> List[Dict]:
    """Scrape menu items from bocabistro.com - Lunch and Dinner Menus"""
    all_items = []
    restaurant_name = "Boca Bistro"
    
    # Menu configurations: (menu_id, menu_name)
    # Note: Wine has two menu IDs - 1826518 for Vinos Blancos (White Wines) and 4084039 for Vinos Tintos (Red Wines)
    # Bar has multiple menu IDs for different sections
    menus = [
        (1826557, "Lunch"),
        (1826548, "Dinner"),
        (3602541, "Brunch"),
        (1826518, "Wine"),  # Vinos Blancos (White Wines)
        (4084039, "Wine"),  # Vinos Tintos (Red Wines)
        (1826513, "Bar"),   # Wine by the Glass
        (1826515, "Bar"),   # Beer Selections
        (4456918, "Bar"),   # Mocktails
        (4205378, "Bar"),   # Brown Liquors
        (4510664, "Bar"),   # Specialty Cocktails
        (4976717, "Bar"),   # Cordials, Liqueurs, Sherries, Ports, Grappas
        (4000880, "Siesta"), # Siesta Happy Hour
        (6210883, "Flights & Bites"), # Flights & Bites
        (1947377, "DZ at Home") # DZ at Home
    ]
    
    print(f"Scraping: {url}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
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
        'referer': 'https://bocabistro.com/',
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
        for menu_id, menu_name in menus:
            menu_widget_url = f"https://places.singleplatform.com/boca-bistro/menu_widget?api_key=ke09z8icq4xu8uiiccighy1bw&display_menu={menu_id}&hide_cover_photo=true&hide_disclaimer=true&widget_background_color=rgba%280%2C%200%2C%200%2C%200%29"
            
            print(f"Fetching {menu_name} Menu HTML...")
            response = requests.get(menu_widget_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            print(f"[OK] Received {menu_name} Menu HTML content\n")
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            print(f"Parsing menu items from {menu_name} Menu...")
            items = extract_menu_items_from_html(soup, menu_name)
            
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
    
    # Save to JSON
    if all_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(all_items, f, indent=2, ensure_ascii=False)
        print(f"Saved to: {output_json}")
    
    return all_items


def extract_menu_items_from_html(soup: BeautifulSoup, menu_name: str = "Lunch") -> List[Dict]:
    """Extract menu items from HTML soup - for specified menu (Lunch or Dinner)"""
    items = []
    
    # Find the menu section - look for h2 with menu name
    # Try different patterns: "Menu Name Menu", "Menu Name", "Sunday Brunch Menu", "Wine List", etc.
    menu_headers = []
    
    if menu_name == 'Wine' or menu_name == 'Bar' or menu_name == 'Siesta' or menu_name == 'Flights & Bites' or menu_name == 'DZ at Home':
        # For Wine and Bar menus, find all h2 with menu-title class (they have multiple sections)
        menu_headers = soup.find_all('h2', class_='menu-title')
        if not menu_headers:
            print(f"  [WARNING] Could not find {menu_name} Menu headers")
            return []
        print(f"  Found {len(menu_headers)} {menu_name} Menu sections")
    else:
        patterns = [
            rf'{menu_name} Menu',
            rf'{menu_name}',
            rf'Sunday {menu_name} Menu' if menu_name == 'Brunch' else None,
            rf'Sunday {menu_name}' if menu_name == 'Brunch' else None,
            rf'{menu_name} List' if menu_name == 'Wine' else None
        ]
        
        menu_header = None
        for pattern in patterns:
            if pattern:
                menu_header = soup.find('h2', class_='menu-title', string=re.compile(pattern, re.I))
                if menu_header:
                    menu_headers = [menu_header]
                    break
        
        if not menu_headers:
            print(f"  [WARNING] Could not find {menu_name} Menu header")
            return []
        
        print(f"  Found {menu_name} Menu section")
    
    # Find all menu containers for wine (multiple menus) or single menu for others
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
        sections = menu_container.find_all('div', class_='section')  # pyright: ignore[reportAttributeAccessIssue]
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
        # Find description divs and check if they have both 'description' and 'text' classes
        section_desc_elems = section.find_all('div', class_='description')
        for desc_elem in section_desc_elems:
            classes = desc_elem.get('class', [])
            if 'text' in classes:
                desc_text = desc_elem.get_text(strip=True)
                if desc_text and ('Add' in desc_text or 'add' in desc_text):
                    section_addons = desc_text
                    break
        
        # Find all items in this section (divs with class containing 'item' AND have item-title-row)
        # This ensures we only get actual menu items, not section descriptions
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
            
            # Get item description - find div with both 'description' and 'text' classes
            description = ""
            item_desc_elems = item_elem.find_all('div', class_='description')
            for desc_elem in item_desc_elems:
                classes = desc_elem.get('class', [])
                if 'text' in classes:
                    desc_text = desc_elem.get_text(strip=True)
                    # Skip if it's just "Small Plates" or similar section notes
                    if desc_text and desc_text.lower() not in ['small plates', 'small plate']:
                        description = desc_text
                        break
            
            # Extract item-level add-ons (like "Add Chorizo $5.00")
            # Only look for addons that are direct children or siblings within the same item div
            # Addons appear after the allergens-group and before the closing </div> of the item
            item_addons = []
            # Look for addon divs (class="addon") - only within this specific item element
            # Make sure we're not picking up addons from other items
            addon_divs = item_elem.find_all('div', class_='addon', recursive=True)
            for addon_div in addon_divs:
                # Verify this addon is actually within the item structure (not from a sibling)
                # Check if it's after the allergens-group or description
                parent_item = addon_div.find_parent('div', class_=re.compile(r'item'))
                if parent_item != item_elem:
                    continue
                
                # Get addon title - it's in a <li> within <span class="title">
                title_span = addon_div.find('span', class_='title')
                if title_span:
                    title_li = title_span.find('li')
                    if title_li:
                        addon_title = title_li.get_text(strip=True)
                    else:
                        addon_title = title_span.get_text(strip=True)
                else:
                    continue
                
                # Get addon price - it's in a <li> within <span class="price">
                price_span = addon_div.find('span', class_='price')
                if price_span:
                    price_li = price_span.find('li')
                    if price_li:
                        addon_price = price_li.get_text(strip=True)
                    else:
                        addon_price = price_span.get_text(strip=True)
                else:
                    continue
                
                if addon_title and addon_price:
                    if not addon_price.startswith('$'):
                        addon_price = f"${addon_price}"
                    item_addons.append(f"{addon_title} {addon_price}")
            
            # Add item-level add-ons to description
            if item_addons:
                if description:
                    description = f"{description}. {' | '.join(item_addons)}"
                else:
                    description = ' | '.join(item_addons)
            
            # Add section-level add-ons to description if applicable
            # Only add to salads (check if item name contains "salad" or "bowl")
            item_name_lower = item_name.lower()
            if section_addons and ('salad' in item_name_lower or 'bowl' in item_name_lower):
                if description:
                    description = f"{description}. {section_addons}"
                else:
                    description = section_addons
            
            # Get price(s)
            price = ""
            
            # Check for single price in item-title-row
            item_title_row = item_elem.find('div', class_='item-title-row')
            if item_title_row:
                price_elem = item_title_row.find('span', class_='price')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    if price_text:
                        price = price_text
            
            # Check for multiprice-group (multiple prices like Cup/Bowl)
            if not price:
                multiprice_group = item_elem.find('div', class_='multiprice-group')
                if multiprice_group:
                    multiprices = multiprice_group.find_all('div', class_='multiprice')
                    price_parts = []
                    for mp in multiprices:
                        title_elem = mp.find('span', class_='title')
                        price_elem = mp.find('span', class_='price')
                        if title_elem and price_elem:
                            title = title_elem.get_text(strip=True)
                            price_val = price_elem.get_text(strip=True)
                            if title and price_val:
                                price_parts.append(f"{price_val} ({title})")
                    
                    if price_parts:
                        price = " | ".join(price_parts)
            
            # Clean up price - ensure $ symbol
            if price and not price.startswith('$'):
                # Extract numbers and add $
                price_match = re.search(r'(\d+\.?\d*)', price)
                if price_match:
                    price = price.replace(price_match.group(1), f"${price_match.group(1)}")
            
            # Skip if no name
            if not item_name:
                continue
            
            # For items without prices (like Brown Liquors, Cordials), set price to empty string
            if not price:
                price = ""
            
            # Skip if description is only add-on text (not a real item description)
            if description and description.startswith('Add ') and 'for $' in description:
                continue
            
            # Skip if description is just section notes like "Small Plates"
            if description and description.lower() in ['small plates', 'small plate']:
                continue
            
            items.append({
                'name': item_name.upper(),
                'description': description,
                'price': price,
                'menu_type': f"{menu_name.upper()} - {section_name.upper()}"
            })
    
    # Remove duplicates (same name, price, and menu_type)
    seen = set()
    unique_items = []
    for item in items:
        key = (item['name'], item['price'], item['menu_type'])
        if key not in seen:
            seen.add(key)
            unique_items.append(item)
    
    return unique_items


def main():
    url = "https://bocabistro.com/"
    scrape_bocabistro_menu(url)


if __name__ == "__main__":
    main()

