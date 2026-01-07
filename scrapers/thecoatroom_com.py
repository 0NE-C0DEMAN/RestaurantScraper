"""
Scraper for The Coat Room (thecoatroom.com)
Scrapes menu from SpotOn ordering website
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time

# Restaurant configuration
RESTAURANT_NAME = "The Coat Room"
RESTAURANT_URL = "https://thecoatroom.com/menus/"

# SpotOn ordering page URL
SPOTON_URL = "https://order.spoton.com/ddi-the-coat-room-13650/saratoga-springs-ny/64513a845d30e020458053a8"


def fetch_menu_html_with_playwright() -> Optional[str]:
    """Fetch menu HTML from SpotOn using Playwright"""
    try:
        print(f"[INFO] Fetching menu HTML from {SPOTON_URL} using Playwright...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            page.goto(SPOTON_URL, wait_until="networkidle", timeout=120000)
            
            # Wait for page to fully load
            time.sleep(5)
            
            # Wait for menu content to load
            try:
                page.wait_for_selector('button[aria-label*="in stock"]', timeout=30000)
            except:
                print("[WARNING] Menu items selector not found, but continuing...")
            
            html = page.content()
            
            # Save HTML to temp directory
            temp_dir = Path(__file__).parent.parent / "temp"
            temp_dir.mkdir(exist_ok=True)
            html_file = temp_dir / "thecoatroom_spoton.html"
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"[INFO] HTML saved to {html_file}")
            
            browser.close()
            
            print(f"[INFO] Successfully fetched HTML ({len(html)} chars)")
            return html
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu HTML with Playwright: {e}")
        return None


def extract_menu_items_from_html(html: str) -> List[Dict]:
    """Extract menu items from SpotOn HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all menu item groups (sections)
    # Sections have data-testid="menu-item-group-name" in h2
    section_headings = soup.find_all('h2', attrs={'data-testid': 'menu-item-group-name'})
    
    for section_heading in section_headings:
        section_name = section_heading.get_text(strip=True)
        if not section_name:
            continue
        
        print(f"[INFO] Processing section: {section_name}")
        
        # Find the parent container that holds items for this section
        # The structure is: div > h2 (section name) > div (items container)
        # Try multiple approaches to find the items container
        section_container = None
        
        # Method 1: Find next sibling div with data-testid
        section_container = section_heading.find_next_sibling('div', attrs={'data-testid': 'menu-item-group-items'})
        
        # Method 2: Find parent div, then find items container within it
        if not section_container:
            parent = section_heading.find_parent('div')
            if parent:
                section_container = parent.find('div', attrs={'data-testid': 'menu-item-group-items'})
        
        # Method 3: Find all divs with data-testid and match by proximity
        if not section_container:
            all_item_containers = soup.find_all('div', attrs={'data-testid': 'menu-item-group-items'})
            all_section_headings = soup.find_all('h2', attrs={'data-testid': 'menu-item-group-name'})
            for i, heading in enumerate(all_section_headings):
                if heading == section_heading and i < len(all_item_containers):
                    section_container = all_item_containers[i]
                    break
        
        if not section_container:
            print(f"[WARNING] Could not find items container for section: {section_name}")
            continue
        
        # Find all menu item cards in this section
        # Items have data-testid="menu-item-card" and role="button"
        menu_items = section_container.find_all(['div', 'button'], attrs={'data-testid': 'menu-item-card'})
        
        for item_card in menu_items:
            # Extract name from data-testid="menu-item-card-name"
            name_elem = item_card.find('p', attrs={'data-testid': 'menu-item-card-name'})
            name = name_elem.get_text(strip=True) if name_elem else None
            
            # If no name from element, try aria-label
            if not name:
                aria_label = item_card.get('aria-label', '')
                if aria_label:
                    # Format: "Item Name, $XX.XX, in stock"
                    parts = aria_label.split(',')
                    if parts:
                        name = parts[0].strip()
            
            if not name or len(name) < 2:
                continue
            
            # Extract description from data-testid="menu-item-card-description"
            desc_elem = item_card.find('p', attrs={'data-testid': 'menu-item-card-description'})
            description = desc_elem.get_text(strip=True) if desc_elem else None
            if description and len(description) < 3:
                description = None
            
            # Extract price from data-testid="menu-item-card-price"
            price_elem = item_card.find('p', attrs={'data-testid': 'menu-item-card-price'})
            price = price_elem.get_text(strip=True) if price_elem else None
            
            # If no price from element, try aria-label
            if not price:
                aria_label = item_card.get('aria-label', '')
                if aria_label and '$' in aria_label:
                    # Extract price from aria-label
                    parts = aria_label.split(',')
                    for part in parts:
                        if '$' in part:
                            price = part.strip()
                            break
            
            # Format price
            formatted_price = None
            if price:
                # Remove $ and format
                price_clean = price.replace('$', '').replace(',', '').strip()
                try:
                    price_float = float(price_clean)
                    formatted_price = f"${price_float:.2f}"
                except:
                    formatted_price = price
            
            # Create item
            item = {
                'name': name,
                'description': description if description else None,
                'price': formatted_price,
                'section': section_name,
                'restaurant_name': RESTAURANT_NAME,
                'restaurant_url': RESTAURANT_URL
            }
            
            all_items.append(item)
    
    # Remove duplicates based on name and section
    seen = set()
    unique_items = []
    for item in all_items:
        key = (item['name'], item.get('section', ''))
        if key not in seen:
            seen.add(key)
            unique_items.append(item)
    
    return unique_items


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME} via SpotOn")
    all_items = []
    
    # Fetch HTML using Playwright
    html = fetch_menu_html_with_playwright()
    
    if not html:
        print("[ERROR] Failed to fetch menu HTML")
        return []
    
    # Extract menu items
    items = extract_menu_items_from_html(html)
    all_items.extend(items)
    
    print(f"[INFO] Extracted {len(items)} menu items")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "thecoatroom_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()
