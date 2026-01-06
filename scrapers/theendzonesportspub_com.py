"""
Scraper for The End Zone Sports Pub (theendzonesportspub.com)
Scrapes menu from the menu page
"""

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pathlib import Path


def fetch_menu_html(url: str) -> Optional[str]:
    """Download menu HTML from the menu page"""
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "cookie": "server-session-bind=637f0bae-3746-492a-8274-ddf4af1a61e3; XSRF-TOKEN=1767686175^|9IRsx_ZRzp_z; hs=-916485631; svSession=0c64d219dfbebccffa75482956fc90953305208460b0cb470481c17d6c0f4fdcd84b2a3433489b7538f70ce53556c7501e60994d53964e647acf431e4f798bcd192241d67a907fd0ffd787b37f3c5dfd6fdc72dceedb8747e29f0324f85e27f67a4e010975bee93cc8318732573fffc4080b0f929744c37c1353dfef5fd0be5d86a19dd2c772e07a79785760afe92e29; bSession=ac7fb5a8-1257-4a8f-962a-43ec30cf0547^|1; _ga=GA1.1.264975997.1767686186; _ga_BVTC5WVTKV=GS2.1.s1767686185^$o1^$g1^$t1767686518^$j30^$l0^$h0^",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://www.theendzonesportspub.com/",
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
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return None


def extract_price_from_text(text: str) -> str:
    """Extract price(s) from text, handling multi-size and multi-price formats"""
    if not text:
        return ""
    
    # Pattern 1: Multi-size with labels (e.g., "Small (Feeds 2-3) $16.99 Large (Feeds 4-6) $21.99")
    multi_size_pattern = r'(\w+(?:\s+\([^)]+\))?)\s+\$(\d+(?:\.\d+)?)'
    matches = list(re.finditer(multi_size_pattern, text))
    
    if len(matches) > 1:
        # Multiple sizes found
        price_parts = []
        for match in matches:
            size_label = match.group(1).strip()
            price = match.group(2)
            price_parts.append(f"{size_label} ${price}")
        return " | ".join(price_parts)
    
    # Pattern 2: Multi-price without explicit size labels (e.g., "12 Cut $22   8 Cut $19   Personal $14")
    # Try pattern that allows numbers before "Cut" with optional spacing
    multi_price_pattern = r'(\d+\s*Cut|Personal)\s+\$(\d+(?:\.\d+)?)'
    matches = list(re.finditer(multi_price_pattern, text))
    
    if len(matches) > 1:
        price_parts = []
        for match in matches:
            size_label = match.group(1).strip()
            # Normalize spacing: "12 Cut" or "12Cut" -> "12 Cut"
            size_label = re.sub(r'(\d+)\s*(Cut)', r'\1 \2', size_label, flags=re.IGNORECASE)
            price = match.group(2)
            price_parts.append(f"{size_label} ${price}")
        return " | ".join(price_parts)
    
    # Also try pattern that looks for numbers near "Cut" (e.g., "12 Cut $22" or "12Cut $22")
    multi_price_pattern_alt = r'(\d+)\s*Cut\s+\$(\d+(?:\.\d+)?)'
    matches_alt = list(re.finditer(multi_price_pattern_alt, text))
    if len(matches_alt) > 1:
        price_parts = []
        for match in matches_alt:
            number = match.group(1)
            price = match.group(2)
            price_parts.append(f"{number} Cut ${price}")
        # Also check for Personal
        personal_match = re.search(r'Personal\s+\$(\d+(?:\.\d+)?)', text)
        if personal_match:
            price_parts.append(f"Personal ${personal_match.group(1)}")
        if len(price_parts) > 1:
            return " | ".join(price_parts)
    
    # Fallback: pattern without numbers (e.g., "Cut $22    Cut $19   Personal $14")
    multi_price_pattern2 = r'(Cut|Personal)\s+\$(\d+(?:\.\d+)?)'
    matches2 = list(re.finditer(multi_price_pattern2, text))
    if len(matches2) > 1:
        # Try to find the numbers before "Cut" by looking at context
        price_parts = []
        for i, match in enumerate(matches2):
            size_label = match.group(1).strip()
            price = match.group(2)
            # Try to infer size from position (12 Cut, 8 Cut, Personal)
            if size_label == "Cut":
                if i == 0:
                    size_label = "12 Cut"
                elif i == 1:
                    size_label = "8 Cut"
            price_parts.append(f"{size_label} ${price}")
        return " | ".join(price_parts)
    
    # Pattern 3: Single price
    single_price_match = re.search(r'\$(\d+(?:\.\d+)?)', text)
    if single_price_match:
        return f"${single_price_match.group(1)}"
    
    return ""


