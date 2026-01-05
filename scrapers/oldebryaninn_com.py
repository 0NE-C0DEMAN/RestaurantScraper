"""
Scraper for oldebryaninn.com (Olde Bryan Inn)
Scrapes menu from HTML pages: Take Out Menu and Daily Specials
"""

import json
import re
from pathlib import Path
from typing import List, Dict
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def format_price(price: str) -> str:
    """Format price string to include $ symbol."""
    if not price:
        return ""
    price = price.strip()
    # Remove any existing $ symbols and add one
    price = re.sub(r'\$+', '', price)
    if price:
        return f"${price}"
    return ""


def parse_takeout_menu(html: str) -> List[Dict]:
    """Parse items from the takeout menu HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find the main content section
    content = soup.find('section', class_='entry-content')
    if not content:
        return items
    
    current_section = None
    
    # Process all elements in order
    for element in content.find_all(['h2', 'p']):
        if element.name == 'h2':
            # Update current section
            current_section = element.get_text(strip=True)
            continue
        
        if element.name == 'p':
            # Skip empty paragraphs
            text = element.get_text(strip=True)
            if not text:
                continue
            
            # Extract item name - handle cases where name has embedded em/strong tags
            strong_tag = element.find('strong')
            if not strong_tag:
                continue
            
            # Get the full name including any embedded tags
            item_name_parts = []
            for content in strong_tag.contents:
                if isinstance(content, str):
                    item_name_parts.append(content.strip())
                else:
                    item_name_parts.append(content.get_text(strip=True))
            item_name = ' '.join(item_name_parts).strip()
            
            if not item_name:
                continue
            
            # Get all text from the paragraph first
            all_text = element.get_text(separator=' ', strip=True)
            
            # Remove the item name from the text
            description = all_text.replace(item_name, '', 1).strip()
            
            # Extract main price from description
            # First, identify potential addon sections to exclude from main price search
            # Addons are usually in patterns like "Add X Y" or "*Add X" followed by a number
            # We'll find the main price first, then process addons
            
            # Pattern 1: "sm X- lg Y" format
            price_match = re.search(r'(?:sm\s+)?(\d+\.?\d*)\s*-\s*(?:lg\s+)?(\d+\.?\d*)(?:\s|$)', description, re.IGNORECASE)
            if price_match:
                # Multiple prices with size labels
                sm_price = price_match.group(1)
                lg_price = price_match.group(2)
                price = f"Small ${sm_price} | Large ${lg_price}"
                # Remove this price from description
                description = description[:price_match.start()].strip() + description[price_match.end():].strip()
            else:
                    # Single price - look for the last number that's not part of an addon
                    # Find all numbers in the text
                    all_numbers = list(re.finditer(r'(\d+\.?\d*)', description))
                    if all_numbers:
                        # The main price is usually the last number before any addon indicators
                        # Check each number from the end backwards
                        main_price_idx = -1
                        for i in range(len(all_numbers) - 1, -1, -1):
                            num_match = all_numbers[i]
                            num_value = num_match.group(1)
                            
                            # Get text before this number (up to 100 chars)
                            text_before = description[max(0, num_match.start() - 100):num_match.start()].lower()
                            
                            # Check if this number is part of an addon
                            # Look for "add", "substitute", or "*" before the number
                            is_addon = (
                                re.search(r'(add|substitute)', text_before, re.IGNORECASE) or
                                re.search(r'\*', text_before) or
                                ('add' in text_before.lower() or 'substitute' in text_before.lower())
                            )
                            
                            if not is_addon:
                                main_price_idx = i
                                break
                        
                        if main_price_idx >= 0:
                            price_match = all_numbers[main_price_idx]
                            price = format_price(price_match.group(1))
                            # Remove price from description
                            description = (description[:price_match.start()].strip() + 
                                         ' ' + description[price_match.end():].strip()).strip()
                        else:
                            # Fallback: use the first number (usually the main price comes first)
                            price_match = all_numbers[0]
                            price = format_price(price_match.group(1))
                            description = (description[:price_match.start()].strip() + 
                                         ' ' + description[price_match.end():].strip()).strip()
                    else:
                        price = ""
            
            # Now extract addons from em and strong tags
            addons = []
            
            # Find all em tags (usually contain addons)
            for em in element.find_all('em'):
                em_text = em.get_text(strip=True)
                if not em_text:
                    continue
                
                # Look for addon patterns in em tags
                # Pattern: "Add X" or "Add X Y" followed by price, or price in separate em tag
                addon_match = re.search(r'(?:add|substitute)\s+(.+?)\s+(\d+\.?\d*)', em_text, re.IGNORECASE)
                if addon_match:
                    addon_name = addon_match.group(1).strip()
                    addon_price = format_price(addon_match.group(2))
                    addons.append(f"{addon_name} {addon_price}")
                elif ('add' in em_text.lower() or 'substitute' in em_text.lower()):
                    # Check if price is in this em or in next sibling
                    price_in_em = re.search(r'(\d+\.?\d*)', em_text)
                    if price_in_em:
                        addon_name = em_text.replace(price_in_em.group(1), '').strip()
                        addon_price = format_price(price_in_em.group(1))
                        if addon_name:
                            addons.append(f"{addon_name} {addon_price}")
                    else:
                        # Check next sibling for price
                        next_sib = em.next_sibling
                        if next_sib:
                            next_text = next_sib.get_text(strip=True) if hasattr(next_sib, 'get_text') else str(next_sib).strip()
                            price_match = re.search(r'(\d+\.?\d*)', next_text)
                            if price_match:
                                addon_price = format_price(price_match.group(1))
                                addons.append(f"{em_text} {addon_price}")
            
            # Find addons in strong tags (like Gochujang case)
            for strong in element.find_all('strong'):
                strong_text = strong.get_text(strip=True)
                if strong_text == item_name:
                    continue
                if '*' in strong_text and ('add' in strong_text.lower()):
                    # Look for price in next sibling
                    next_sib = strong.next_sibling
                    if next_sib:
                        next_text = next_sib.get_text(strip=True) if hasattr(next_sib, 'get_text') else str(next_sib).strip()
                        price_match = re.search(r'(\d+\.?\d*)', next_text)
                        if price_match:
                            addon_name = strong_text.replace('*', '').strip()
                            addon_price = format_price(price_match.group(1))
                            addons.append(f"{addon_name} {addon_price}")
            
            # Add addons to description if found
            if addons:
                if description:
                    description += f" | Add-ons: {' / '.join(addons)}"
                else:
                    description = f"Add-ons: {' / '.join(addons)}"
            
            # Clean up description
            description = re.sub(r'\s+', ' ', description).strip()
            
            # Skip if no price and no description
            if not price and not description:
                continue
            
            items.append({
                "name": item_name,
                "description": description,
                "price": price,
                "restaurant_name": "Olde Bryan Inn",
                "restaurant_url": "http://www.oldebryaninn.com/",
                "menu_type": "Take Out",
                "menu_name": current_section or "main menu"
            })
    
    return items


def parse_daily_specials(html: str) -> List[Dict]:
    """Parse items from the daily specials HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find the main content section
    content = soup.find('section', class_='entry-content')
    if not content:
        return items
    
    current_section = None
    
    # Process all paragraphs
    for p in content.find_all('p'):
        text = p.get_text(strip=True)
        if not text:
            continue
        
        # Check for section headers (em tags with ~)
        em_tags = p.find_all('em')
        for em in em_tags:
            em_text = em.get_text(strip=True)
            if '~' in em_text:
                # This might be a section header
                section_match = re.search(r'~(.+?)~', em_text)
                if section_match:
                    current_section = section_match.group(1).strip()
                continue
        
        # Process paragraph by finding all strong tags and extracting items
        skip_patterns = [
            'january', 'february', 'march', 'april', 'may', 'june', 
            'july', 'august', 'september', 'october', 'november', 'december',
            'saturday', 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
            'from the bar', 'soup of the day', 'appetizer special', 
            'main events', 'sweet ending', 'chefs are', 'our chefs',
            'brandon', 'conklin', 'matthew', 'phillips', 'stephen', 'peterson',
            'david', 'bruschi', 'josh', 'kerwood', 'jacob', 'corrigan',
            'tyler', 'hanmann', 'john', 'capelli', 'saturd', 'ay,',
            'cream of broccoli', 'ham & cheese'
        ]
        
        # Find all strong/b tags in order
        all_strong_tags = p.find_all(['strong', 'b'])
        processed_names = set()
        
        for i, strong_tag in enumerate(all_strong_tags):
            item_name = strong_tag.get_text(strip=True)
            if not item_name or len(item_name) < 3:
                continue
            
            # Skip if it matches skip patterns
            if any(pattern in item_name.lower() for pattern in skip_patterns):
                continue
            
            # Skip duplicates
            if item_name in processed_names:
                continue
            processed_names.add(item_name)
            
            # Get text content by walking through siblings after this strong tag
            description_parts = []
            current = strong_tag.next_sibling
            
            # Find the next valid strong tag to know where to stop
            next_strong_tag = None
            for j in range(i + 1, len(all_strong_tags)):
                next_strong = all_strong_tags[j]
                next_strong_text = next_strong.get_text(strip=True)
                if next_strong_text and len(next_strong_text) >= 3:
                    if not any(pattern in next_strong_text.lower() for pattern in skip_patterns):
                        next_strong_tag = next_strong
                        break
            
            # Collect text until we hit the next strong tag or a price followed by br
            collected_text = []
            price = ""
            description = ""
            
            while current:
                if current == next_strong_tag:
                    break
                
                # Get text from this node
                node_text = ""
                if hasattr(current, 'name'):
                    if current.name in ['strong', 'b']:
                        # Hit another strong tag, check if it's the next item
                        if current == next_strong_tag:
                            break
                        # Otherwise, it's probably formatting, include it
                        node_text = current.get_text(strip=True)
                    elif current.name == 'br':
                        # Check if there's a price at the END of text before this br
                        text_so_far = ' '.join(collected_text)
                        # Look for price at the very end (before the br) - number at end, possibly with *
                        price_match = re.search(r'(\d+\.?\d*)\s*(?:\*|$)\s*$', text_so_far)
                        if price_match:
                            should_stop = False
                            
                            # If we have a next_strong_tag, assume this is the end of current item
                            if next_strong_tag:
                                should_stop = True
                            else:
                                # Check if any strong tag follows after empty formatting tags
                                after_br = current.next_sibling
                                search_depth = 0
                                while after_br and search_depth < 5:
                                    if not hasattr(after_br, 'name'):
                                        break
                                    if after_br.name in ['strong', 'b']:
                                        # Found a strong tag after br - this is likely the next item
                                        tag_text = after_br.get_text(strip=True)
                                        if tag_text and len(tag_text) >= 3:
                                            if not any(pattern in tag_text.lower() for pattern in skip_patterns):
                                                # Valid item name found
                                                should_stop = True
                                                break
                                    if after_br.name not in ['b', 'span']:
                                        break
                                    tag_text = after_br.get_text(strip=True)
                                    if tag_text:
                                        break
                                    after_br = after_br.next_sibling
                                    search_depth += 1
                            
                            if should_stop:
                                # Found price at end, next item starts, extract it and stop immediately
                                price = format_price(price_match.group(1))
                                description = text_so_far[:price_match.start()].strip()
                                break
                        node_text = ' '
                    else:
                        # Check if this node contains a <br /> tag
                        if hasattr(current, 'find') and current.find('br'):
                            # Node contains br, get text up to the first br
                            # Clone the node and get text before first br
                            node_clone = BeautifulSoup(str(current), 'html.parser')
                            first_br = node_clone.find('br')
                            if first_br:
                                # Get all text before the br
                                before_br_parts = []
                                for elem in first_br.previous_siblings:
                                    if hasattr(elem, 'get_text'):
                                        before_br_parts.append(elem.get_text(strip=True))
                                    elif isinstance(elem, str):
                                        before_br_parts.append(str(elem).strip())
                                # Also get text from parent before br
                                parent_text = ''
                                for content in node_clone.contents:
                                    if content == first_br:
                                        break
                                    if hasattr(content, 'get_text'):
                                        parent_text += ' ' + content.get_text(strip=True)
                                    elif isinstance(content, str):
                                        parent_text += ' ' + str(content).strip()
                                node_text = parent_text.strip()
                                
                                # Check if this text ends with a price
                                price_match = re.search(r'(\d+\.?\d*)\s*(?:\*|$)\s*$', node_text)
                                if price_match:
                                    # Check if after this node is the next strong tag
                                    after_node = current.next_sibling
                                    while after_node and hasattr(after_node, 'name') and after_node.name in ['b', 'span'] and not after_node.get_text(strip=True):
                                        after_node = after_node.next_sibling
                                    
                                    if after_node == next_strong_tag or (hasattr(after_node, 'name') and after_node.name in ['strong', 'b'] and after_node in all_strong_tags):
                                        # Price found, next item starts, extract and stop
                                        price = format_price(price_match.group(1))
                                        collected_text.append(node_text[:price_match.start()].strip())
                                        description = ' '.join(collected_text).strip()
                                        break
                            else:
                                node_text = current.get_text(strip=True)
                        else:
                            node_text = current.get_text(strip=True)
                elif isinstance(current, str):
                    node_text = str(current).strip()
                
                if node_text:
                    collected_text.append(node_text)
                    # Check if we just added a price (at the end of collected text)
                    text_so_far = ' '.join(collected_text)
                    # Look for price at the very end (number followed by optional * and end)
                    price_match = re.search(r'(\d+\.?\d*)\s*(?:\*|$)\s*$', text_so_far)
                    if price_match:
                        # Check if next sibling is br followed by strong tag, or next_strong_tag
                        next_sib = current.next_sibling
                        # Skip empty/whitespace siblings
                        while next_sib and hasattr(next_sib, 'name') and next_sib.name in ['b', 'span'] and not next_sib.get_text(strip=True):
                            next_sib = next_sib.next_sibling
                        
                        if next_sib:
                            if next_sib == next_strong_tag:
                                # Next item starts, extract price and stop
                                price = format_price(price_match.group(1))
                                description = text_so_far[:price_match.start()].strip()
                                break
                            elif hasattr(next_sib, 'name') and next_sib.name == 'br':
                                # Check if after br is the next strong tag
                                after_br = next_sib.next_sibling
                                while after_br and hasattr(after_br, 'name') and after_br.name in ['b', 'span'] and not after_br.get_text(strip=True):
                                    after_br = after_br.next_sibling
                                if after_br == next_strong_tag or (hasattr(after_br, 'name') and after_br.name in ['strong', 'b'] and after_br == next_strong_tag):
                                    # Price found, next item starts after br, extract and stop
                                    price = format_price(price_match.group(1))
                                    description = text_so_far[:price_match.start()].strip()
                                    break
                
                current = current.next_sibling
            
            # If we didn't break early, process collected text
            if not price:
                description = ' '.join(collected_text).strip()
                # Extract price from the end
                price_match = re.search(r'(\d+\.?\d*)\s*(?:\*|$)', description)
                if price_match:
                    price = format_price(price_match.group(1))
                    description = description[:price_match.start()].strip()
            
            # Clean up description
            description = re.sub(r'~.*?~', '', description, flags=re.IGNORECASE)
            description = re.sub(r'\s+', ' ', description).strip()
            
            # Remove asterisks and donation notes
            description = re.sub(r'\*.*?$', '', description).strip()
            description = re.sub(r'\$.*?donated.*?$', '', description, flags=re.IGNORECASE).strip()
            
            # Remove any remaining standalone numbers that look like prices
            description = re.sub(r'\s+\d+\.?\d*\s*$', '', description).strip()
            
            # Remove asterisks and donation notes
            description = re.sub(r'\*.*?$', '', description).strip()
            description = re.sub(r'\$.*?donated.*?$', '', description, flags=re.IGNORECASE).strip()
            
            # Skip if no price and no description, or if description is too short
            if not price and not description:
                continue
            if len(description) < 10 and not price:
                continue
            
            items.append({
                "name": item_name,
                "description": description,
                "price": price,
                "restaurant_name": "Olde Bryan Inn",
                "restaurant_url": "http://www.oldebryaninn.com/",
                "menu_type": "Daily Specials",
                "menu_name": current_section or "daily specials"
            })
    
    return items


