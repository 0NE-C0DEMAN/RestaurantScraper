"""
Scraper for: https://burnthillscafe.shop/
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
    Structure: h2 for sections, h3 for item names, prices and descriptions in following elements
    """
    items = []
    
    try:
        # Find the main content area
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        if not main_content:
            main_content = soup
        
        # Find all h2 headings (section headers)
        h2_elements = main_content.find_all('h2')  # pyright: ignore[reportAttributeAccessIssue]
        
        current_section = ""
        
        for i, h2 in enumerate(h2_elements):
            h2_text = h2.get_text(strip=True)
            
            if not h2_text:
                continue
            
            # Skip the main menu title if it's an h1 or first h2
            if h2_text.lower() in ['menu', 'menu burnt hills cafe']:
                continue
            
            # This is a section header
            current_section = h2_text
            
            # Find the next h2 (boundary for this section)
            next_h2 = None
            if i + 1 < len(h2_elements):
                next_h2 = h2_elements[i + 1]
            
            # Find all h3 elements (item names) after this h2 until next h2
            h3_elements = []
            current_h3 = h2.find_next('h3')
            while current_h3:
                # Stop if we've reached the next section
                if next_h2:
                    # Check if there's an h2 between current h2 and this h3 that is the next_h2
                    prev_h2 = current_h3.find_previous('h2')
                    if prev_h2 == next_h2:
                        break
                
                # Only include h3 if its previous h2 is our current section
                prev_h2 = current_h3.find_previous('h2')
                if prev_h2 == h2:
                    h3_text = current_h3.get_text(strip=True)
                    if h3_text and len(h3_text) > 1:
                        h3_elements.append(current_h3)
                else:
                    # We've gone past our section
                    break
                
                current_h3 = current_h3.find_next('h3')
            
            # Process each h3 element (item)
            for h3 in h3_elements:
                item_name = h3.get_text(strip=True)
                
                if not item_name or len(item_name) < 2:
                    continue
                
                # Look for description and price in following elements
                description = ""
                price = ""
                
                # Find next p, span, or div element after this h3
                next_elem = h3.find_next(['p', 'span', 'div'])
                if next_elem:
                    # Check if this element is before the next h3 or h2
                    next_h3_after = h3.find_next('h3')
                    next_h2_after = h3.find_next('h2')
                    
                    # Only use this element if it's before the next h3/h2
                    if (not next_h3_after or (next_elem.find_previous('h3') == h3 and next_elem.find_previous('h3') != next_h3_after)) and \
                       (not next_h2_after or (next_elem.find_previous('h2') == h2 or next_elem.find_previous('h2') != next_h2_after)):
                        text = next_elem.get_text(strip=True)
                        
                        if text:
                            # Look for price pattern (handle "US$10.95" format)
                            price_match = re.search(r'(?:US\s*)?(\$?\d+\.?\d*)', text)
                            if price_match:
                                price = price_match.group(1)
                                if not price.startswith('$'):
                                    price = f"${price}"
                                
                                # Description is text before price (but exclude "US" if it's just currency prefix)
                                desc_text = text[:price_match.start()].strip()
                                # Remove "US" if it's just a currency prefix
                                desc_text = re.sub(r'^US\s*$', '', desc_text).strip()
                                if desc_text and desc_text.lower() != 'us':
                                    description = desc_text
                            else:
                                # No price, might be description only
                                if text.lower() != 'us':
                                    description = text
                
                # Also check for price in the h3 text itself or in parent element
                if not price:
                    # Check h3 text (handle "US$10.95" format)
                    price_match = re.search(r'(?:US\s*)?(\$?\d+\.?\d*)', item_name)
                    if price_match:
                        price = price_match.group(1)
                        if not price.startswith('$'):
                            price = f"${price}"
                        item_name = item_name[:price_match.start()].strip()
                        # Remove "US" prefix if present
                        item_name = re.sub(r'^US\s*$', '', item_name).strip()
                    else:
                        # Check parent element for price
                        parent = h3.parent
                        if parent:
                            parent_text = parent.get_text(strip=True)
                            price_match = re.search(r'(?:US\s*)?(\$?\d+\.?\d*)', parent_text)
                            if price_match:
                                price = price_match.group(1)
                                if not price.startswith('$'):
                                    price = f"${price}"
                
                # Look for description in other nearby elements if not found
                if not description:
                    # Check for description in div or span after h3
                    next_div = h3.find_next(['div', 'span'])
                    if next_div:
                        next_h3 = h3.find_next('h3')
                        next_h2 = h3.find_next('h2')
                        if (not next_h3 or (next_div.find_previous('h3') == h3)) and \
                           (not next_h2 or (next_div.find_previous('h2') == h2)):
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


def scrape_burnthillscafe_menu():
    """
    Main function to scrape menu from burnthillscafe.shop
    """
    url = "https://burnthillscafe.shop/"
    restaurant_name = "Burnt Hills Cafe"
    
    print(f"Scraping: {url}")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    all_items = []
    
    # ===== MENU (HTML) =====
    print("\n[1/1] Processing Menu (HTML)...")
    menu_url = "https://burnthillscafe.shop/menu"
    
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://burnthillscafe.shop/',
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
    output_file = output_dir / "burnthillscafe_shop_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Extracted {len(all_items)} total items from all menus")
    print(f"Saved to: {output_file}")
    
    return all_items


if __name__ == "__main__":
    scrape_burnthillscafe_menu()