def extract_addons(text: str) -> List[str]:
    """Extract add-on information from text"""
    addons = []
    
    # Pattern: "Add X + $Y" or "Add X +$Y" or "X + $Y"
    addon_patterns = [
        r'Add\s+([^+]+?)\s*\+\s*\$(\d+(?:\.\d+)?)',
        r'([^+]+?)\s*\+\s*\$(\d+(?:\.\d+)?)',
    ]
    
    for pattern in addon_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            addon_name = match.group(1).strip()
            addon_price = match.group(2)
            # Skip if it looks like a size/price combo (e.g., "12 Cut + $22")
            if not re.match(r'^\d+\s+Cut$', addon_name, re.IGNORECASE):
                addons.append(f"{addon_name} +${addon_price}")
    
    return addons


def parse_menu_items(html: str) -> List[Dict]:
    """Parse menu items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all item containers
    item_containers = soup.find_all(attrs={"data-hook": "item.container"})
    
    # Track current section
    current_section = "Menu"
    
    for container in item_containers:
        # Check if there's a section header before this container
        # Look for section elements
        prev_elements = container.find_all_previous(attrs={"data-hook": re.compile(r'section', re.I)})
        if prev_elements:
            # Get the closest section element
            closest_section = prev_elements[0]
            section_text = closest_section.get_text(strip=True)
            # Clean up section name (remove item names that might be included)
            if section_text and len(section_text) < 100:
                # Check if it's actually a section name (not an item)
                if not '$' in section_text and not any(char.isdigit() for char in section_text[-10:]):
                    current_section = section_text
        
        # Find name
        name_elem = container.find(attrs={"data-hook": "item.name"})
        if not name_elem:
            continue
        
        item_name = name_elem.get_text(strip=True)
        
        # Find description
        desc_elem = container.find(attrs={"data-hook": "item.description"})
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        # Remove item name from description if it appears at the start
        if description and item_name:
            # Remove item name from beginning of description
            description = re.sub(rf'^{re.escape(item_name)}\s+', '', description, flags=re.IGNORECASE)
        
        # Find price
        price_elem = container.find(attrs={"data-hook": "item.price"})
        price_text = price_elem.get_text(strip=True) if price_elem else ""
        
        # If no price element, check description for price
        if not price_text and description:
            price_text = description
        
        # Get full container text for better price extraction
        full_text = container.get_text(separator=' ', strip=True)
        
        # Extract price(s) from full text (more reliable)
        item_price = extract_price_from_text(full_text)
        
        # If still no price, try from price_text
        if not item_price:
            item_price = extract_price_from_text(price_text)
        
        # Clean description - remove price information
        if description:
            # Remove price patterns from description (more comprehensive)
            # Remove multi-size patterns
            description = re.sub(r'Small\s+\([^)]+\)\s*\$?[\d.]+', '', description, flags=re.IGNORECASE)
            description = re.sub(r'Large\s+\([^)]+\)\s*\$?[\d.]+', '', description, flags=re.IGNORECASE)
            # Remove pizza size patterns
            description = re.sub(r'\d+\s+Cut\s+\$?[\d.]+', '', description, flags=re.IGNORECASE)
            description = re.sub(r'\d+\s+Cut\s+', '', description, flags=re.IGNORECASE)  # Remove "12 Cut " or "8 Cut "
            description = re.sub(r'Personal\s+\$?[\d.]+', '', description, flags=re.IGNORECASE)
            description = re.sub(r'Personal\s*$', '', description, flags=re.IGNORECASE)  # Remove trailing "Personal"
            # Remove standalone prices
            description = re.sub(r'\$[\d.]+', '', description)
            # Clean up extra whitespace
            description = re.sub(r'\s+', ' ', description).strip()
        
        # Extract add-ons from description (before cleaning prices)
        # Use a clean version of description (without item name) for add-on extraction
        clean_desc_for_addons = description
        if item_name and clean_desc_for_addons:
            clean_desc_for_addons = re.sub(rf'^{re.escape(item_name)}\s+', '', clean_desc_for_addons, flags=re.IGNORECASE)
        
        addons = extract_addons(clean_desc_for_addons)
        
        # Also check full container text for add-ons, but avoid duplicates
        full_text = container.get_text(separator=' ', strip=True)
        # Remove item name from full text before extracting addons
        full_text_clean = re.sub(rf'^{re.escape(item_name)}\s+', '', full_text, flags=re.IGNORECASE)
        addons_from_full = extract_addons(full_text_clean)
        # Only add unique addons
        seen_addons = set(addons)
        for addon in addons_from_full:
            if addon not in seen_addons:
                addons.append(addon)
                seen_addons.add(addon)
        
        # Remove add-on text from description
        if addons:
            for addon in addons:
                addon_name = addon.split(' +')[0].strip()
                addon_price = addon.split(' +')[1] if ' +' in addon else ""
                # Remove add-on patterns
                description = re.sub(rf'Add\s+{re.escape(addon_name)}\s*\+\s*\$?{re.escape(addon_price)}', '', description, flags=re.IGNORECASE)
                description = re.sub(rf'{re.escape(addon_name)}\s*\+\s*\$?{re.escape(addon_price)}', '', description, flags=re.IGNORECASE)
                # Also remove incomplete add-on patterns (e.g., "Add Chicken +")
                description = re.sub(rf'Add\s+{re.escape(addon_name)}\s*\+', '', description, flags=re.IGNORECASE)
        
        # Clean up description
        description = re.sub(r'\s+', ' ', description).strip()
        description = re.sub(r'[.\s]+$', '', description)
        
        # Append add-ons to description if any
        if addons:
            # Remove duplicates (more thorough)
            unique_addons = []
            seen = set()
            for addon in addons:
                # Normalize addon for comparison (remove extra spaces)
                normalized = re.sub(r'\s+', ' ', addon.strip())
                if normalized not in seen:
                    seen.add(normalized)
                    unique_addons.append(addon)
            
            # Also check if description already contains the add-on info
            if unique_addons:
                addon_text = " / ".join(unique_addons)
                # Check if addon text is already in description
                if addon_text not in description:
                    if description:
                        description = f"{description}. Add-ons: {addon_text}"
                    else:
                        description = f"Add-ons: {addon_text}"
        
        item = {
            "name": item_name,
            "description": description if description else None,
            "price": item_price,
            "section": current_section,
            "restaurant_name": "The End Zone Sports Pub",
            "restaurant_url": "https://www.theendzonesportspub.com/",
            "menu_type": "Main Menu",
            "menu_name": "Main Menu"
        }
        
        all_items.append(item)
    
    return all_items


def scrape_endzone() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print("Scraping The End Zone Sports Pub (theendzonesportspub.com)")
    print("=" * 60)
    
    menu_url = "https://www.theendzonesportspub.com/menu"
    
    print(f"\n[1] Downloading menu HTML...")
    html = fetch_menu_html(menu_url)
    
    if not html:
        print("[ERROR] Failed to download menu HTML")
        return []
    
    print(f"[OK] Downloaded {len(html)} characters")
    
    print(f"\n[2] Parsing menu items...")
    items = parse_menu_items(html)
    
    print(f"[OK] Extracted {len(items)} items")
    
    # Save to JSON
    output_path = Path("output/theendzonesportspub_com.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_path}")
    
    return items


if __name__ == "__main__":
    scrape_endzone()

