"""
Scraper for: https://www.horseshoesaratoga.com/menu
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
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-IN,en;q=0.9',
            'referer': 'https://www.horseshoesaratoga.com/',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to download HTML: {e}")
        return ""


def extract_image_urls_from_html(html: str, base_url: str = "https://www.horseshoesaratoga.com") -> List[str]:
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
        if any(skip in src_lower for skip in ['logo', 'icon', 'facebook', 'instagram', 'email', 'phone', 'userway', 'spin_', 'body_']):
            continue
        
        # Convert relative URLs to absolute
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = base_url + src
        elif not src.startswith('http'):
            src = base_url + '/' + src
        
        # Filter for menu images only - look for menu-related filenames
        if any(keyword in src_lower for keyword in ['breakfast', 'lunch', 'dinner', 'menu', '2369h', '3346h']):
            if src not in image_urls:
                image_urls.append(src)
    
    return image_urls


def download_image(url: str, output_path: Path, headers: dict = None) -> bool:  # pyright: ignore[reportArgumentType]
    """Download image from URL"""
    if headers is None:
        headers = {
            'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'accept-language': 'en-IN,en;q=0.9',
            'referer': 'https://www.horseshoesaratoga.com/menu',
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
3. **price**: The price (e.g., "$12", "$15.99", "Dozen - $17.99 / Two Dozen - $32.99")
4. **menu_type**: The section/category name (e.g., "Starters", "Entrees", "Sides", "Desserts", "Drinks", "Burgers", "Sandwiches", "Breakfast", "Lunch", "Dinner"). DO NOT include the word "Menu" in menu_type values.

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
   - If an item has multiple prices based on size/quantity (e.g., "5 for $12, 10 for $18" or "8/11" meaning Small $8 / Large $11), format them in the price field with size labels
   - Format: "5 for $12 / 10 for $18" or "Small - $8 / Large - $11" for two sizes, or "Cup - $6.99 / Bowl - $9.99 / Crock - $10.99" for three sizes
   - ALWAYS include the size label (5 for, 10 for, Small, Large, Cup, Bowl, Crock, Dozen, Two Dozen, etc.) before each price
   - Separate multiple prices with " / " (space-slash-space)
   - Do NOT include price information in the description field - keep descriptions clean with only ingredients/details
   - Common size variations include: Dozen/Two Dozen, Cup/Bowl/Crock, Small/Large, Single/Double, 5 for/10 for, etc.
   - The price field format should be: "Size1 - $Price1 / Size2 - $Price2"

4. **Price Format Examples:**
   - Single price: "$19"
   - Two sizes: "Small - $8 / Large - $11" or "5 for $12 / 10 for $18"
   - Three sizes: "Cup - $6.99 / Bowl - $9.99 / Crock - $10.99"
   - If prices are shown as "8/11" or "10/13", interpret as "Small - $8 / Large - $11" or "Small - $10 / Large - $13"

5. **General Pricing Notes:**
   - If a section has a general pricing note (e.g., "All sides are $5.99 a la carte unless noted"), apply that price to items without explicit prices
   - Items with explicit up-charges should have those prices (e.g., "Add Chicken (+7)" → note in description, not in price)
   - Add-ons like "(+$1)", "(+$2)", "(+$3)" should be mentioned in description, not in the main price

6. **Standard Extraction:**
   - Extract ALL menu items from the image, including appetizers, entrees, sides, desserts, drinks, etc.
   - Item names are usually in larger/bolder font
   - Descriptions are usually in smaller font below the name
   - Prices are usually at the end of the description line or on a separate line
   - If an item has no description, use empty string ""
   - Include section headers in the menu_type field (like "Starters", "Entrees", "Sides Dishes", "Soups & Salads", "Breakfast", "Lunch", "Dinner", etc.). NEVER include the word "Menu" in menu_type values.
   - Skip footer text (address, phone, website, etc.)
   - Handle two-column layouts correctly - items in left column and right column should be separate
   - Group items by their section/category using the menu_type field

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Wings",
    "description": "Buffalo, Hot, BBQ, Spicy BBQ, Korean BBQ, Garlic Parm, General Tso's",
    "price": "5 for $12 / 10 for $18",
    "menu_type": "Starters"
  },
  {
    "name": "Market Salad",
    "description": "Mixed greens, English cucumber, tomato, & red onion. Choice of dressing",
    "price": "Small - $8 / Large - $11",
    "menu_type": "Salads"
  },
  {
    "name": "Horseshoe Burger",
    "description": "Hand pounded 6 oz. burger, cheddar, lettuce, tomato & onion",
    "price": "$19",
    "menu_type": "Burgers"
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
                # Don't auto-add $ if price already has size labels (e.g., "Cup - $6.99")
                # Check if it has size labels (contains " - $") or already starts with $
                if price and not price.startswith('$') and ' - $' not in price:
                    # Only add $ if it's a simple numeric price without size labels
                    price = f"${price}"
                # Fix prices that incorrectly start with $ when they have size labels
                elif price and price.startswith('$') and ' - $' in price:
                    # Remove the leading $ if size labels are present
                    price = price.lstrip('$').strip()
                
                menu_type = str(item.get('menu_type', '')).strip()
                # Remove "menu" keyword from menu_type (case-insensitive)
                menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
                if not menu_type:
                    menu_type = 'General'
                
                cleaned_item = {
                    'name': str(item.get('name', '')).strip(),
                    'description': str(item.get('description', '')).strip(),
                    'price': price,
                    'menu_type': menu_type
                }
                if cleaned_item['name']:
                    all_items.append(cleaned_item)
        
        # Post-processing: Fix missing prices and format prices correctly
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
                if not item_no_price['price']:
                    if len(items_without_prices) <= 3 and len(items_with_prices) > 0:
                        item_no_price['price'] = items_with_prices[0]['price']
                        break
        
        # Post-processing: Remove "menu" from menu_type and format prices with size labels
        for item in all_items:
            # Remove "menu" keyword from menu_type (case-insensitive)
            if item.get('menu_type'):
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = 'General'
            # Remove any price patterns from description
            if item['description']:
                desc = item['description']
                # Remove patterns like "Dozen: $X | Two Dozen: $Y" or "Cup: $X | Bowl: $Y"
                desc = re.sub(r'\s*(?:Dozen|Two Dozen|Cup|Bowl|Crock|Small|Large|Single|Double|5 for|10 for):\s*\$?\d+\.?\d*\s*\|?\s*', '', desc, flags=re.IGNORECASE)
                # Remove standalone price patterns at the end
                desc = re.sub(r'\s*\$?\d+\.?\d*\s*/\s*\$?\d+\.?\d*.*$', '', desc)
                # Clean up extra spaces and separators
                desc = re.sub(r'\s*\|\s*$', '', desc)
                desc = desc.strip()
                item['description'] = desc
            
            # Format price field to include size labels if multiple prices exist
            if item['price']:
                price_str = item['price']
                # Check if price already has size labels (e.g., "Cup - $6.99")
                has_size_labels = ' - $' in price_str or any(keyword in price_str.lower() for keyword in ['dozen -', 'cup -', 'bowl -', 'crock -', 'small -', 'large -', 'single -', 'double -', 'for $'])
                
                # Fix prices that have incorrect format like "$Cup - $6.99" (extra $ at start)
                if price_str.startswith('$') and ' - $' in price_str:
                    # Remove the leading $ if size labels are present
                    item['price'] = price_str.lstrip('$').strip()
                    price_str = item['price']
                
                # If price has multiple values but no size labels, add them
                if '/' in price_str and not has_size_labels:
                    prices = price_str.split('/')
                    
                    if len(prices) == 2:
                        # Format: "Size1 - $Price1 / Size2 - $Price2"
                        price1 = prices[0].replace('$', '').strip()
                        price2 = prices[1].replace('$', '').strip()
                        name_lower = item['name'].lower()
                        
                        if 'wing' in name_lower:
                            item['price'] = f"5 for ${price1} / 10 for ${price2}"
                        elif 'soup' in name_lower or 'chowder' in name_lower:
                            item['price'] = f"Cup - ${price1} / Bowl - ${price2}"
                        elif 'salad' in name_lower:
                            item['price'] = f"Small - ${price1} / Large - ${price2}"
                        else:
                            # Default format
                            item['price'] = f"Small - ${price1} / Large - ${price2}"
                    elif len(prices) == 3:
                        # Format: "Size1 - $Price1 / Size2 - $Price2 / Size3 - $Price3"
                        price1 = prices[0].replace('$', '').strip()
                        price2 = prices[1].replace('$', '').strip()
                        price3 = prices[2].replace('$', '').strip()
                        name_lower = item['name'].lower()
                        
                        if 'soup' in name_lower or 'chowder' in name_lower:
                            item['price'] = f"Cup - ${price1} / Bowl - ${price2} / Crock - ${price3}"
                        else:
                            # Default format
                            item['price'] = f"${price1} / ${price2} / ${price3}"
        
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


def scrape_horseshoesaratoga_menu(url: str) -> List[Dict]:
    """
    Scrape menu from horseshoesaratoga.com
    The menu is displayed as images in HTML
    """
    all_items = []
    restaurant_name = "Horseshoe Inn Bar & Grill"
    restaurant_url = "https://www.horseshoesaratoga.com/"
    
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
        menu_url = "https://www.horseshoesaratoga.com/menu"
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
        
        menu_names = ["Breakfast-Lunch", "Dinner"]  # Default names, will be updated based on image filenames
        
        for img_idx, img_url in enumerate(image_urls):
            print(f"[3/4] Processing image {img_idx + 1}/{len(image_urls)}...")
            print(f"  Image URL: {img_url}")
            
            # Determine menu name from URL
            menu_name = f"Page {img_idx + 1}"
            if 'breakfast' in img_url.lower() or 'lunch' in img_url.lower() or '2369h' in img_url.lower():
                menu_name = "Breakfast-Lunch"
            elif 'dinner' in img_url.lower() or '3346h' in img_url.lower():
                menu_name = "Dinner"
            
            # Download image
            img_filename = f"horseshoe_menu_{img_idx + 1}.png"
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
                    item['menu_name'] = menu_name
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items from {menu_name}\n")
            else:
                print(f"  [WARNING] No items extracted from {menu_name}\n")
            
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
    url = "https://www.horseshoesaratoga.com/menu"
    scrape_horseshoesaratoga_menu(url)

