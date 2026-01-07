"""
Scraper for 550 Waterfront by Druthers (550waterfrontbydruthers.com)
Scrapes draft list (beer menu) from HTML using Playwright
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

# Check for optional dependencies
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed. Install with: pip install playwright")

# Restaurant configuration
RESTAURANT_NAME = "550 Waterfront by Druthers"
RESTAURANT_URL = "https://550waterfrontbydruthers.com/"

# Menu URL
MENU_URL = "https://550waterfrontbydruthers.com/menus/"


def fetch_menu_html() -> Optional[str]:
    """Fetch menu HTML using Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available")
        return None
    
    try:
        print(f"[INFO] Fetching menu HTML from {MENU_URL} using Playwright...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(MENU_URL, wait_until="networkidle", timeout=60000)
            # Wait a bit for dynamic content to load
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            print(f"[INFO] Successfully fetched menu HTML ({len(html)} chars)")
            return html
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu HTML with Playwright: {e}")
        return None


def extract_draft_list_items(html: str) -> List[Dict]:
    """Extract draft list (beer) items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    section_name = "Draft List"
    
    # Look for beer items - they have links to untappd.com
    beer_links = soup.find_all('a', href=lambda x: x and 'untappd.com' in str(x))
    
    seen_names = set()
    items_by_name = {}  # Track items by cleaned name to avoid duplicates
    
    for beer_link in beer_links:
        # Navigate up to find the beer item container
        # The structure seems to be: link -> parent -> parent -> container with all info
        item_container = beer_link
        for _ in range(8):  # Go up several levels
            if not item_container:
                break
            item_container = item_container.parent
            
            # Check if this container has both name and price
            has_name = item_container.find(['h2', 'h3', 'h4']) or beer_link.get_text(strip=True)
            has_price = item_container.find(string=re.compile(r'\d+\.\d+'))
            
            if has_name and has_price:
                break
        
        if not item_container:
            continue
        
        # Extract beer name from heading (h4) - this is more reliable
        name_elem = item_container.find(['h4', 'h3', 'h2'])
        if name_elem:
            # Get text from the heading, but exclude nested links
            name = name_elem.get_text(strip=True)
            # If heading has a link inside, prefer the link text
            heading_link = name_elem.find('a')
            if heading_link:
                name = heading_link.get_text(strip=True)
        else:
            # Fallback to link text
            name = beer_link.get_text(strip=True)
        
        # Filter out non-beer items and section headings
        name_lower = name.lower()
        if name_lower in ['untappd', 'menu powered by', 'lago by druthers', 'draft list', 
                         'lago by druthers draft & can list']:
            continue
        
        # Clean up name - remove type info that comes after " - "
        if ' - ' in name:
            parts = name.split(' - ')
            name = parts[0].strip()
            # Sometimes the type is useful, but we'll put it in description
        
        # Remove trailing type words that are concatenated without space
        # Pattern: "NameType" where Type is a beer style
        # Note: Don't remove "IPA" as it's often part of the name
        beer_styles = ['Shandy', 'Kölsch', 'Lager', 'Stout', 'Porter', 'Sour', 'Ale', 'Beer', 
                      'Spiced', 'Fruited', 'Imperial', 'Session', 'New England', 'American', 'Pastry', 
                      'Oatmeal', 'Dark', 'Export', 'Winter Warmer', 'Gose', 'Blonde', 'NEIPA',
                      'Fruit Beer', 'Export Ale', 'Other', 'Scottish Export']
        
        # Remove trailing concatenated style words
        for style in sorted(beer_styles, key=len, reverse=True):  # Longer styles first
            if name.lower().endswith(style.lower()):
                # Check if it's concatenated (no space before the style)
                before_style = name[:-len(style)]
                if before_style and not before_style[-1].isspace():
                    # It's concatenated, but check if removing it leaves a valid name
                    if len(before_style.strip()) >= 2:
                        name = before_style.rstrip()
                        break
        
        # Remove duplicate words at the end
        words = name.split()
        if len(words) > 1 and words[-1].lower() == words[-2].lower():
            name = ' '.join(words[:-1])
        
        name = name.strip()
        
        if not name or len(name) < 2:
            continue
        
        # Normalize name for duplicate detection (lowercase, remove extra spaces)
        name_normalized = re.sub(r'\s+', ' ', name.lower().strip())
        
        # Skip duplicates - check both exact and normalized
        if name in seen_names or name_normalized in seen_names:
            continue
        seen_names.add(name)
        seen_names.add(name_normalized)
        
        # Extract beer type/style - look for text like "Shandy", "IPA", etc.
        beer_type = None
        type_texts = item_container.find_all(string=re.compile(r'\b(Shandy|Kölsch|Lager|IPA|Stout|Porter|Sour|Ale|Beer|Spiced|Fruited|Imperial|Session|New England|American|Pastry|Oatmeal|Dark|Export|Winter Warmer)\b', re.I))
        if type_texts:
            # Get the first one that's not part of the name and not "Beer Name + Style"
            for t in type_texts:
                text = t.strip()
                if text and text not in name and 'beer name' not in text.lower():
                    beer_type = text
                    break
        
        # Extract ABV
        abv = None
        abv_elem = item_container.find(string=re.compile(r'\d+\.?\d*%\s*ABV', re.I))
        if abv_elem:
            abv = abv_elem.strip()
        
        # Extract description
        desc_elem = item_container.find('p')
        description = desc_elem.get_text(strip=True) if desc_elem else None
        
        # Combine type, ABV, and description
        desc_parts = []
        if beer_type and beer_type.lower() not in ['beer details', 'beer name + style']:
            desc_parts.append(beer_type)
        if abv:
            desc_parts.append(abv)
        if description:
            # Remove placeholder text like "Beer Name + Style" and "Beer Details"
            desc_clean = description.replace('Beer Name + Style.', '').replace('Beer Name + Style', '')
            desc_clean = desc_clean.replace('Beer Details.', '').replace('Beer Details', '')
            desc_clean = desc_clean.strip()
            # Clean up newlines and extra spaces
            desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
            # Remove if it's just placeholder text
            if desc_clean and desc_clean.lower() not in ['beer name + style', 'beer name + style.', 'beer details', 'beer details.']:
                # Remove if it starts with placeholder text
                desc_clean = re.sub(r'^(beer\s+name\s+\+\s+style|beer\s+details)\.?\s*', '', desc_clean, flags=re.I).strip()
                if desc_clean:
                    desc_parts.append(desc_clean)
        
        full_description = '. '.join(desc_parts) if desc_parts else None
        
        # Extract prices - find all price elements with their size labels
        prices = []
        
        # Find all elements containing prices
        all_text = item_container.get_text()
        
        # Look for patterns like "16oz Draft $9.00" or "4 Pack To Go $12.00"
        price_patterns = [
            (r'(\d+oz\s+(?:Draft|Can))\s+\$?(\d+\.\d+)', 1),  # "16oz Draft $9.00"
            (r'(\d+\s+Pack\s+(?:To\s+Go|Can\s+\d+\s+Pack)?)\s+\$?(\d+\.\d+)', 1),  # "4 Pack To Go $12.00"
            (r'(\d+ml\s+Btl)\s+\$?(\d+\.\d+)', 1),  # "750ml Btl $25.00"
            (r'(\d+oz\s+Can\s+\d+\s+Pack)\s+\$?(\d+\.\d+)', 1),  # "16oz Can 4 Pack $12.00"
        ]
        
        for pattern, size_group in price_patterns:
            matches = re.finditer(pattern, all_text, re.I)
            for match in matches:
                size_label = match.group(size_group)
                price_val = match.group(size_group + 1)
                # Clean up size label and price
                size_label = re.sub(r'\s+', ' ', size_label.strip())
                price_val = price_val.strip()
                prices.append(f"{size_label} ${price_val}")
        
        # If no structured prices found, look for any price numbers
        if not prices:
            price_numbers = re.findall(r'\$?(\d+\.\d+)', all_text)
            if price_numbers:
                # Try to find size labels near prices
                for price_num in set(price_numbers):  # Remove duplicates
                    # Look for size label before the price
                    price_index = all_text.find(price_num)
                    if price_index > 0:
                        before_text = all_text[max(0, price_index-50):price_index]
                        size_match = re.search(r'(\d+oz|\d+\s+Pack|\d+ml)', before_text, re.I)
                        if size_match:
                            size_label = size_match.group(1)
                            prices.append(f"{size_label} ${price_num}")
                        else:
                            prices.append(f"${price_num}")
        
        # Format price - remove duplicates and clean up
        if prices:
            # Remove duplicates while preserving order
            seen_prices = set()
            unique_prices = []
            for p in prices:
                if p not in seen_prices:
                    seen_prices.add(p)
                    unique_prices.append(p)
            
            if len(unique_prices) > 1:
                price = " | ".join(unique_prices)
            else:
                price = unique_prices[0]
            
            # Clean up any newlines or extra whitespace
            price = re.sub(r'\s+', ' ', price).strip()
        else:
            price = None
        
        # Only add if we have a name and price
        if name and price:
            # Store in dict to handle duplicates (keep the one with better price info)
            if name_normalized not in items_by_name or len(price) > len(items_by_name[name_normalized]['price']):
                items_by_name[name_normalized] = {
                    'name': name,
                    'description': full_description,
                    'price': price,
                    'section': section_name,
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                }
    
    # Convert dict to list
    all_items = list(items_by_name.values())
    
    return all_items


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME}")
    all_items = []
    
    # Fetch menu HTML using Playwright
    html = fetch_menu_html()
    if not html:
        print("[ERROR] Failed to fetch menu HTML")
        return []
    
    # Extract draft list items
    print("[INFO] Extracting draft list items...")
    draft_items = extract_draft_list_items(html)
    all_items.extend(draft_items)
    print(f"[INFO] Extracted {len(draft_items)} items from draft list")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "550waterfrontbydruthers_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

