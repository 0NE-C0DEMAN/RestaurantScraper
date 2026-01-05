"""
Scraper for Pennell's Restaurant (pennellsrestaurant.com)
"""
import json
import re
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup

# Get the project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_FILE = PROJECT_ROOT / "config.json"

def load_config() -> Dict:
    """Load configuration from config.json"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def format_price(price_value) -> str:
    """Format price value to string with $ symbol"""
    if price_value is None:
        return ""
    try:
        price_float = float(price_value)
        return f"${price_float:.2f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return str(price_value) if price_value else ""

def scrape_pennellsrestaurant() -> List[Dict]:
    """Scrape menu from Pennell's Restaurant website"""
    print("=" * 60)
    print("Scraping Pennell's Restaurant (pennellsrestaurant.com)")
    print("=" * 60)
    
    url = "https://www.pennellsrestaurant.com/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    
    print(f"\n[1] Fetching menu from {url}...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        html_content = response.text
        print(f"  [OK] Downloaded {len(html_content)} characters")
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu: {e}")
        return []
    
    print(f"\n[2] Parsing menu items...")
    items = parse_menu_items(html_content)
    print(f"  [OK] Found {len(items)} items")
    
    # Save to JSON
    output_file = OUTPUT_DIR / "pennellsrestaurant_com.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved {len(items)} items to {output_file}")
    
    # Show sample items
    if items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(items[:5], 1):
            price_str = item.get('price', 'N/A')
            section = item.get('menu_name', 'Menu')
            print(f"  {i}. {item.get('name', 'N/A')} - {price_str} ({section})")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
    
    return items

def parse_menu_items(html_content: str) -> List[Dict]:
    """Parse menu items from HTML content"""
    items = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all menu sections
    menu_sections = soup.find_all('div', class_='menu-section')
    
    for section in menu_sections:
        # Get section name
        section_header = section.find('div', class_='menu-section-title')
        if not section_header:
            continue
        
        section_name = section_header.get_text(strip=True)
        
        # Find all menu items in this section
        menu_items = section.find_all('div', class_='menu-item')
        
        for item_div in menu_items:
            # Get item name
            title_elem = item_div.find('div', class_='menu-item-title')
            if not title_elem:
                continue
            
            item_name = title_elem.get_text(strip=True)
            if not item_name:
                continue
            
            # Get description
            desc_elem = item_div.find('div', class_='menu-item-description')
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            # Get price - check both top and bottom price elements
            price_str = ""
            price_top = item_div.find('span', class_='menu-item-price-top')
            price_bottom = item_div.find('div', class_='menu-item-price-bottom')
            
            price_elem = price_bottom if price_bottom else price_top
            if price_elem:
                # Get all text, including size labels like "/ dozen"
                price_text = price_elem.get_text(strip=True)
                # Clean up the price text
                price_text = re.sub(r'\s+', ' ', price_text)
                # Format as "$X" or "$X / size"
                if price_text:
                    # Remove currency sign if present and add it back consistently
                    price_text = price_text.replace('$', '').strip()
                    if price_text:
                        # Check if there's a size label
                        if '/' in price_text:
                            parts = price_text.split('/', 1)
                            price_part = parts[0].strip()
                            size_part = parts[1].strip()
                            # Try to extract numeric price
                            price_match = re.search(r'(\d+\.?\d*)', price_part)
                            if price_match:
                                price_value = price_match.group(1)
                                price_str = f"${price_value} / {size_part}"
                        else:
                            # Single price
                            price_match = re.search(r'(\d+\.?\d*)', price_text)
                            if price_match:
                                price_value = price_match.group(1)
                                price_str = f"${price_value}"
            
            # Look for addons in menu-item-options div
            addons = []
            options_div = item_div.find('div', class_='menu-item-options')
            if options_div:
                option_divs = options_div.find_all('div', class_='menu-item-option')
                for option_div in option_divs:
                    option_text = option_div.get_text(strip=True)
                    if option_text:
                        # Format: "Add mushrooms $7" or "Topped with crumbled Bleu Cheese $8"
                        addons.append(option_text)
            
            # Also check description for addon patterns (fallback)
            if not addons and description:
                # Look for patterns like "Add mushrooms $7" or "Add onions $7" or "Topped with crumbled Bleu Cheese $8"
                addon_patterns = [
                    r'Add\s+([^$]+?)\s+\$(\d+)',
                    r'Topped\s+with\s+([^$]+?)\s+\$(\d+)',
                ]
                for pattern in addon_patterns:
                    matches = re.finditer(pattern, description, re.IGNORECASE)
                    for match in matches:
                        addon_name = match.group(1).strip()
                        addon_price = match.group(2)
                        addons.append(f"Add {addon_name} ${addon_price}")
                
                # Remove addon text from description if found there
                if addons:
                    for pattern in addon_patterns:
                        description = re.sub(pattern, '', description, flags=re.IGNORECASE)
                    description = re.sub(r'\s+', ' ', description).strip()
            
            # Add addons to description
            if addons:
                if description:
                    description += f" | Add-ons: {' / '.join(addons)}"
                else:
                    description = f"Add-ons: {' / '.join(addons)}"
            
            # Skip if no price and no description
            if not price_str and not description:
                continue
            
            items.append({
                "name": item_name,
                "description": description,
                "price": price_str,
                "restaurant_name": "Pennell's Restaurant",
                "restaurant_url": "https://www.pennellsrestaurant.com/",
                "menu_type": "Menu",
                "menu_name": section_name
            })
    
    return items

if __name__ == "__main__":
    scrape_pennellsrestaurant()

