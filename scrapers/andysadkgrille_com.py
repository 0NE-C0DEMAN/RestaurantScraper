"""
Scraper for: https://andysadkgrille.com/
Uses requests to fetch HTML menu and BeautifulSoup for parsing
All code consolidated in a single file
"""

import json
import sys
import re
import requests
from pathlib import Path
from typing import Dict, List

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("Warning: beautifulsoup4 not installed.")
    print("Install with: pip install beautifulsoup4 lxml")

def scrape_andysadkgrille_menu(url: str) -> List[Dict]:
    """Scrape menu items from andysadkgrille.com"""
    all_items = []
    restaurant_name = "Andy's Adirondack Grille"
    menu_url = "https://andysadkgrille.com/menu"
    
    print(f"Scraping: {url}")
    print(f"Menu URL: {menu_url}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    if not BS4_AVAILABLE:
        print("ERROR: beautifulsoup4 is required for HTML parsing.")
        print("Please install it with: pip install beautifulsoup4 lxml")
        return []
    
    try:
        # Headers from curl command
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Cookie': 'dps_site_id=ap-south-1; _tccl_visitor=24a256a6-3b3d-4f74-838d-2ef08f19508e; _tccl_visit=24a256a6-3b3d-4f74-838d-2ef08f19508e; _scc_session=pc=1&C_TOUCH=2025-12-31T13:44:55.023Z',
            'Pragma': 'no-cache',
            'Referer': 'https://andysadkgrille.com/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        print("Fetching menu HTML...")
        response = requests.get(menu_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        print("[OK] Received HTML content\n")
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'lxml')
        
        print("Parsing menu items...")
        items = extract_menu_items_from_html(soup)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = url
                item['menu_type'] = item.get('menu_type', 'Menu')  # Use extracted menu type or default
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items from menu\n")
        else:
            print(f"[WARNING] No items extracted from menu\n")
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching menu data: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
    
    # Save JSON file with menu items
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Restaurant: {restaurant_name}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")
    
    return all_items


def extract_beverages_from_description(description: str) -> List[Dict]:
    """Extract individual beverages from the beverages description text"""
    beverages = []
    # The description text contains multiple beverage items separated by text
    # Examples from HTML:
    # "Pepsi, Diet Pepsi, Starry, Mug Root Beer, Ginger Ale,"
    # "Tropicana Lemonade GLASS $3.50/ Pitcher $7.95"
    # "Saranac Root Beer $3.75 /bottle"
    # "Milk & Juice  Small $1.50 / Large $2.50"
    # "Iced Tea  $2.50"
    # "Coffee / Tea / Hot Chocolate $1.99"
    # "Saratoga Water Sparkling or Regular $5.25"
    
    # Normalize the description
    description = re.sub(r'\s+', ' ', description).strip()
    
    # Split by looking for patterns that indicate a new beverage item
    # Each beverage typically starts with a name and ends with a price
    # We'll look for patterns like: "Name $price" or "Name GLASS $price"
    
    # Pattern 1: "Tropicana Lemonade GLASS $3.50/ Pitcher $7.95"
    glass_pitcher_match = re.search(r'([A-Za-z\s&]+?)\s+GLASS\s+\$(\d+\.\d+)[/\s]+Pitcher\s+\$(\d+\.\d+)', description, re.I)
    if glass_pitcher_match:
        name = glass_pitcher_match.group(1).strip()
        beverages.append({
            'name': name.upper(),
            'description': "",
            'price': f"${glass_pitcher_match.group(2)} (Glass) | ${glass_pitcher_match.group(3)} (Pitcher)",
            'menu_type': 'BEVERAGES'
        })
    
    # Pattern 2: "Saranac Root Beer $3.75 /bottle" (check this before Small/Large to avoid overlap)
    bottle_match = re.search(r'([A-Za-z\s&]+?)\s+\$(\d+\.\d+)\s*/bottle', description, re.I)
    if bottle_match:
        name = bottle_match.group(1).strip()
        beverages.append({
            'name': name.upper(),
            'description': "",
            'price': f"${bottle_match.group(2)} /bottle",
            'menu_type': 'BEVERAGES'
        })
    
    # Pattern 3: "Milk & Juice  Small $1.50 / Large $2.50" (after bottle to avoid overlap)
    # Split description by "/bottle" to separate it from "Milk & Juice"
    parts = re.split(r'/bottle', description, flags=re.I)
    # Process each part - the part after "/bottle" should contain "Milk & Juice"
    for i, part in enumerate(parts):
        small_large_match = re.search(r'([A-Za-z\s&]+?)\s+Small\s+\$(\d+\.\d+)\s*/\s*Large\s+\$(\d+\.\d+)', part, re.I)
        if small_large_match:
            name = small_large_match.group(1).strip()
            # Clean up name - remove any trailing numbers or extra spaces
            name = re.sub(r'\s+\d+.*$', '', name).strip()
            # Make sure name is valid and doesn't contain "bottle"
            if name and len(name) > 2 and 'bottle' not in name.lower():
                beverages.append({
                    'name': name.upper(),
                    'description': "",
                    'price': f"${small_large_match.group(2)} (Small) | ${small_large_match.group(3)} (Large)",
                    'menu_type': 'BEVERAGES'
                })
                break  # Only process first valid match
    
    # Pattern 4: "Iced Tea  $2.50"
    iced_tea_match = re.search(r'Iced\s+Tea\s+\$(\d+\.\d+)', description, re.I)
    if iced_tea_match:
        beverages.append({
            'name': 'ICED TEA',
            'description': "",
            'price': f"${iced_tea_match.group(1)}",
            'menu_type': 'BEVERAGES'
        })
    
    # Pattern 5: "Coffee / Tea / Hot Chocolate $1.99"
    coffee_tea_match = re.search(r'(Coffee)\s*/\s*(Tea)\s*/\s*(Hot\s+Chocolate)\s+\$(\d+\.\d+)', description, re.I)
    if coffee_tea_match:
        beverages.append({
            'name': 'COFFEE',
            'description': "",
            'price': f"${coffee_tea_match.group(4)}",
            'menu_type': 'BEVERAGES'
        })
        beverages.append({
            'name': 'TEA',
            'description': "",
            'price': f"${coffee_tea_match.group(4)}",
            'menu_type': 'BEVERAGES'
        })
        beverages.append({
            'name': 'HOT CHOCOLATE',
            'description': "",
            'price': f"${coffee_tea_match.group(4)}",
            'menu_type': 'BEVERAGES'
        })
    
    # Pattern 6: "Saratoga Water Sparkling or Regular $5.25"
    saratoga_match = re.search(r'Saratoga\s+Water\s+(Sparkling|Regular)\s+(?:or\s+)?(?:Sparkling|Regular)?\s+\$(\d+\.\d+)', description, re.I)
    if saratoga_match:
        beverages.append({
            'name': 'SARATOGA WATER',
            'description': "",
            'price': f"${saratoga_match.group(2)}",
            'menu_type': 'BEVERAGES'
        })
    
    return beverages


def extract_menu_items_from_html(soup: BeautifulSoup) -> List[Dict]:
    """Extract menu items from HTML soup using data-aid attributes"""
    items = []
    
    # Find all section titles
    section_titles = soup.find_all(attrs={'data-aid': re.compile(r'MENU_SECTION_TITLE_\d+')})
    print(f"  Found {len(section_titles)} sections")
    
    for section_title in section_titles:
        section_name = section_title.get_text(strip=True)
        if not section_name:
            continue
        
        # Clean up section name (remove extra spaces, normalize)
        section_name = re.sub(r'\s+', ' ', section_name).strip()
        
        # For long section names, extract just the main part (e.g., "GOURMET PIZZA" from "GOURMET PIZZA Medium-12...")
        if len(section_name) > 50:
            # Try to extract main section name (first few words)
            words = section_name.split()
            if words:
                # Take first 2 words as section name (e.g., "GOURMET PIZZA")
                section_name = ' '.join(words[:2])
        
        # Normalize section name
        if 'GOURMET PIZZA' in section_name.upper():
            section_name = 'GOURMET PIZZA'
        
        current_section = section_name.upper()
        print(f"  Processing section: {current_section}")
        
        # Extract section number from data-aid (e.g., "MENU_SECTION_TITLE_0" -> 0)
        section_match = re.search(r'MENU_SECTION_TITLE_(\d+)', section_title.get('data-aid', ''))
        if not section_match:
            print(f"    [WARNING] Could not extract section number from {section_title.get('data-aid', '')}")
            continue
        section_num = section_match.group(1)
        print(f"    Section number: {section_num}")
        
        # Find section description (may contain first item like "Steamed Clams-Little Necks served with drawn butter 14.95")
        section_desc = soup.find(attrs={'data-aid': f'MENU_SECTION_DESCRIPTION_{section_num}'})
        if section_desc:
            section_desc_text = section_desc.get_text(strip=True)
            # Check if it contains an item with price
            # Pattern: "Item Name description price" or "Item Name price"
            price_match = re.search(r'(.+?)\s+(\d+\.?\d*)\s*$', section_desc_text)
            if price_match:
                # Extract name and price
                full_text = price_match.group(1).strip()
                price_val = price_match.group(2)
                price = f"${price_val}"
                
                # Try to separate name and description
                # Look for "served with" pattern
                if 'served with' in full_text.lower():
                    parts = re.split(r'\s+served with\s+', full_text, flags=re.I)
                    if len(parts) > 1:
                        item_name = parts[0].strip()
                        description = f"Served with {parts[1].strip()}"
                    else:
                        item_name = full_text
                        description = ""
                else:
                    # Assume everything before last few words is name
                    item_name = full_text
                    description = ""
                
                items.append({
                    'name': item_name.upper(),
                    'description': description,
                    'price': price,
                    'menu_type': current_section
                })
        
        # Find all items in this section using data-aid pattern
        # Pattern: MENU_SECTION{section_num}_ITEM{item_num}_TITLE
        item_num = 0
        items_in_section = 0
        max_items = 100  # Safety limit
        while item_num < max_items:
            # Find item title
            item_title = soup.find(attrs={'data-aid': f'MENU_SECTION{section_num}_ITEM{item_num}_TITLE'})
            if not item_title:
                break
            
            item_name = item_title.get_text(strip=True)
            
            # Find item description first (needed for price extraction)
            item_desc_elem = soup.find(attrs={'data-aid': f'MENU_SECTION{section_num}_ITEM{item_num}_DESC'})
            description = ""
            if item_desc_elem:
                description = item_desc_elem.get_text(strip=True)
                # Clean up description (remove extra spaces, add spaces before "ADD")
                description = re.sub(r'\s+', ' ', description).strip()
                # Add space before "ADD" if it's directly attached to previous text (no space before ADD)
                description = re.sub(r'([a-zA-Z0-9])ADD\s+', r'\1 ADD ', description, flags=re.I)
                # Also handle cases where ADD is at start of a sentence or after punctuation
                description = re.sub(r'\.ADD\s+', r'. ADD ', description, flags=re.I)
                description = re.sub(r'\s+', ' ', description).strip()
            
            # Find item price
            item_price_elem = soup.find(attrs={'data-aid': f'MENU_SECTION{section_num}_ITEM{item_num}_PRICE'})
            price = ""
            if item_price_elem:
                price_text = item_price_elem.get_text(strip=True)
                # Check for Market Price
                if 'Market' in price_text or 'MP' in price_text.upper():
                    price = ""
                else:
                    # Extract all prices (might have dual prices like "5.95 / 7.95" or "18.95/21.95")
                    all_prices = re.findall(r'(\d+\.?\d*)', price_text)
                    if len(all_prices) > 1:
                        # Format dual prices with Medium/Large labels
                        price = f"${all_prices[0]} (Medium) | ${all_prices[1]} (Large)"
                    elif all_prices:
                        price = f"${all_prices[0]}"
                    
                    # Also check price text for cup/bowl/crock patterns (like "cup-5.95, bowl-6.95" or "cup/5.95, crock/7.95")
                    if 'cup' in price_text.lower() or 'bowl' in price_text.lower() or 'crock' in price_text.lower():
                        # Handle "cup-5.95, bowl-6,95" (note: comma might be used instead of period)
                        cup_match = re.search(r'cup[-\s/]*(\d+[,.]?\d*)', price_text, re.I)
                        bowl_match = re.search(r'bowl[-\s/]*(\d+[,.]?\d*)', price_text, re.I)
                        crock_match = re.search(r'crock[-\s/]*(\d+[,.]?\d*)', price_text, re.I)
                        
                        if cup_match and bowl_match:
                            cup_price = cup_match.group(1).replace(',', '.')
                            bowl_price = bowl_match.group(1).replace(',', '.')
                            price = f"${cup_price} (cup) / ${bowl_price} (bowl)"
                        elif cup_match and crock_match:
                            cup_price = cup_match.group(1).replace(',', '.')
                            crock_price = crock_match.group(1).replace(',', '.')
                            price = f"${cup_price} (cup) / ${crock_price} (crock)"
            
            # Skip if it's clearly not a menu item
            if item_name and len(item_name) > 2 and len(item_name) < 100:
                # Skip add-ons and instructions
                if (not item_name.upper().startswith('ADD ') and
                    not item_name.upper().startswith('ALL ') and
                    'served with' not in item_name.lower()[:20] and
                    item_name.upper() not in ['WHITE CRUST']):
                    # Special handling for BEVERAGES section - extract individual beverages from description
                    if current_section == 'BEVERAGES' and item_name.upper() == 'BEVERAGES' and description:
                        # Parse beverages from description text
                        beverage_items = extract_beverages_from_description(description)
                        for bev_item in beverage_items:
                            items.append(bev_item)
                            items_in_section += 1
                    else:
                        # Create unique key for items with same name but different sections/prices
                        # This allows "Chicken Tenders" in both APPETIZERS and KIDS CORNER
                        item_key = f"{item_name.upper()}_{current_section}_{price}"
                        items.append({
                            'name': item_name.upper(),
                            'description': description,
                            'price': price,
                            'menu_type': current_section
                        })
                        items_in_section += 1
            
            item_num += 1
        
        print(f"    Extracted {items_in_section} items from {current_section}")
    
    # Remove duplicates based on name, section, and price
    # This allows same item name in different sections (e.g., "Chicken Tenders" in APPETIZERS and KIDS CORNER)
    seen_items = set()
    unique_items = []
    for item in items:
        item_key = f"{item['name']}_{item['menu_type']}_{item['price']}"
        if item_key not in seen_items:
            seen_items.add(item_key)
            unique_items.append(item)
    
    return unique_items


def main():
    url = "https://andysadkgrille.com/"
    scrape_andysadkgrille_menu(url)


if __name__ == "__main__":
    main()

