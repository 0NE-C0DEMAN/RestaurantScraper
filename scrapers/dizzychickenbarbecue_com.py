"""
Scraper for: https://www.dizzychickenbarbecue.com/
Extracts menu items from food menu and drink menu pages
"""

import json
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup


def extract_price_and_addons(text: str) -> tuple:
    """
    Extract price and add-ons from item text.
    Returns: (price_string, addons_list)
    """
    # First, extract add-ons (they come after "Add" or "Add:")
    addon_pattern = r'(?:Add|Add:)\s+([^|]+?)\s+(\$?\d+\.\d{2})'
    addons = re.findall(addon_pattern, text, re.IGNORECASE)
    
    # Format add-ons
    addon_list = []
    for addon_name, addon_price in addons:
        addon_name = addon_name.strip()
        if not addon_price.startswith('$'):
            addon_price = f"${addon_price}"
        addon_list.append(f"Add {addon_name} {addon_price}")
    
    # Remove add-on text from text to extract main price
    text_without_addons = text
    for addon_name, addon_price in addons:
        text_without_addons = re.sub(
            rf'(?:Add|Add:)\s+{re.escape(addon_name)}\s+\$?{re.escape(addon_price)}',
            '',
            text_without_addons,
            flags=re.IGNORECASE
        )
    
    # Check for Glass/Bottle format (e.g., "Glass 9.00, Bottle 31.00")
    glass_bottle_pattern = r'Glass\s+(\$?\d+\.\d{2}),?\s+Bottle\s+(\$?\d+\.\d{2})'
    glass_bottle_match = re.search(glass_bottle_pattern, text_without_addons, re.IGNORECASE)
    
    if glass_bottle_match:
        glass_price = glass_bottle_match.group(1)
        bottle_price = glass_bottle_match.group(2)
        # Format prices
        if not glass_price.startswith('$'):
            glass_price = f"${glass_price}"
        if not bottle_price.startswith('$'):
            bottle_price = f"${bottle_price}"
        price_str = f"Glass {glass_price}, Bottle {bottle_price}"
        return price_str, addon_list
    
    # Check for single Bottle price (e.g., "Bottle 14" or "Bottle 14.00")
    bottle_only_pattern = r'Bottle\s+(\$?\d+(?:\.\d{2})?)'
    bottle_match = re.search(bottle_only_pattern, text_without_addons, re.IGNORECASE)
    if bottle_match:
        bottle_price = bottle_match.group(1)
        if '.' not in bottle_price:
            bottle_price = f"{bottle_price}.00"
        if not bottle_price.startswith('$'):
            bottle_price = f"${bottle_price}"
        price_str = f"Bottle {bottle_price}"
        return price_str, addon_list
    
    # Extract main price(s) - look for prices before "Add" text or at the end
    # Pattern to match prices like "$12.95", "12.95", "sm 6.95 | lg 9.95"
    # First try to match decimal prices, then whole numbers
    price_pattern = r'(\$?\d+\.\d{2})'
    prices = re.findall(price_pattern, text_without_addons)
    
    # If no decimal prices found, try whole numbers
    if not prices:
        # Look for patterns like "Bottle 14", "Glass 9", etc.
        whole_number_pattern = r'(?:Bottle|Glass|Split)\s+(\d+)'
        whole_numbers = re.findall(whole_number_pattern, text_without_addons, re.IGNORECASE)
        if whole_numbers:
            # Convert to decimal format
            prices = [f"{num}.00" for num in whole_numbers]
        else:
            # Check for standalone whole numbers at the end (like "NY 8", "VT 8", or "crust.7")
            # Pattern: space or period followed by a single digit or two digits at end of text
            end_number_pattern = r'[.\s]+(\d{1,2})(?:\s|$)'
            end_numbers = re.findall(end_number_pattern, text_without_addons)
            if end_numbers:
                # Take the last number (most likely the price)
                prices = [f"{end_numbers[-1]}.00"]
    
    # Format price
    if not prices:
        price_str = ""
    elif len(prices) == 1:
        price_str = f"${prices[0]}" if not prices[0].startswith('$') else prices[0]
    else:
        # Multiple prices (like "sm 6.95 | lg 9.95")
        price_parts = []
        for price in prices:
            if not price.startswith('$'):
                price_parts.append(f"${price}")
            else:
                price_parts.append(price)
        price_str = " - ".join(price_parts)
    
    return price_str, addon_list


