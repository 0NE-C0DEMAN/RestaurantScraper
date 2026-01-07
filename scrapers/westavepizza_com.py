"""
Scraper for West Avenue Pizzeria (westavepizza.com)
Scrapes menu from JSON API endpoint
Handles: multi-price, multi-size, and add-ons
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
import requests

# Restaurant configuration
RESTAURANT_NAME = "West Avenue Pizzeria"
RESTAURANT_URL = "https://www.westavepizza.com/"

# Menu JSON API URL
MENU_JSON_URL = "https://appkudos.blob.core.windows.net/menu-widget/348.json"

# Headers for requests
HEADERS = {
    'Accept': '*/*',
    'Accept-Language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Origin': 'https://www.westavepizza.com',
    'Pragma': 'no-cache',
    'Referer': 'https://www.westavepizza.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}


def fetch_menu_json() -> Optional[Dict]:
    """Fetch the menu JSON from the API"""
    try:
        print(f"[INFO] Fetching menu JSON from {MENU_JSON_URL}...")
        response = requests.get(MENU_JSON_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"[INFO] Successfully fetched menu JSON")
        return data
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu JSON: {e}")
        return None


def format_price(price: float) -> str:
    """Format price as currency string"""
    if price is None or price == 0:
        return None
    return f"${price:.2f}"


def format_multiple_price(multiple_price: List[Dict]) -> str:
    """Format multiple prices as a string"""
    if not multiple_price:
        return None
    
    price_parts = []
    for price_item in multiple_price:
        name = price_item.get('name', '').strip()
        price = price_item.get('price', 0)
        if price > 0:
            if name:
                price_parts.append(f"{name} ${price:.2f}")
            else:
                price_parts.append(f"${price:.2f}")
    
    if price_parts:
        return " | ".join(price_parts)
    return None


def format_modifiers(modifiers: Optional[List[Dict]]) -> Optional[str]:
    """Format modifiers/add-ons as a string"""
    if not modifiers:
        return None
    
    modifier_parts = []
    for modifier in modifiers:
        modifier_name = modifier.get('name', '').strip()
        modifier_price = modifier.get('price', 0)
        
        if modifier_name:
            if modifier_price and modifier_price > 0:
                modifier_parts.append(f"{modifier_name} (+${modifier_price:.2f})")
            else:
                modifier_parts.append(modifier_name)
    
    if modifier_parts:
        return ", ".join(modifier_parts)
    return None


def extract_items_from_json(menu_data: Dict) -> List[Dict]:
    """Extract menu items from the JSON structure"""
    all_items = []
    
    if not menu_data or 'menu' not in menu_data:
        print("[ERROR] Invalid menu JSON structure")
        return []
    
    menu = menu_data['menu']
    
    # Get main categories
    main_categories = menu.get('main_Categories', [])
    
    for main_cat in main_categories:
        main_cat_name = main_cat.get('main_Category_Name', 'Menu')
        categories = main_cat.get('categories', [])
        
        for category in categories:
            category_name = category.get('category_Name', '')
            category_description = category.get('category_Description')
            items = category.get('items', [])
            
            # Use category name as section, or main category if no category name
            section = category_name if category_name else main_cat_name
            
            for item in items:
                item_name = item.get('item_Name', '').strip()
                if not item_name:
                    continue
                
                description = item.get('description')
                if description:
                    description = description.strip() or None
                else:
                    description = None
                
                # Handle pricing
                is_multiple_pricing = item.get('isMultiplePricing', False)
                item_price = item.get('item_Price', 0)
                multiple_price = item.get('multiplePrice')
                
                price = None
                if is_multiple_pricing and multiple_price:
                    price = format_multiple_price(multiple_price)
                elif item_price and item_price > 0:
                    price = format_price(item_price)
                
                # Handle modifiers/add-ons
                modifiers = item.get('modifiers')
                addons_text = format_modifiers(modifiers)
                
                # Combine description with add-ons if available
                if addons_text:
                    if description:
                        description = f"{description} | Add-ons: {addons_text}"
                    else:
                        description = f"Add-ons: {addons_text}"
                
                all_items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'section': section,
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                })
    
    return all_items


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME}")
    
    # Fetch menu JSON
    menu_data = fetch_menu_json()
    if not menu_data:
        print("[ERROR] Failed to fetch menu JSON")
        return []
    
    # Extract items
    print("[INFO] Extracting menu items from JSON...")
    items = extract_items_from_json(menu_data)
    print(f"[INFO] Extracted {len(items)} menu items")
    
    return items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "westavepizza_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

