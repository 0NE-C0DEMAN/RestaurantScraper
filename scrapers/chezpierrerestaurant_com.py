"""
Scraper for chezpierrerestaurant.com
Extracts menu items from the dinner menu and wine menu pages
"""

import json
import re
import requests
from typing import List, Dict
from bs4 import BeautifulSoup
from pathlib import Path


def extract_dinner_menu_items(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract dinner menu items from HTML soup
    
    Args:
        soup: BeautifulSoup object of the dinner menu HTML
    
    Returns:
        List of dictionaries containing menu items
    """
    items = []
    
    # Find the main content area
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        print("  [WARNING] Could not find entry-content")
        return []
    
    current_section = ""
    
    # Find all headings (h2 and h3) which are section headers
    # Process h3 first (subsections), then h2 (main sections)
    # This ensures subsections take precedence over parent sections
    all_headings = entry_content.find_all(['h2', 'h3'])
    
    for element in all_headings:
        section_name = element.get_text(strip=True)
        
        # Skip if it's just an anchor link or empty
        if not section_name or section_name.startswith('#'):
            continue
        
        # Clean up section name (remove anchor links)
        section_name = re.sub(r'^#\w+\s*', '', section_name)
        
        # Skip generic parent sections like "DINNER MENU" if there are subsections
        # Check if there's an h3 subsection coming after this h2
        if element.name == 'h2' and section_name.upper() == "DINNER MENU":
            # Check if there are h3 subsections after this h2
            next_h3 = element.find_next_sibling('h3')
            if next_h3:
                # Skip this h2, let the h3 subsections handle the items
                continue
        
        # Update current section
        current_section = section_name
        
        # Find the next list after this heading
        # But make sure we don't go past the next heading of same or higher level
        next_list = None
        next_elem = element.find_next_sibling()
        
        # Find the next heading to know where to stop
        next_heading = None
        if element.name == 'h3':
            # For h3, stop at next h2 or h3
            next_heading = element.find_next_sibling(['h2', 'h3'])
        elif element.name == 'h2':
            # For h2, stop at next h2
            next_heading = element.find_next_sibling('h2')
        
        # Look for list between current heading and next heading
        if next_elem:
            # Check if next element is a list
            if next_elem.name in ['ul', 'ol']:
                next_list = next_elem
            else:
                # Check if there's a list in the next element
                next_list = next_elem.find(['ul', 'ol'])
                
                # If not found, keep looking until we hit the next heading
                if not next_list:
                    current = next_elem
                    while current and current != next_heading:
                        if current.name in ['ul', 'ol']:
                            next_list = current
                            break
                        current = current.find_next_sibling()
        
        if not next_list:
            continue
        
        # Process list items - handle cases where items span multiple <li> elements
        list_items = next_list.find_all('li', recursive=False)
        i = 0
        while i < len(list_items):
            li = list_items[i]
            li_text = li.get_text(separator=' ', strip=True)
            
            if not li_text or len(li_text.strip()) < 2:
                i += 1
                continue
            
            # Find strong tag for item name
            strong_tag = li.find('strong')
            item_name = ""
            description = ""
            price = ""
            full_text = li_text
            
            if strong_tag:
                # Item has a strong tag - extract name
                item_name = strong_tag.get_text(strip=True)
                
                # Check if price is in the strong tag itself (like "Mousse au Chocolate $7")
                price_in_name = re.search(r'\$\s*(\d+\.?\d*)', item_name)
                if price_in_name:
                    price = f"${price_in_name.group(1)}"
                    item_name = re.sub(r'\s*\$\s*\d+\.?\d*\s*$', '', item_name).strip()
                    # Don't look for price in next li if we already found it in the name
                    price_found_in_name = True
                else:
                    price_found_in_name = False
                
                # Get text after strong tag in this li (but not including the strong tag text)
                # Remove the strong tag content from li_text
                strong_text = strong_tag.get_text(strip=True)
                desc_text = li_text.replace(strong_text, "", 1).strip()
                
                # Extract add-on prices before processing description
                # Pattern: "12 / Add Chicken 22/ Add Shrimp 32" or "12 / Add Chicken $22 / Add Shrimp $32"
                addon_prices = []
                addon_pattern = r'Add\s+(\w+)\s+(\d+\.?\d*)'
                addon_matches = re.findall(addon_pattern, desc_text, re.I)
                for addon_name, addon_price in addon_matches:
                    addon_prices.append(f"Add {addon_name}: ${addon_price}")
                
                # Check if next li contains price or description
                # But be careful - if next li looks like a separate item (has price and no strong tag), don't merge it
                # Also skip if we already found price in the name
                if not price_found_in_name and i + 1 < len(list_items):
                    next_li = list_items[i + 1]
                    next_li_text = next_li.get_text(separator=' ', strip=True)
                    next_li_has_strong = next_li.find('strong') is not None
                    
                    # If next li is just a number, it's likely the price for current item
                    if re.match(r'^\d+\.?\d*$', next_li_text):
                        price = f"${next_li_text}"
                        i += 1  # Skip the next li as it's the price
                    # If next li has a strong tag, it's a separate item - don't merge
                    elif next_li_has_strong:
                        # This is a separate item, don't process it here
                        pass
                    # If next li has text but no strong tag, check if it's a separate item or description
                    elif not next_li_has_strong and next_li_text:
                        # Check if it looks like a separate item (has price at the end and starts with capital letter)
                        # Pattern: "Item Name description price" or "Item Name price"
                        looks_like_separate_item = (
                            re.search(r'[A-Z][a-z].*\d+\.?\d*\s*$', next_li_text) and
                            len(next_li_text.split()) >= 3  # At least 3 words suggests it's an item name + description
                        )
                        
                        if looks_like_separate_item:
                            # This is likely a separate item, don't merge it
                            pass
                        else:
                            # Check if it contains a price
                            price_match = re.search(r'(\d+\.?\d*)\s*$', next_li_text)
                            if price_match:
                                # Extract description and price
                                desc_and_price = next_li_text
                                # Remove price from end
                                desc_part = re.sub(r'\s*\d+\.?\d*\s*$', '', desc_and_price).strip()
                                if desc_part:
                                    if desc_text:
                                        description = f"{desc_text} {desc_part}"
                                    else:
                                        description = desc_part
                                price = f"${price_match.group(1)}"
                                i += 1  # Skip the next li
                            else:
                                # Just description, no price yet
                                if desc_text:
                                    description = f"{desc_text} {next_li_text}"
                                else:
                                    description = next_li_text
                                i += 1
                                # Check if the li after that has the price
                                if i + 1 < len(list_items):
                                    price_li = list_items[i + 1]
                                    price_text = price_li.get_text(separator=' ', strip=True)
                                    if re.match(r'^\d+\.?\d*$', price_text):
                                        price = f"${price_text}"
                                        i += 1
                
                if not description:
                    # Clean up desc_text - remove price patterns
                    desc_text = re.sub(r'\s*\d+\.?\d*\s*(/|\|).*$', '', desc_text)
                    desc_text = re.sub(r'\s*\$\d+\.?\d*\s*$', '', desc_text)
                    desc_text = re.sub(r'\s*\d+\.?\d*\s*$', '', desc_text)
                    desc_text = re.sub(r'\s*half[–\-\s]*\d+\.?\d*\s*[\/\|]\s*full[–\-\s]*\d+\.?\d*\s*$', '', desc_text, flags=re.I)
                    desc_text = desc_text.strip()
                    description = desc_text
            else:
                # No strong tag - try to extract from text pattern
                # Pattern: "Item Name description price" or "Item Name price"
                # Look for items like "Veg- Gnocchi Chez Pierre without shrimp 30"
                # or "French Cream Cheese cake garnished w/ raspberry puree $10"
                
                # First try: "Item Name $XX" or "Item Name XX"
                text_match = re.search(r'(.+?)\s+(\$\s*)?(\d+\.?\d*)\s*$', li_text)
                if text_match:
                    full_item_text = text_match.group(1).strip()
                    price = f"${text_match.group(3)}"
                    
                    # Try to split into name and description
                    # Look for patterns like "Item Name description" where description might be longer
                    # Common pattern: "Veg- Gnocchi Chez Pierre without shrimp 30"
                    # or "French Cream Cheese cake garnished w/ raspberry puree $10"
                    
                    # If the text is short (<= 40 chars), it's likely just the name
                    if len(full_item_text) <= 40:
                        item_name = full_item_text
                    else:
                        # Try to split - name is usually first 2-4 words
                        words = full_item_text.split()
                        if len(words) <= 4:
                            item_name = full_item_text
                        else:
                            # First 3-4 words are likely the name
                            item_name = " ".join(words[:4])
                            description = " ".join(words[4:])
                else:
                    # No price found in this li, skip it
                    i += 1
                    continue
            
            if not item_name:
                i += 1
                continue
            
            # If we still don't have a price, try to extract from full_text
            if not price:
                # Extract base price first (before add-ons)
                # Pattern: "12 / Add Chicken 22/ Add Shrimp 32" - base price is "12"
                base_price_match = re.search(r'^(\d+\.?\d*)\s*/\s*Add', full_text, re.I)
                if base_price_match:
                    price = f"${base_price_match.group(1)}"
                else:
                    # Remove add-on prices (like "Add Chicken 22/ Add Shrimp 32") for price extraction
                    text_for_price = re.sub(r'Add\s+\w+\s+\d+[\/\|]?', '', full_text, flags=re.I)
                    text_for_price = re.sub(r'Add\s+\w+\s+\d+', '', text_for_price, flags=re.I)
                    
                    # Remove quantity patterns like "10/20", "Four extra large", etc.
                    text_for_price = re.sub(r'\d+/\d+', '', text_for_price)  # Remove "10/20" patterns
                    text_for_price = re.sub(r'\b\d+\s*(extra|oz|oz\.|ounce|ounces)\b', '', text_for_price, flags=re.I)
                    
                    # First, check for half/full prices
                    if 'half' in text_for_price.lower() and 'full' in text_for_price.lower():
                        prices = []
                        half_match = re.search(r'half[–\-\s]+(\d+\.?\d*)', text_for_price, re.I)
                        full_match = re.search(r'full[–\-\s]*(\d+\.?\d*)', text_for_price, re.I)
                        if half_match:
                            prices.append(f"Half: ${half_match.group(1)}")
                        if full_match:
                            prices.append(f"Full: ${full_match.group(1)}")
                        if prices:
                            price = " | ".join(prices)
                    
                    # If no half/full price, look for single price
                    if not price:
                        numbers = re.findall(r'\b(\d+\.?\d*)\b', text_for_price)
                        if numbers:
                            valid_prices = [n for n in numbers if float(n) >= 4]  # Lower threshold for items like coffee
                            if valid_prices:
                                price = f"${valid_prices[-1]}"
                            elif numbers:
                                price = f"${numbers[-1]}"
            
            # Append add-on prices to the price field
            if addon_prices:
                if price:
                    price = f"{price} | {' | '.join(addon_prices)}"
                else:
                    price = " | ".join(addon_prices)
            
            # Clean up description - remove price patterns and add-on prices
            if description:
                # Remove add-on prices from description (we've already captured them)
                description = re.sub(r'\s*/\s*Add\s+\w+\s+\d+[\/\|]?\s*Add\s+\w+\s+\d+', '', description, flags=re.I)
                description = re.sub(r'\s*/\s*Add\s+\w+\s+\d+[\/\|]?', '', description, flags=re.I)
                description = re.sub(r'\s*\d+\.?\d*\s*(/|\|).*$', '', description)
                description = re.sub(r'\s*\$\d+\.?\d*\s*$', '', description)
                description = re.sub(r'\s*\d+\.?\d*\s*$', '', description)
                description = re.sub(r'\s*half[–\-\s]*\d+\.?\d*\s*[\/\|]\s*full[–\-\s]*\d+\.?\d*\s*$', '', description, flags=re.I)
                description = re.sub(r'\s*half[–\-\s]*$', '', description, flags=re.I)
                description = description.strip()
            
            # Skip if no price (for dinner menu, items should have prices)
            if not price:
                i += 1
                continue
            
            items.append({
                'name': item_name,
                'description': description,
                'price': price,
                'menu_type': current_section,
                'restaurant_name': "Chez Pierre Restaurant",
                'restaurant_url': "https://www.chezpierrerestaurant.com/",
                'menu_name': "Dinner Menu"
            })
            
            i += 1
    
    return items


def extract_wine_menu_items(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract wine menu items from HTML soup
    
    Args:
        soup: BeautifulSoup object of the wine menu HTML
    
    Returns:
        List of dictionaries containing wine items (no prices)
    """
    items = []
    
    # Find the main content area
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        print("  [WARNING] Could not find entry-content")
        return []
    
    current_section = ""
    
    # Find all h2 headings which are section headers
    for h2 in entry_content.find_all('h2'):
        section_name = h2.get_text(strip=True)
        
        # Skip if it's just an anchor link
        if not section_name or section_name.startswith('#'):
            continue
        
        # Clean up section name (remove anchor links)
        section_name = re.sub(r'^#\w+\s*', '', section_name)
        
        # Update current section
        current_section = section_name
        
        # Find the next list after this heading
        next_list = h2.find_next_sibling('ul')
        if not next_list:
            # Sometimes the list is in a div or other element
            next_elem = h2.find_next_sibling()
            if next_elem:
                next_list = next_elem.find('ul')
        
        if not next_list:
            continue
        
        # Process each list item
        for li in next_list.find_all('li', recursive=False):
            wine_name = li.get_text(strip=True)
            
            if not wine_name or len(wine_name) < 3:
                continue
            
            items.append({
                'name': wine_name,
                'description': "",
                'price': "",  # Wine menu doesn't have prices
                'menu_type': current_section,
                'restaurant_name': "Chez Pierre Restaurant",
                'restaurant_url': "https://www.chezpierrerestaurant.com/",
                'menu_name': "Wine Menu"
            })
    
    return items


def scrape_chezpierre_menu() -> List[Dict]:
    """
    Main function to scrape menus from chezpierrerestaurant.com
    
    Returns:
        List of dictionaries containing all menu items
    """
    all_items = []
    
    headers = {
        'Referer': 'https://www.chezpierrerestaurant.com/',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
    
    # Scrape Dinner Menu
    try:
        print("Fetching dinner menu...")
        response = requests.get('https://www.chezpierrerestaurant.com/dinner-menu/', headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print("Extracting dinner menu items...")
        dinner_items = extract_dinner_menu_items(soup)
        all_items.extend(dinner_items)
        print(f"  Extracted {len(dinner_items)} items from dinner menu")
    except Exception as e:
        print(f"Error fetching dinner menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Scrape Wine Menu
    try:
        print("\nFetching wine menu...")
        response = requests.get('https://www.chezpierrerestaurant.com/wine-menu/', headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print("Extracting wine menu items...")
        wine_items = extract_wine_menu_items(soup)
        all_items.extend(wine_items)
        print(f"  Extracted {len(wine_items)} items from wine menu")
    except Exception as e:
        print(f"Error fetching wine menu: {e}")
        import traceback
        traceback.print_exc()
    
    return all_items


if __name__ == "__main__":
    items = scrape_chezpierre_menu()
    
    # Save to JSON file
    output_dir = Path('output')
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "chezpierrerestaurant_com_.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(items)} items to {output_file}")

