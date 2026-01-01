"""
Scraper for: https://www.druthersbrewing.com/
Also handles:
- Lago By Druthers: https://lagobydruthers.com/
- Blackbirds Tavern: https://blackbirdstavern.com/
HTML-based menus with different structures
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
    Structure: h2 for sections, h3 for item names, p for price and description
    """
    items = []
    
    try:
        # Find the main content area
        main_content = soup.find('main')
        if not main_content:
            print("  [WARNING] Could not find main content")
            return []
        
        # Find all h2 headings (section headers)
        h2_elements = main_content.find_all('h2')
        
        current_section = ""
        
        # Find all item containers (divs with w-hwrapper class that contain h3)
        item_containers = main_content.find_all('div', class_='w-hwrapper')
        
        # Map items to sections by finding the previous h2
        for container in item_containers:
            h3 = container.find('h3')
            if not h3:
                continue
            
            item_name = h3.get_text(strip=True)
            
            # Find the section (previous h2)
            section_h2 = h3.find_previous('h2')
            if section_h2:
                section_name = section_h2.get_text(strip=True)
                # Skip certain sections that aren't menu categories
                skip_sections = ['Pair With Druthers Beer', 'Download Menu PDF', 'Check Out Our Beers', 
                               'Catering Information', 'Brewpub Menu']
                if section_name in skip_sections:
                    continue
                current_section = section_name
            else:
                continue
            
            # Find price (p with class containing usg_post_custom_field_1) - should be in same container
            price_elem = container.find('p', class_=lambda x: x and 'usg_post_custom_field_1' in x)
            price = ""
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Price is just a number, format it
                if price_text and price_text.isdigit():
                    price = f"${price_text}.00"
            
            # Find description (p with class containing usg_post_custom_field_2 and description)
            # This is in the NEXT sibling of the container
            desc_elem = container.find_next_sibling('p', class_=lambda x: x and 'usg_post_custom_field_2' in x and 'description' in x)
            description = ""
            if desc_elem:
                description = desc_elem.get_text(strip=True)
            
            # Find add-ons (p with class containing usg_post_custom_field_3 and notes)
            # This is in the NEXT sibling after the description
            addons = []
            notes_elem = container.find_next_sibling('p', class_=lambda x: x and 'usg_post_custom_field_3' in x and 'notes' in x)
            if notes_elem:
                notes_text = notes_elem.get_text(strip=True)
                # Look for "Add-Ons:" pattern (case insensitive, with optional hyphen)
                addon_match = re.search(r'Add-Ons?:\s*(.+?)(?:\s*$|$)', notes_text, re.IGNORECASE | re.DOTALL)
                if addon_match:
                    addon_text = addon_match.group(1).strip()
                    # Parse add-ons (format: "Extra Patty +$4, Chopped Bacon +$3, Fried Egg +$2")
                    # Match: name followed by +$number, separated by commas
                    addon_items = re.findall(r'([^,+]+?)\s*\+\$(\d+)', addon_text)
                    for addon_name, addon_price in addon_items:
                        addon_name = addon_name.strip()
                        if addon_name:  # Only add if name is not empty
                            addons.append(f"Add {addon_name} ${addon_price}")
            
            # If we have a valid item (has name and either price or description)
            if item_name and (price or description):
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'section': current_section,
                    'addons': addons
                })
        
        # Group items by section for reporting
        section_counts = {}
        for item in items:
            section = item.get('section', '')
            section_counts[section] = section_counts.get(section, 0) + 1
        
        for section, count in section_counts.items():
            print(f"    Extracting {section}...")
            print(f"      Found {count} items")
        
    except Exception as e:
        print(f"  [ERROR] Error extracting menu items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def extract_beer_items_from_html(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract beer items from HTML soup.
    Structure: h2 with class 'h1' for sections, div with class 'beer-card' for beers
    """
    items = []
    
    try:
        # Find the main content area
        main_content = soup.find('main')
        if not main_content:
            print("  [WARNING] Could not find main content")
            return []
        
        # Find section headers (h2 with class 'h1')
        section_headers = main_content.find_all('h2', class_='h1')
        
        # Find all beer cards
        beer_cards = main_content.find_all('div', class_=lambda x: x and 'beer-card' in str(x))
        
        current_section = "Beer"
        
        # Map beers to sections by finding the previous section header
        for card in beer_cards:
            # Find beer name (h2 in the card)
            h2 = card.find('h2')
            if not h2:
                continue
            
            beer_name = h2.get_text(strip=True)
            
            # Find the section (previous h2 with class 'h1')
            section_h2 = h2.find_previous('h2', class_='h1')
            if section_h2:
                current_section = section_h2.get_text(strip=True)
            
            # Find details div (contains style, ABV, IBU)
            details_div = card.find('div', class_=lambda x: x and 'usg_hwrapper_1' in str(x))
            description = ""
            style = ""
            abv = ""
            ibu = ""
            
            if details_div:
                details_text = details_div.get_text(strip=True)
                
                # Parse style, ABV, IBU
                # Format: "StyleABV: X.X%IBU: XX" or "StyleABV: X.X%"
                # Style comes before "ABV:", extract everything up to "ABV:"
                style_match = re.search(r'^(.+?)(?=ABV:)', details_text)
                if style_match:
                    style = style_match.group(1).strip()
                    # Clean up style (remove any trailing spaces or special chars)
                    style = re.sub(r'\s+', ' ', style).strip()
                
                abv_match = re.search(r'ABV:\s*([\d.]+)\s*%', details_text)
                if abv_match:
                    abv = abv_match.group(1)
                
                ibu_match = re.search(r'IBU:\s*(\d+)', details_text)
                if ibu_match:
                    ibu = ibu_match.group(1)
                
                # Build description
                desc_parts = []
                if style:
                    desc_parts.append(style)
                if abv:
                    desc_parts.append(f"ABV: {abv}%")
                if ibu:
                    desc_parts.append(f"IBU: {ibu}")
                
                description = " | ".join(desc_parts)
            
            if beer_name:
                items.append({
                    'name': beer_name,
                    'description': description,
                    'price': '',
                    'section': current_section,
                    'style': style,
                    'abv': abv,
                    'ibu': ibu
                })
        
    except Exception as e:
        print(f"  [ERROR] Error extracting beer items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def extract_lago_menu_items(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract menu items from Lago menu (uses brxe-heading classes)
    Structure: h2 for sections, h4 for subsections, h5 for item names and prices, p for descriptions
    """
    items = []
    
    try:
        main_content = soup.find('main')
        if not main_content:
            print("  [WARNING] Could not find main content")
            return []
        
        # Find all h2 section headers
        h2_sections = main_content.find_all('h2', class_=lambda x: x and 'brxe-heading' in str(x))
        
        # Find all h4 subsections
        h4_subsections = main_content.find_all('h4', class_=lambda x: x and 'brxe-heading' in str(x))
        
        # Find all item containers (divs with brxe-div class)
        all_item_containers = main_content.find_all('div', class_=lambda x: x and 'brxe-div' in str(x), recursive=True)
        
        # Use a global processed_items set to prevent duplicates across all sections
        processed_items = set()
        processed_sections = set()
        
        for h2 in h2_sections:
            section_name = h2.get_text(strip=True)
            # Skip non-menu sections
            skip_sections = ['HandcrafteD Food', 'HandcrafteD Drinks', 'HandCrafted Food', 'HandCrafted DRINKS', 
                           'Dinner Menu', 'Lunch Menu', 'Always Up To Date', 'Menu']
            if section_name in skip_sections:
                continue
            
            # Avoid processing same section twice
            if section_name in processed_sections:
                continue
            processed_sections.add(section_name)
            
            print(f"    Extracting {section_name}...")
            
            # Find the next h2 to determine section boundaries
            next_h2 = None
            h2_index = h2_sections.index(h2)
            if h2_index + 1 < len(h2_sections):
                next_h2 = h2_sections[h2_index + 1]
            
            section_items = 0
            
            # Process all item containers and check if they belong to this section
            for container in all_item_containers:
                # Check if container comes after this h2 and before next h2
                # Use find_previous to check which h2 precedes this container
                prev_h2 = container.find_previous('h2', class_=lambda x: x and 'brxe-heading' in str(x))
                if prev_h2 != h2:
                    continue
                
                # Check if there's a next h2 between h2 and this container
                if next_h2:
                    # Check all elements between h2 and container
                    check_elem = h2.find_next()
                    found_next_h2 = False
                    while check_elem and check_elem != container:
                        if check_elem == next_h2:
                            found_next_h2 = True
                            break
                        check_elem = check_elem.find_next()
                    if found_next_h2:
                        continue  # Container is after next_h2, skip it
                
                # Process this container - extract item information
                # Find all nested divs with brxe-block class that contain h5 elements
                brxe_blocks = container.find_all('div', class_=lambda x: x and 'brxe-block' in str(x))
                
                # Only process blocks that have exactly 2 h5s (name + price together)
                # This avoids processing duplicate blocks that have only name or only price
                valid_blocks = []
                for block in brxe_blocks:
                    h5s = block.find_all('h5', class_=lambda x: x and 'brxe-heading' in str(x))
                    if len(h5s) == 2:
                        valid_blocks.append(block)
                
                if not valid_blocks:
                    continue
                
                # Get all container-level descriptions (p tags)
                container_ps = container.find_all('p', class_=lambda x: x and 'brxe-text-basic' in str(x))
                
                # Process each valid block (has both name and price)
                for block_idx, block in enumerate(valid_blocks):
                    h5s = block.find_all('h5', class_=lambda x: x and 'brxe-heading' in str(x))
                    if len(h5s) != 2:
                        continue
                    
                    item_name_h5 = h5s[0]
                    price_h5 = h5s[1]
                    
                    item_name = item_name_h5.get_text(strip=True)
                    price_text = price_h5.get_text(strip=True)
                    
                    # Skip if invalid
                    if not item_name or len(item_name) > 100 or 'Menu' in item_name:
                        continue
                    
                    # Check if price_text looks like a price
                    is_price = False
                    if price_text.isdigit():
                        is_price = True
                    elif '/' in price_text:
                        parts = [p.strip() for p in price_text.split('/')]
                        if len(parts) == 2 and (parts[0].isdigit() or parts[1].isdigit()):
                            is_price = True
                    
                    if not is_price:
                        continue
                    
                    # Format price
                    price = ""
                    if '/' in price_text:
                        parts = [p.strip() for p in price_text.split('/')]
                        if len(parts) == 2:
                            if parts[0].isdigit() and parts[1].isdigit():
                                price = f"Glass ${parts[0]}.00, Bottle ${parts[1]}.00"
                            elif parts[0].isdigit():
                                price = f"Glass ${parts[0]}.00"
                            elif parts[1].isdigit():
                                price = f"Bottle ${parts[1]}.00"
                    elif price_text.isdigit():
                        price = f"${price_text}.00"
                    
                    if not price:
                        continue
                    
                    # Find the preceding h4 to determine subsection
                    subsection_name = section_name
                    preceding_h4 = container.find_previous('h4', class_=lambda x: x and 'brxe-heading' in str(x))
                    if preceding_h4:
                        check_elem = preceding_h4
                        h2_between = False
                        while check_elem and check_elem != container:
                            if check_elem.name == 'h2':
                                h2_between = True
                                break
                            check_elem = check_elem.find_next_sibling()
                            if not check_elem:
                                check_elem = check_elem.find_next() if hasattr(check_elem, 'find_next') else None
                        
                        if not h2_between:
                            h4_text = preceding_h4.get_text(strip=True)
                            if h4_text and h4_text not in ['Celebration Pours']:
                                subsection_name = f"{section_name} - {h4_text}"
                    
                    # Find description
                    # Descriptions are at container level
                    # For wines: alternating region (short), description (long) - use odd indices
                    # For cocktails: sequential descriptions - use same index as block
                    description = ""
                    if container_ps:
                        # Check if descriptions alternate (wines) or are sequential (cocktails)
                        # If first p is short (< 20 chars), it's likely a region, so use alternating pattern
                        first_p_short = len(container_ps[0].get_text(strip=True)) < 20 if container_ps else False
                        
                        if first_p_short and len(container_ps) > 1:
                            # Wines: alternating pattern (region, desc, region, desc, ...)
                            desc_index = block_idx * 2 + 1
                        else:
                            # Cocktails: sequential pattern (desc0, desc1, desc2, ...)
                            desc_index = block_idx
                        
                        if desc_index < len(container_ps):
                            description = container_ps[desc_index].get_text(strip=True)
                            # If description is too short and there are more, try next one
                            if len(description) < 20 and desc_index + 1 < len(container_ps):
                                description = container_ps[desc_index + 1].get_text(strip=True)
                        else:
                            # Fallback: use longest description
                            long_descs = [p.get_text(strip=True) for p in container_ps if len(p.get_text(strip=True)) > 20]
                            if long_descs:
                                description = long_descs[0] if len(long_descs) == 1 else max(long_descs, key=len)
                    
                    # Create unique key for duplicate detection
                    desc_hash = hash(description[:50]) if description else 0
                    item_key = (item_name, price, desc_hash)
                    if item_key not in processed_items:
                        items.append({
                            'name': item_name,
                            'description': description,
                            'price': price,
                            'section': subsection_name
                        })
                        section_items += 1
                        processed_items.add(item_key)
                
                # Skip old processing code below
                continue
                
                # OLD CODE BELOW - NOT REACHED
                i = 0
                while i < len(h5_blocks) - 1:
                    item_name_h5 = h5_blocks[i]
                    item_name = item_name_h5.get_text(strip=True)
                    
                    # Find the next h5 that looks like a price
                    price_h5 = None
                    price_text = ""
                    for j in range(i + 1, len(h5_blocks)):
                        text = h5_blocks[j].get_text(strip=True)
                        # Check if it looks like a price
                        if text.isdigit() or ('/' in text and any(c.isdigit() for c in text)):
                            price_h5 = h5_blocks[j]
                            price_text = text
                            i = j + 1  # Move past this price
                            break
                    
                    if not price_h5 or not price_text:
                        i += 1
                        continue
                    
                    # Skip if invalid
                    if not item_name or len(item_name) > 100 or 'Menu' in item_name:
                        continue
                    
                    # Check if price_text looks like a price
                    is_price = False
                    if price_text.isdigit():
                        is_price = True
                    elif '/' in price_text:
                        parts = [p.strip() for p in price_text.split('/')]
                        if len(parts) == 2 and (parts[0].isdigit() or parts[1].isdigit()):
                            is_price = True
                    
                    if not is_price:
                        continue
                    
                    # Format price
                    price = ""
                    if '/' in price_text:
                        parts = [p.strip() for p in price_text.split('/')]
                        if len(parts) == 2:
                            if parts[0].isdigit() and parts[1].isdigit():
                                price = f"Glass ${parts[0]}.00, Bottle ${parts[1]}.00"
                            elif parts[0].isdigit():
                                price = f"Glass ${parts[0]}.00"
                            elif parts[1].isdigit():
                                price = f"Bottle ${parts[1]}.00"
                    elif price_text.isdigit():
                        price = f"${price_text}.00"
                    
                    if not price:
                        continue
                    
                    # Find the preceding h4 to determine subsection
                    subsection_name = section_name  # Default to main section
                    preceding_h4 = container.find_previous('h4', class_=lambda x: x and 'brxe-heading' in str(x))
                    if preceding_h4:
                        # Check if there's a h2 between this h4 and the container
                        check_elem = preceding_h4
                        h2_between = False
                        while check_elem and check_elem != container:
                            if check_elem.name == 'h2':
                                h2_between = True
                                break
                            check_elem = check_elem.find_next_sibling()
                            if not check_elem:
                                check_elem = check_elem.find_next() if hasattr(check_elem, 'find_next') else None
                        
                        if not h2_between:
                            h4_text = preceding_h4.get_text(strip=True)
                            # Only use h4 if it's a valid subsection (not "Celebration Pours" for wines)
                            if h4_text and h4_text not in ['Celebration Pours']:
                                subsection_name = f"{section_name} - {h4_text}"
                    
                    # Find description for this specific item
                    # The description should be in a p tag that comes after the item name h5
                    desc_elems = []
                    # Look for p tags in the container, but prefer ones that come after the item name
                    all_ps = container.find_all('p', class_=lambda x: x and 'brxe-text-basic' in str(x))
                    # Find the p that comes after this item's name h5
                    for p in all_ps:
                        # Check if this p comes after the item_name_h5 in the DOM
                        if item_name_h5.sourceline and p.sourceline:
                            if p.sourceline > item_name_h5.sourceline:
                                desc_elems.append(p)
                    
                    # If no p found after name, use all ps in container
                    if not desc_elems:
                        desc_elems = all_ps
                    
                    description = ""
                    if desc_elems:
                        # If multiple paragraphs, use the longest one (actual description, not region)
                        if len(desc_elems) > 1:
                            desc_elem = max(desc_elems, key=lambda p: len(p.get_text(strip=True)))
                        else:
                            desc_elem = desc_elems[0]
                        description = desc_elem.get_text(strip=True)
                        # Skip very short descriptions (likely regions like "VENETO, ITALY")
                        if len(description) < 20 and len(desc_elems) > 1:
                            # Try to get the longer description
                            longer_desc = [p.get_text(strip=True) for p in desc_elems if len(p.get_text(strip=True)) > 20]
                            if longer_desc:
                                description = longer_desc[0]
                    
                    # Create unique key for duplicate detection
                    desc_hash = hash(description[:50]) if description else 0
                    item_key = (item_name, price, desc_hash)
                    if item_key not in processed_items:
                        items.append({
                            'name': item_name,
                            'description': description,
                            'price': price,
                            'section': subsection_name
                        })
                        section_items += 1
                        processed_items.add(item_key)
                    
                    # Continue to next item
                    continue
                
                # Old single-item processing (skip if we processed items above)
                continue
                
                # Find the price h5 (should be a number or "X / Y" format)
                price_h5 = None
                price_text = ""
                for h5 in h5_blocks[1:]:  # Skip the first one (name)
                    text = h5.get_text(strip=True)
                    # Check if it looks like a price
                    if text.isdigit() or ('/' in text and any(c.isdigit() for c in text)):
                        price_h5 = h5
                        price_text = text
                        break
                
                if not price_h5 or not price_text:
                    continue
                
                # Skip if invalid
                if not item_name or len(item_name) > 100 or 'Menu' in item_name:
                    continue
                
                # Check if price_text looks like a price
                is_price = False
                if price_text.isdigit():
                    is_price = True
                elif '/' in price_text:
                    parts = [p.strip() for p in price_text.split('/')]
                    if len(parts) == 2 and (parts[0].isdigit() or parts[1].isdigit()):
                        is_price = True
                
                if not is_price:
                    continue
                
                # Format price
                price = ""
                if '/' in price_text:
                    parts = [p.strip() for p in price_text.split('/')]
                    if len(parts) == 2:
                        if parts[0].isdigit() and parts[1].isdigit():
                            price = f"Glass ${parts[0]}.00, Bottle ${parts[1]}.00"
                        elif parts[0].isdigit():
                            price = f"Glass ${parts[0]}.00"
                        elif parts[1].isdigit():
                            price = f"Bottle ${parts[1]}.00"
                elif price_text.isdigit():
                    price = f"${price_text}.00"
                
                if not price:
                    continue
                
                # Find the preceding h4 to determine subsection
                # Need to ensure the h4 is within the same h2 section
                subsection_name = section_name  # Default to main section
                preceding_h4 = container.find_previous('h4', class_=lambda x: x and 'brxe-heading' in str(x))
                if preceding_h4:
                    # Check if there's a h2 between this h4 and the container
                    # If so, this h4 belongs to a different section
                    check_elem = preceding_h4
                    h2_between = False
                    while check_elem and check_elem != container:
                        if check_elem.name == 'h2':
                            h2_between = True
                            break
                        check_elem = check_elem.find_next_sibling()
                        if not check_elem:
                            check_elem = check_elem.find_next() if hasattr(check_elem, 'find_next') else None
                    
                    if not h2_between:
                        h4_text = preceding_h4.get_text(strip=True)
                        # Only use h4 if it's a valid subsection (not "Celebration Pours" for wines)
                        if h4_text and h4_text not in ['Celebration Pours']:
                            subsection_name = f"{section_name} - {h4_text}"
                
                # Find description (p tag in the same container)
                # For wines, there are two paragraphs: region (short) and description (longer)
                # We want the longer one (actual description)
                desc_elems = container.find_all('p', class_=lambda x: x and 'brxe-text-basic' in str(x))
                description = ""
                if desc_elems:
                    # If multiple paragraphs, use the longest one (actual description, not region)
                    if len(desc_elems) > 1:
                        desc_elem = max(desc_elems, key=lambda p: len(p.get_text(strip=True)))
                    else:
                        desc_elem = desc_elems[0]
                    description = desc_elem.get_text(strip=True)
                    # Skip very short descriptions (likely regions like "VENETO, ITALY")
                    if len(description) < 20 and len(desc_elems) > 1:
                        # Try to get the longer description
                        longer_desc = [p.get_text(strip=True) for p in desc_elems if len(p.get_text(strip=True)) > 20]
                        if longer_desc:
                            description = longer_desc[0]
                
                # Create unique key for duplicate detection
                # Include a hash of description to make it more unique
                desc_hash = hash(description[:50]) if description else 0
                item_key = (item_name, price, subsection_name, desc_hash)
                if item_key not in processed_items:
                    items.append({
                        'name': item_name,
                        'description': description,
                        'price': price,
                        'section': subsection_name
                    })
                    section_items += 1
                    processed_items.add(item_key)
            
            if section_items > 0:
                print(f"      Found {section_items} items")
        
    except Exception as e:
        print(f"  [ERROR] Error extracting Lago menu items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def extract_blackbirds_menu_items(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract menu items from Blackbirds menu (similar structure to Lago)
    """
    return extract_lago_menu_items(soup)  # Same structure


def scrape_druthersbrewing_menu():
    """
    Main function to scrape menus from all Druthers locations
    """
    all_items = []
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    # ===== DRUTHERS BREWPUB MENU =====
    url = "https://www.druthersbrewing.com/"
    restaurant_name = "Druthers Brewing Company"
    
    print(f"\n============================================================")
    print(f"Scraping: {url}")
    print(f"============================================================\n")
    
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    # Remove trailing underscores and 'menu' if present
    url_safe = url_safe.rstrip('_').replace('_menu', '')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    # ===== BREWPUB MENU (HTML) =====
    print("Scraping Brewpub Menu...")
    menu_url = "https://www.druthersbrewing.com/menu/"
    
    try:
        headers = {
            'Referer': 'https://www.druthersbrewing.com/the-food/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Upgrade-Insecure-Requests': '1',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        response = requests.get(menu_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        menu_items = extract_menu_items_from_html(soup)
        
        for item in menu_items:
            # Format price with add-ons if present
            price_str = item.get('price', '')
            addons = item.get('addons', [])
            if addons:
                if price_str:
                    price_str += " / " + " / ".join(addons)
                else:
                    price_str = " / ".join(addons)
            
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': price_str,
                'menu_type': item.get('section', ''),
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Brewpub Menu'
            })
        
        print(f"[OK] Extracted {len(menu_items)} items from Brewpub Menu\n")
        
    except Exception as e:
        print(f"[ERROR] Error scraping menu: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== BEER MENU (HTML) =====
    print("Scraping Beer Menu...")
    beer_url = "https://www.druthersbrewing.com/beer/"
    
    try:
        headers = {
            'Referer': 'https://www.druthersbrewing.com/beer/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Upgrade-Insecure-Requests': '1',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        response = requests.get(beer_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        beer_items = extract_beer_items_from_html(soup)
        
        # Group beers by section for reporting
        section_counts = {}
        for item in beer_items:
            section = item.get('section', '')
            section_counts[section] = section_counts.get(section, 0) + 1
        
        for section, count in section_counts.items():
            print(f"    Extracting {section}...")
            print(f"      Found {count} items")
        
        for item in beer_items:
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': item.get('section', ''),
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Beer Menu'
            })
        
        print(f"[OK] Extracted {len(beer_items)} items from Beer Menu\n")
        
    except Exception as e:
        print(f"[ERROR] Error scraping beer menu: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== LAGO BY DRUTHERS MENUS =====
    lago_url = "https://lagobydruthers.com/"
    lago_restaurant_name = "Lago By Druthers"
    
    print(f"\n============================================================")
    print(f"Scraping: {lago_url}")
    print(f"============================================================\n")
    
    lago_items = []
    
    # Lago Food Menu
    print("Scraping Lago Food Menu...")
    try:
        headers = {
            'Referer': 'https://www.druthersbrewing.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get("https://lagobydruthers.com/menu/", headers=headers, timeout=30)
        response.raise_for_status()
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        menu_items = extract_lago_menu_items(soup)
        
        for item in menu_items:
            lago_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': item.get('section', ''),
                'restaurant_name': lago_restaurant_name,
                'restaurant_url': lago_url,
                'menu_name': 'Food Menu'
            })
        
        print(f"[OK] Extracted {len(menu_items)} items from Lago Food Menu\n")
    except Exception as e:
        print(f"[ERROR] Error scraping Lago food menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Lago Drink Menu
    print("Scraping Lago Drink Menu...")
    try:
        headers = {
            'Referer': 'https://lagobydruthers.com/menu/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get("https://lagobydruthers.com/drink-menu/", headers=headers, timeout=30)
        response.raise_for_status()
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        drink_items = extract_lago_menu_items(soup)
        
        for item in drink_items:
            lago_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': item.get('section', ''),
                'restaurant_name': lago_restaurant_name,
                'restaurant_url': lago_url,
                'menu_name': 'Drink Menu'
            })
        
        print(f"[OK] Extracted {len(drink_items)} items from Lago Drink Menu\n")
    except Exception as e:
        print(f"[ERROR] Error scraping Lago drink menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Lago Beer Menu (live menu - might be different structure)
    print("Scraping Lago Beer Menu...")
    try:
        headers = {
            'Referer': 'https://lagobydruthers.com/drink-menu/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get("https://lagobydruthers.com/beer-menu/", headers=headers, timeout=30)
        response.raise_for_status()
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        beer_items = extract_lago_menu_items(soup)
        
        for item in beer_items:
            lago_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': item.get('section', ''),
                'restaurant_name': lago_restaurant_name,
                'restaurant_url': lago_url,
                'menu_name': 'Beer Menu'
            })
        
        print(f"[OK] Extracted {len(beer_items)} items from Lago Beer Menu\n")
    except Exception as e:
        print(f"[ERROR] Error scraping Lago beer menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Track Lago count before adding
    lago_count = len(lago_items)
    
    # Add Lago items to all_items
    all_items.extend(lago_items)
    
    # ===== BLACKBIRDS TAVERN MENUS =====
    blackbirds_url = "https://blackbirdstavern.com/"
    blackbirds_restaurant_name = "Blackbirds Tavern by Druthers"
    
    print(f"\n============================================================")
    print(f"Scraping: {blackbirds_url}")
    print(f"============================================================\n")
    
    blackbirds_items = []
    
    # Blackbirds Food Menu
    print("Scraping Blackbirds Food Menu...")
    try:
        headers = {
            'Referer': 'https://www.druthersbrewing.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get("https://blackbirdstavern.com/menu/", headers=headers, timeout=30)
        response.raise_for_status()
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        menu_items = extract_blackbirds_menu_items(soup)
        
        for item in menu_items:
            blackbirds_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': item.get('section', ''),
                'restaurant_name': blackbirds_restaurant_name,
                'restaurant_url': blackbirds_url,
                'menu_name': 'Food Menu'
            })
        
        print(f"[OK] Extracted {len(menu_items)} items from Blackbirds Food Menu\n")
    except Exception as e:
        print(f"[ERROR] Error scraping Blackbirds food menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Blackbirds Drink Menu
    print("Scraping Blackbirds Drink Menu...")
    try:
        headers = {
            'Referer': 'https://blackbirdstavern.com/menu/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get("https://blackbirdstavern.com/drink-menu/", headers=headers, timeout=30)
        response.raise_for_status()
        # Use html.parser for Lago menus as they may have complex nested structures
        parser = 'html.parser' if 'lagobydruthers.com' in response.url or 'blackbirdstavern.com' in response.url else 'lxml'
        soup = BeautifulSoup(response.text, parser)
        drink_items = extract_blackbirds_menu_items(soup)
        
        for item in drink_items:
            blackbirds_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': item.get('section', ''),
                'restaurant_name': blackbirds_restaurant_name,
                'restaurant_url': blackbirds_url,
                'menu_name': 'Drink Menu'
            })
        
        print(f"[OK] Extracted {len(drink_items)} items from Blackbirds Drink Menu\n")
    except Exception as e:
        print(f"[ERROR] Error scraping Blackbirds drink menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Track Blackbirds count before adding
    blackbirds_count = len(blackbirds_items)
    
    # Add Blackbirds items to all_items
    all_items.extend(blackbirds_items)
    
    # Track Druthers count
    druthers_count = len(all_items) - lago_count - blackbirds_count
    
    # Save all items to a single file
    if all_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(all_items, f, indent=2, ensure_ascii=False)
        print(f"\nSaving {len(all_items)} items to: {output_json}\n")
    
    # Final summary
    print(f"============================================================")
    print(f"[OK] Scraping complete!")
    print(f"  - Druthers Brewpub: {druthers_count} items")
    print(f"  - Lago By Druthers: {lago_count} items")
    print(f"  - Blackbirds Tavern: {blackbirds_count} items")
    print(f"  - Total: {len(all_items)} items")
    print(f"============================================================\n")
    
    return all_items


if __name__ == "__main__":
    scrape_druthersbrewing_menu()

