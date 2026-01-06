"""
Test script for beverages menu parsing
This script only tests the beverages HTML parsing without using Gemini API
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import json
from typing import List, Dict

# Add scrapers directory to path
sys.path.insert(0, str(Path(__file__).parent))

def parse_beverages_html(html: str) -> List[Dict]:
    """Parse beverages menu from HTML (structured Untappd data)"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Structure based on actual HTML:
    # - Section: h3.section-name (e.g., "THE BASICS")
    # - Menu item: div.menu-item
    #   - Beer name: h4.item-name > a > span (e.g., "Bud Light")
    #   - Beer type: span.item-category (e.g., "Light Lager")
    #   - ABV: span.item-abv (e.g., "4.2% ABV")
    #   - Brewery: span.brewery > a (e.g., "Anheuser-Busch")
    #   - Size: span.type (e.g., "12oz")
    #   - Price: span.price (contains "4.00")
    
    # Find all menu items
    menu_items = soup.find_all('div', class_='menu-item')
    
    if menu_items:
        print(f"Found {len(menu_items)} menu items - parsing structured data...")
        
        current_section = "Beverages"  # Default section
        
        for menu_item in menu_items:
            # Find section - look for nearest h3.section-name before this item
            section_header = menu_item.find_previous('h3', class_='section-name')
            if section_header:
                current_section = section_header.get_text(strip=True)
            
            # Find item-details div
            item_details = menu_item.find('div', class_='item-details')
            if not item_details:
                continue
            
            # Extract beer name from h4.item-name > a > span
            h4_name = item_details.find('h4', class_='item-name')
            if not h4_name:
                continue
            
            # Get the span inside the link
            name_link = h4_name.find('a')
            if not name_link:
                continue
            
            name_span = name_link.find('span')
            if not name_span:
                continue
            
            beer_name = name_span.get_text(strip=True)
            if not beer_name:
                continue
            
            # Extract beer type from span.item-category
            category_span = h4_name.find('span', class_='item-category')
            beer_type = category_span.get_text(strip=True) if category_span else None
            
            # Extract ABV from span.item-abv
            abv_span = item_details.find('span', class_='item-abv')
            abv_text = abv_span.get_text(strip=True) if abv_span else None
            
            # Extract brewery from span.brewery > a
            brewery_span = item_details.find('span', class_='brewery')
            brewery_name = None
            if brewery_span:
                brewery_link = brewery_span.find('a')
                if brewery_link:
                    brewery_name = brewery_link.get_text(strip=True)
            
            # Build description
            description_parts = []
            if beer_type:
                description_parts.append(beer_type)
            if abv_text:
                description_parts.append(abv_text)
            if brewery_name:
                description_parts.append(f"Brewery: {brewery_name}")
            description = " | ".join(description_parts) if description_parts else None
            
            # Extract size and price from div.container-list
            container_list = item_details.find('div', class_='container-list')
            size = None
            price_value = None
            
            if container_list:
                # Find size from span.type
                type_span = container_list.find('span', class_='type')
                if type_span:
                    size = type_span.get_text(strip=True)
                
                # Find price from span.price
                price_span = container_list.find('span', class_='price')
                if price_span:
                    # Get all text from price span (e.g., "4.00" or "$4.00")
                    price_text = price_span.get_text(strip=True)
                    # Extract number (might have $ or other text)
                    price_match = re.search(r'(\d+\.?\d*)', price_text)
                    if price_match:
                        price_value = price_match.group(1)
            
            # Format price
            if price_value:
                if size:
                    price = f"{size} ${price_value}"
                else:
                    price = f"${price_value}"
            else:
                price = "Price not listed"
            
            item = {
                "name": beer_name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "The Hideaway",
                "restaurant_url": "https://www.hideawaysaratoga.com/",
                "menu_type": "Beverages",
                "menu_name": "Beverages Menu"
            }
            
            items.append(item)
    
    print(f"[OK] Extracted {len(items)} items from structured HTML")
    
    return items


def fetch_beverages_html_with_playwright(url: str) -> str:
    """Fetch beverages page HTML using Playwright"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            print(f"Loading page: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Wait a bit for any dynamic content to load
            page.wait_for_timeout(2000)
            
            # Get the HTML
            html = page.content()
            
            browser.close()
            return html
    except Exception as e:
        print(f"[ERROR] Failed to fetch beverages page with Playwright: {e}")
        return None


def main():
    """Test beverages parsing"""
    print("=" * 60)
    print("Testing Beverages Menu Parsing")
    print("=" * 60)
    
    # Fetch beverages HTML
    beverages_url = "https://www.hideawaysaratoga.com/beverages"
    beverages_html = fetch_beverages_html_with_playwright(beverages_url)
    
    if not beverages_html:
        print("[ERROR] Failed to fetch beverages HTML")
        return
    
    print(f"[OK] Fetched beverages HTML ({len(beverages_html)} characters)\n")
    
    # Parse beverages
    beverages = parse_beverages_html(beverages_html)
    
    if beverages:
        print(f"\n[OK] Successfully extracted {len(beverages)} beverage items")
        
        # Group by section
        sections = {}
        for item in beverages:
            section = item.get('section', 'Unknown')
            if section not in sections:
                sections[section] = []
            sections[section].append(item)
        
        print(f"\nItems by section:")
        for section, items in sections.items():
            print(f"  {section}: {len(items)} items")
        
        # Show first few items from each section
        print(f"\nSample items:")
        for section, items in list(sections.items())[:3]:
            print(f"\n  {section}:")
            for item in items[:3]:
                print(f"    - {item['name']}: {item['price']} ({item.get('description', 'N/A')[:50]})")
        
        # Save to JSON
        output_path = Path("output/test_beverages.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(beverages, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Saved {len(beverages)} items to {output_path}")
    else:
        print("[ERROR] No beverage items found")


if __name__ == "__main__":
    main()

