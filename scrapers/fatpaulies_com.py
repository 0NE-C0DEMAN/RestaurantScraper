"""
Scraper for Fat Paulie's Deli
Website: https://www.fatpaulies.com/
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict
import os

def scrape_fatpaulies_menu() -> List[Dict]:
    """
    Scrape catering menu items from Fat Paulie's.
    """
    items = []
    
    try:
        url = "https://www.fatpaulies.com/paulies-catering-menu"
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find main content
        main = soup.find('main')
        if not main:
            main = soup.find('body')
        
        if not main:
            print("  [WARNING] Could not find main content")
            return []
        
        # Find all h1 elements
        h1s = main.find_all('h1')
        
        current_section = ""
        
        for h1 in h1s:
            text = h1.get_text(strip=True)
            
            # Skip empty or very short headings
            if not text or len(text) < 3:
                continue
            
            # Check if it's a section header (all caps, no price, or specific patterns)
            # Section headers are typically: all caps, or contain words like "SERVES", "minimum"
            is_section = False
            if text.isupper() and not re.search(r'\$', text):
                is_section = True
            elif re.match(r'^(HALF-TRAY|FULL-TRAY|SERVES)', text, re.I):
                is_section = True
            elif 'minimum' in text.lower():
                is_section = True
            
            if is_section:
                # Clean section name
                section_name = text.strip()
                # Remove common prefixes
                section_name = re.sub(r'\s*\([^)]+\)\s*$', '', section_name)  # Remove parentheses
                current_section = section_name
                print(f"    Extracting {current_section}...")
                continue
            
            # It's an item - extract name and price
            item_name = text
            
            # Extract add-ons first (e.g., "Add Italian Mix +$1.00 per person")
            addon_matches = re.findall(r'Add\s+[^+]+?\s+\+\$[\d.]+(?:\s+per\s+person)?', text, re.I)
            
            # Remove add-ons from text before extracting main prices
            text_for_price = text
            for addon in addon_matches:
                text_for_price = text_for_price.replace(addon, '')
            
            # Extract all prices (handle multiple prices like "$44.95/$74.95" or "$89.95 $104.95")
            # But exclude add-on prices (those with +$)
            # Match $ followed by digits and exactly 2 decimal places (standard price format)
            # Allow prices to be followed by space, end of string, /, "per", "LB", or a capital letter (for sizes like "4 FooT")
            price_matches = re.findall(r'(?<!\+)\$[\d]+\.\d{2}(?=\s|$|/|per|LB|lb|PEOPLE|[A-Z])', text_for_price)
            
            # If no matches with .XX format, try without decimals (e.g., "$19")
            if not price_matches:
                price_matches = re.findall(r'(?<!\+)\$[\d]+(?=\s|$|/|per|LB|lb|PEOPLE|[A-Z])', text_for_price)
            
            # Build price string
            price = ""
            if price_matches:
                if len(price_matches) == 1:
                    # Single price
                    price = price_matches[0]
                    # Check for "per person" or "/LB" suffix
                    if 'per person' in text.lower():
                        price += " per person"
                    elif '/LB' in text or '/lb' in text:
                        price += "/LB"
                else:
                    # Multiple prices - check if they're for different sizes (e.g., half/full tray)
                    # Format as "Half $X / Full $Y" or just "$X / $Y"
                    if 'half' in text.lower() and 'full' in text.lower():
                        # Try to match half and full prices
                        half_match = re.search(r'[Hh]alf[^$]*(\$[\d.]+)', text)
                        full_match = re.search(r'[Ff]ull[^$]*(\$[\d.]+)', text)
                        if half_match and full_match:
                            price = f"Half {half_match.group(1)} / Full {full_match.group(1)}"
                        else:
                            price = " / ".join(price_matches)
                    else:
                        # Just join with /
                        price = " / ".join(price_matches)
            
            # Handle special case: items with multiple sizes (e.g., "3 FooT $89.95 4 FooT $104.95")
            # Check BEFORE building price string - look for pattern of two sizes with prices
            party_hero_pattern = r'(\d+)\s*[Ff]oo?[Tt].*?(\$[\d]+\.[\d]{2}).*?(\d+)\s*[Ff]oo?[Tt].*?(\$[\d]+\.[\d]{2})'
            party_hero_match = re.search(party_hero_pattern, text)
            
            if party_hero_match:
                # Extract both sizes and prices
                size1 = party_hero_match.group(1)
                price1 = party_hero_match.group(2)
                size2 = party_hero_match.group(3)
                price2 = party_hero_match.group(4)
                
                # Get description first
                item_desc = ""
                next_sib = h1.find_next_sibling()
                if next_sib and hasattr(next_sib, 'get_text'):
                    item_desc = next_sib.get_text(strip=True)
                    # Clean up description - remove nested item info
                    item_desc = re.sub(r'[A-Z][A-Z\s]+\$[\d.]+.*$', '', item_desc).strip()
                    item_desc = re.sub(r'Charcuterie\s+Platter.*$', '', item_desc, flags=re.I).strip()
                
                # Create items for each size
                items.append({
                    'name': f"{size1} Foot Party Hero",
                    'description': item_desc,
                    'price': price1,
                    'section': current_section
                })
                
                items.append({
                    'name': f"{size2} Foot Party Hero",
                    'description': item_desc,
                    'price': price2,
                    'section': current_section
                })
                
                continue  # Skip normal processing for this item
            
            # Remove price from item name
            if price_matches:
                # Remove all price patterns and their suffixes
                for pm in price_matches:
                    # Remove price and any text after it on the same line
                    item_name = re.sub(r'\s*' + re.escape(pm) + r'[^\w]*.*$', '', item_name, flags=re.I).strip()
                # Remove "per person", "/LB", etc.
                item_name = re.sub(r'\s*(per\s+person|/LB|/lb)\s*', '', item_name, flags=re.I).strip()
                # Remove add-ons from name
                for addon in addon_matches:
                    item_name = re.sub(r'\s*' + re.escape(addon) + r'.*$', '', item_name, flags=re.I).strip()
            
            # Clean up item name - remove any trailing text that looks like prices or add-ons
            item_name = re.sub(r'\s*(Add\s+.*|\+\$.*|per\s+person.*|/LB.*|/lb.*).*$', '', item_name, flags=re.I).strip()
            # Remove any remaining price patterns
            item_name = re.sub(r'\s*\$\d+.*$', '', item_name).strip()
            item_name = re.sub(r'\s+', ' ', item_name).strip()
            
            # Skip if no name
            if not item_name or len(item_name) < 3:
                continue
            
            # Add add-ons to price if present
            if addon_matches:
                if price:
                    price += " | " + " | ".join(addon_matches)
                else:
                    price = " | ".join(addon_matches)
            
            # Find description - include all text including choices and notes
            description = ""
            next_sib = h1.find_next_sibling()
            description_parts = []
            
            # Look for description in next siblings
            while next_sib:
                # Stop if we hit another h1 (next item or section)
                if next_sib.name == 'h1':
                    break
                
                if next_sib.name == 'strong':
                    desc_text = next_sib.get_text(strip=True)
                    if desc_text and len(desc_text) > 5:
                        description_parts.append(desc_text)
                elif hasattr(next_sib, 'get_text'):
                    desc_text = next_sib.get_text(strip=True)
                    
                    # Include list items (choices, options) - they start with "-"
                    if desc_text and desc_text.startswith('-'):
                        description_parts.append(desc_text)
                    # Include parenthetical notes
                    elif desc_text and desc_text.startswith('(') and desc_text.endswith(')'):
                        description_parts.append(desc_text)
                    # Include regular description text
                    elif desc_text and len(desc_text) > 5:
                        # Check if it contains actual description text (not another item name)
                        if not re.match(r'^[-•]\s*', desc_text):
                            # Check if it looks like an item name (all caps, has price)
                            if not (desc_text.isupper() and re.search(r'\$', desc_text)):
                                description_parts.append(desc_text)
                
                next_sib = next_sib.find_next_sibling()
            
            # Join description parts with proper formatting
            if description_parts:
                # Join with proper spacing
                formatted_parts = []
                for i, part in enumerate(description_parts):
                    # Clean up tabs and extra whitespace
                    part = part.replace('\t', ' ').strip()
                    part = re.sub(r'\s+', ' ', part)
                    
                    if not part:
                        continue
                    
                    # Add space before list items
                    if part.startswith('-'):
                        if formatted_parts:
                            prev = formatted_parts[-1].rstrip()
                            # If previous part ends with ":" or doesn't end with space, add space
                            if prev.endswith(':'):
                                formatted_parts.append(' ')
                            elif not prev.endswith(' '):
                                formatted_parts.append(' ')
                    # Add space before parenthetical notes
                    elif part.startswith('('):
                        if formatted_parts:
                            prev = formatted_parts[-1].rstrip()
                            if not prev.endswith(' '):
                                formatted_parts.append(' ')
                    # Add space between regular text parts
                    elif formatted_parts and not formatted_parts[-1].endswith((' ', ':', '-', '(')):
                        formatted_parts.append(' ')
                    
                    formatted_parts.append(part)
                
                description = ''.join(formatted_parts)
                # Clean up - remove any item names that might have leaked in
                description = re.sub(r'[A-Z][A-Z\s]+\$[\d.]+.*$', '', description).strip()
                # Add space after colons if missing
                description = re.sub(r':([^-])', r': \1', description)
                # Add space after list items (before next list item or parenthetical)
                description = re.sub(r'([a-z])(-|\([A-Z])', r'\1 \2', description)
                # Final cleanup of multiple spaces
                description = re.sub(r' {2,}', ' ', description).strip()
            
            items.append({
                'name': item_name,
                'description': description,
                'price': price,
                'section': current_section
            })
        
        # Count items per section
        section_counts = {}
        for item in items:
            section = item.get('section', '')
            section_counts[section] = section_counts.get(section, 0) + 1
        
        for section, count in section_counts.items():
            if section:
                print(f"      Found {count} items")
        
    except Exception as e:
        print(f"  [ERROR] Error scraping menu: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_fatpaulies() -> List[Dict]:
    """
    Main function to scrape Fat Paulie's catering menu.
    """
    print("=" * 60)
    print("Scraping: https://www.fatpaulies.com/")
    print("=" * 60)
    
    print("\nScraping Catering Menu...")
    items = scrape_fatpaulies_menu()
    print(f"[OK] Extracted {len(items)} items from Catering Menu")
    
    # Add metadata to all items
    for item in items:
        item['menu_type'] = item.get('section', '')
        item['restaurant_name'] = "Fat Paulie's Deli"
        item['restaurant_url'] = "https://www.fatpaulies.com/"
        item['menu_name'] = "Catering Menu"
    
    # Save to JSON
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'www_fatpaulies_com.json')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaving {len(items)} items to: {output_file}")
    
    print("\n" + "=" * 60)
    print("[OK] Scraping complete!")
    print(f"  - Total: {len(items)} items")
    print("=" * 60)
    
    return items


if __name__ == "__main__":
    scrape_fatpaulies()

