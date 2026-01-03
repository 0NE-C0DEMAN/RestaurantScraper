"""
Scraper for: https://humptydumptyicecream.weebly.com/
The menu is organized across multiple HTML pages
"""

import json
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup


def download_html_with_requests(url: str, headers: dict = None) -> str:  # pyright: ignore[reportArgumentType]
    """Download HTML from URL using requests"""
    if headers is None:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-IN,en;q=0.9',
            'referer': 'https://humptydumptyicecream.weebly.com/menu.html',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to download HTML: {e}")
        return ""


def extract_price(text: str) -> str:
    """Extract price(s) from text"""
    # Find all price patterns like $1.00, $3.50, etc.
    prices = re.findall(r'\$(\d+\.?\d*)', text)
    if not prices:
        return ""
    
    # If multiple prices, format them
    if len(prices) == 1:
        return f"${prices[0]}"
    elif len(prices) == 2:
        return f"${prices[0]} / ${prices[1]}"
    else:
        return " / ".join([f"${p}" for p in prices])


def parse_menu_page(html: str, page_name: str) -> List[Dict]:
    """Parse menu items from a single page"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find all tables (menu items are in tables)
    tables = soup.find_all('table')
    
    for table in tables:
        # Find all cells (td or th)
        cells = table.find_all(['td', 'th'])
        
        current_section = None
        
        for cell in cells:
            # Check for section headings (h2, h3)
            headings = cell.find_all(['h2', 'h3'])
            for heading in headings:
                section_text = heading.get_text(strip=True)
                # Remove "menu" keyword
                section_text = re.sub(r'\bmenu\b', '', section_text, flags=re.IGNORECASE).strip()
                if section_text:
                    current_section = section_text
            
            # Special handling for subs page - extract items from table rows
            if 'subs' in page_name.lower() or 'hot dog' in page_name.lower():
                rows = cell.find_all('tr')
                if rows:
                    for row in rows:
                        cells_in_row = row.find_all(['td', 'th'])
                        if len(cells_in_row) >= 2:
                            # Check if this looks like a sub item row (has prices in last columns)
                            first_cell_text = cells_in_row[0].get_text(strip=True)
                            # Skip header rows
                            if first_cell_text in ['Cold Subs', '6"', '12"', 'Hot Dogs', 'Bacon Add-on']:
                                if 'Cold Subs' in first_cell_text:
                                    current_section = 'Cold Subs'
                                elif 'Hot Dogs' in first_cell_text:
                                    current_section = 'Hot Dogs'
                                continue
                            
                            # Extract item name from first cell
                            item_name_elem = cells_in_row[0].find('strong')
                            if not item_name_elem:
                                item_name_elem = cells_in_row[0]
                            
                            item_name = item_name_elem.get_text(strip=True)
                            item_name = re.sub(r'\s+', ' ', item_name).strip()
                            
                            # Skip if empty or too short
                            if not item_name or len(item_name) < 2:
                                continue
                            
                            # Extract prices from remaining cells
                            prices = []
                            for price_cell in cells_in_row[1:]:
                                cell_text = price_cell.get_text(strip=True)
                                price_matches = re.findall(r'\$(\d+\.?\d*)', cell_text)
                                prices.extend(price_matches)
                            
                            # Format price with size labels
                            if len(prices) == 2:
                                price = f'6" - ${prices[0]} / 12" - ${prices[1]}'
                            elif len(prices) == 1:
                                price = f"${prices[0]}"
                            else:
                                price = ""
                            
                            # Get description from first cell (after item name)
                            description = cells_in_row[0].get_text(strip=True)
                            description = re.sub(re.escape(item_name), '', description, count=1).strip()
                            description = re.sub(r'\$\d+\.?\d*', '', description).strip()
                            
                            menu_type = current_section or page_name
                            menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
                            if not menu_type:
                                menu_type = page_name
                            
                            if item_name:
                                items.append({
                                    'name': item_name,
                                    'description': description,
                                    'price': price,
                                    'menu_type': menu_type
                                })
                    continue  # Skip the strong tag processing for subs
            
            # Find all strong tags (item names)
            strong_tags = cell.find_all('strong')
            
            for idx, strong in enumerate(strong_tags):
                item_name = strong.get_text(strip=True)
                # Clean up item name - remove extra whitespace
                item_name = re.sub(r'\s+', ' ', item_name).strip()
                
                # Skip if it's a section heading or too short
                if not item_name or len(item_name) < 2:
                    continue
                
                # Skip known section headings
                if item_name in ['Sizes', 'Toppings', 'Dips', 'Cones Types', 'Pints and Quarts', 'Other Treats']:
                    current_section = item_name
                    # Remove "menu" keyword
                    current_section = re.sub(r'\bmenu\b', '', current_section, flags=re.IGNORECASE).strip()
                    continue
                
                # Special handling for "Cold Subs 6" 12"" - extract individual subs
                if 'Cold Subs' in item_name and ('6"' in item_name or '12"' in item_name):
                    current_section = 'Cold Subs'
                    # Get all text from the parent cell after this strong tag
                    cell_text = cell.get_text(separator=' ', strip=True)
                    
                    # Find the position of "Cold Subs" in the text
                    cold_subs_pos = cell_text.find('Cold Subs')
                    if cold_subs_pos != -1:
                        # Get text after "Cold Subs 6" 12""
                        sub_section = cell_text[cold_subs_pos:]
                        # Remove the "Cold Subs 6" 12"" header
                        sub_section = re.sub(r'Cold Subs\s*6["\s]*12["\s]*', '', sub_section, flags=re.IGNORECASE).strip()
                        
                        # Split by common separators and extract sub items
                        # Pattern: "SubName $X.XX $Y.YY" (may have multiple on same line)
                        # Updated pattern to better match sub names
                        sub_pattern = r'\b([A-Z][A-Za-z\s:,\-]+?)\s+\$(\d+\.?\d*)\s+\$(\d+\.?\d*)'
                        sub_matches = re.findall(sub_pattern, sub_section)
                        
                        for sub_match in sub_matches:
                            sub_name = sub_match[0].strip()
                            price1 = sub_match[1]
                            price2 = sub_match[2]
                            price = f'6" - ${price1} / 12" - ${price2}'
                            
                            # Skip if it's not a real sub name (too short or contains unwanted words)
                            # But allow "Cheese" as it's a valid sub name
                            skip_words = ['white', 'rolls', 'subs', 'are', 'served', 'with', 'lettuce', 'tomato', 'onions', 'blend', 'swiss', 'american', 'hot', 'peppers', 'pickles', 'available', 'request', 'dressings']
                            # Don't skip if it's "Cheese" (capitalized, standalone)
                            if sub_name.lower() == 'cheese' and sub_name[0].isupper():
                                pass  # Allow "Cheese" as a sub
                            elif len(sub_name) < 2 or any(word in sub_name.lower() for word in skip_words):
                                continue
                            # Skip if it contains "bacon" and "add" (will be handled separately)
                            if 'bacon' in sub_name.lower() and 'add' in sub_name.lower():
                                continue
                            
                            # Handle "Bacon Add-on" separately - look for it in the text
                            if 'bacon' in sub_name.lower() and 'add' in sub_name.lower():
                                sub_name = 'Bacon Add-on'
                            
                            menu_type = current_section or page_name
                            menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
                            if not menu_type:
                                menu_type = page_name
                            
                            items.append({
                                'name': sub_name,
                                'description': '',
                                'price': price,
                                'menu_type': menu_type
                            })
                    
                    # Also extract "Bacon Add-on" separately if it appears in the cell
                    if 'Bacon Add-on' in cell_text or ('bacon' in cell_text.lower() and 'add-on' in cell_text.lower()):
                        bacon_match = re.search(r'Bacon\s+Add-on[^$]*\$(\d+\.?\d*)[^$]*\$(\d+\.?\d*)', cell_text, re.IGNORECASE)
                        if bacon_match:
                            price1 = bacon_match.group(1)
                            price2 = bacon_match.group(2)
                            price = f'6" - ${price1} / 12" - ${price2}'
                            
                            menu_type = current_section or page_name
                            menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
                            if not menu_type:
                                menu_type = page_name
                            
                            items.append({
                                'name': 'Bacon Add-on',
                                'description': '',
                                'price': price,
                                'menu_type': menu_type
                            })
                    
                    continue
                
                # Special handling for "Pints" and "Quarts" - they should be separate items
                # Check if item_name contains "Pints" or "Quarts" but also has "Yogurt"
                if 'Pints' in item_name or 'Quarts' in item_name:
                    # If it's "Pints Yogurt and Dole Whip", split it
                    if 'Yogurt' in item_name or 'Dole Whip' in item_name:
                        # Extract just "Pints" or "Quarts"
                        if 'Pints' in item_name:
                            item_name = 'Pints'
                        elif 'Quarts' in item_name:
                            item_name = 'Quarts'
                    
                    # Get text after the strong tag
                    text_parts = []
                    current = strong.next_sibling
                    next_strong = None
                    if idx + 1 < len(strong_tags):
                        next_strong = strong_tags[idx + 1]
                    
                    while current and current != next_strong:
                        if isinstance(current, str):
                            text = current.strip()
                            if text:
                                text_parts.append(text)
                        elif current.name == 'br':
                            text_parts.append(' ')
                        current = current.next_sibling
                    
                    item_text = ' '.join(text_parts).strip()
                    price = extract_price(item_text)
                    
                    # Format price with size labels if multiple prices
                    if '/' in price:
                        prices = re.findall(r'\$(\d+\.?\d*)', price)
                        if len(prices) == 2:
                            price = f"Regular - ${prices[0]} / Yogurt and Dole Whip - ${prices[1]}"
                    
                    description = item_text
                    description = re.sub(r'\$\d+\.?\d*\s*/\s*\$\d+\.?\d*', '', description)
                    description = re.sub(r'\$\d+\.?\d*', '', description)
                    description = re.sub(r'\s+', ' ', description).strip()
                    description = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', description)
                    
                    menu_type = current_section or page_name
                    menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
                    if not menu_type:
                        menu_type = page_name
                    
                    items.append({
                        'name': item_name,
                        'description': description,
                        'price': price,
                        'menu_type': menu_type
                    })
                    continue
                
                # Get text content between this strong tag and the next one
                text_parts = []
                price = ""
                description = ""
                
                # Walk through siblings after the strong tag
                current = strong.next_sibling
                next_strong = None
                if idx + 1 < len(strong_tags):
                    next_strong = strong_tags[idx + 1]
                
                while current and current != next_strong:
                    if isinstance(current, str):
                        text = current.strip()
                        if text:
                            text_parts.append(text)
                    elif current.name == 'br':
                        text_parts.append(' ')
                    current = current.next_sibling
                
                # Combine text parts
                item_text = ' '.join(text_parts).strip()
                
                # Extract price from this item's text
                price = extract_price(item_text)
                
                # Extract description - remove price patterns
                description = item_text
                # Remove prices
                description = re.sub(r'\$\d+\.?\d*\s*/\s*\$\d+\.?\d*', '', description)
                description = re.sub(r'\$\d+\.?\d*', '', description)
                # Clean up extra spaces and special characters
                description = re.sub(r'\s+', ' ', description).strip()
                description = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', description)  # Remove zero-width spaces
                
                # If no price found in item text, try looking in the cell
                if not price:
                    cell_text = cell.get_text(separator=' ', strip=True)
                    # Try to find price near the item name
                    # Look for pattern: item_name ... $price
                    pattern = re.escape(item_name) + r'.*?(\$\d+\.?\d*(?:\s*/\s*\$\d+\.?\d*)?)'
                    match = re.search(pattern, cell_text, re.IGNORECASE)
                    if match:
                        price = match.group(1)
                
                # Determine menu_type
                menu_type = current_section or page_name
                # Remove "menu" keyword
                menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
                if not menu_type:
                    menu_type = page_name
                
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'menu_type': menu_type
                })
    
    return items


def scrape_humptydumptyicecream_menu(url: str) -> List[Dict]:
    """
    Scrape menu from humptydumptyicecream.weebly.com
    The menu is organized across multiple HTML pages
    """
    all_items = []
    restaurant_name = "Humpty Dumpty Ice Cream"
    restaurant_url = "https://humptydumptyicecream.weebly.com/"
    
    print("=" * 60)
    print(f"Scraping: {url}")
    print("=" * 60)
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output filename
    url_safe = url.replace('https://', '').replace('http://', '').replace('www.', '').replace('/', '_').replace('.', '_').rstrip('_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    # Menu pages to scrape
    menu_pages = [
        {
            'url': 'https://humptydumptyicecream.weebly.com/cones.html',
            'name': 'Cones & Dishes'
        },
        {
            'url': 'https://humptydumptyicecream.weebly.com/sundaes.html',
            'name': 'Sundaes'
        },
        {
            'url': 'https://humptydumptyicecream.weebly.com/shakes-sodas-and-slushes.html',
            'name': 'Shakes, Sodas, & Slushes'
        },
        {
            'url': 'https://humptydumptyicecream.weebly.com/crunch-cream-and-flurries.html',
            'name': 'Crunch Cream & Flurries'
        },
        {
            'url': 'https://humptydumptyicecream.weebly.com/subs.html',
            'name': 'Subs & Hot Dogs'
        },
        {
            'url': 'https://humptydumptyicecream.weebly.com/etc.html',
            'name': 'Extras'
        }
    ]
    
    try:
        for idx, page_info in enumerate(menu_pages, 1):
            page_url = page_info['url']
            page_name = page_info['name']
            
            print(f"[{idx}/{len(menu_pages)}] Processing: {page_name}")
            print(f"  URL: {page_url}")
            
            # Download HTML
            html = download_html_with_requests(page_url)
            
            if not html:
                print(f"  [ERROR] Failed to download page")
                continue
            
            # Parse menu items
            items = parse_menu_page(html, page_name)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                    item['menu_name'] = page_name
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items\n")
            else:
                print(f"  [WARNING] No items extracted\n")
        
        # Post-processing: Format prices with size labels and clean up items
        for item in all_items:
            # Format prices with size labels for items with multiple prices
            if item['price'] and '/' in item['price']:
                price_str = item['price']
                # Check if already has size labels
                has_size_labels = any(keyword in price_str.lower() for keyword in ['6"', '12"', 'regular', 'yogurt', 'dole whip', 'small', 'large', 'cup', 'bowl', 'single', '2 for', 'for $'])
                
                if not has_size_labels:
                    prices = re.findall(r'\$(\d+\.?\d*)', price_str)
                    if len(prices) == 2:
                        name_lower = item['name'].lower()
                        # Format based on item type
                        if 'sub' in name_lower or 'salami' in name_lower or 'bologna' in name_lower or 'ham' in name_lower or 'turkey' in name_lower or 'tuna' in name_lower or 'roast beef' in name_lower or 'deluxe' in name_lower:
                            item['price'] = f'6" - ${prices[0]} / 12" - ${prices[1]}'
                        elif 'bacon' in name_lower or 'add-on' in name_lower:
                            item['price'] = f'6" - ${prices[0]} / 12" - ${prices[1]}'
                        elif 'pints' in name_lower or 'quarts' in name_lower:
                            item['price'] = f"Regular - ${prices[0]} / Yogurt and Dole Whip - ${prices[1]}"
                        elif 'yogurt' in name_lower and 'dole whip' in name_lower:
                            # Items like "Small Yogurt and Dole Whip" should have Regular/Yogurt labels
                            if 'small' in name_lower:
                                item['price'] = f"Regular - ${prices[0]} / Yogurt and Dole Whip - ${prices[1]}"
                            elif 'medium' in name_lower:
                                item['price'] = f"Regular - ${prices[0]} / Yogurt and Dole Whip - ${prices[1]}"
                            else:
                                item['price'] = f"Regular - ${prices[0]} / Yogurt and Dole Whip - ${prices[1]}"
                        elif 'hot dog' in name_lower:
                            item['price'] = f"Single - ${prices[0]} / 2 for ${prices[1]}"
                        elif prices[0] == prices[1]:
                            # Same price twice - might be a mistake, keep as is
                            item['price'] = f"${prices[0]}"
                        else:
                            # Default: assume it's size-based
                            item['price'] = f"Small - ${prices[0]} / Large - ${prices[1]}"
            
            # Clean up item names - remove zero-width spaces and extra whitespace
            item['name'] = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', item['name']).strip()
            item['name'] = re.sub(r'\s+', ' ', item['name'])
            
            # Clean up descriptions
            if item['description']:
                item['description'] = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', item['description']).strip()
                item['description'] = re.sub(r'\s+', ' ', item['description'])
        
        # Remove parsing artifacts (items that shouldn't be menu items)
        artifacts_to_remove = [',', ', and', 'lettuce', 'tomato', 'onions', 'cheese', 'Subs are served with']
        all_items = [item for item in all_items if item['name'] not in artifacts_to_remove and not item['name'].startswith('(') and 'Subs are served with' not in item['name']]
        
        # Deduplicate items
        unique_items = []
        seen = set()
        for item in all_items:
            item_tuple = (item['name'], item['description'], item['price'], item['menu_type'])
            if item_tuple not in seen:
                unique_items.append(item)
                seen.add(item_tuple)
        
        print(f"[OK] Extracted {len(unique_items)} unique items from all pages\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        unique_items = []
    
    # Save to JSON
    print(f"Saving results...")
    if unique_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(unique_items, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved {len(unique_items)} unique items to: {output_json}")
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(unique_items)}")
    print(f"Saved to: {output_json}")
    print(f"{'='*60}")
    
    return unique_items


if __name__ == '__main__':
    url = "https://humptydumptyicecream.weebly.com/"
    scrape_humptydumptyicecream_menu(url)