def extract_item_from_li(li_element) -> Dict:
    """
    Extract menu item information from a <li> element.
    """
    # Get all text
    full_text = li_element.get_text(separator=' | ', strip=True)
    
    # Find strong or bold tags (item name) - HTML uses both <strong> and <b>
    strong_tags = li_element.find_all(['strong', 'b'])
    if strong_tags:
        # First strong/bold tag is usually the item name
        item_name = strong_tags[0].get_text(strip=True)
        
        # Get description - extract from <em> tags and plain text, excluding the name tag
        description_parts = []
        name_found = False
        
        # Process all children in order
        for child in li_element.children:
            if hasattr(child, 'name'):
                # Skip the strong/b tag that contains the name
                if child.name in ['strong', 'b'] and not name_found:
                    name_found = True
                    continue
                # Get text from <em> tags and other elements
                text = child.get_text(strip=True)
                if text and text != item_name:
                    # Don't add if it's just the item name repeated
                    if text != item_name:
                        description_parts.append(text)
            elif hasattr(child, 'string') and child.string:
                # Plain text node
                text = child.string.strip()
                if text and text != item_name:
                    # Don't add if it's just the item name
                    if text != item_name:
                        description_parts.append(text)
        
        # Join description parts
        description = ' | '.join(description_parts).strip()
        
        # If description is empty, fall back to removing name from full_text
        if not description:
            description = full_text.replace(item_name, '', 1).strip()
            # Remove leading/trailing separators
            description = re.sub(r'^\s*\|\s*|\s*\|\s*$', '', description)
    else:
        # No strong tag - item name is the first text node or first part before price
        # Try to get the first non-empty text node
        item_name = ""
        description = ""
        
        # Get all direct children
        children = list(li_element.children)
        
        # Find first text node or element with text
        first_text = None
        remaining_parts = []
        
        for child in children:
            if hasattr(child, 'string') and child.string and child.string.strip():
                text = child.string.strip()
                if not first_text:
                    first_text = text
                else:
                    remaining_parts.append(text)
            elif hasattr(child, 'get_text'):
                text = child.get_text(strip=True)
                if text:
                    if not first_text:
                        first_text = text
                    else:
                        remaining_parts.append(text)
        
        if first_text:
            # First text is the name, but might contain description too
            # Split by common separators or price patterns
            # Check if it contains a price - if so, name is before price
            price_match = re.search(r'(\$?\d+\.\d{2})', first_text)
            if price_match:
                # Price found, name is before price
                item_name = first_text[:price_match.start()].strip()
                description = first_text[price_match.start():].strip()
                if remaining_parts:
                    description += ' | ' + ' | '.join(remaining_parts)
            else:
                # No price in first text, use it as name
                item_name = first_text
                # Description is remaining parts, but make sure name is not in them
                description = ' | '.join(remaining_parts) if remaining_parts else ""
        else:
            # Fallback: split by | and take first part
            parts = full_text.split('|', 1)
            item_name = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""
            # Immediately remove name from description if it appears (from fallback split)
            if item_name and description and item_name in description:
                description = description.replace(item_name, '', 1).strip()
                description = re.sub(r'^\s*\|\s*', '', description)
                description = re.sub(r'\s*\|\s*$', '', description)
        
        # After extracting name and description, make sure name is not in description
        # (This handles cases where name might appear in remaining_parts)
        if item_name and description and item_name in description:
            # Remove name from description (handle with separators)
            description = description.replace(item_name, '', 1).strip()
            description = re.sub(r'^\s*\|\s*', '', description)
            description = re.sub(r'\s*\|\s*$', '', description)
    
    # Extract price and add-ons
    price, addons = extract_price_and_addons(full_text)
    
    # Remove item name from description if it appears there (do this BEFORE price removal)
    # This is critical - do it multiple times to catch all occurrences
    if item_name and description:
        # Keep removing name until it's gone (handle cases where name appears multiple times)
        max_iterations = 5
        iteration = 0
        while item_name in description and iteration < max_iterations:
            # Try simple string replacement first (most reliable for exact matches)
            new_desc = description.replace(item_name, '', 1)
            if new_desc != description:
                description = new_desc
            else:
                # If simple replace didn't work, try regex with separators
                name_pattern = re.escape(item_name)
                # Remove name at start of description (with optional separator)
                description = re.sub(rf'^{name_pattern}\s*\|\s*', '', description, flags=re.IGNORECASE)
                # Remove name in middle (with separators on both sides)
                description = re.sub(rf'\s*\|\s*{name_pattern}\s*\|\s*', ' | ', description, flags=re.IGNORECASE)
                # Remove name at end (with separator before)
                description = re.sub(rf'\s*\|\s*{name_pattern}$', '', description, flags=re.IGNORECASE)
            iteration += 1
        # Clean up any double separators or leading/trailing separators
        description = re.sub(r'\s*\|\s*\|\s*', ' | ', description)
        description = re.sub(r'^\s*\|\s*', '', description)
        description = re.sub(r'\s*\|\s*$', '', description)
        description = description.strip()
    
    # Remove price from description
    if price:
        # Remove price patterns from description
        description = re.sub(r'\$\d+\.\d{2}', '', description)
        description = re.sub(r'\d+\.\d{2}', '', description)
        
        # Remove patterns like "Bottle 14", "Glass 9", "Bottle 14.00", etc.
        description = re.sub(r'(?:Bottle|Glass|Split)\s+\d+(?:\.\d{2})?', '', description, flags=re.IGNORECASE)
        
        # Remove leftover "Glass , Bottle" or "Glass, Bottle" patterns
        description = re.sub(r'Glass\s*,?\s*Bottle', '', description, flags=re.IGNORECASE)
        description = re.sub(r'Bottle\s*,?\s*Glass', '', description, flags=re.IGNORECASE)
        
        # Remove standalone whole numbers at the end (like "NY 8" -> "NY", "crust.7" -> "crust")
        # This handles cases where price is a whole number at the end of description
        # Match space or period followed by 1-2 digits at the end
        description = re.sub(r'[.\s]+\d{1,2}\s*$', '', description)
        
        # Clean up separators and whitespace
        description = re.sub(r'\s*\|\s*\|+\s*', ' | ', description)  # Multiple separators
        description = re.sub(r'\s*\|\s*$', '', description)  # Remove trailing separator
        description = re.sub(r'^\s*\|\s*', '', description)  # Remove leading separator
        description = re.sub(r'\s+', ' ', description)  # Multiple spaces to single
        description = description.strip()
    
    # Remove add-on text from description
    if addons:
        for addon_name, _ in re.findall(r'(?:Add|Add:)\s+([^|]+?)\s+(\$?\d+\.\d{2})', full_text, re.IGNORECASE):
            description = description.replace(f"Add {addon_name}", '').replace(f"Add: {addon_name}", '')
        description = re.sub(r'\s*\|\s*$', '', description).strip()
    
    # Format price with add-ons
    if addons:
        if price:
            price = f"{price} / {' / '.join(addons)}"
        else:
            price = " / ".join(addons)
    
    return {
        'name': item_name,
        'description': description,
        'price': price
    }


