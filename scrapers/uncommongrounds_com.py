"""
Scraper for Uncommon Grounds (uncommongrounds.com)
Scrapes menus from multiple locations
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup
import requests


RESTAURANT_NAME = "Uncommon Grounds"
RESTAURANT_URL = "http://www.uncommongrounds.com/"

MENU_URLS = {
    'saratoga': {
        'url': 'https://www.uncommongrounds.com/locations/saratoga-springs/saratoga-springs-menu/',
        'name': 'Saratoga Springs'
    },
    'albany': {
        'url': 'https://www.uncommongrounds.com/locations/albany/albany-menu/',
        'name': 'Albany'
    },
    'clifton': {
        'url': 'https://www.uncommongrounds.com/clifton-park-menu/',
        'name': 'Clifton Park'
    }
}


def fetch_menu_html(location_key: str) -> Optional[str]:
    """Fetch menu HTML for a location"""
    menu_info = MENU_URLS.get(location_key)
    if not menu_info:
        return None
    
    url = menu_info['url']
    
    if location_key == 'saratoga':
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'referer': 'https://www.uncommongrounds.com/locations/saratoga-springs/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        cookies = {
            'sbjs_migrations': '1418474375998%3D1',
            'sbjs_current_add': 'fd%3D2026-01-07%2006%3A21%3A41%7C%7C%7Cep%3Dhttps%3A%2F%2Fwww.uncommongrounds.com%2F%7C%7C%7Crf%3D%28none%29',
            'sbjs_first_add': 'fd%3D2026-01-07%2006%3A21%3A41%7C%7C%7Cep%3Dhttps%3A%2F%2Fwww.uncommongrounds.com%2F%7C%7C%7Crf%3D%28none%29',
            'sbjs_current': 'typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29',
            'sbjs_first': 'typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29',
            'sbjs_udata': 'vst%3D1%7C%7C%7Cuip%3D%28none%29%7C%7C%7Cuag%3DMozilla%2F5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F143.0.0.0%20Safari%2F537.36',
            'tk_or': '""',
            'tk_r3d': '""',
            'tk_lr': '""',
            '_gid': 'GA1.2.1571704649.1767768703',
            '_gat_gtag_UA_10476373_1': '1',
            'tk_ai': 'ye5FfvParBDTcnAIkKgePxsx',
            '__kla_id': 'eyJjaWQiOiJOalpoWXpNMlpEVXRNemN4T1MwME56QmhMV0k0WlRFdFpETmlabUZtWm1SaFlqRTAifQ==',
            '_fbp': 'fb.1.1767768705114.235975551759901102',
            'sbjs_session': 'pgs%3D3%7C%7C%7Ccpg%3Dhttps%3A%2F%2Fwww.uncommongrounds.com%2Flocations%2Fsaratoga-springs%2Fsaratoga-springs-menu%2F',
            '_ga_RSV773CGVP': 'GS2.1.s1767768703$o1$g1$t1767768742$j21$l0$h0',
            '_ga': 'GA1.2.939201297.1767768703'
        }
        response = requests.get(url, headers=headers, cookies=cookies)
    else:
        headers = {
            'Referer': f'https://www.uncommongrounds.com/locations/{location_key}/' if location_key == 'albany' else 'https://www.uncommongrounds.com/locations/clifton-park/',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        response = requests.get(url, headers=headers)
    
    response.raise_for_status()
    return response.text


def format_price(prices: List[str]) -> str:
    """Format prices as multi-size pricing"""
    if len(prices) == 1:
        return f"${prices[0]}"
    elif len(prices) == 2:
        return f"Small ${prices[0]} | Large ${prices[1]}"
    elif len(prices) == 3:
        return f"Small ${prices[0]} | Medium ${prices[1]} | Large ${prices[2]}"
    else:
        return ' | '.join([f"Size {i+1} ${p}" for i, p in enumerate(prices)])


def extract_menu_items(html: str, location_name: str) -> List[Dict]:
    """Extract menu items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find the main content area
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        entry_content = soup.find('main') or soup.find('article')
    
    if not entry_content:
        return items
    
    current_section = None
    
    # Process all elements in order
    for elem in entry_content.find_all(['h2', 'h3', 'h4', 'p']):
        if elem.name in ['h2', 'h3', 'h4']:
            section_text = elem.get_text(strip=True)
            # Skip empty or very short headings, and descriptive headings
            if len(section_text) > 2 and not any(x in section_text.lower() for x in ['are made', 'at uncommon', 'sourced from']):
                current_section = section_text
        
        elif elem.name == 'p':
            text = elem.get_text(strip=True)
            if not text or len(text) < 3:
                continue
            
            # Skip paragraphs that are just lists (like cream cheese flavors)
            if not re.search(r'[\d.]+\s*$|[\d.]+\s+[\d.]+', text):
                # Check if it has prices
                if not re.search(r'\$?[\d.]+', text):
                    continue
            
            # Special handling for Bagels section - combine Single, Half Dozen, Baker's Dozen
            if current_section and 'Bagels:' in current_section:
                strongs = elem.find_all('strong')
                ems = elem.find_all('em')
                if strongs and ems:
                    bagel_names = [s.get_text(strip=True) for s in strongs]
                    if 'Single' in bagel_names and 'Half Dozen' in bagel_names and any('Baker' in n for n in bagel_names):
                        # Extract prices by processing children in order
                        prices = []
                        children = list(elem.children)
                        
                        i = 0
                        while i < len(children):
                            child = children[i]
                            # Look for em tags
                            if hasattr(child, 'name') and child.name == 'em':
                                em_text = child.get_text(strip=True)
                                # Check if previous sibling is a NavigableString with a number
                                if i > 0:
                                    prev = children[i-1]
                                    if isinstance(prev, str) or (hasattr(prev, 'string') and prev.string):
                                        prev_text = str(prev).strip()
                                        # Check if it's a number
                                        if prev_text.isdigit() and em_text.startswith('.'):
                                            # Split price - combine
                                            whole = prev_text
                                            decimal = em_text.lstrip('.')
                                            prices.append(f"{whole}.{decimal}")
                                        else:
                                            prices.extend(re.findall(r'[\d.]+', em_text))
                                    else:
                                        prices.extend(re.findall(r'[\d.]+', em_text))
                                else:
                                    prices.extend(re.findall(r'[\d.]+', em_text))
                            i += 1
                        
                        if len(prices) >= 3:
                            item = {
                                'name': 'Bagels',
                                'description': 'Plain, Sesame, Poppy, Everything, Cinnamon Raisin, Honey Wheat, Onion, Garlic, Rosemary Olive, Jalapeno, Pumpernickel, Oat Bran, Salt, Cheddar-Parm',
                                'price': f"Single ${prices[0]} | Half Dozen ${prices[1]} | Baker's Dozen ${prices[2]}",
                                'section': current_section
                            }
                            items.append(item)
                            continue
            
            # Special handling for Soup section - combine Cup and Bowl
            if current_section and 'Soup' in current_section:
                text_lower = text.lower()
                if 'cup' in text_lower and 'bowl' in text_lower:
                    prices = re.findall(r'[\d.]+', text)
                    if len(prices) >= 2:
                        item = {
                            'name': 'Soup',
                            'description': 'Soup served with house-made bagel chips or oyster crackers. Soup selections vary daily.',
                            'price': f"Cup ${prices[0]} | Bowl ${prices[1]}",
                            'section': current_section
                        }
                        items.append(item)
                        continue
            
            # Process regular menu items
            strongs = elem.find_all('strong')
            ems = elem.find_all('em')
            
            if not strongs:
                # Check for prices in plain text (not in em tags)
                price_match = re.search(r'([A-Za-z\s]+?)\s+([\d.]+)', text)
                if price_match and current_section:
                    name = price_match.group(1).strip()
                    price = price_match.group(2)
                    # Get description after price
                    desc_start = price_match.end()
                    desc = text[desc_start:].strip()
                    if len(name) > 2 and len(name) < 100:
                        item = {
                            'name': name,
                            'description': desc if desc and len(desc) > 5 else None,
                            'price': f"${price}",
                            'section': current_section
                        }
                        items.append(item)
                continue
            
            # Process each strong element
            for strong_index, strong_elem in enumerate(strongs):
                name = strong_elem.get_text(strip=True)
                
                # Skip certain items that are modifiers or not menu items
                if any(skip in name.lower() for skip in ['cream cheese flavors', 'dressings', 'variety of', 'soup selections']):
                    continue
                
                # Skip "With" items that are modifiers - they're separate items with their own prices
                # Don't skip them, just process them normally
                
                # Find associated price(s)
                full_text = elem.get_text()
                name_pos = full_text.find(name)
                
                # Find all em elements after this name
                # Use children order to find the correct em tag
                candidate_ems = []
                children = list(elem.children)
                
                # Find the position of this strong in children
                try:
                    strong_child_index = children.index(strong_elem)
                    # Look for em tags after this strong in the children
                    for i in range(strong_child_index + 1, len(children)):
                        child = children[i]
                        if hasattr(child, 'name') and child.name == 'em':
                            em_text = child.get_text(strip=True)
                            # Check if it's before the next strong
                            next_strong = strongs[strong_index + 1] if strong_index + 1 < len(strongs) else None
                            if next_strong:
                                try:
                                    next_strong_index = children.index(next_strong)
                                    if i < next_strong_index:
                                        em_pos = full_text.find(em_text, name_pos)
                                        if em_pos > name_pos:
                                            candidate_ems.append((child, em_text, em_pos))
                                except ValueError:
                                    pass
                            else:
                                em_pos = full_text.find(em_text, name_pos)
                                if em_pos > name_pos:
                                    candidate_ems.append((child, em_text, em_pos))
                            # Only take the first em tag(s) associated with this strong
                            break
                except ValueError:
                    # Fallback to old method
                    for em in ems:
                        em_text = em.get_text(strip=True)
                        em_pos = full_text.find(em_text, name_pos)
                        if em_pos > name_pos:
                            next_strong = strongs[strong_index + 1] if strong_index + 1 < len(strongs) else None
                            if next_strong:
                                next_name = next_strong.get_text(strip=True)
                                next_pos = full_text.find(next_name, name_pos)
                                if next_pos > 0 and em_pos < next_pos:
                                    candidate_ems.append((em, em_text, em_pos))
                            else:
                                candidate_ems.append((em, em_text, em_pos))
                
                # Extract all prices from em elements
                all_prices = []
                for em, em_text, em_pos in candidate_ems:
                    prices = re.findall(r'[\d.]+', em_text)
                    all_prices.extend(prices)
                
                # Handle split prices where whole number is in plain text before em
                # Pattern: "Name</strong>2<em>.50</em>" or "Name</strong>6<em>.75</em>"
                split_price_whole = None
                if candidate_ems:
                    first_em = candidate_ems[0][0]
                    first_em_text = candidate_ems[0][1]
                    # Check if first em text starts with "."
                    if first_em_text.startswith('.'):
                        # Check if there's a NavigableString (plain text) right before this em
                        children = list(elem.children)
                        try:
                            em_index = children.index(first_em)
                            if em_index > 0:
                                prev_child = children[em_index - 1]
                                # Check if previous is a NavigableString with a number
                                prev_text = None
                                if isinstance(prev_child, str):
                                    prev_text = prev_child.strip()
                                elif hasattr(prev_child, 'string') and prev_child.string:
                                    prev_text = str(prev_child.string).strip()
                                
                                if prev_text and prev_text.isdigit():
                                    # Split price - combine
                                    split_price_whole = prev_text
                                    decimal = first_em_text.lstrip('.')
                                    # Replace in all_prices
                                    if decimal in all_prices:
                                        idx = all_prices.index(decimal)
                                        all_prices[idx] = f"{split_price_whole}.{decimal}"
                                    elif all_prices and all_prices[0].startswith('.'):
                                        all_prices[0] = f"{split_price_whole}{all_prices[0]}"
                        except (ValueError, AttributeError):
                            pass
                        
                        # Also check text before em for the number (fallback)
                        if not split_price_whole:
                            first_em_pos = candidate_ems[0][2]
                            text_before_em = full_text[name_pos + len(name):first_em_pos]
                            if text_before_em:
                                number_match = re.search(r'(\d+)', text_before_em)
                                if number_match:
                                    split_price_whole = number_match.group(1)
                                    decimal = first_em_text.lstrip('.')
                                    if decimal in all_prices:
                                        idx = all_prices.index(decimal)
                                        all_prices[idx] = f"{split_price_whole}.{decimal}"
                                    elif all_prices and all_prices[0].startswith('.'):
                                        all_prices[0] = f"{split_price_whole}{all_prices[0]}"
                
                # Also check for price in plain text after name (if no em found)
                # BUT: Don't add if it's part of a split price we already combined
                price_in_plain_text = None
                if not candidate_ems:
                    after_name = full_text[name_pos + len(name):]
                    price_match = re.search(r'([\d.]+)', after_name[:50])
                    if price_match:
                        price_text = price_match.group(1)
                        # Don't add if it's the whole number part of a split price
                        if price_text != split_price_whole:
                            all_prices.append(price_text)
                            price_in_plain_text = price_text
                
                if not all_prices:
                    continue
                
                # If we have multiple prices but they're actually a split price, combine them
                # This handles cases like "Biscotti" where "2" and ".50" are separate
                if len(all_prices) == 2 and not split_price_whole:
                    # Check if second starts with "." and first is a small number (1-2 digits)
                    if all_prices[1].startswith('.') and all_prices[0].isdigit() and len(all_prices[0]) <= 2:
                        # Also check if there's only one em tag with price (indicating it's a split price, not multi-size)
                        # Count em tags that actually have prices (not just whitespace)
                        price_ems = [em for em, em_text, _ in candidate_ems if re.search(r'[\d.]+', em_text)]
                        if len(price_ems) == 1:
                            # They're likely split - combine
                            all_prices = [f"{all_prices[0]}{all_prices[1]}"]
                
                if not all_prices:
                    continue
                
                # Get description - it comes AFTER the price, not before
                desc_text = None
                if candidate_ems:
                    # Description is after the last em tag
                    last_em_pos = candidate_ems[-1][2]
                    last_em_text = candidate_ems[-1][1]
                    # Find the end position of the last em tag
                    last_em_end_pos = last_em_pos + len(last_em_text)
                    
                    # Find the next strong tag to know where to stop
                    next_strong = strongs[strong_index + 1] if strong_index + 1 < len(strongs) else None
                    if next_strong:
                        next_name = next_strong.get_text(strip=True)
                        next_pos = full_text.find(next_name, last_em_end_pos)
                        if next_pos > 0:
                            desc_text = full_text[last_em_end_pos:next_pos].strip()
                    else:
                        # No next strong, take everything after the price
                        desc_text = full_text[last_em_end_pos:].strip()
                    
                    # Clean description - remove price numbers and dollar signs
                    if desc_text:
                        # Remove all price patterns from description
                        # First remove the prices we found
                        for price in all_prices:
                            desc_text = re.sub(r'\b' + re.escape(price) + r'\b', '', desc_text)
                        # Also remove any remaining price patterns (like "3.10" that might be part of multi-size)
                        desc_text = re.sub(r'\b\d+\.\d+\b', '', desc_text)
                        desc_text = re.sub(r'\$\s*', '', desc_text)
                        desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                        
                        # Skip if description is just a number or very short
                        if desc_text and (desc_text.isdigit() or len(desc_text) < 3):
                            desc_text = None
                else:
                    # No em tags - price is in plain text, description comes after the price
                    if price_in_plain_text:
                        # Find the price position
                        price_pos = full_text.find(price_in_plain_text, name_pos + len(name))
                        if price_pos > 0:
                            price_end_pos = price_pos + len(price_in_plain_text)
                            # Get description after the price
                            next_strong = strongs[strong_index + 1] if strong_index + 1 < len(strongs) else None
                            if next_strong:
                                next_name = next_strong.get_text(strip=True)
                                desc_end = full_text.find(next_name, price_end_pos)
                                if desc_end > 0:
                                    desc_text = full_text[price_end_pos:desc_end].strip()
                            else:
                                desc_text = full_text[price_end_pos:].strip()
                            
                            # Clean description - remove prices
                            if desc_text:
                                for price in all_prices:
                                    desc_text = re.sub(r'\b' + re.escape(price) + r'\b', '', desc_text)
                                # Also remove any remaining price patterns
                                desc_text = re.sub(r'\b\d+\.\d+\b', '', desc_text)
                                desc_text = re.sub(r'\$\s*', '', desc_text)
                                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                                if desc_text and (desc_text.isdigit() or len(desc_text) < 3):
                                    desc_text = None
                    else:
                        # No price found, try to get description after name
                        desc_start = name_pos + len(name)
                        next_strong = strongs[strong_index + 1] if strong_index + 1 < len(strongs) else None
                        if next_strong:
                            next_name = next_strong.get_text(strip=True)
                            desc_end = full_text.find(next_name, desc_start)
                            if desc_end > 0:
                                desc_text = full_text[desc_start:desc_end].strip()
                                # Remove prices
                                for price in all_prices:
                                    desc_text = re.sub(r'\b' + re.escape(price) + r'\b', '', desc_text)
                                # Also remove any remaining price patterns
                                desc_text = re.sub(r'\b\d+\.\d+\b', '', desc_text)
                                desc_text = re.sub(r'\$\s*', '', desc_text)
                                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                                if desc_text and (desc_text.isdigit() or len(desc_text) < 3):
                                    desc_text = None
                
                # Format price
                price = format_price(all_prices)
                
                item = {
                    'name': name,
                    'description': desc_text if desc_text and len(desc_text) > 2 else None,
                    'price': price,
                    'section': current_section or 'Menu'
                }
                items.append(item)
    
    return items


def scrape_uncommongrounds() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    for location_key, menu_info in MENU_URLS.items():
        location_name = menu_info['name']
        print(f"\n[{location_key.upper()}] Scraping {location_name} menu...")
        
        html = fetch_menu_html(location_key)
        if not html:
            print(f"  [ERROR] Failed to fetch {location_name} menu")
            continue
        
        print(f"  [OK] Received {len(html)} characters")
        
        items = extract_menu_items(html, location_name)
        print(f"  [OK] Extracted {len(items)} items")
        
        # Format items
        for item in items:
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
            item['menu_type'] = "Menu"
            item['menu_name'] = f"{location_name} - {item.get('section', 'Menu')}"
            item['location'] = location_name
        
        all_items.extend(items)
    
    print(f"\n[OK] Extracted {len(all_items)} items total from all locations")
    
    return all_items


if __name__ == "__main__":
    items = scrape_uncommongrounds()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "uncommongrounds_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")
