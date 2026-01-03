"""
Scraper for mamamiassaratoga.com menu
Scrapes menu from a single page with multiple sections
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
            "referer": "https://mamamiassaratoga.com/menu/house-specialties",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_menu_page(html: str) -> List[Dict]:
    """Parse menu from the menu page"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    restaurant_name = "Mama Mia's"
    restaurant_url = "https://mamamiassaratoga.com/"
    
    # Find all menu sections
    menu_sections = soup.find_all('div', class_='ccm-block-page-list-wrapper')
    
    for section in menu_sections:
        # Get section name from header
        header = section.find('div', class_='ccm-block-page-list-header')
        if header:
            section_name_elem = header.find('h5')
            section_name = section_name_elem.get_text(strip=True) if section_name_elem else "Menu"
        else:
            section_name = "Menu"
        
        # Find all menu items in this section
        menu_items = section.find_all('div', class_=lambda x: x and 'ccm-block-page-list-page-entry' in x)
        
        for item_div in menu_items:
            # Extract price
            price_elem = item_div.find('div', class_='label-price')
            price = ""
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Extract price (format: $XX.XX)
                price_match = re.search(r'\$\s*([\d,]+\.?\d*)', price_text)
                if price_match:
                    price = f"${price_match.group(1).replace(',', '')}"
            
            # Extract item name
            item_title = item_div.find('div', class_='item-title')
            name = ""
            if item_title:
                type_three_title = item_title.find('div', class_='type-three-title')
                if type_three_title:
                    name = type_three_title.get_text(strip=True)
            
            # Extract description
            description = ""
            # Description is in a <p> tag after the item-title
            p_tag = item_div.find('p')
            if p_tag:
                description = p_tag.get_text(strip=True)
            
            # Skip if no name
            if not name:
                continue
            
            items.append({
                'name': name,
                'description': description,
                'price': price,
                'menu_type': 'Menu',
                'restaurant_name': restaurant_name,
                'restaurant_url': restaurant_url,
                'menu_name': section_name
            })
    
    return items


def scrape_mamamia_menu() -> List[Dict]:
    """Scrape menu from Mama Mia's"""
    print("=" * 60)
    print("Scraping Mama Mia's (mamamiassaratoga.com)")
    print("=" * 60)
    
    url = "https://mamamiassaratoga.com/menu"
    print(f"\n[1] Downloading menu page...")
    print(f"    URL: {url}")
    
    html = download_html_with_requests(url)
    if not html:
        print(f"[ERROR] Failed to download HTML")
        return []
    
    # Save HTML for debugging
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    html_file = temp_dir / "mamamiassaratoga_com_menu.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] Saved HTML to {html_file.name}")
    
    # Parse menu
    print(f"\n[2] Parsing menu...")
    items = parse_menu_page(html)
    print(f"[OK] Total items extracted: {len(items)}")
    
    # Display sample
    if items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(items[:5], 1):
            try:
                price_str = item['price'] if item['price'] else "No price"
                print(f"  {i}. {item['name']} - {price_str} ({item['menu_name']})")
            except UnicodeEncodeError:
                name = item['name'].encode('ascii', 'ignore').decode('ascii')
                price_str = item['price'] if item['price'] else "No price"
                print(f"  {i}. {name} - {price_str} ({item['menu_name']})")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
    
    return items


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    items = scrape_mamamia_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "mamamiassaratoga_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

