"""
Scraper for The Iron's Edge (ironsedgeny.com)
Scrapes menu from menu2order API
Handles: multi-price, multi-size, and add-ons
"""

import json
import requests
from typing import List, Dict, Optional
from pathlib import Path


RESTAURANT_NAME = "The Iron's Edge"
RESTAURANT_URL = "https://www.ironsedgeny.com/"

API_URL = "https://apiv5.menu2order.com/api/menu"
API_HEADERS = {
    'Accept': 'application/json',
    'Accept-Language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'Cache-Control': 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Expires': '0',
    'Origin': 'https://order.ironsedgeny.com',
    'Pragma': 'no-cache',
    'Referer': 'https://order.ironsedgeny.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}
API_DATA = {
    'id': 223,
    'isOffline': True
}


def fetch_menu_data() -> Optional[dict]:
    """Fetch menu data from the API"""
    try:
        response = requests.post(API_URL, headers=API_HEADERS, json=API_DATA, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu data: {e}")
        return None


def format_price(price: float) -> str:
    """Format price as string with $ symbol"""
    if price is None or price == 0:
        return ""
    return f"${price:.2f}"


def extract_size_prices(menu_addons: List[Dict]) -> Optional[str]:
    """
    Extract size-based prices from addon groups.
    Returns formatted price string like "Dozen $17.99 | Two Dozen $32.99" or None if no size options.
    """
    for addon_group in menu_addons:
        group_name = addon_group.get('groupName', '').lower()
        # Look for size-related group names
        if any(keyword in group_name for keyword in ['size', 'pick your', 'portion', 'serving']):
            addon_items = addon_group.get('menuAddonItems', [])
            if len(addon_items) > 1:
                # Multiple size options found
                price_parts = []
                for item in addon_items:
                    size_name = item.get('name', '').strip()
                    price = item.get('price') or item.get('basePrice', 0)
                    if price > 0:
                        price_parts.append(f"{size_name} {format_price(price)}")
                if price_parts:
                    return " | ".join(price_parts)
    return None


def extract_addons_description(menu_addons: List[Dict]) -> str:
    """
    Extract addon information and format as description text.
    Excludes size options (those are handled separately).
    """
    addon_descriptions = []
    
    for addon_group in menu_addons:
        group_name = addon_group.get('groupName', '').strip()
        group_name_lower = group_name.lower()
        
        # Skip size-related groups (handled separately)
        if any(keyword in group_name_lower for keyword in ['size', 'pick your', 'portion', 'serving']):
            continue
        
        addon_items = addon_group.get('menuAddonItems', [])
        if not addon_items:
            continue
        
        # Format addon options
        addon_options = []
        for item in addon_items:
            addon_name = item.get('name', '').strip()
            addon_price = item.get('price') or item.get('basePrice', 0)
            
            if addon_price > 0:
                addon_options.append(f"{addon_name} +{format_price(addon_price)}")
            else:
                addon_options.append(addon_name)
        
        if addon_options:
            if len(addon_options) == 1:
                addon_descriptions.append(f"{group_name}: {addon_options[0]}")
            else:
                addon_descriptions.append(f"{group_name}: {' / '.join(addon_options)}")
    
    if addon_descriptions:
        return "Add-ons: " + " | ".join(addon_descriptions)
    return ""


def process_menu_item(menu_item: Dict, section_name: str) -> Dict:
    """Process a single menu item and return formatted item dict"""
    item_name = menu_item.get('itemName', '').strip()
    description = menu_item.get('description', '').strip() if menu_item.get('description') else None
    unit_price = menu_item.get('unitPrice', 0) or menu_item.get('basePrice', 0)
    menu_addons = menu_item.get('menuAddons', [])
    
    # Extract size-based prices
    size_price_str = extract_size_prices(menu_addons)
    
    # Format price
    if size_price_str:
        # Multi-size pricing
        price = size_price_str
    elif unit_price > 0:
        # Single price
        price = format_price(unit_price)
    else:
        price = ""
    
    # Extract addons (excluding size options)
    addons_text = extract_addons_description(menu_addons)
    
    # Combine description with addons
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
        "section": section_name,
        "restaurant_name": RESTAURANT_NAME,
        "restaurant_url": RESTAURANT_URL,
        "menu_type": "Menu",
        "menu_name": section_name
    }


def scrape_ironsedge() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Fetch menu data from API
    print("\n[1] Fetching menu data from API...")
    menu_data = fetch_menu_data()
    
    if not menu_data:
        print("[ERROR] Failed to fetch menu data")
        return []
    
    print(f"[OK] Received menu data")
    
    # Process categories and subcategories
    print("\n[2] Processing menu items...")
    
    for category in menu_data:
        category_name = category.get('name', '')
        subcategories = category.get('subCategory', [])
        
        print(f"\n  Processing category: {category_name}")
        print(f"    Found {len(subcategories)} subcategories")
        
        for subcategory in subcategories:
            subcategory_name = subcategory.get('name', '')
            menu_items = subcategory.get('menuItems', [])
            
            if not menu_items:
                continue
            
            print(f"    Processing subcategory: {subcategory_name} ({len(menu_items)} items)")
            
            for menu_item in menu_items:
                # Only process active items
                if not menu_item.get('isActive', False):
                    continue
                
                item = process_menu_item(menu_item, subcategory_name)
                all_items.append(item)
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    return all_items


if __name__ == "__main__":
    items = scrape_ironsedge()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "ironsedgeny_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

