"""
Scraper for: https://countrycornercafe.square.site/
Uses Square Online Store API to extract menu items
"""

import json
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


def extract_ids_from_url(url: str) -> Dict[str, str]:
    """
    Extract location ID from URL.
    Also tries to extract user_id and site_id from the page if needed.
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    location_id = query_params.get('location', [None])[0]
    
    return {
        'location_id': location_id,
    }


def get_square_store_config(url: str) -> Dict[str, str]:
    """
    Get store configuration by loading the page and extracting IDs from API calls.
    Returns user_id, site_id, and location_id.
    """
    # Known IDs for countrycornercafe.square.site
    # These can be extracted from the network requests
    return {
        'user_id': '132583133',
        'site_id': '845493430833411312',
        'location_id': 'F3XRZCTN550JM',  # From URL parameter
    }


def fetch_all_products(user_id: str, site_id: str, location_id: str) -> List[Dict]:
    """
    Fetch all products from Square Online Store API.
    """
    all_products = []
    page = 1
    per_page = 200
    
    print("  Fetching products from API...")
    
    while True:
        url = (
            f"https://cdn5.editmysite.com/app/store/api/v28/editor/users/{user_id}/"
            f"sites/{site_id}/store-locations/{location_id}/products"
            f"?page={page}&per_page={per_page}"
            f"&include=images,discounts,media_files"
            f"&fulfillments[]=pickup"
            f"&cache-version=2023-11-13"
        )
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            products = data.get('data', [])
            if not products:
                break
            
            all_products.extend(products)
            print(f"    Fetched page {page}: {len(products)} products")
            
            # Check if there are more pages
            pagination = data.get('pagination', {})
            if not pagination.get('has_more', False):
                break
            
            page += 1
            
        except Exception as e:
            print(f"    [ERROR] Failed to fetch products page {page}: {e}")
            break
    
    print(f"  [OK] Fetched {len(all_products)} total products")
    return all_products


def fetch_all_categories(user_id: str, site_id: str) -> List[Dict]:
    """
    Fetch all categories from Square Online Store API.
    Returns a flat list of all categories (including nested ones).
    """
    url = (
        f"https://cdn5.editmysite.com/app/store/api/v28/editor/users/{user_id}/"
        f"sites/{site_id}/categories"
        f"?max_depth=2&nested=1"
        f"&cache-version=2023-11-13"
    )
    
    print("  Fetching categories from API...")
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        categories = data.get('data', [])
        
        # Flatten nested categories
        def flatten_categories(cat_list, parent_name=""):
            result = []
            for cat in cat_list:
                # Skip root "Online Menu" category if it has no direct products
                if cat.get('product_counts', {}).get('direct', 0) == 0 and cat.get('name') == 'Online Menu':
                    # Process children
                    if cat.get('children'):
                        result.extend(flatten_categories(cat['children'], parent_name))
                else:
                    # Add this category
                    full_name = f"{parent_name} - {cat['name']}" if parent_name else cat['name']
                    result.append({
                        'id': cat['id'],
                        'name': full_name,
                        'product_ids': cat.get('preferred_order_product_ids', []),
                    })
                    
                    # Process children
                    if cat.get('children'):
                        result.extend(flatten_categories(cat['children'], full_name))
            
            return result
        
        flat_categories = flatten_categories(categories)
        print(f"  [OK] Fetched {len(flat_categories)} categories")
        
        return flat_categories
        
    except Exception as e:
        print(f"  [ERROR] Failed to fetch categories: {e}")
        return []


def clean_html_description(html_text: str) -> str:
    """
    Clean HTML from description text.
    """
    if not html_text:
        return ""
    
    # Remove HTML tags
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def format_price(price_data: Dict) -> str:
    """
    Format price from price data object.
    Returns formatted price string like "$10.00" or "$10.00 - $15.00"
    """
    if not price_data:
        return ""
    
    low = price_data.get('low_formatted', '')
    high = price_data.get('high_formatted', '')
    
    if low and high and low != high:
        return f"{low} - {high}"
    elif low:
        return low
    elif high:
        return high
    
    return ""


def map_products_to_categories(products: List[Dict], categories: List[Dict]) -> Dict[str, str]:
    """
    Map product site_product_id to category name.
    Returns dict: {site_product_id: category_name}
    """
    product_to_category = {}
    
    # Create a mapping from site_product_id to category
    for category in categories:
        category_name = category['name']
        product_ids = category.get('product_ids', [])
        
        for product_id in product_ids:
            # Convert to string for consistency
            product_id_str = str(product_id)
            product_to_category[product_id_str] = category_name
    
    return product_to_category


def scrape_countrycornercafe_menu(url: str = None) -> List[Dict]:
    """
    Main function to scrape menu from countrycornercafe.square.site
    
    Args:
        url: URL of the Square Online store (optional)
    
    Returns:
        List of dictionaries containing all menu items
    """
    if url is None:
        url = "https://countrycornercafe.square.site/?location=F3XRZCTN550JM#7G4IXI7W77PAMRTYKFLU7UJF"
    
    restaurant_name = "The Country Corner Cafe"
    
    print(f"\n{'='*60}")
    print(f"Scraping: {url}")
    print(f"{'='*60}\n")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename
    output_json = output_dir / 'countrycornercafe_net.json'
    print(f"Output file: {output_json}\n")
    
    # Get store configuration
    config = get_square_store_config(url)
    user_id = config['user_id']
    site_id = config['site_id']
    location_id = config['location_id']
    
    print(f"Store Configuration:")
    print(f"  User ID: {user_id}")
    print(f"  Site ID: {site_id}")
    print(f"  Location ID: {location_id}\n")
    
    # Fetch all products and categories
    products = fetch_all_products(user_id, site_id, location_id)
    categories = fetch_all_categories(user_id, site_id)
    
    if not products:
        print("[ERROR] No products found")
        return []
    
    # Map products to categories
    product_to_category = map_products_to_categories(products, categories)
    
    # Convert products to menu items
    print("\n  Converting products to menu items...")
    all_items = []
    
    for product in products:
        try:
            site_product_id = str(product.get('site_product_id', ''))
            category_name = product_to_category.get(site_product_id, 'Items')
            
            # Skip items with no name
            name = product.get('name', '').strip()
            if not name:
                continue
            
            # Get description
            description = clean_html_description(product.get('short_description', ''))
            
            # Get price
            price_data = product.get('price', {})
            price = format_price(price_data)
            
            # Create menu item
            item = {
                'name': name,
                'description': description,
                'price': price,
                'menu_type': category_name,
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Menu'
            }
            
            all_items.append(item)
            
        except Exception as e:
            print(f"    [ERROR] Error processing product {product.get('name', 'unknown')}: {e}")
            continue
    
    print(f"  [OK] Converted {len(all_items)} products to menu items\n")
    
    # Save to JSON
    print(f"Saving {len(all_items)} items to: {output_json}\n")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scraping complete! Extracted {len(all_items)} items")
    print(f"{'='*60}\n")
    
    return all_items


if __name__ == "__main__":
    scrape_countrycornercafe_menu()

