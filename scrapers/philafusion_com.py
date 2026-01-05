"""
Scraper for Phila Fusion (philafusion.com)
Scrapes menu from multiple pages: Lunch, Dinner, Sushi Bar, Desserts and Beverages
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

def scrape_philafusion() -> List[Dict]:
    """Scrape menu from Phila Fusion website"""
    print("=" * 60)
    print("Scraping Phila Fusion (philafusion.com)")
    print("=" * 60)
    
    menu_urls = [
        {
            "name": "Lunch",
            "url": "https://philafusion.com/menu/lunch/",
            "menu_type": "Lunch"
        },
        {
            "name": "Dinner",
            "url": "https://philafusion.com/dinner/",
            "menu_type": "Dinner"
        },
        {
            "name": "Sushi Bar",
            "url": "https://philafusion.com/menu/sushi-bar/",
            "menu_type": "Sushi Bar"
        },
        {
            "name": "Desserts and Beverages",
            "url": "https://philafusion.com/menu/desserts-and-beverages/",
            "menu_type": "Desserts and Beverages"
        }
    ]
    
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    
    all_items = []
    
    for menu_info in menu_urls:
        print(f"\n[1] Fetching {menu_info['name']} menu from {menu_info['url']}...")
        try:
            response = requests.get(menu_info['url'], headers=headers, timeout=30)
            response.raise_for_status()
            html_content = response.text
            print(f"  [OK] Downloaded {len(html_content)} characters")
            
            print(f"\n[2] Parsing {menu_info['name']} menu items...")
            items = parse_menu_items(html_content, menu_info['menu_type'])
            all_items.extend(items)
            print(f"  [OK] Found {len(items)} items")
        except Exception as e:
            print(f"  [ERROR] Failed to fetch {menu_info['name']} menu: {e}")
            continue
    
    # Save to JSON
    output_file = OUTPUT_DIR / "philafusion_com.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved {len(all_items)} items to {output_file}")
    
    # Show sample items
    if all_items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            price_str = item.get('price', 'N/A')
            section = item.get('menu_name', 'Menu')
            print(f"  {i}. {item.get('name', 'N/A')} - {price_str} ({section})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items

def parse_menu_items(html_content: str, menu_type: str) -> List[Dict]:
    """Parse menu items from HTML content"""
    items = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all menu item containers
    menu_items = soup.find_all('div', class_='menu_content_classic')
    
    current_section = menu_type  # Default section name
    
    for item_div in menu_items:
        # Check if there's a section title before this item
        # Look for h2 with class ppb_menu_title
        prev_section = item_div.find_previous('h2', class_='ppb_menu_title')
        if prev_section:
            section_text = prev_section.get_text(strip=True)
            if section_text:
                current_section = section_text
        
        # Get main item title and price
        main_post = item_div.find('h5', class_='menu_post')
        if not main_post:
            continue
        
        title_elem = main_post.find('span', class_='menu_title')
        if not title_elem:
            continue
        
        item_name = title_elem.get_text(strip=True)
        if not item_name:
            continue
        
        # Skip if it's a size variant (has class 'size')
        if 'size' in title_elem.get('class', []):
            continue
        
        # Get main price
        price_elem = main_post.find('span', class_='menu_price')
        main_price = ""
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Clean and format price
            price_text = re.sub(r'\s+', ' ', price_text)
            if price_text:
                main_price = price_text
        
        # Get description
        desc_elem = item_div.find('div', class_='menu_excerpt')
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        # Check for size variants (multiple prices)
        size_variants = []
        size_posts = item_div.find_all('h5', class_='menu_post size')
        for size_post in size_posts:
            size_title = size_post.find('span', class_='menu_title size')
            size_price = size_post.find('span', class_='menu_price size')
            if size_title and size_price:
                size_name = size_title.get_text(strip=True)
                size_price_text = size_price.get_text(strip=True)
                if size_name and size_price_text:
                    size_variants.append((size_name, size_price_text))
        
        # Format price string
        price_str = ""
        if size_variants:
            # Multiple prices with size labels
            price_parts = []
            for size_name, size_price in size_variants:
                price_parts.append(f"{size_name} {size_price}")
            price_str = " | ".join(price_parts)
        elif main_price:
            price_str = main_price
        
        # Look for addons in description
        addons = []
        if description:
            # Look for patterns like "Add X $Y" or "+$Y" or similar
            addon_patterns = [
                r'Add\s+([^$]+?)\s+\$?(\d+\.?\d*)',
                r'\+?\$?(\d+\.?\d*)\s+for\s+([^,\.]+)',
            ]
            for pattern in addon_patterns:
                matches = re.finditer(pattern, description, re.IGNORECASE)
                for match in matches:
                    if len(match.groups()) == 2:
                        addon_name = match.group(1).strip()
                        addon_price = match.group(2)
                        addons.append(f"Add {addon_name} ${addon_price}")
                    # Remove addon text from description
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
            "restaurant_name": "Phila Fusion",
            "restaurant_url": "https://philafusion.com/",
            "menu_type": menu_type,
            "menu_name": current_section
        })
    
    return items

if __name__ == "__main__":
    scrape_philafusion()