def scrape_oldebryaninn():
    """Main scraping function."""
    print("=" * 60)
    print("Scraping Olde Bryan Inn (oldebryaninn.com)")
    print("=" * 60)
    
    all_items = []
    
    # URLs
    urls = [
        {
            "url": "https://www.oldebryaninn.com/take-out-menu/",
            "name": "Take Out Menu",
            "parser": parse_takeout_menu
        },
        {
            "url": "https://www.oldebryaninn.com/daily-specials/",
            "name": "Daily Specials",
            "parser": parse_daily_specials
        }
    ]
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        for menu_info in urls:
            print(f"\n[{len(all_items) + 1}] Processing {menu_info['name']}...")
            try:
                # Navigate to page
                page.goto(menu_info['url'], wait_until='networkidle', timeout=30000)
                
                # Wait a bit for any dynamic content
                page.wait_for_timeout(1000)
                
                # Get page content
                html = page.content()
                
                items = menu_info['parser'](html)
                all_items.extend(items)
                
                print(f"  [OK] Found {len(items)} items")
            except Exception as e:
                print(f"  [ERROR] Failed to scrape {menu_info['name']}: {e}")
        
        browser.close()
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Save to JSON
    output_path = Path(__file__).parent.parent / "output" / "oldebryaninn_com.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(all_items)} items to {output_path}")
    
    # Print sample items
    if all_items:
        print(f"\n[2] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            print(f"  {i}. {item['name']} - {item['price']} ({item['menu_type']} / {item['menu_name']})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")


if __name__ == "__main__":
    scrape_oldebryaninn()

