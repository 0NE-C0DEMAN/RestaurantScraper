"""
Scraper for cantinasaratoga.com
Extracts menu items from Food Menu, Drink Menu, and Tequila & Mezcal sections
"""

import json
import re
import requests
from typing import List, Dict
from bs4 import BeautifulSoup


def extract_menu_items_from_html(soup: BeautifulSoup, menu_name: str = "Food Menu") -> List[Dict]:
    """
    Extract menu items from HTML soup for a specific menu tab
    
    Args:
        soup: BeautifulSoup object of the HTML
        menu_name: Name of the menu tab ("Food Menu", "Drink Menu", or "Tequila & Mezcal")
    
    Returns:
        List of dictionaries containing menu items
    """
    items = []
    
    # Map menu names to tab IDs
    tab_ids = {
        "Food Menu": "tab-1588165557567-0-1",
        "Drink Menu": "tab-1588165568536-0-6",
        "Tequila & Mezcal": "tab-1620913222545-5-9"
    }
    
    tab_id = tab_ids.get(menu_name)
    if not tab_id:
        print(f"  [WARNING] Unknown menu name: {menu_name}")
        return []
    
    # Find the tab content
    tab_content = soup.find('div', id=tab_id)
    if not tab_content:
        print(f"  [WARNING] Could not find {menu_name} tab")
        return []
    
    print(f"  Found {menu_name} tab")
    
    # Find all sections (h2 headings) within this tab
    sections = tab_content.find_all('h2')
    
    for section in sections:
        section_name = section.get_text(strip=True)
        if not section_name:
            continue
        
        # Skip section headers that are just descriptions (like "Blanco", "Reposado", "Anejo")
        if section_name in ["Blanco", "Reposado", "Anejo", "Extra Anejo", "Mezcal/Other Agave Spirits"]:
            # These are sub-sections, we'll use the parent h2 if available
            parent_h2 = section.find_previous('h2')
            if parent_h2 and parent_h2 != section:
                # Use parent section name
                parent_section = parent_h2.get_text(strip=True)
                if parent_section and len(parent_section) > 3:
                    section_name = f"{parent_section} - {section_name}"
            else:
                # Use this as the section name
                pass
        
        # Find the table after this h2
        # Look for the next table with class mk-fancy-table
        table = None
        next_elem = section.find_next_sibling()
        while next_elem:
            if hasattr(next_elem, 'name') and next_elem.name == 'div':
                table = next_elem.find('table')
                if table:
                    break
            elif hasattr(next_elem, 'name') and next_elem.name == 'table':
                table = next_elem
                break
            next_elem = next_elem.find_next_sibling()
        
        # If not found as sibling, look in parent containers
        if not table:
            # Find the parent container and look for table within it
            parent_container = section.find_parent(['div', 'section'])
            if parent_container:
                table = parent_container.find('table', class_=lambda x: x and 'mk-fancy-table' in ' '.join(x) if isinstance(x, list) else 'mk-fancy-table' in str(x))
                if not table:
                    # Try finding any table
                    table = parent_container.find('table')
        
        if not table:
            # Try finding table that comes after this h2 in document order
            table = section.find_next('table')
        
        if not table:
            print(f"    [WARNING] No table found for section: {section_name}")
            continue
        
        # Extract items from table
        rows = table.find_all('tr')
        current_item = None
        
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 2:
                continue
            
            first_td = tds[0]
            second_td = tds[1]
            
            # Check if this is an add-on (has class "add-food")
            is_addon = 'add-food' in first_td.get('class', [])
            
            if is_addon:
                # This is an add-on, append to previous item's description
                addon_name = first_td.get_text(strip=True)
                addon_price = second_td.get_text(strip=True)
                
                if current_item and addon_name and addon_price:
                    # Remove "Add" prefix if already present
                    if addon_name.lower().startswith('add '):
                        addon_name = addon_name[4:].strip()
                    
                    if current_item.get('description'):
                        current_item['description'] += f" | Add {addon_name}: ${addon_price}"
                    else:
                        current_item['description'] = f"Add {addon_name}: ${addon_price}"
                continue
            
            # Extract item name from first td (in <strong> tags)
            strong_tag = first_td.find('strong')
            if not strong_tag:
                continue
            
            item_name = strong_tag.get_text(strip=True)
            if not item_name:
                continue
            
            # Extract description (text in first td after strong tag)
            description = ""
            # Get all text from first td, remove the strong text
            full_text = first_td.get_text(strip=True)
            if full_text.startswith(item_name):
                desc_text = full_text[len(item_name):].strip()
                if desc_text:
                    description = desc_text
            
            # Extract price from second td
            price_text = second_td.get_text(strip=True)
            price = ""
            
            if menu_name == "Tequila & Mezcal":
                # Prices are in format like "10/11/12" (Blanco/Reposado/Anejo) or "_/15/17"
                # Format: "Blanco/Reposado/Anejo" or just numbers
                if '/' in price_text:
                    # Multiple prices
                    price_parts = price_text.split('/')
                    formatted_prices = []
                    labels = ["Blanco", "Reposado", "Anejo"]
                    for i, part in enumerate(price_parts[:3]):
                        part = part.strip()
                        if part and part != '_':
                            label = labels[i] if i < len(labels) else ""
                            if label:
                                formatted_prices.append(f"{label}: ${part}")
                            else:
                                formatted_prices.append(f"${part}")
                    if formatted_prices:
                        price = " | ".join(formatted_prices)
                else:
                    # Single price
                    price_match = re.search(r'(\d+\.?\d*)', price_text)
                    if price_match:
                        price = f"${price_match.group(1)}"
            else:
                # Regular price format: "12.95" or "6.95 / 10.95"
                if '/' in price_text:
                    # Multiple prices
                    price_parts = re.findall(r'(\d+\.?\d*)', price_text)
                    formatted_prices = [f"${p}" for p in price_parts]
                    price = " | ".join(formatted_prices)
                else:
                    # Single price
                    price_match = re.search(r'(\d+\.?\d*)', price_text)
                    if price_match:
                        price = f"${price_match.group(1)}"
            
            # Create item
            current_item = {
                'name': item_name,
                'description': description,
                'price': price,
                'menu_type': section_name,
                'restaurant_name': "Cantina Saratoga",
                'restaurant_url': "https://www.cantinasaratoga.com/",
                'menu_name': menu_name
            }
            
            items.append(current_item)
    
    return items


