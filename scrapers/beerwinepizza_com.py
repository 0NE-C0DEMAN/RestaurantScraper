"""
Scraper for: https://beerwinepizza.com/
HTML-based menu using accura-fmwp-food-menu plugin
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
    Structure: h2.menu-head for sections, li.accura-fmwp-hover-bg for items
    """
    items = []
    
    try:
        # Find all section headers (h2 with class "menu-head")
        section_headers = soup.find_all('h2', class_='menu-head')
        
        for section_header in section_headers:
            section_name = section_header.get_text(strip=True)
            
            if not section_name:
                continue
            
            # Find the menu items container after this section header
            menu_container = section_header.find_next('div', class_='accura-fmwp-food-menu')
            if not menu_container:
                continue
            
            # Find all list items in this section
            list_items = menu_container.find_all('li', class_=re.compile(r'accura-fmwp-hover-bg'))
            
            for li in list_items:
                try:
                    # Extract price from span.accura-fmwp-regular-price
                    price_elem = li.find('span', class_='accura-fmwp-regular-price')
                    price = ""
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        # Handle multiple prices like "6/12 12/21 18/30" (quantity/price pairs)
                        if '/' in price_text and ' ' in price_text:
                            # Format: "6/12 12/21 18/30" means 6 wings for $12, 12 wings for $21, 18 wings for $30
                            # Extract all quantity/price pairs
                            pairs = re.findall(r'(\d+)/(\d+)', price_text)
                            if pairs:
                                # Format as "6/$12 | 12/$21 | 18/$30"
                                price = " | ".join([f"{q}/${p}" for q, p in pairs])
                            else:
                                # Fallback: just extract all numbers
                                price_parts = re.findall(r'\d+', price_text)
                                if price_parts:
                                    price = " / ".join([f"${p}" for p in price_parts])
                        elif '/' in price_text:
                            # Single pair like "6/12"
                            pair_match = re.search(r'(\d+)/(\d+)', price_text)
                            if pair_match:
                                price = f"{pair_match.group(1)}/${pair_match.group(2)}"
                            else:
                                # Fallback
                                price_match = re.search(r'(\d+\.?\d*)', price_text)
                                if price_match:
                                    price = f"${price_match.group(1)}"
                        else:
                            # Single price
                            price_match = re.search(r'(\d+\.?\d*)', price_text)
                            if price_match:
                                price = f"${price_match.group(1)}"
                    
                    # Extract item name from span.accura-fmwp-menu-items-title
                    title_elem = li.find('span', class_='accura-fmwp-menu-items-title')
                    item_name = ""
                    description = ""
                    
                    if title_elem:
                        # Get the main title text (excluding nested span)
                        title_text = title_elem.get_text(strip=True)
                        
                        # Check for nested span.accura-fmwp-span-content (description in parentheses)
                        nested_span = title_elem.find('span', class_='accura-fmwp-span-content')
                        if nested_span:
                            nested_text = nested_span.get_text(strip=True)
                            # Remove the nested text from title_text to get just the name
                            item_name = title_text.replace(nested_text, '').strip()
                            # Clean up parentheses and extra spaces
                            item_name = re.sub(r'\s*\(\s*\)\s*', '', item_name).strip()
                            
                            # The nested text is the description
                            if nested_text:
                                description = nested_text.strip()
                        else:
                            item_name = title_text
                    
                    # Extract additional description from p.accura-fmwp-item-description
                    desc_elem = li.find('p', class_='accura-fmwp-item-description')
                    if desc_elem:
                        desc_text = desc_elem.get_text(separator=' | ', strip=True)
                        if desc_text:
                            # Clean up the text
                            desc_text = re.sub(r'\s+', ' ', desc_text)
                            # Add space before "Add" if it's directly attached to a number
                            desc_text = re.sub(r'(\d)(Add)', r'\1 | \2', desc_text, flags=re.I)
                            # Add space after "For" if followed by a number
                            desc_text = re.sub(r'(For)(\d)', r'\1 \2', desc_text, flags=re.I)
                            
                            # If description already exists, append with separator
                            if description:
                                description = f"{description}. {desc_text}"
                            else:
                                description = desc_text
                    
                    # Only add item if we have a name
                    if item_name and len(item_name) > 2:
                        items.append({
                            'name': item_name,
                            'description': description,
                            'price': price,
                            'section': section_name
                        })
                
                except Exception as e:
                    print(f"  Error processing item: {e}")
                    continue
        
    except Exception as e:
        print(f"  Error extracting HTML menu items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_beerwinepizza_menu():
    """
    Main function to scrape menu from beerwinepizza.com
    """
    url = "https://beerwinepizza.com/"
    restaurant_name = "Beer Wine Pizza"
    
    print(f"Scraping: {url}")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    all_items = []
    
    # ===== MENU (HTML) =====
    print("\n[1/1] Processing Menu (HTML)...")
    menu_url = "https://beerwinepizza.com/menu/"
    
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://beerwinepizza.com/',
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
    output_file = output_dir / "beerwinepizza_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Extracted {len(all_items)} total items from all menus")
    print(f"Saved to: {output_file}")
    
    return all_items


if __name__ == "__main__":
    scrape_beerwinepizza_menu()
