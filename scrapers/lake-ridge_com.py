"""
Scraper for lake-ridge.com
Scrapes Dinner, Desserts, and Spirits menus from a single page
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
            "referer": "https://www.lake-ridge.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_menu_tab(soup: BeautifulSoup, tab_name: str, menu_type: str) -> List[Dict]:
    """Parse a menu tab (Dinner, Desserts, or Spirits)"""
    items = []
    restaurant_name = "Lake Ridge"
    restaurant_url = "https://www.lake-ridge.com/"
    
    # Find the tab pane
    tab_pane = soup.find('div', {'data-w-tab': tab_name})
    if not tab_pane:
        print(f"[WARNING] Tab '{tab_name}' not found")
        return items
    
    # Find all menu items
    menu_items = tab_pane.find_all('div', role='listitem', class_='w-dyn-item')  # pyright: ignore[reportAttributeAccessIssue]
    
    for item in menu_items:
        # Find the closest preceding h1 heading
        current_section = menu_type  # Default
        prev_heading = item.find_previous('h1', class_='menu-heading')
        if prev_heading:
            current_section = prev_heading.get_text(strip=True)
        
        # Get item name from div with class "text-span-128"
        name_elem = item.find('div', class_='text-span-128')
        if not name_elem:
            continue
        
        name = name_elem.get_text(strip=True)
        if not name:
            continue
        
        # Get description from div with class "menu-block" (not bold)
        description = ""
        menu_blocks = item.find_all('div', class_='menu-block')
        for block in menu_blocks:
            # Skip if it's bold (that's the price)
            if 'bold' in block.get('class', []):
                continue
            # Skip if it's empty or has w-dyn-bind-empty
            if 'w-dyn-bind-empty' in block.get('class', []):
                continue
            block_text = block.get_text(strip=True)
            if block_text:
                description = block.get_text(separator=' ', strip=True)
                break
        
        # Get price from div with class "menu-block bold"
        price = ""
        price_elem = item.find('div', class_='menu-block bold')
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Skip if empty or has w-dyn-bind-empty
            if price_text and 'w-dyn-bind-empty' not in price_elem.get('class', []):
                # Extract price value - format is "$17.95" or "$49.95 / $51.95"
                prices = re.findall(r'\$\s*([\d,]+\.?\d*)', price_text)
                if prices:
                    if len(prices) > 1:
                        price = f"${prices[0].replace(',', '')} / ${prices[1].replace(',', '')}"
                    else:
                        price = f"${prices[0].replace(',', '')}"
        
        items.append({
            'name': name,
            'description': description,
            'price': price,
            'menu_type': menu_type,
            'restaurant_name': restaurant_name,
            'restaurant_url': restaurant_url,
            'menu_name': current_section
        })
    
    return items


def parse_menu_page(html: str) -> List[Dict]:
    """Parse all menus from the menu page"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Parse Dinner menu
    print("[1] Parsing Dinner menu...")
    dinner_items = parse_menu_tab(soup, 'Dinner', 'Dinner')
    print(f"[OK] Extracted {len(dinner_items)} items from Dinner")
    all_items.extend(dinner_items)
    
    # Parse Desserts menu
    print("[2] Parsing Desserts menu...")
    desserts_items = parse_menu_tab(soup, 'Desserts', 'Desserts')
    print(f"[OK] Extracted {len(desserts_items)} items from Desserts")
    all_items.extend(desserts_items)
    
    # Parse Spirits menu
    print("[3] Parsing Spirits menu...")
    spirits_items = parse_menu_tab(soup, 'Spirit', 'Spirits')
    print(f"[OK] Extracted {len(spirits_items)} items from Spirits")
    all_items.extend(spirits_items)
    
    return all_items


def scrape_lake_ridge_menu() -> List[Dict]:
    """Scrape all menus from Lake Ridge"""
    print("=" * 60)
    print("Scraping Lake Ridge (lake-ridge.com)")
    print("=" * 60)
    
    url = "https://www.lake-ridge.com/menu"
    print(f"\n[1] Downloading menu page...")
    print(f"    URL: {url}")
    
    html = download_html_with_requests(url)
    if not html:
        print(f"[ERROR] Failed to download HTML")
        return []
    
    # Save HTML for debugging
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    html_file = temp_dir / "lake-ridge_com_menu.html"
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
    items = scrape_lake_ridge_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "lake-ridge_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