def extract_menu_section(section_heading, soup: BeautifulSoup) -> List[Dict]:
    """
    Extract all items from a menu section.
    """
    items = []
    
    # Find all headings
    headings = soup.find_all(['h2', 'h3', 'h4'])
    
    # Find the section heading
    heading = None
    for h in headings:
        heading_text = h.get_text(strip=True)
        # Try exact match first, then partial match
        if heading_text == section_heading or section_heading.lower() in heading_text.lower():
            heading = h
            break
    
    if not heading:
        return items
    
    # Find the next <ul> list after the heading
    # Use find_next to search all following elements, but stop at next heading
    next_list = None
    current = heading.find_next()
    
    while current:
        if hasattr(current, 'name'):
            if current.name == 'ul':
                next_list = current
                break
            elif current.name in ['h2', 'h3', 'h4']:
                # Reached next section heading, stop
                break
        current = current.find_next()
    
    if not next_list:
        return items
    
    # Extract items from list
    for li in next_list.find_all('li', recursive=False):
        try:
            item = extract_item_from_li(li)
            # Only skip if name is truly empty (not just whitespace)
            if item['name'] and item['name'].strip():
                items.append(item)
            else:
                # If name is empty, try to extract from first part of text
                full_text = li.get_text(separator=' | ', strip=True)
                if full_text:
                    # Take first part before | or price as name
                    parts = full_text.split('|', 1)
                    potential_name = parts[0].strip()
                    # Remove price from potential name
                    potential_name = re.sub(r'\s*\$\d+\.\d{2}.*$', '', potential_name).strip()
                    if potential_name:
                        item['name'] = potential_name
                        items.append(item)
        except Exception as e:
            continue
    
    return items