def scrape_cantinasaratoga_menu(url: str) -> List[Dict]:
    """
    Main function to scrape menu from cantinasaratoga.com
    
    Args:
        url: URL of the menu page
    
    Returns:
        List of dictionaries containing all menu items
    """
    all_items = []
    restaurant_name = "Cantina Saratoga"
    
    # Menu tabs to scrape
    menus = ["Food Menu", "Drink Menu", "Tequila & Mezcal"]
    
    try:
        # Fetch the HTML
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.cantinasaratoga.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        print(f"Fetching menu from {url}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract items from each menu
        for menu_name in menus:
            print(f"\nExtracting {menu_name}...")
            items = extract_menu_items_from_html(soup, menu_name)
            print(f"  Extracted {len(items)} items from {menu_name}")
            all_items.extend(items)
        
        print(f"\nTotal items extracted: {len(all_items)}")
        
    except requests.RequestException as e:
        print(f"Error fetching menu: {e}")
        return []
    except Exception as e:
        print(f"Error scraping menu: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return all_items


if __name__ == "__main__":
    url = "https://www.cantinasaratoga.com/menu/"
    items = scrape_cantinasaratoga_menu(url)
    
    # Save to JSON file
    output_file = "output/cantinasaratoga_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(items)} items to {output_file}")

