"""
Scraper for The Local Pub and Teahouse (thelocalpubandteahouse.com)
Scrapes menu from checkle.menu iframe
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time


RESTAURANT_NAME = "The Local Pub and Teahouse"
RESTAURANT_URL = "https://www.thelocalpubandteahouse.com/"

MENU_URL = "https://thelocalpubandteahouse.com/menu/"


def fetch_menu_html() -> Optional[str]:
    """Fetch menu HTML using Playwright to handle iframe"""
    print("  Loading page with Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Navigate to the menu page
            page.goto(MENU_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for iframe to load
            print("  Waiting for iframe content to load...")
            time.sleep(5)
            
            # Get iframe content
            try:
                iframe = page.frame_locator("#menuFrame")
                # Wait a bit more for content to load
                time.sleep(3)
                iframe_html = iframe.locator("body").inner_html()
                browser.close()
                return iframe_html
            except Exception as e:
                print(f"  [WARNING] Could not access iframe: {e}")
                # Fall back to full page HTML
                full_html = page.content()
                browser.close()
                return full_html
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu: {e}")
        return None


def extract_price(text: str) -> Optional[str]:
    """Extract price from text"""
    # Look for price patterns like $10.00, $12, etc.
    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', text)
    if price_match:
        return f"${price_match.group(1)}"
    return None


def extract_all_prices(text: str) -> List[str]:
    """Extract all prices from text (for multi-price items)"""
    prices = re.findall(r'\$(\d+(?:\.\d{2})?)', text)
    return [f"${p}" for p in prices]


def extract_addons_from_text(text: str, item_name: str) -> str:
    """Extract addon information from text"""
    addons = []
    
    # Look for "Add X $Y" patterns (most reliable)
    add_pattern = r'Add\s+([A-Z][^$]+?)\s+\$(\d+(?:\.\d{2})?)'
    add_matches = re.finditer(add_pattern, text, re.IGNORECASE)
    for match in add_matches:
        addon_name = match.group(1).strip()
        addon_price = match.group(2)
        # Filter out very long addon names (likely false positives)
        if len(addon_name) < 100:
            addons.append(f"{addon_name} +${addon_price}")
    
    # Look for patterns like "/ X +$Y" (common format)
    slash_pattern = r'/\s+([A-Z][^$]+?)\s+\+?\$(\d+(?:\.\d{2})?)'
    slash_matches = re.finditer(slash_pattern, text)
    for match in slash_matches:
        addon_name = match.group(1).strip()
        addon_price = match.group(2)
        if len(addon_name) < 100 and not any(addon_name in a for a in addons):
            addons.append(f"{addon_name} +${addon_price}")
    
    if addons:
        return "Add-ons: " + " / ".join(addons)
    return ""


def process_menu_item(item_name_elem, soup: BeautifulSoup, current_section: str) -> Optional[Dict]:
    """Process a single menu item"""
    item_name = item_name_elem.get_text(strip=True)
    if not item_name:
        return None
    
    # Find the parent container (usually a div that contains name, description, price)
    parent = item_name_elem.parent
    description = None
    price = None
    addons_text = ""
    
    # Find the heading element (h4) that contains the item name
    heading = item_name_elem.find_parent(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    if not heading:
        # If no heading found, the item_name_elem might be the heading itself
        if item_name_elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            heading = item_name_elem
        else:
            heading = item_name_elem.parent
    
    # Look for description paragraph - it's usually the next sibling paragraph after the heading
    if heading:
        # Find the parent container
        container = heading.parent
        if container:
            # Find all paragraphs in the container
            all_paras = container.find_all('p', recursive=False)
            # Also check in the container's parent
            if container.parent:
                all_paras.extend(container.parent.find_all('p', recursive=False))
            
            for para in all_paras:
                para_text = para.get_text(strip=True)
                # Skip if it looks like a price, size indicator, or addon
                if (para_text and 
                    not para_text.startswith('$') and 
                    not para_text.startswith('Add') and 
                    not para_text.startswith('Sub') and
                    not para_text.startswith('For') and
                    not para_text.startswith('Make') and
                    not re.match(r'^\(\d+\)$', para_text) and  # Skip "(10)" or "(20)"
                    not para_text.startswith('Option') and
                    not para_text in ['Half', 'Full', 'Sm', 'Large', 'Gluten Free'] and
                    len(para_text) > 3 and
                    '$' not in para_text and
                    not re.search(r'\$(\d+(?:\.\d{2})?)', para_text)):  # Description shouldn't contain prices
                    description = para_text
                    break
    
    while parent and parent.name != 'body':
        # Look for price in parent or siblings
        parent_text = parent.get_text(strip=True)
        
        # Find all text nodes in parent
        all_text = parent.get_text(separator=' ', strip=True)
        
        # Remove the item name from the text
        remaining_text = all_text.replace(item_name, '', 1).strip()
        # Remove description if we found it
        if description:
            remaining_text = remaining_text.replace(description, '', 1).strip()
        
        # Extract price - look for patterns like "(10) $16.00" or "(20) $26.00"
        # ONLY apply this to items that actually have size options (like Wings)
        # Check if the item container has size/price div structures
        has_size_containers = False
        if parent:
            # Look for divs with (number) and $price patterns
            size_containers = parent.find_all('div', recursive=False)
            for container in size_containers:
                paras = container.find_all('p', recursive=False)
                if len(paras) >= 2:
                    size_text = paras[0].get_text(strip=True)
                    price_text = paras[1].get_text(strip=True)
                    if re.match(r'^\(\d+\)$', size_text) and '$' in price_text:
                        has_size_containers = True
                        break
        
        # Only apply multi-size detection if we found size containers OR if item name suggests it (like Wings)
        if has_size_containers or any(keyword in item_name.lower() for keyword in ['wings', 'wing']):
            size_price_pattern = r'\((\d+)\)\s*\$(\d+(?:\.\d{2})?)'
            size_price_matches = list(re.finditer(size_price_pattern, remaining_text))
            
            if len(size_price_matches) > 1:
                # Multiple size options found (e.g., "(10) $16.00" and "(20) $26.00")
                price_parts = []
                for match in size_price_matches:
                    size_num = match.group(1)
                    price_val = match.group(2)
                    # Use item name or a generic label
                    if 'wings' in item_name.lower():
                        size_label = f"{size_num} Wings"
                    else:
                        size_label = f"{size_num} {item_name}" if item_name else f"{size_num} pieces"
                    price_parts.append(f"{size_label} ${price_val}")
                price = " | ".join(price_parts)
                
                # Remove size indicators from description
                for match in reversed(size_price_matches):  # Reverse to preserve indices
                    remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
        if not price:
            # Standard price extraction
            prices = extract_all_prices(remaining_text)
            if prices:
                if len(prices) == 1:
                    price = prices[0]
                else:
                    # Multiple prices - need to determine if they're sizes or addons
                    # Check if there are size indicators
                    size_keywords = ['small', 'large', 'regular', 'cup', 'bowl', 'pint', 'half', 'full', 'single', 'double']
                    has_sizes = any(keyword in remaining_text.lower() for keyword in size_keywords)
                    
                    if has_sizes:
                        # Multi-size pricing
                        # Try to extract size labels
                        price_parts = []
                        for p in prices:
                            # Look for text before the price that might be a size
                            price_index = remaining_text.find(p)
                            if price_index > 0:
                                before_price = remaining_text[max(0, price_index-30):price_index].strip()
                                # Extract potential size label
                                size_match = re.search(r'(\w+(?:\s+\w+)?)\s*$', before_price)
                                if size_match:
                                    size_label = size_match.group(1)
                                    price_parts.append(f"{size_label} {p}")
                                else:
                                    price_parts.append(p)
                            else:
                                price_parts.append(p)
                        price = " | ".join(price_parts)
                    else:
                        # Likely base price + addon prices
                        price = prices[0]  # First price is usually the base
                        # Remaining prices are addons (handled separately)
            
            # Extract description (text before first price, excluding addon patterns)
            # Remove size patterns like "(10)" or "(20)" from description
            remaining_text = re.sub(r'\(\d+\)', '', remaining_text)
            
            if price:
                # Find the first price in remaining text to extract description
                price_match = re.search(r'\$(\d+(?:\.\d{2})?)', remaining_text)
                if price_match:
                    price_index = price_match.start()
                    desc_text = remaining_text[:price_index].strip()
                    # Clean up description - remove trailing size indicators
                    desc_text = re.sub(r'\s*\(\d+\)\s*$', '', desc_text)
                    desc_text = re.sub(r'\s+', ' ', desc_text)
                    if desc_text and len(desc_text) > 3:
                        description = desc_text
                else:
                    # No price found in remaining text, use all as description
                    desc_text = remaining_text.strip()
                    desc_text = re.sub(r'\s*\(\d+\)\s*', '', desc_text)
                    desc_text = re.sub(r'\s+', ' ', desc_text)
                    if desc_text and len(desc_text) > 3:
                        description = desc_text
        
        # Extract addons
        addons_text = extract_addons_from_text(remaining_text, item_name)
        
        # If we found price, we're done
        if price:
            break
        
        parent = parent.parent
    
    # If no price found, skip this item (it's likely a section header or description-only item)
    if not price:
        return None
    
    # If we still don't have a description, try to extract it from remaining text
    if not description and remaining_text:
        # Clean up remaining text
        desc_text = remaining_text.strip()
        # Remove price patterns
        desc_text = re.sub(r'\$(\d+(?:\.\d{2})?)', '', desc_text)
        # Remove size patterns
        desc_text = re.sub(r'\(\d+\)', '', desc_text)
        # Remove addon patterns
        desc_text = re.sub(r'Add\s+[^$]+\s+\$(\d+(?:\.\d{2})?)', '', desc_text, flags=re.IGNORECASE)
        desc_text = re.sub(r'\s+', ' ', desc_text).strip()
        if desc_text and len(desc_text) > 3:
            description = desc_text
    
    # Combine description and addons
    if description and addons_text:
        full_description = f"{description}. {addons_text}"
    elif addons_text:
        full_description = addons_text
    else:
        full_description = description
    
    return {
        "name": item_name,
        "description": full_description,
        "price": price,
        "section": current_section,
        "restaurant_name": RESTAURANT_NAME,
        "restaurant_url": RESTAURANT_URL,
        "menu_type": "Menu",
        "menu_name": current_section
    }


def scrape_localpub() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Fetch menu HTML
    print("\n[1] Fetching menu HTML...")
    html = fetch_menu_html()
    
    if not html:
        print("[ERROR] Failed to fetch menu HTML")
        return []
    
    print(f"[OK] Received {len(html)} characters")
    
    # Parse HTML
    print("\n[2] Parsing menu items...")
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all item names
    item_name_elems = soup.find_all(class_='item-name')
    print(f"  Found {len(item_name_elems)} items with 'item-name' class")
    
    # Determine current section by looking for headers before items
    current_section = "Menu"
    
    # Build a set of item names for comparison
    item_names_set = {item.get_text(strip=True) for item in item_name_elems}
    
    # Process each item
    for item_name_elem in item_name_elems:
        # Try to find the section this item belongs to
        # Look backwards for h3 headers (section headers are typically h3)
        prev_h3 = item_name_elem.find_previous('h3')
        if prev_h3:
            section_text = prev_h3.get_text(strip=True)
            # Check if it's a valid section name (not an item name, and reasonable length)
            if (section_text and len(section_text) < 50 and 
                section_text not in item_names_set and
                len(section_text.split()) < 5):  # Section names are usually short
                current_section = section_text
        else:
            # Fallback to h4 or other headers
            prev_elem = item_name_elem.find_previous(['h1', 'h2', 'h4', 'h5', 'h6'])
            if prev_elem:
                section_text = prev_elem.get_text(strip=True)
                if (section_text and len(section_text) < 50 and 
                    section_text not in item_names_set and
                    len(section_text.split()) < 5):
                    current_section = section_text
        
        item = process_menu_item(item_name_elem, soup, current_section)
        if item:
            all_items.append(item)
    
    print(f"\n[OK] Extracted {len(all_items)} items")
    
    return all_items


if __name__ == "__main__":
    items = scrape_localpub()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "thelocalpubandteahouse_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