def scrape_food_menu(url: str) -> List[Dict]:
    """
    Scrape food menu from saratoga-menu page.
    """
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'cookie': '_ga=GA1.2.1994360667.1767258237; _gid=GA1.2.579227803.1767258237; _gat=1; _ga_DCSFWLRKG5=GS2.2.s1767258237$o1$g1$t1767258248$j49$l0$h0',
        'pragma': 'no-cache',
        'referer': 'https://www.dizzychickenbarbecue.com/saratoga-menu/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    print(f"  Fetching food menu from {url}...")
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Menu sections to extract
    sections = [
        'Specials',
        'Appetizers',
        'Soup',
        'Salads',
        'Panini',
        'Cold Sandwiches: Wraps & House Made Focaccia!',
        'Additional Toppings:',
        'Entree Selections',
        'Meat Selections Á La Carte',
        'Sides',
        'Dessert',
        'Beverages'
    ]
    
    all_items = []
    for section_name in sections:
        print(f"    Extracting {section_name}...")
        items = extract_menu_section(section_name, soup)
        for item in items:
            item['menu_type'] = section_name
        all_items.extend(items)
        print(f"      Found {len(items)} items")
    
    return all_items


def scrape_drink_menu(url: str) -> List[Dict]:
    """
    Scrape drink menu from drink-menu page.
    """
    headers = {
        'Referer': 'https://www.dizzychickenbarbecue.com/saratoga-menu/',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
    
    print(f"  Fetching drink menu from {url}...")
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Drink menu sections - need to handle subsections properly
    # First extract main sections, then subsections
    all_items = []
    
    # Find all h2 headings to process sections
    all_h2 = soup.find_all('h2')
    
    for h2 in all_h2:
        h2_text = h2.get_text(strip=True)
        
        if h2_text == 'Cocktails':
            print(f"    Extracting Cocktails...")
            items = extract_menu_section('Cocktails', soup)
            for item in items:
                item['menu_type'] = 'Cocktails'
            all_items.extend(items)
            print(f"      Found {len(items)} items")
        
        elif h2_text == 'On Tap':
            print(f"    Extracting On Tap...")
            # On Tap has h3 subsections, so extract those
            current = h2.find_next()
            while current:
                if hasattr(current, 'name'):
                    if current.name == 'h2':
                        break  # Next main section
                    elif current.name == 'h3':
                        subsection_name = current.get_text(strip=True)
                        # Find ul after this h3
                        next_ul = None
                        temp = current.find_next()
                        while temp:
                            if hasattr(temp, 'name'):
                                if temp.name == 'ul':
                                    next_ul = temp
                                    break
                                elif temp.name in ['h2', 'h3']:
                                    break  # Next heading
                            temp = temp.find_next()
                        
                        if next_ul:
                            items = []
                            for li in next_ul.find_all('li', recursive=False):
                                try:
                                    item = extract_item_from_li(li)
                                    if item['name']:
                                        item['menu_type'] = f'On Tap - {subsection_name}'
                                        items.append(item)
                                except:
                                    continue
                            all_items.extend(items)
                            print(f"      Found {len(items)} items in {subsection_name}")
                current = current.find_next()
        
        elif h2_text == 'Bottles & Cans':
            print(f"    Extracting Bottles & Cans...")
            # Bottles & Cans has h3 subsections
            current = h2.find_next()
            while current:
                if hasattr(current, 'name'):
                    if current.name == 'h2':
                        break  # Next main section
                    elif current.name == 'h3':
                        subsection_name = current.get_text(strip=True)
                        # Find ul after this h3
                        next_ul = None
                        temp = current.find_next()
                        while temp:
                            if hasattr(temp, 'name'):
                                if temp.name == 'ul':
                                    next_ul = temp
                                    break
                                elif temp.name in ['h2', 'h3']:
                                    break  # Next heading
                            temp = temp.find_next()
                        
                        if next_ul:
                            items = []
                            for li in next_ul.find_all('li', recursive=False):
                                try:
                                    item = extract_item_from_li(li)
                                    if item['name']:
                                        item['menu_type'] = f'Bottles & Cans - {subsection_name}'
                                        items.append(item)
                                except:
                                    continue
                            all_items.extend(items)
                            print(f"      Found {len(items)} items in {subsection_name}")
                current = current.find_next()
        
        elif h2_text == 'White Wines':
            print(f"    Extracting White Wines...")
            items = extract_menu_section('White Wines', soup)
            for item in items:
                item['menu_type'] = 'White Wines'
            all_items.extend(items)
            print(f"      Found {len(items)} items")
        
        elif h2_text == 'Red Wines':
            print(f"    Extracting Red Wines...")
            items = extract_menu_section('Red Wines', soup)
            for item in items:
                item['menu_type'] = 'Red Wines'
            all_items.extend(items)
            print(f"      Found {len(items)} items")
    
    return all_items
    
    all_items = []
    for section_name, menu_type in sections:
        print(f"    Extracting {section_name}...")
        items = extract_menu_section(section_name, soup)
        for item in items:
            item['menu_type'] = menu_type
        all_items.extend(items)
        print(f"      Found {len(items)} items")
    
    return all_items


def scrape_dizzychickenbarbecue_menu() -> List[Dict]:
    """
    Main function to scrape all menus from dizzychickenbarbecue.com
    """
    restaurant_name = "Dizzy Chicken Woodfired Rotisserie"
    restaurant_url = "https://www.dizzychickenbarbecue.com/"
    
    print(f"\n{'='*60}")
    print(f"Scraping: {restaurant_url}")
    print(f"{'='*60}\n")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_json = output_dir / 'dizzychickenbarbecue_com.json'
    print(f"Output file: {output_json}\n")
    
    all_items = []
    
    try:
        # Scrape food menu
        print("Scraping Food Menu...")
        food_url = "https://www.dizzychickenbarbecue.com/saratoga-menu/"
        food_items = scrape_food_menu(food_url)
        for item in food_items:
            item['restaurant_name'] = restaurant_name
            item['restaurant_url'] = restaurant_url
            item['menu_name'] = 'Food Menu'
        all_items.extend(food_items)
        print(f"[OK] Extracted {len(food_items)} items from Food Menu\n")
        
        # Scrape drink menu
        print("Scraping Drink Menu...")
        drink_url = "https://www.dizzychickenbarbecue.com/drink-menu/"
        drink_items = scrape_drink_menu(drink_url)
        for item in drink_items:
            item['restaurant_name'] = restaurant_name
            item['restaurant_url'] = restaurant_url
            item['menu_name'] = 'Drink Menu'
        all_items.extend(drink_items)
        print(f"[OK] Extracted {len(drink_items)} items from Drink Menu\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Save to JSON
    print(f"Saving {len(all_items)} items to: {output_json}\n")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scraping complete! Extracted {len(all_items)} total items")
    print(f"{'='*60}\n")
    
    return all_items


if __name__ == "__main__":
    scrape_dizzychickenbarbecue_menu()

