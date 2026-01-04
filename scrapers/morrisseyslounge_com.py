"""
Scraper for morrisseyslounge.com
Scrapes all menu tabs: Breakfast, Brunch, Lunch, Sushi, Dinner, Dessert, Libations
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
            "referer": "https://morrisseyslounge.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        cookies = {
            "_ga": "GA1.1.1539195955.1767530537",
            "cookieyes-consent": "consentid:WWNtaHZwQVFCTXk1UmN6UkJQenhVWFFndE1nV25TSHo,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes",
            "_ga_28J771WN4Q": "GS2.1.s1767530538$o1$g1$t1767530588$j10$l0$h0",
            "_ga_RGF9HYTDL8": "GS2.1.s1767530536$o1$g1$t1767530588$j8$l0$h0"
        }
        response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_menu_tab(soup: BeautifulSoup, tab_id: str, menu_type: str) -> List[Dict]:
    """Parse a menu tab (Breakfast, Brunch, Lunch, Sushi, Dinner, Dessert, Libations)"""
    items = []
    restaurant_name = "Morrissey's Lounge & Bistro"
    restaurant_url = "https://morrisseyslounge.com/"
    
    # Find the tab pane
    tab_pane = soup.find('div', {'id': tab_id})
    if not tab_pane:
        print(f"[WARNING] Tab '{tab_id}' not found")
        return items
    
    # Track current section
    current_section = menu_type  # Default to menu type
    
    # Find all elements in the tab
    all_elements = tab_pane.find_all(['h5', 'div'], recursive=True)
    
    for elem in all_elements:
        # Check if it's a section heading (h5)
        if elem.name == 'h5':
            current_section = elem.get_text(strip=True)
            continue
        
        # Check if it's a menu item
        if elem.name == 'div' and 'nectar_food_menu_item' in elem.get('class', []):
            # Extract item name
            name_elem = elem.find('div', class_='item_name')
            if not name_elem:
                continue
            
            name_h4 = name_elem.find('h4')
            if not name_h4:
                continue
            
            name = name_h4.get_text(strip=True)
            if not name:
                continue
            
            # Extract price
            price_elem = elem.find('div', class_='item_price')
            price = ""
            if price_elem:
                price_h4 = price_elem.find('h4')
                if price_h4:
                    price = price_h4.get_text(strip=True)
                    # Clean up price (remove extra spaces, handle MP for market price)
                    price = re.sub(r'\s+', ' ', price).strip()
            
            # Extract description
            description_elem = elem.find('div', class_='item_description')
            description = ""
            if description_elem:
                description = description_elem.get_text(strip=True)
            
            # Skip items with no price and no description
            if not price and not description:
                continue
            
            # Create item (key order: name, description, price, restaurant_name, restaurant_url, menu_type, menu_name)
            item = {
                'name': name,
                'description': description,
                'price': price,
                'restaurant_name': restaurant_name,
                'restaurant_url': restaurant_url,
                'menu_type': menu_type,
                'menu_name': current_section
            }
            
            items.append(item)
    
    return items


def scrape_morrisseys_menu() -> List[Dict]:
    """Scrape menu from Morrissey's Lounge"""
    print("=" * 60)
    print("Scraping Morrissey's Lounge & Bistro (morrisseyslounge.com)")
    print("=" * 60)
    
    url = "https://morrisseyslounge.com/home/dinein-menus/"
    
    # Download HTML
    print(f"\n[1] Downloading menu HTML...")
    html = download_html_with_requests(url)
    if not html:
        print("[ERROR] Failed to download HTML")
        return []
    
    print(f"[OK] Downloaded {len(html)} characters")
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    
    # Define menu tabs
    menu_tabs = [
        {"tab_id": "tab-breakfast", "menu_type": "Breakfast"},
        {"tab_id": "tab-brunch", "menu_type": "Brunch"},
        {"tab_id": "tab-lunch", "menu_type": "Lunch"},
        {"tab_id": "tab-sushi", "menu_type": "Sushi"},
        {"tab_id": "tab-dinner", "menu_type": "Dinner"},
        {"tab_id": "tab-dessert", "menu_type": "Dessert"},
        {"tab_id": "tab-libations", "menu_type": "Libations"},
    ]
    
    all_items = []
    
    # Parse each menu tab
    print(f"\n[2] Parsing menu tabs...")
    for tab_info in menu_tabs:
        tab_id = tab_info["tab_id"]
        menu_type = tab_info["menu_type"]
        
        print(f"    Parsing {menu_type} menu...", end=" ")
        items = parse_menu_tab(soup, tab_id, menu_type)
        print(f"[OK] Found {len(items)} items")
        
        all_items.extend(items)
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Display sample
    if all_items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            try:
                price_str = item.get('price', '') if item.get('price') else "No price"
                print(f"  {i}. {item.get('name', 'Unknown')} - {price_str} ({item.get('menu_type', 'Unknown')} / {item.get('menu_name', 'Unknown')})")
            except Exception as e:
                print(f"  {i}. [Error displaying item: {e}]")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items


if __name__ == "__main__":
    items = scrape_morrisseys_menu()
    
    # Save to JSON
    if items:
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "morrisseyslounge_com.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Saved {len(items)} items to {output_file}")

