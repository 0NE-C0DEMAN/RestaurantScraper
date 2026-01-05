"""
Scraper for SPoT Coffee (spotcoffee.com)
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os


def fetch_menu_html(url: str, headers: dict, cookies: dict) -> str:
    """Download menu HTML."""
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    return response.text


def parse_menu_items(html_content: str) -> List[Dict]:
    """Parse menu items from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find the main content section
    content_sections = soup.find_all('section', class_='Content')
    if not content_sections:
        return items
    
    # Use the last Content section (the one with the menu)
    content_section = content_sections[-1] if len(content_sections) > 1 else content_sections[0]
    
    current_section = "Menu"
    addons_info = []
    coffee_tea_addons = []  # Store add-ons separately for coffee/tea
    breakfast_addons = []  # Store add-ons separately for breakfast
    coffee_tea_sections = ['COFFEE & TEA', 'COFFEE & TEA – REGULAR/LARGE', 'COFFEE & TEA - REGULAR/LARGE']
    breakfast_sections = ['ALL DAY BREAKFAST', 'THREE-EGG OMELETS']
    
    # Process all paragraphs in the content
    paragraphs = content_section.find_all('p')
    
    for p in paragraphs:
        p_text = p.get_text(strip=True)
        if not p_text:
            continue
        
        # Check if this is a section header (has strong tag)
        strong = p.find('strong')
        if strong:
            strong_text = strong.get_text(strip=True)
            # Check if it's a section header
            if strong_text and len(strong_text) > 3:
                # Extract section name (remove REGULAR/LARGE or similar suffixes)
                section_name = re.sub(r'\s*[–-]\s*REGULAR/LARGE.*$', '', strong_text, flags=re.IGNORECASE)
                section_name = section_name.strip()
                if section_name and len(section_name) > 2:
                    current_section = section_name
                    # Clear addons when leaving coffee/tea section
                    if current_section not in coffee_tea_sections:
                        addons_info = []
                    continue
        
        # Check for add-ons information
        if 'ADD-ON' in p_text.upper() or 'ADD ON' in p_text.upper():
            # Clean up add-ons text
            addon_text = p_text.replace('&#8211;', '-').replace('&amp;', '&')
            addon_text = re.sub(r'\s+', ' ', addon_text)  # Fix spacing issues
            addon_text = addon_text.replace('atno charge', 'at no charge')
            
            # Determine which section these add-ons belong to based on context
            # Coffee/tea add-ons mention "flavor shot" and "milk"
            if 'flavor shot' in addon_text.lower() or 'milk' in addon_text.lower():
                coffee_tea_addons.append(addon_text)
            # Breakfast add-ons mention ingredients like "lettuce, tomato" etc.
            elif 'lettuce' in addon_text.lower() or 'tomato' in addon_text.lower() or 'chicken' in addon_text.lower():
                breakfast_addons.append(addon_text)
            else:
                # Default to current section
                if current_section in coffee_tea_sections:
                    coffee_tea_addons.append(addon_text)
                elif current_section in breakfast_sections:
                    breakfast_addons.append(addon_text)
            
            addons_info = [addon_text]  # Keep for current section
            continue
        
        # Skip if it's just a note or disclaimer
        if 'Note:' in p_text or 'Pricing and menu items may vary' in p_text or 'ALLERGY ALERT' in p_text:
            continue
        
        # Skip if it's just "Served with" or similar serving info (standalone)
        if p_text.startswith('Served with') and '$' not in p_text:
            continue
        
        # Extract item name and price
        # Pattern: "ITEM NAME $X.XX/$Y.YY" or "ITEM NAME $X.XX"
        price_pattern = r'\$([\d.]+)(?:/\$([\d.]+))?'
        
        # Get all spans in the paragraph to process them in order
        spans = p.find_all('span')
        
        # First, check if this paragraph has "With" patterns (multiple variations)
        # Use a pattern that handles both with and without comma
        with_pattern = r'With\s+(.+?)\s*[,]?\s*\$([\d.]+)'
        with_matches = list(re.finditer(with_pattern, p_text, re.IGNORECASE))
        
        # If we find "With" patterns, handle them separately
        base_item_name = None
        base_price = None
        base_description = None
        
        if with_matches:
            # Sort matches by position
            with_matches.sort(key=lambda x: x.start())
            first_with_match = with_matches[0]
            
            # Get text before first "With"
            before_with = p_text[:first_with_match.start()].strip()
            
            # Look for base item name in first span (usually the item title)
            if spans:
                first_span_text = spans[0].get_text(strip=True)
                if first_span_text and not re.search(price_pattern, first_span_text) and 'With' not in first_span_text:
                    base_item_name = first_span_text
                
                # Look for price and description in subsequent spans
                for i, span in enumerate(spans[1:], 1):
                    span_text = span.get_text(strip=True)
                    if 'With' in span_text:
                        break
                    
                    # Check if this span has a price
                    span_price_match = re.search(price_pattern, span_text)
                    if span_price_match:
                        # This is the base price
                        price1 = span_price_match.group(1)
                        price2 = span_price_match.group(2) if span_price_match.group(2) else None
                        if price2:
                            base_price = f"Regular: ${price1} / Large: ${price2}"
                        else:
                            base_price = f"${price1}"
                        
                        # Get description part after price
                        after_price = span_text[span_price_match.end():].strip()
                        if after_price:
                            base_description = after_price
                    elif span_text and not re.search(price_pattern, span_text):
                        # This is description
                        if base_description:
                            base_description += f"; {span_text}"
                        else:
                            base_description = span_text
            
            # Process "With" variations
            for with_match in with_matches:
                variation = with_match.group(1).strip()
                price = f"${with_match.group(2)}"
                
                if base_item_name:
                    item_name = f"{base_item_name} (with {variation})"
                else:
                    # Try to find base item from first span
                    if spans:
                        first_span_text = spans[0].get_text(strip=True)
                        if first_span_text and 'With' not in first_span_text:
                            base_item_name = first_span_text
                            item_name = f"{base_item_name} (with {variation})"
                        else:
                            continue
                    else:
                        continue
                
                items.append({
                    "name": item_name,
                    "description": base_description,
                    "price": price,
                    "section": current_section,
                    "restaurant_name": "SPoT Coffee",
                    "restaurant_url": "https://www.spotcoffee.com/",
                    "menu_type": "Menu",
                    "menu_name": "Our Menu"
                })
            
            # Also handle base item if it exists
            if base_item_name and base_price:
                description = base_description
                # Include add-ons info only for coffee/tea sections
                if current_section in coffee_tea_sections and addons_info:
                    addon_text = '; '.join(addons_info).replace('atno charge', 'at no charge')
                    if description:
                        description = f"{description}; Add-ons: {addon_text}"
                    else:
                        description = f"Add-ons: {addon_text}"
                
                items.append({
                    "name": base_item_name,
                    "description": description,
                    "price": base_price,
                    "section": current_section,
                    "restaurant_name": "SPoT Coffee",
                    "restaurant_url": "https://www.spotcoffee.com/",
                    "menu_type": "Menu",
                    "menu_name": "Our Menu"
                })
                continue
        
        # Regular item processing (no "With" patterns)
        price_match = re.search(price_pattern, p_text)
        if not price_match:
            continue
        
        # Extract the item name (everything before the price)
        item_text = p_text[:price_match.start()].strip()
        
        # Clean up item name - remove extra whitespace and HTML entities
        item_name = re.sub(r'\s+', ' ', item_text).strip()
        item_name = item_name.replace('&#8211;', '-').replace('&amp;', '&')
        
        if not item_name or len(item_name) < 2:
            continue
        
        # Get prices
        price1 = price_match.group(1)
        price2 = price_match.group(2) if price_match.group(2) else None
        
        # Format price string
        if price2:
            price_str = f"Regular: ${price1} / Large: ${price2}"
        else:
            price_str = f"${price1}"
        
        # Get description - check spans after the price
        description_parts = []
        found_price = False
        
        for span in spans:
            span_text = span.get_text(strip=True)
            if not span_text:
                continue
            
            # Check if this span contains the price
            if re.search(price_pattern, span_text):
                found_price = True
                # Get text after price in this span
                span_price_match = re.search(price_pattern, span_text)
                if span_price_match:
                    after_price_in_span = span_text[span_price_match.end():].strip()
                    if after_price_in_span and 'With' not in after_price_in_span:
                        description_parts.append(after_price_in_span)
            elif found_price and 'With' not in span_text:
                # This span comes after the price span - it's a description
                description_parts.append(span_text)
        
        # Also check for text after <br> tags
        br_tags = p.find_all('br')
        for br in br_tags:
            # Get next sibling
            next_elem = br.next_sibling
            if next_elem:
                if isinstance(next_elem, str):
                    desc_text = next_elem.strip()
                    if desc_text and not re.search(price_pattern, desc_text) and 'With' not in desc_text:
                        if desc_text not in description_parts:
                            description_parts.append(desc_text)
                elif hasattr(next_elem, 'get_text'):
                    desc_text = next_elem.get_text(strip=True)
                    if desc_text and not re.search(price_pattern, desc_text) and 'With' not in desc_text:
                        if desc_text not in description_parts:
                            description_parts.append(desc_text)
        
        description = '; '.join(description_parts) if description_parts else None
        
        # Include add-ons info only for coffee/tea sections
        if current_section in coffee_tea_sections and addons_info:
            addon_text = '; '.join(addons_info).replace('atno charge', 'at no charge')
            if description:
                description = f"{description}; Add-ons: {addon_text}"
            else:
                description = f"Add-ons: {addon_text}"
        
        items.append({
            "name": item_name,
            "description": description,
            "price": price_str,
            "section": current_section,
            "restaurant_name": "SPoT Coffee",
            "restaurant_url": "https://www.spotcoffee.com/",
            "menu_type": "Menu",
            "menu_name": "Our Menu"
        })
    
    # Apply add-ons retroactively to relevant items
    if coffee_tea_addons:
        addon_text = '; '.join(coffee_tea_addons).replace('atno charge', 'at no charge')
        for item in items:
            if item['section'] in coffee_tea_sections:
                if item['description']:
                    if 'Add-ons:' not in item['description']:
                        item['description'] = f"{item['description']}; Add-ons: {addon_text}"
                else:
                    item['description'] = f"Add-ons: {addon_text}"
    
    if breakfast_addons:
        addon_text = '; '.join(breakfast_addons).replace('atno charge', 'at no charge')
        for item in items:
            if item['section'] in breakfast_sections:
                if item['description']:
                    if 'Add-ons:' not in item['description']:
                        item['description'] = f"{item['description']}; Add-ons: {addon_text}"
                else:
                    item['description'] = f"Add-ons: {addon_text}"
    
    return items


