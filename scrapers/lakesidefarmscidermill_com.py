"""
Scraper for lakesidefarmscidermill.com
Scrapes Breakfast, Lunch, Pies, and Catering menus from a single page
"""

import json
import re
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup


def download_html_with_requests(url: str) -> str:
    """Download HTML from URL"""
    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://www.lakesidefarmscidermill.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_menu_tab(soup: BeautifulSoup, tab_id: str, menu_type: str) -> List[Dict]:
    """Parse a menu tab (breakfast, lunch, pies, or catering)"""
    items = []
    restaurant_name = "Lakeside Farms"
    restaurant_url = "https://www.lakesidefarmscidermill.com/"
    
    # Find the tab panel
    tab_panel = soup.find('section', id=tab_id)
    if not tab_panel:
        print(f"[WARNING] Tab '{tab_id}' not found")
        return items
    
    # Find all menu sections in this tab
    menu_sections = tab_panel.find_all('section', class_='menu-section')
    
    for section in menu_sections:
        # Get section name from header
        section_header = section.find('div', class_='menu-section__header')
        current_section = ""
        if section_header:
            h2 = section_header.find('h2')
            if h2:
                current_section = h2.get_text(strip=True)
        
        # Find all menu items in this section
        menu_items = section.find_all('li', class_='menu-item')
        
        for item in menu_items:
            # Get item name
            name_elem = item.find('p', class_='menu-item__heading--name')
            if not name_elem:
                continue
            
            name = name_elem.get_text(strip=True)
            if not name:
                continue
            
            # Get description
            description = ""
            desc_elem = item.find('p', class_='menu-item__details--description')
            if desc_elem:
                description = desc_elem.get_text(separator=' ', strip=True)
            
            # Get prices - items can have multiple prices
            prices = []
            price_elems = item.find_all('p', class_='menu-item__details--price')
            for price_elem in price_elems:
                # Extract price text
                price_text = price_elem.get_text(strip=True)
                # Find price value (format: $X.XX)
                price_match = re.search(r'\$\s*([\d,]+\.?\d*)', price_text)
                if price_match:
                    price_value = f"${price_match.group(1).replace(',', '')}"
                    # Check if there's a description for this price (e.g., "1 Egg", "2 Eggs")
                    strong_tags = price_elem.find_all('strong')
                    price_desc = ""
                    if len(strong_tags) > 0:
                        price_desc = strong_tags[0].get_text(strip=True)
                    prices.append({
                        'value': price_value,
                        'description': price_desc
                    })
            
            # Format price string
            if prices:
                if len(prices) == 1:
                    price = prices[0]['value']
                    if prices[0]['description']:
                        price = f"{prices[0]['value']} ({prices[0]['description']})"
                else:
                    # Multiple prices - format as list
                    price_parts = []
                    for p in prices:
                        if p['description']:
                            price_parts.append(f"{p['value']} ({p['description']})")
                        else:
                            price_parts.append(p['value'])
                    price = " / ".join(price_parts)
            else:
                price = ""
            
            # Use section name or default to menu_type
            menu_section = current_section if current_section else menu_type
            
            items.append({
                'name': name,
                'description': description,
                'price': price,
                'menu_type': menu_type,
                'restaurant_name': restaurant_name,
                'restaurant_url': restaurant_url,
                'menu_name': menu_section
            })
    
    return items


def parse_menu_page(html: str) -> List[Dict]:
    """Parse all menus from the menu page"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Parse Breakfast menu
    print("[1] Parsing Breakfast menu...")
    breakfast_items = parse_menu_tab(soup, 'breakfast', 'Breakfast')
    print(f"[OK] Extracted {len(breakfast_items)} items from Breakfast")
    all_items.extend(breakfast_items)
    
    # Parse Lunch menu
    print("[2] Parsing Lunch menu...")
    lunch_items = parse_menu_tab(soup, 'lunch', 'Lunch')
    print(f"[OK] Extracted {len(lunch_items)} items from Lunch")
    all_items.extend(lunch_items)
    
    # Parse Pies menu
    print("[3] Parsing Pies menu...")
    pies_items = parse_menu_tab(soup, 'pies', 'Pies')
    print(f"[OK] Extracted {len(pies_items)} items from Pies")
    all_items.extend(pies_items)
    
    # Parse Catering menu
    print("[4] Parsing Catering menu...")
    catering_items = parse_menu_tab(soup, 'catering', 'Catering')
    print(f"[OK] Extracted {len(catering_items)} items from Catering")
    all_items.extend(catering_items)
    
    return all_items


def scrape_lakesidefarms_menu() -> List[Dict]:
    """Scrape all menus from Lakeside Farms"""
    print("=" * 60)
    print("Scraping Lakeside Farms (lakesidefarmscidermill.com)")
    print("=" * 60)
    
    url = "https://www.lakesidefarmscidermill.com/menus/"
    print(f"\n[1] Downloading menu page...")
    print(f"    URL: {url}")
    
    html = download_html_with_requests(url)
    if not html:
        print(f"[ERROR] Failed to download HTML")
        return []
    
    # Save HTML for debugging
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    html_file = temp_dir / "lakesidefarmscidermill_com_menus.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] Saved HTML to {html_file.name}")
    
    # Parse menus
    print(f"\n[2] Parsing menus...")
    items = parse_menu_page(html)
    print(f"[OK] Total items extracted: {len(items)}")
    
    # Display sample
    if items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(items[:5], 1):
            try:
                price_str = item['price'] if item['price'] else "No price"
                print(f"  {i}. {item['name']} - {price_str} ({item['menu_type']})")
            except UnicodeEncodeError:
                name = item['name'].encode('ascii', 'ignore').decode('ascii')
                price_str = item['price'] if item['price'] else "No price"
                print(f"  {i}. {name} - {price_str} ({item['menu_type']})")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
    
    return items


if __name__ == '__main__':
    items = scrape_lakesidefarms_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "lakesidefarmscidermill_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

