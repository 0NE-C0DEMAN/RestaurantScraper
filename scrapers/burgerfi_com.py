"""
Scraper for: https://www.burgerfi.com/
HTML-based menu
"""

import json
import os
import sys
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup


def extract_menu_items_from_html(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract menu items from HTML soup.
    Structure: h2 for sections and items, p for descriptions, prices in various formats
    """
    items = []
    
    try:
        # Find the main content area
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        if not main_content:
            main_content = soup
        
        # Find all h2 headings
        h2_elements = main_content.find_all('h2')  # pyright: ignore[reportAttributeAccessIssue]
        
        # Section names that indicate a new category (not an item)
        # These are the actual section headers
        section_names = ['Burgers', 'Chicken & Sliders', 'Fries + Onion Rings', 'Kids Meals', 
                        'Custard Shakes', 'Nutritional Information']
        
        current_section = ""
        
        for h2 in h2_elements:
            h2_text = h2.get_text(strip=True)
            
            if not h2_text:
                continue
            
            # Check if this is a section header (exact match with known section names)
            is_section = h2_text in section_names
            
            if is_section:
                current_section = h2_text
                continue
            
            # This is an item name
            item_name = h2_text
            
            # Look for description and price in following elements
            description = ""
            price = ""
            
            # Find next p element after this h2
            next_p = h2.find_next('p')
            if next_p:
                # Check if this p is before the next h2
                next_h2 = h2.find_next('h2')
                if not next_h2 or (next_p.find_previous('h2') == h2 and next_p.find_previous('h2') != next_h2):
                    text = next_p.get_text(strip=True)
                    
                    if text:
                        # Look for price pattern
                        price_match = re.search(r'(\$?\d+\.?\d*)', text)
                        if price_match:
                            price = price_match.group(1)
                            if not price.startswith('$'):
                                price = f"${price}"
                            
                            # Description is text before price
                            desc_text = text[:price_match.start()].strip()
                            if desc_text:
                                description = desc_text
                        else:
                            # No price, might be description only
                            description = text
            
            # Also check for price in span or div elements near the h2
            if not price:
                # Look for price in sibling elements
                parent = h2.parent
                if parent:
                    # Look for price in spans or divs
                    price_elements = parent.find_all(['span', 'div'], string=re.compile(r'\$?\d+\.?\d*'))
                    for price_elem in price_elements:
                        price_text = price_elem.get_text(strip=True)
                        price_match = re.search(r'(\$?\d+\.?\d*)', price_text)
                        if price_match:
                            price = price_match.group(1)
                            if not price.startswith('$'):
                                price = f"${price}"
                            break
                
                # Also check in the h2 text itself
                if not price:
                    price_match = re.search(r'(\$?\d+\.?\d*)', item_name)
                    if price_match:
                        price = price_match.group(1)
                        if not price.startswith('$'):
                            price = f"${price}"
                        item_name = item_name[:price_match.start()].strip()
            
            # Look for description in other nearby elements if not found
            if not description:
                # Check for description in div or span after h2
                next_div = h2.find_next(['div', 'span'])
                if next_div:
                    next_h2 = h2.find_next('h2')
                    if not next_h2 or (next_div.find_previous('h2') == h2):
                        desc_text = next_div.get_text(strip=True)
                        # Remove price if present
                        desc_text = re.sub(r'\$?\d+\.?\d*', '', desc_text).strip()
                        if desc_text and len(desc_text) > 5:
                            description = desc_text
            
            if item_name and len(item_name) > 1:
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'section': current_section
                })
        
    except Exception as e:
        print(f"  Error extracting HTML menu items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_burgerfi_menu():
    """
    Main function to scrape menu from burgerfi.com
    """
    url = "https://www.burgerfi.com/"
    restaurant_name = "BurgerFi"
    
    print(f"Scraping: {url}")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    all_items = []
    
    # ===== MENU (HTML) =====
    print("\n[1/1] Processing Menu (HTML)...")
    menu_url = "https://www.burgerfi.com/menu"
    
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.burgerfi.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get(menu_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        menu_items = extract_menu_items_from_html(soup)
        
        for item in menu_items:
            section = item.get('section', '').upper() if item.get('section') else 'MENU'
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': section,
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Menu'
            })
        
        print(f"[OK] Extracted {len(menu_items)} items from Menu")
        
    except Exception as e:
        print(f"[ERROR] Failed to scrape Menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Save to JSON
    output_file = output_dir / "burgerfi_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Extracted {len(all_items)} total items from all menus")
    print(f"Saved to: {output_file}")
    
    return all_items


if __name__ == "__main__":
    scrape_burgerfi_menu()

