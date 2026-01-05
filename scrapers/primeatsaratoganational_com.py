"""
Scraper for Prime at Saratoga National (primeatsaratoganational.com)
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

def scrape_primeatsaratoganational() -> List[Dict]:
    """Scrape menu from Prime at Saratoga National website"""
    print("=" * 60)
    print("Scraping Prime at Saratoga National (primeatsaratoganational.com)")
    print("=" * 60)
    
    url = "https://primeatsaratoganational.com/prime-restaurant/"
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
    output_file = OUTPUT_DIR / "primeatsaratoganational_com.json"
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
    
    # Find all menu item containers
    menu_items = soup.find_all('div', class_='module-service-menu')
    
    current_section = "Menu"  # Default section name
    current_menu_type = "Menu"  # Default menu type (Lunch, Dinner, etc.)
    
    for item_div in menu_items:
        # Check for section headers before this item
        # Look for h2, h3 with section names
        prev_h2 = item_div.find_previous('h2', class_='simulate_h1')
        prev_h3 = item_div.find_previous('h3')
        
        # Check for menu type (Lunch, Dinner, etc.)
        if prev_h2:
            h2_text = prev_h2.get_text(strip=True)
            if 'LUNCH' in h2_text.upper():
                current_menu_type = "Lunch"
            elif 'DINNER' in h2_text.upper():
                current_menu_type = "Dinner"
            elif 'KIDS' in h2_text.upper():
                current_menu_type = "Kids"
            elif 'DESSERT' in h2_text.upper():
                current_menu_type = "Desserts"
            elif 'COCKTAIL' in h2_text.upper():
                current_menu_type = "Cocktails"
        
        # Check for section name (STARTERS, SOUPS, etc.)
        if prev_h3:
            h3_text = prev_h3.get_text(strip=True)
            if h3_text and h3_text.upper() not in ['PRIME RESTAURANT', 'OUR MENUS', 'RESTAURANT HOURS']:
                current_section = h3_text.strip()
        
        # Get item title
        title_elem = item_div.find('h4', class_='tb-menu-title')
        if not title_elem:
            continue
        
        item_name = title_elem.get_text(strip=True)
        if not item_name:
            continue
        
        # Get description
        desc_elem = item_div.find('div', class_='tb-menu-description')
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        # Get price - check for multiple formats
        price_str = ""
        price_elem = item_div.find('div', class_='tb-menu-price')
        
        if price_elem:
            # Check if it has multiple price items (tb-price-item)
            price_items = price_elem.find_all('div', class_='tb-price-item')
            if price_items:
                # Multiple prices with labels
                price_parts = []
                for price_item in price_items:
                    price_title = price_item.find('div', class_='tb-price-title')
                    price_value = price_item.find('div', class_='tb-price-value')
                    if price_title and price_value:
                        title = price_title.get_text(strip=True)
                        value = price_value.get_text(strip=True)
                        # Clean value (remove trailing period)
                        value = value.rstrip('.')
                        if title and value:
                            # Format as "$X" or "$X" if no title
                            try:
                                price_float = float(value)
                                if title:
                                    price_parts.append(f"{title} ${price_float:.0f}")
                                else:
                                    price_parts.append(f"${price_float:.0f}")
                            except ValueError:
                                pass
                if price_parts:
                    price_str = " | ".join(price_parts)
            else:
                # Single or multiple prices separated by "|"
                price_text = price_elem.get_text(strip=True)
                # Remove trailing period
                price_text = price_text.rstrip('.')
                if price_text:
                    # Check if it contains "|" for multiple prices
                    if '|' in price_text:
                        # Multiple prices without labels (e.g., "24|47")
                        prices = [p.strip() for p in price_text.split('|')]
                        formatted_prices = []
                        for p in prices:
                            try:
                                price_float = float(p)
                                formatted_prices.append(f"${price_float:.0f}")
                            except ValueError:
                                formatted_prices.append(f"${p}")
                        price_str = " | ".join(formatted_prices)
                    else:
                        # Single price
                        # Check if it's "MP" (Market Price)
                        if price_text.upper() in ['MP', 'MARKET PRICE']:
                            price_str = "MP"
                        else:
                            try:
                                price_float = float(price_text)
                                price_str = f"${price_float:.0f}"
                            except ValueError:
                                price_str = price_text if price_text else ""
        
        # Extract addons from description
        addons = []
        if description:
            # Look for patterns like "(Add X | MP)" or "(Add X $Y)"
            addon_patterns = [
                r'\(Add\s+([^|)]+?)\s*\|\s*MP\)',
                r'\(Add\s+([^|)]+?)\s*\$\s*(\d+\.?\d*)\)',
                r'Add\s+([^|)]+?)\s*\|\s*MP',
                r'Add\s+([^|)]+?)\s*\$\s*(\d+\.?\d*)',
            ]
            for pattern in addon_patterns:
                matches = re.finditer(pattern, description, re.IGNORECASE)
                for match in matches:
                    if len(match.groups()) == 2:
                        addon_name = match.group(1).strip()
                        addon_price = match.group(2)
                        addons.append(f"Add {addon_name} ${addon_price}")
                    elif len(match.groups()) == 1:
                        addon_name = match.group(1).strip()
                        addons.append(f"Add {addon_name} (MP)")
                    # Remove addon text from description
                    description = re.sub(pattern, '', description, flags=re.IGNORECASE)
            description = re.sub(r'\s+', ' ', description).strip()
            # Remove empty parentheses
            description = re.sub(r'\(\s*\)', '', description).strip()
            # Remove artifacts like ". |" or "| ."
            description = re.sub(r'\s*\.\s*\|\s*', ' ', description).strip()
            description = re.sub(r'\s*\|\s*\.\s*', ' ', description).strip()
            description = re.sub(r'^\|\s*', '', description).strip()
            description = re.sub(r'\s*\|$', '', description).strip()
        
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
            "restaurant_name": "Prime at Saratoga National",
            "restaurant_url": "https://primeatsaratoganational.com/",
            "menu_type": current_menu_type,
            "menu_name": current_section
        })
    
    return items

if __name__ == "__main__":
    scrape_primeatsaratoganational()