def parse_catering_menu_items(html_content: str) -> List[Dict]:
    """Parse catering menu items from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all menu tab content sections
    tab_contents = soup.find_all('div', class_='MenuTabs-content')
    
    for tab_content in tab_contents:
        # Get section name from data-content-id
        section_id = tab_content.get('data-content-id', '')
        section_name = section_id.replace('-', ' ').title() if section_id else "Catering"
        
        # Find all products in this tab
        products = tab_content.find_all('li', class_='MenuTabs-product')
        
        for product in products:
            # Get item name from h5
            name_elem = product.find('h5')
            if not name_elem:
                continue
            
            item_name = name_elem.get_text(strip=True)
            if not item_name:
                continue
            
            # Get description and prices from MenuTabs-productDesc
            desc_elem = product.find('span', class_='MenuTabs-productDesc')
            if not desc_elem:
                continue
            
            # Get all text from description
            desc_text = desc_elem.get_text(separator=' ', strip=True)
            
            # Extract prices - look for patterns like "$XX.XX" or "Serves X-Y – $XX.XX"
            price_pattern = r'\$([\d.]+)'
            prices = re.findall(price_pattern, desc_text)
            
            # Also look for "Small/Large" patterns
            small_large_pattern = r'(?:Small|Large)\s*(?:\([^)]+\))?\s*\$([\d.]+)'
            small_large_prices = re.findall(small_large_pattern, desc_text, re.IGNORECASE)
            
            # Format price string
            price_str = None
            if small_large_prices:
                # Has Small/Large pricing
                if len(small_large_prices) >= 2:
                    price_str = f"Small: ${small_large_prices[0]} / Large: ${small_large_prices[1]}"
                elif len(small_large_prices) == 1:
                    price_str = f"${small_large_prices[0]}"
            elif prices:
                # Single or multiple prices
                if len(prices) == 1:
                    price_str = f"${prices[0]}"
                elif len(prices) == 2:
                    price_str = f"${prices[0]} / ${prices[1]}"
                else:
                    price_str = " / ".join([f"${p}" for p in prices])
            
            # Clean up description - preserve "Serves" info but remove redundant price mentions
            description = desc_text
            # Remove standalone price patterns (but keep "Serves X-Y – $XX.XX" format)
            # First, replace "Serves X-Y – $XX.XX" with just "Serves X-Y"
            description = re.sub(r'Serves\s+(\d+[-\d\s]*)\s*[–-]\s*\$[\d.]+', r'Serves \1', description, flags=re.IGNORECASE)
            # Remove standalone prices
            description = re.sub(r'\s+\$[\d.]+', '', description)
            # Remove "Small (serves X) $XX.XX" and "Large (serves Y) $YY.YY" patterns, but keep the serves info
            description = re.sub(r'(?:Small|Large)\s*\(serves\s+([^)]+)\)\s*\$[\d.]+', r'', description, flags=re.IGNORECASE)
            # Clean up extra whitespace
            description = re.sub(r'\s+', ' ', description).strip()
            description = description.strip('–-').strip()
            
            if not description or len(description) < 3:
                description = None
            
            items.append({
                "name": item_name,
                "description": description,
                "price": price_str,
                "section": section_name,
                "restaurant_name": "SPoT Coffee",
                "restaurant_url": "https://www.spotcoffee.com/",
                "menu_type": "Catering",
                "menu_name": "Catering Menu"
            })
    
    return items


def scrape_spotcoffee() -> List[Dict]:
    """Main scraping function for SPoT Coffee."""
    print("Scraping SPoT Coffee menu...")
    
    all_items = []
    
    # Scrape regular menu
    url = "https://www.spotcoffee.com/home/our-menu/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://www.spotcoffee.com/our-coffee/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    cookies = {
        "sbjs_migrations": "1418474375998%3D1",
        "sbjs_current_add": "fd%3D2026-01-05%2015%3A37%3A35%7C%7C%7Cep%3Dhttps%3A%2F%2Fwww.spotcoffee.com%2F%7C%7C%7Crf%3D%28none%29",
        "sbjs_first_add": "fd%3D2026-01-05%2015%3A37%3A35%7C%7C%7Cep%3Dhttps%3A%2F%2Fwww.spotcoffee.com%2F%7C%7C%7Crf%3D%28none%29",
        "sbjs_current": "typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29",
        "sbjs_first": "typ%3Dtypein%7C%7C%7Csrc%3D%28direct%29%7C%7C%7Cmdm%3D%28none%29%7C%7C%7Ccmp%3D%28none%29%7C%7C%7Ccnt%3D%28none%29%7C%7C%7Ctrm%3D%28none%29%7C%7C%7Cid%3D%28none%29%7C%7C%7Cplt%3D%28none%29%7C%7C%7Cfmt%3D%28none%29%7C%7C%7Ctct%3D%28none%29",
        "sbjs_udata": "vst%3D1%7C%7C%7Cuip%3D%28none%29%7C%7C%7Cuag%3DMozilla%2F5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F143.0.0.0%20Safari%2F537.36",
        "tk_or": "",
        "tk_r3d": "",
        "tk_lr": "",
        "_ga": "GA1.1.1171684169.1767629261",
        "_wpfuuid": "602808e4-09f7-40ac-80a9-f2000ecd8cf5",
        "tk_ai": "gATlyw0Rajox/aizTULFx2Dp",
        "sbjs_session": "pgs%3D4%7C%7C%7Ccpg%3Dhttps%3A%2F%2Fwww.spotcoffee.com%2Fhome%2Four-menu%2F",
        "_wpfuj": '{"1767629256":"https%3A%2F%2Fwww.spotcoffee.com%2F%7C%23%7CHome%20-%20SPoT%20Coffee%7C%23%7C48","1767630252":"https%3A%2F%2Fwww.spotcoffee.com%2Fhome%2Four-menu%2F%7C%23%7COur%20Menu%20-%20SPoT%20Coffee%7C%23%7C9646","1767630345":"https%3A%2F%2Fwww.spotcoffee.com%2Four-coffee%2F%7C%23%7COur%20Coffee%20-%20SPoT%20Coffee%7C%23%7C7","1767630445":"https%3A%2F%2Fwww.spotcoffee.com%2Fhome%2Four-menu%2F%7C%23%7COur%20Menu%20-%20SPoT%20Coffee%7C%23%7C9646"}',
        "__rkp": "fpc=29YWGDw7daq125kvepLTG.1767630445091",
        "_ga_ZR1Q0FT3SR": "GS2.1.s1767629260$o1$g1$t1767630451$j47$l0$h0"
    }
    
    print("  Downloading regular menu...")
    html = fetch_menu_html(url, headers, cookies)
    items = parse_menu_items(html)
    print(f"  Found {len(items)} regular menu items")
    all_items.extend(items)
    
    # Scrape catering menu
    catering_url = "https://www.spotcoffee.com/catering/"
    catering_headers = {
        "Referer": "https://www.spotcoffee.com/shop/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    print("  Downloading catering menu...")
    catering_html = fetch_menu_html(catering_url, catering_headers, {})
    catering_items = parse_catering_menu_items(catering_html)
    print(f"  Found {len(catering_items)} catering menu items")
    all_items.extend(catering_items)
    
    print(f"Total: {len(all_items)} items scraped from SPoT Coffee")
    
    return all_items


if __name__ == "__main__":
    items = scrape_spotcoffee()
    
    # Save to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "spotcoffee_com.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(items)} items to {output_file}")

