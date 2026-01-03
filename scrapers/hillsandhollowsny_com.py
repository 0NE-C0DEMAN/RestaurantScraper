"""
Scraper for: http://www.hillsandhollowsny.com/
The menu is displayed as images in HTML, so we extract image URLs and use Gemini Vision API
"""

import json
import re
import time
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup
from io import BytesIO

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed. Install with: pip install google-generativeai")

# Load API Key from config.json
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GOOGLE_API_KEY = config.get("gemini_api_key", "")
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    print(f"Warning: Could not load API key from config.json: {e}")
    GOOGLE_API_KEY = ""

if GEMINI_AVAILABLE and GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)  # pyright: ignore[reportPrivateImportUsage]


def download_html_with_requests(url: str, headers: dict = None) -> str:  # pyright: ignore[reportArgumentType]
    """Download HTML from URL using requests"""
    if headers is None:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.hillsandhollowsny.com/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to download HTML: {e}")
        return ""


def extract_image_urls_from_html(html: str, base_url: str = "https://www.hillsandhollowsny.com") -> List[str]:
    """Extract menu image URLs from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    image_urls = []
    
    # Find all img tags
    img_tags = soup.find_all('img')
    
    for img in img_tags:
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if not src:
            continue
        
        # Skip non-menu images (logos, icons, etc.)
        src_lower = src.lower()
        if any(skip in src_lower for skip in ['logo', 'icon', 'facebook', 'instagram', 'email', 'phone', 'doordash']):
            continue
        
        # Convert relative URLs to absolute
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = base_url + src
        elif not src.startswith('http'):
            src = base_url + '/' + src
        
        # Filter for menu images only - menu images have specific patterns:
        # - Contain "HH" or "Newest" in filename
        # - Are typically larger images (menu pages are 1200x1553, headers are 1068x497)
        # - Menu images don't have the "sc-fqkvVR fECgwp" class (that's for header carousel)
        src_lower_check = src.lower()
        img_class = ' '.join(img.get('class', []))
        
        # Skip header/carousel images (they have specific class or are H-H1 through H-H5)
        if 'H-H' in src and '1920w' in src:
            continue  # Skip header images (H-H1, H-H2, etc.)
        
        # Only include menu images - they contain "HH" or "Newest" or are large PNGs
        if 'newest' in src_lower_check or 'hh' in src_lower_check or (src.endswith('.png') and '1863h' in src):
            if src not in image_urls:
                image_urls.append(src)
    
    return image_urls


def download_image(url: str, output_path: Path, headers: dict = None) -> bool:  # pyright: ignore[reportArgumentType]
    """Download image from URL"""
    if headers is None:
        headers = {
            'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'referer': 'https://www.hillsandhollowsny.com/menu',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
    
    try:
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download image: {e}")
        return False


def extract_menu_from_image(image_path: str) -> List[Dict]:
    """Extract menu items from image using Gemini Vision API"""
    if not GEMINI_AVAILABLE:
        print("  [ERROR] Gemini not available")
        return []
    
    all_items = []
    
    try:
        # Read image file
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Wings", "Burger", "Salad")
2. **description**: The description/ingredients/details
3. **price**: The price (e.g., "$12", "$15.99", "$17.99/$32.99")
4. **menu_type**: The section/category name (e.g., "Starters", "Entrees", "Sides", "Desserts", "Drinks", "Burgers", "Sandwiches")

CRITICAL EXTRACTION RULES:

1. **Items with Sub-Options/Variations:**
   - If an item has sub-options listed under it (like "Loaded Tots" with "Reuben", "Philly Steak", "Loaded"), extract EACH sub-option as a separate item
   - Each sub-option should have the SAME price as the parent item
   - Include the sub-option details in the description field
   - Example: If "Loaded Tots - $15.99" has sub-options "Reuben", "Philly Steak", "Loaded", create separate items for each with price "$15.99"

2. **Items Grouped Together (Boxes/Shared Pricing):**
   - If multiple items are grouped in a box or section with a shared price (like "Sharable Dips - $14.99" with "Crab Dip" and "Spinach Artichoke"), extract EACH item separately
   - Each item in the group should have the SAME price as the group header
   - Example: "Sharable Dips - $14.99" contains "Crab Dip" and "Spinach Artichoke" → extract both with price "$14.99"

3. **Multiple Prices for Same Item (Size Variations):**
   - If an item has multiple prices based on size/quantity (e.g., "Dozen - $17.99, Two Dozen - $32.99" or "Cup - $6.99, Bowl - $9.99, Crock - $10.99"), combine them ONLY in the price field
   - Format: "$17.99/$32.99" for two sizes, or "$6.99/$9.99/$10.99" for three sizes
   - Do NOT include price information in the description field - keep descriptions clean with only ingredients/details
   - Common size variations include: Dozen/Two Dozen, Cup/Bowl/Crock, Small/Large, Single/Double, etc.
   - The price field should contain all price variations separated by "/"

4. **General Pricing Notes:**
   - If a section has a general pricing note (e.g., "All sides are $5.99 a la carte unless noted"), apply that price to items without explicit prices
   - Items with explicit up-charges should have those prices (e.g., "Cup of Soup ($1.00 up charge)" → price should reflect the up-charge)

5. **Standard Extraction:**
   - Extract ALL menu items from the image, including appetizers, entrees, sides, desserts, drinks, etc.
   - Item names are usually in larger/bolder font
   - Descriptions are usually in smaller font below the name
   - Prices are usually at the end of the description line or on a separate line
   - If an item has no description, use empty string ""
   - Include section headers in the menu_type field (like "Starters", "Entrees", "Sides Dishes", "Soups & Salads", etc.)
   - Skip footer text (address, phone, website, etc.)
   - Handle two-column layouts correctly - items in left column and right column should be separate
   - Ensure all prices have a "$" symbol
   - Group items by their section/category using the menu_type field

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Wings",
    "description": "Bone-in or Boneless. Buffalo - Hot - BBQ - Garlic Parm - Carolina Gold - Sweet Chili - Teriyaki - Honey Sriracha - Kickin' Bourbon - Nashville Hot - Cajun Dry Rub - Korean BBQ. Served with Bleu Cheese & Veggies",
    "price": "$17.99/$32.99",
    "menu_type": "Starters"
  },
  {
    "name": "Soup of the Day",
    "description": "",
    "price": "$6.99/$9.99",
    "menu_type": "Soups & Salads"
  },
  {
    "name": "New England Clam Chowder",
    "description": "",
    "price": "$10.99",
    "menu_type": "Soups & Salads"
  },
  {
    "name": "Crab Dip",
    "description": "",
    "price": "$14.99",
    "menu_type": "Starters"
  },
  {
    "name": "Reuben",
    "description": "Corned Beef, Sauerkraut, Swiss, Russian",
    "price": "$15.99",
    "menu_type": "Starters"
  }
]"""
        
        print(f"  Processing image with Gemini...")
        response = model.generate_content(
            [prompt, {
                "mime_type": "image/jpeg",
                "data": image_data
            }],
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 8000,
            }
        )
        response_text = response.text.strip()
        
        # Clean up response text (remove markdown code blocks)
        response_text = re.sub(r'```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        # Attempt to load JSON
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        menu_items = json.loads(response_text)
        
        for item in menu_items:
            if isinstance(item, dict):
                price = str(item.get('price', '')).strip()
                if price and not price.startswith('$'):
                    price = f"${price}"
                
                cleaned_item = {
                    'name': str(item.get('name', '')).strip(),
                    'description': str(item.get('description', '')).strip(),
                    'price': price,
                    'menu_type': str(item.get('menu_type', 'Menu')).strip()
                }
                if cleaned_item['name']:
                    all_items.append(cleaned_item)
        
        # Post-processing: Fix missing prices and ensure size information is in descriptions
        # Group items by menu_type to find parent-child relationships
        items_by_type = {}
        for item in all_items:
            menu_type = item['menu_type']
            if menu_type not in items_by_type:
                items_by_type[menu_type] = []
            items_by_type[menu_type].append(item)
        
        # For each menu type, find items without prices and try to match them to parent items
        for menu_type, type_items in items_by_type.items():
            # Find items with prices (potential parents)
            items_with_prices = [i for i in type_items if i['price']]
            items_without_prices = [i for i in type_items if not i['price']]
            
            # Known parent-child relationships based on menu structure
            parent_child_map = {
                'Sharable Dips': ['Crab Dip', 'Spinach Artichoke'],
                'Loaded Tots': ['Reuben', 'Philly Steak', 'Loaded'],
            }
            
            # Try to match items without prices to parent items
            for item_no_price in items_without_prices:
                item_name = item_no_price['name']
                
                # Check if this item is a known sub-item
                for parent_name, child_names in parent_child_map.items():
                    if item_name in child_names:
                        # Find the parent item with matching price
                        parent_item = next((i for i in items_with_prices if parent_name.lower() in i['name'].lower()), None)
                        if parent_item:
                            item_no_price['price'] = parent_item['price']
                            break
                
                # If still no price, check if there's a nearby item with a price in the same section
                # This handles cases where items are grouped together
                if not item_no_price['price']:
                    # Look for items with prices that might be the parent
                    for item_with_price in items_with_prices:
                        # Check if the item name appears near items with prices (heuristic)
                        # This is a fallback for items that might be sub-options
                        if len(items_without_prices) <= 3 and len(items_with_prices) > 0:
                            # If there are few items without prices, they might share the price of nearby items
                            item_no_price['price'] = items_with_prices[0]['price']
                            break
        
        # Post-processing: Remove price information from descriptions (keep only in price field)
        for item in all_items:
            if item['description']:
                # Remove any price patterns from description (e.g., "Dozen: $17.99 | Two Dozen: $32.99")
                desc = item['description']
                # Remove patterns like "Dozen: $X | Two Dozen: $Y"
                desc = re.sub(r'\s*(?:Dozen|Two Dozen|Cup|Bowl|Crock|Small|Large|Single|Double):\s*\$?\d+\.?\d*\s*\|?\s*', '', desc, flags=re.IGNORECASE)
                # Remove standalone price patterns at the end
                desc = re.sub(r'\s*\$?\d+\.?\d*\s*/\s*\$?\d+\.?\d*.*$', '', desc)
                # Clean up extra spaces and separators
                desc = re.sub(r'\s*\|\s*$', '', desc)
                desc = desc.strip()
                item['description'] = desc
        
        print(f"  [OK] Extracted {len(all_items)} items from image")
        return all_items
        
    except json.JSONDecodeError as e:
        print(f"  [WARNING] Could not parse JSON from Gemini response: {e}")
        print(f"  Response text (first 500 chars): {response_text[:500]}")
        return []
    except Exception as e:
        print(f"  [ERROR] Gemini API error: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_hillsandhollowsny_menu(url: str) -> List[Dict]:
    """
    Scrape menu from hillsandhollowsny.com
    The menu is displayed as images in HTML
    """
    all_items = []
    restaurant_name = "Hills & Hollows"
    restaurant_url = "http://www.hillsandhollowsny.com/"
    
    print("=" * 60)
    print(f"Scraping: {url}")
    print("=" * 60)
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output filename
    url_safe = url.replace('https://', '').replace('http://', '').replace('www.', '').replace('/', '_').replace('.', '_').rstrip('_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    try:
        # Download HTML
        menu_url = "https://www.hillsandhollowsny.com/menu"
        print(f"[1/4] Downloading menu HTML...")
        html = download_html_with_requests(menu_url)
        
        if not html:
            print(f"[ERROR] Failed to download menu HTML")
            return []
        
        print(f"[OK] Menu HTML downloaded\n")
        
        # Extract image URLs
        print(f"[2/4] Extracting menu image URLs...")
        image_urls = extract_image_urls_from_html(html)
        
        if not image_urls:
            print(f"[ERROR] No menu images found")
            return []
        
        print(f"[OK] Found {len(image_urls)} menu images\n")
        
        # Download and process each image
        temp_dir = Path(__file__).parent.parent / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        for img_idx, img_url in enumerate(image_urls):
            print(f"[3/4] Processing image {img_idx + 1}/{len(image_urls)}...")
            print(f"  Image URL: {img_url}")
            
            # Download image
            img_filename = f"hills_menu_{img_idx + 1}.jpg"
            img_path = temp_dir / img_filename
            
            if not download_image(img_url, img_path):
                print(f"  [ERROR] Failed to download image {img_idx + 1}")
                continue
            
            print(f"  [OK] Image downloaded")
            
            # Extract menu items using Gemini
            items = extract_menu_from_image(str(img_path))
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                    item['menu_name'] = f'Menu Page {img_idx + 1}'
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items from image {img_idx + 1}\n")
            else:
                print(f"  [WARNING] No items extracted from image {img_idx + 1}\n")
            
            # Clean up temp image file
            try:
                img_path.unlink()
            except:
                pass
            
            time.sleep(1)  # Delay between API calls
        
        # Deduplicate items
        unique_items = []
        seen = set()
        for item in all_items:
            item_tuple = (item['name'], item['description'], item['price'], item['menu_type'])
            if item_tuple not in seen:
                unique_items.append(item)
                seen.add(item_tuple)
        
        print(f"[OK] Extracted {len(unique_items)} unique items from all images\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        unique_items = []
    
    # Save to JSON
    print(f"[4/4] Saving results...")
    if unique_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(unique_items, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved {len(unique_items)} unique items to: {output_json}")
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(unique_items)}")
    print(f"Saved to: {output_json}")
    print(f"{'='*60}")
    
    return unique_items


if __name__ == '__main__':
    url = "http://www.hillsandhollowsny.com/"
    scrape_hillsandhollowsny_menu(url)

