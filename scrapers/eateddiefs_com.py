"""
Scraper for Eddie F's New England Seafood Restaurant
Website: https://www.eateddiefs.com/
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict
import os

def scrape_food_menu(url: str) -> List[Dict]:
    """
    Scrape food menu items from Eddie F's menu page.
    Note: The menu page doesn't display prices, so prices will be empty.
    """
    items = []
    
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find main content
        main = soup.find('main')
        if not main:
            print("  [WARNING] Could not find main content")
            return []
        
        article = main.find('article')
        if not article:
            print("  [WARNING] Could not find article")
            return []
        
        # Find the food menu grid
        food_menu_grid = article.find('div', class_=lambda x: x and 'food-menu-grid' in str(x))
        if not food_menu_grid:
            print("  [WARNING] Could not find food-menu-grid")
            return []
        
        # Find all food-menu-grid-item divs
        grid_items = food_menu_grid.find_all('div', class_=lambda x: x and 'food-menu-grid-item' in str(x))
        
        current_section = ""
        section_items = 0
        
        for grid_item in grid_items:
            # Find food-menu-grid-item-content
            content = grid_item.find('div', class_=lambda x: x and 'food-menu-grid-item-content' in str(x))
            if not content:
                continue
            
            # Check if this container has an h2 (section header)
            h2 = content.find('h2')
            if h2:
                section_name = h2.get_text(strip=True)
                # Skip if it's just a description container
                if section_name in ['Our Menu']:
                    continue
                if section_name != current_section:
                    if current_section and section_items > 0:
                        print(f"      Found {section_items} items")
                    current_section = section_name
                    section_items = 0
                    print(f"    Extracting {current_section}...")
                
                # Process all h3 items in this section's menu_content
                menu_content = content.find('div', class_=lambda x: x and 'food-menu-content' in str(x))
                if menu_content:
                    # Find all h3 elements in this section
                    h3_items = menu_content.find_all('h3')
                    
                    for h3 in h3_items:
                        item_name = h3.get_text(strip=True)
                        
                        # Skip if invalid
                        if not item_name or len(item_name) > 100:
                            continue
                        
                        # Find description - it's in the next sibling div after h3's parent
                        description = ""
                        h3_parent = h3.parent
                        if h3_parent:
                            current = h3_parent.find_next_sibling()
                            while current:
                                if hasattr(current, 'name') and current.name == 'div':
                                    text = current.get_text(strip=True)
                                    # Check if this is a description (has text, not the item name, not another h3)
                                    if text and text != item_name and len(text) > 3:
                                        # Check if it's not another item (doesn't contain h3)
                                        if not current.find('h3'):
                                            description = text
                                            break
                                # Stop if we hit another h3 (next item)
                                if hasattr(current, 'find') and current.find('h3'):
                                    break
                                current = current.find_next_sibling()
                        
                        # Find price (usually empty on menu page)
                        price = ""
                        price_elem = grid_item.find('div', class_=lambda x: x and 'food-price' in str(x))
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            if price_text:
                                price = price_text
                        
                        items.append({
                            'name': item_name,
                            'description': description,
                            'price': price,
                            'section': current_section
                        })
                        section_items += 1
        
        if current_section and section_items > 0:
            print(f"      Found {section_items} items")
        
    except Exception as e:
        print(f"  [ERROR] Error scraping food menu: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_specials(url: str) -> List[Dict]:
    """
    Scrape specials from Eddie F's specials page.
    Specials have prices embedded in the text.
    """
    items = []
    
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find main content
        main = soup.find('main')
        if not main:
            print("  [WARNING] Could not find main content")
            return []
        
        article = main.find('article')
        if not article:
            print("  [WARNING] Could not find article")
            return []
        
        # Find all h2 sections (days of the week)
        h2_sections = article.find_all('h2')
        
        for h2 in h2_sections:
            day_name = h2.get_text(strip=True)
            print(f"    Extracting {day_name} specials...")
            
            # Find all special items for this day
            current = h2.find_next_sibling()
            day_items = 0
            
            while current:
                if current.name == 'h2':
                    break
                
                # Look for generic divs that contain special text
                if current.name == 'div' or (hasattr(current, 'get') and current.get('class')):
                    # Find text content that looks like a special
                    text_content = current.get_text(strip=True)
                    
                    # Skip time ranges (e.g., "11:00 AM - 09:00 PM")
                    if re.match(r'\d{1,2}:\d{2}\s*(AM|PM)\s*-\s*\d{1,2}:\d{2}\s*(AM|PM)', text_content):
                        current = current.find_next_sibling()
                        continue
                    
                    if text_content and len(text_content) > 10:
                        # Skip time ranges
                        if re.match(r'^\d{1,2}:\d{2}\s*(AM|PM)\s*-\s*\d{1,2}:\d{2}\s*(AM|PM)', text_content):
                            current = current.find_next_sibling()
                            continue
                        
                        # Extract price if present
                        price_match = re.search(r'\$(\d+(?:\.\d{2})?)', text_content)
                        price = f"${price_match.group(1)}" if price_match else ""
                        
                        # Extract item name and description
                        # Format is usually: "All Day - Item Name - Description" or "Weekly Lunch Special - Item Name - Description $12"
                        parts = text_content.split(' - ')
                        item_name = ""
                        description = text_content
                        
                        if len(parts) >= 2:
                            # Remove "All Day" or "Weekly Lunch Special" prefix
                            if parts[0] in ['All Day', 'Weekly Lunch Special']:
                                item_name = parts[1].split(' - ')[0].strip()
                                # Remove price from item name if present
                                item_name = re.sub(r'\s*\$\d+(?:\.\d{2})?.*$', '', item_name).strip()
                                # Description is the rest
                                desc_parts = ' - '.join(parts[2:]) if len(parts) > 2 else parts[1]
                                description = desc_parts.strip()
                                # Remove price from description
                                description = re.sub(r'\s*\$\d+(?:\.\d{2})?', '', description).strip()
                            else:
                                item_name = parts[0].strip()
                                description = ' - '.join(parts[1:]).strip()
                                # Remove price from both
                                item_name = re.sub(r'\s*\$\d+(?:\.\d{2})?.*$', '', item_name).strip()
                                description = re.sub(r'\s*\$\d+(?:\.\d{2})?', '', description).strip()
                        else:
                            # Try to extract name from text
                            item_name = text_content.split(' - ')[0] if ' - ' in text_content else text_content[:50]
                            item_name = re.sub(r'\s*\$\d+(?:\.\d{2})?.*$', '', item_name).strip()
                            description = text_content
                            description = re.sub(r'\s*\$\d+(?:\.\d{2})?', '', description).strip()
                        
                        # Remove time ranges from description (e.g., "11:00 AM - 09:00 PM")
                        description = re.sub(r'\d{1,2}:\d{2}\s*(AM|PM)\s*-\s*\d{1,2}:\d{2}\s*(AM|PM)', '', description).strip()
                        description = re.sub(r'\s+', ' ', description).strip()
                        
                        if item_name and len(item_name) > 3:
                            items.append({
                                'name': item_name,
                                'description': description,
                                'price': price,
                                'section': f"Specials - {day_name}"
                            })
                            day_items += 1
                
                current = current.find_next_sibling()
            
            if day_items > 0:
                print(f"      Found {day_items} items")
        
    except Exception as e:
        print(f"  [ERROR] Error scraping specials: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_eateddiefs_menu() -> List[Dict]:
    """
    Main function to scrape Eddie F's menu and specials.
    """
    all_items = []
    
    print("=" * 60)
    print("Scraping: https://www.eateddiefs.com/")
    print("=" * 60)
    
    # Scrape food menu
    menu_url = "https://www.eateddiefs.com/clifton-park-eddie-f-s-new-england-seafood-restaurant-clifton-park-food-menu"
    print("\nScraping Food Menu...")
    menu_items = scrape_food_menu(menu_url)
    all_items.extend(menu_items)
    print(f"[OK] Extracted {len(menu_items)} items from Food Menu")
    
    # Scrape specials
    specials_url = "https://www.eateddiefs.com/clifton-park-eddie-f-s-new-england-seafood-restaurant-clifton-park-happy-hours-specials"
    print("\nScraping Specials...")
    specials_items = scrape_specials(specials_url)
    all_items.extend(specials_items)
    print(f"[OK] Extracted {len(specials_items)} items from Specials")
    
    # Add metadata to all items
    for item in all_items:
        item['menu_type'] = item.get('section', '')
        item['restaurant_name'] = "Eddie F's New England Seafood Restaurant"
        item['restaurant_url'] = "https://www.eateddiefs.com/"
        item['menu_name'] = "Food Menu" if item.get('section', '').startswith('Specials') == False else "Specials"
    
    # Save to JSON
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'www_eateddiefs_com.json')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaving {len(all_items)} items to: {output_file}")
    
    print("\n" + "=" * 60)
    print("[OK] Scraping complete!")
    print(f"  - Food Menu: {len(menu_items)} items")
    print(f"  - Specials: {len(specials_items)} items")
    print(f"  - Total: {len(all_items)} items")
    print("=" * 60)
    
    return all_items


if __name__ == "__main__":
    scrape_eateddiefs_menu()

