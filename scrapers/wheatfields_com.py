"""
Scraper for Wheatfields Restaurant (wheatfields.com)
Scrapes menu from HTML pages for both Saratoga and Clifton Park locations
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

# Restaurant configuration
RESTAURANT_NAME = "Wheatfields Restaurant & Bar"
RESTAURANT_URL = "http://www.wheatfields.com/"

# Menu URLs
SARATOGA_MENU_URL = "https://wheatfields.com/saratoga/menu/"
CLIFTON_PARK_MENU_URL = "https://wheatfields.com/cliftonpark/menu/"

# Headers for requests
HEADERS_SARATOGA = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://wheatfields.com/saratoga/',
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

HEADERS_CLIFTON_PARK = {
    'Referer': 'https://wheatfields.com/cliftonpark/',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}


def fetch_menu_html(url: str, headers: Dict) -> Optional[str]:
    """Fetch menu HTML from URL"""
    try:
        print(f"[INFO] Fetching menu HTML from {url}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"[INFO] Successfully fetched menu HTML ({len(response.text)} chars)")
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu HTML: {e}")
        return None


def extract_price(price_elem) -> Optional[str]:
    """Extract and format price from element"""
    if not price_elem:
        return None
    
    price_text = price_elem.get_text(strip=True)
    if not price_text:
        return None
    
    # Check for multiple prices (e.g., "12/15" or "12 | 15")
    if '/' in price_text or '|' in price_text:
        # Split by / or |
        separators = ['/', '|']
        for sep in separators:
            if sep in price_text:
                prices = [p.strip() for p in price_text.split(sep)]
                # Format each price
                formatted_prices = []
                for p in prices:
                    try:
                        price_val = float(p)
                        formatted_prices.append(f"${price_val:.2f}")
                    except ValueError:
                        formatted_prices.append(p)
                return " | ".join(formatted_prices)
    
    # Single price
    try:
        price_val = float(price_text)
        return f"${price_val:.2f}"
    except ValueError:
        return price_text


def extract_menu_items_from_html(html: str, location: str) -> List[Dict]:
    """Extract menu items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all menu containers (there may be multiple sections)
    menu_containers = soup.find_all('div', class_='accura-fmwp-food-menu')
    if not menu_containers:
        print("[WARNING] Could not find menu containers")
        return []
    
    # Track current section
    current_section = "Menu"
    
    # Process each menu container
    for menu_container in menu_containers:
        # Find the section heading before this container
        # Look for h2 with class "menu-head" that comes before this container
        prev_elements = []
        for elem in menu_container.find_all_previous(['h2', 'h3', 'h4']):
            if elem.name == 'h2' and 'menu-head' in str(elem.get('class', [])):
                current_section = elem.get_text(strip=True)
                break
            elif elem.name in ['h2', 'h3']:
                # Check if it's a section heading
                heading_text = elem.get_text(strip=True)
                if heading_text and len(heading_text) < 100:  # Reasonable section name length
                    current_section = heading_text
                    break
        
        # Find all menu items in this container
        menu_items = menu_container.find_all('li', class_=lambda x: x and 'accura-fmwp-hover-bg' in str(x))
        
        # Process each menu item
        for item_li in menu_items:
            # Extract price
            price_elem = item_li.find('span', class_='accura-fmwp-regular-price')
            price = extract_price(price_elem)
            
            # Extract name and additional info
            title_elem = item_li.find('span', class_='accura-fmwp-menu-items-title')
            if not title_elem:
                continue
            
            # Get the main title text (before any nested spans)
            name_parts = []
            for content in title_elem.contents:
                if isinstance(content, str):
                    name_parts.append(content.strip())
                elif content.name != 'span' or 'accura-fmwp-span-content' not in str(content.get('class', [])):
                    # Include non-span-content elements
                    text = content.get_text(strip=True) if hasattr(content, 'get_text') else str(content).strip()
                    if text:
                        name_parts.append(text)
            
            name = ' '.join(name_parts).strip()
            
            # Extract additional info from span-content (ingredients, etc.)
            span_content = title_elem.find('span', class_='accura-fmwp-span-content')
            additional_info = span_content.get_text(strip=True) if span_content else None
            
            # Extract description
            desc_elem = item_li.find('p', class_='accura-fmwp-item-description')
            description = desc_elem.get_text(strip=True) if desc_elem else None
            
            # Combine description and additional info
            if additional_info:
                if description:
                    description = f"{description} ({additional_info})"
                else:
                    description = additional_info
            
            # Skip if no name or invalid name
            if not name or name.strip() in ['NA', 'N/A', 'n/a', 'na']:
                continue
            
            all_items.append({
                'name': name,
                'description': description,
                'price': price,
                'section': current_section,
                'location': location,
                'restaurant_name': RESTAURANT_NAME,
                'restaurant_url': RESTAURANT_URL
            })
    
    return all_items


def scrape_menu() -> List[Dict]:
    """Main function to scrape menus from both locations"""
    print(f"[INFO] Scraping menus from {RESTAURANT_NAME}")
    all_items = []
    
    # 1. Scrape Saratoga menu
    print(f"\n[1] Scraping Saratoga menu...")
    saratoga_html = fetch_menu_html(SARATOGA_MENU_URL, HEADERS_SARATOGA)
    if not saratoga_html:
        # Try with saved HTML if available
        saved_html_path = Path(__file__).parent.parent / "temp" / "wheatfields_saratoga_menu.html"
        if saved_html_path.exists():
            print("[INFO] Using saved Saratoga HTML file...")
            with open(saved_html_path, 'r', encoding='utf-8') as f:
                saratoga_html = f.read()
    
    if saratoga_html:
        saratoga_items = extract_menu_items_from_html(saratoga_html, "Saratoga")
        all_items.extend(saratoga_items)
        print(f"[INFO] Extracted {len(saratoga_items)} items from Saratoga menu")
    else:
        print("[WARNING] Failed to fetch Saratoga menu")
    
    # 2. Scrape Clifton Park menu
    print(f"\n[2] Scraping Clifton Park menu...")
    clifton_park_html = fetch_menu_html(CLIFTON_PARK_MENU_URL, HEADERS_CLIFTON_PARK)
    if clifton_park_html:
        clifton_park_items = extract_menu_items_from_html(clifton_park_html, "Clifton Park")
        all_items.extend(clifton_park_items)
        print(f"[INFO] Extracted {len(clifton_park_items)} items from Clifton Park menu")
    else:
        print("[WARNING] Failed to fetch Clifton Park menu")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "wheatfields_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

