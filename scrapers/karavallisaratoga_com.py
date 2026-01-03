"""
Scraper for karavallisaratoga.com
Menu is provided via JSON API, bar menu is images
"""

import json
import re
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

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
    genai.configure(api_key=GOOGLE_API_KEY)
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
    except:
        try:
            model = genai.GenerativeModel('gemini-1.5-pro')
        except:
            model = None
else:
    model = None


def download_json_with_requests(url: str) -> dict:
    """Download JSON from URL"""
    try:
        headers = {
            "sec-ch-ua-platform": '"Windows"',
            "Referer": "https://www.karavallisaratoga.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[ERROR] Failed to download JSON: {e}")
        return {}


def download_html_with_requests(url: str) -> str:
    """Download HTML from URL"""
    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.karavallisaratoga.com/menu"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML: {e}")
        return ""


def download_image_with_requests(url: str, save_path: Path) -> bool:
    """Download image from URL"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Referer": "https://www.karavallisaratoga.com/"
        }
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = save_path.stat().st_size / 1024
        print(f"  [OK] Downloaded image: {save_path.name} ({file_size:.1f} KB)")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download image: {e}")
        return False


def parse_menu_json(menu_data: dict) -> List[Dict]:
    """Parse menu items from JSON API response"""
    items = []
    
    if not menu_data or 'menu' not in menu_data:
        return items
    
    menu = menu_data['menu']
    categories = menu.get('categories', [])
    
    for category in categories:
        category_name = category.get('category_Name', 'Unknown')
        category_description = category.get('category_Description', '')
        
        category_items = category.get('items', [])
        for item in category_items:
            item_name = item.get('item_Name', '').strip()
            if not item_name:
                continue
            
            description = item.get('description') or ''
            description = description.strip() if description else ''
            
            # Handle pricing
            price = ""
            item_price = item.get('item_Price')
            is_multiple_pricing = item.get('isMultiplePricing', False)
            multiple_price = item.get('multiplePrice')
            
            if is_multiple_pricing and multiple_price:
                # Handle multiple pricing (e.g., different sizes)
                price_parts = []
                if isinstance(multiple_price, dict):
                    for size, price_val in multiple_price.items():
                        if price_val:
                            price_parts.append(f"{size} - ${price_val:.2f}")
                elif isinstance(multiple_price, list):
                    for price_obj in multiple_price:
                        if isinstance(price_obj, dict):
                            size = price_obj.get('size', '')
                            price_val = price_obj.get('price')
                            if price_val:
                                if size:
                                    price_parts.append(f"{size} - ${price_val:.2f}")
                                else:
                                    price_parts.append(f"${price_val:.2f}")
                price = " / ".join(price_parts) if price_parts else ""
            elif item_price is not None:
                price = f"${item_price:.2f}"
            
            # Handle modifiers/add-ons
            modifiers = item.get('modifiers', [])
            if modifiers:
                modifier_texts = []
                for modifier in modifiers:
                    if isinstance(modifier, dict):
                        mod_name = modifier.get('name', '').strip()
                        mod_price = modifier.get('price')
                        if mod_name:
                            if mod_price is not None:
                                modifier_texts.append(f"{mod_name} - ${mod_price:.2f}")
                            else:
                                modifier_texts.append(mod_name)
                    elif isinstance(modifier, str):
                        modifier_texts.append(modifier)
                
                if modifier_texts:
                    if description:
                        description += f" (Add-ons: {', '.join(modifier_texts)})"
                    else:
                        description = f"Add-ons: {', '.join(modifier_texts)}"
            
            items.append({
                'name': item_name,
                'description': description,
                'price': price,
                'menu_type': category_name
            })
    
    return items


def extract_menu_from_image_with_gemini(image_path: str, menu_type: str = "Bar Menu") -> List[Dict]:
    """Extract menu items from image using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not model:
        print("  [ERROR] Gemini API not available, cannot extract from image")
        return []
    
    all_items = []
    
    try:
        # Load image
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        print(f"  Processing image with Gemini...")
        
        # Determine MIME type from file extension
        mime_type = "image/png"
        if image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
            mime_type = "image/jpeg"
        elif image_path.lower().endswith('.webp'):
            mime_type = "image/webp"
        elif image_path.lower().endswith('.gif'):
            mime_type = "image/gif"
        
        prompt = """Analyze this restaurant menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Wine By Glass", "JOSH Chardonnay")
2. **description**: The description/ingredients/notes (e.g., "California", tasting notes)
3. **price**: The price (e.g., "$9", "$21.00", "$9 / $12")
4. **menu_type**: The category/section (e.g., "Wine By Glass", "White Wine", "Red Wine")

CRITICAL PRICING RULES:
- Extract prices exactly as shown (e.g., "$9", "$21.00", "MP" for market price)
- If multiple prices exist (e.g., "White $9" and "Red $9"), create separate items or combine with labels
- If a section has a general price (e.g., "White $9"), items in that section should have that price
- Handle "Half Bottle" pricing separately if shown
- Handle "(New)" labels if present

Important guidelines:
- Extract ALL menu items from the image, including wines, cocktails, beers, etc.
- Item names are usually in larger/bolder font
- Descriptions include origin (e.g., "CALIFORNIA", "ITALY"), tasting notes, etc.
- Prices are usually at the end of the line or in a separate column
- If an item has no description, use empty string ""
- Skip section headers as items (like "WINE BY GLASS", "WINE BY THE BOTTLE") but note them as menu_type
- Handle two-column layouts correctly
- Group items by their section/category for menu_type

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.

Example output format:
[
  {
    "name": "Chardonnay",
    "description": "California",
    "price": "$9",
    "menu_type": "Wine By Glass - White"
  },
  {
    "name": "JOSH Chardonnay Half Bottle",
    "description": "CALIFORNIA - The nose exudes aromas of tropical fruits...",
    "price": "$21.00",
    "menu_type": "Wine By The Bottle - White"
  }
]"""
        
        response = model.generate_content(
            [prompt, {
                "mime_type": "image/png",
                "data": image_data
            }],
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 8000,
            }
        )
        
        response_text = response.text.strip()
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        try:
            response_text = response_text.encode('utf-8', errors='ignore').decode('utf-8')
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            menu_items = json.loads(response_text)
            
            for item in menu_items:
                if isinstance(item, dict):
                    if not item.get('menu_type'):
                        item['menu_type'] = menu_type
                    all_items.append(item)
            
            print(f"  [OK] Extracted {len(all_items)} items from image")
            
        except json.JSONDecodeError as e:
            print(f"  [WARNING] Could not parse JSON from Gemini response: {e}")
            print(f"  Response text (first 500 chars): {response_text[:500]}")
            return []
        
    except Exception as e:
        print(f"  [ERROR] Error processing image: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return all_items


def scrape_bar_menu_images(html: str) -> List[Dict]:
    """Extract menu items from bar menu page images"""
    all_items = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all images on the page - look in common containers
    menu_images = []
    
    # Try to find images in various ways
    # 1. Look for img tags
    images = soup.find_all('img')
    for img in images:
        src = img.get('src', '') or img.get('data-src', '') or img.get('data-lazy-src', '')
        if not src:
            continue
        
        # Make URL absolute if relative
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = 'https://www.karavallisaratoga.com' + src
        elif not src.startswith('http'):
            continue
        
        # Skip common non-menu images
        if any(skip in src.lower() for skip in ['logo', 'icon', 'avatar', 'profile', 'social', 'facebook', 'instagram', 'twitter']):
            continue
        
        # Include images that might be menu images
        # If it's a large image or in a menu-related container, include it
        parent = img.find_parent(['div', 'section', 'article'])
        if parent:
            parent_class = parent.get('class', [])
            parent_id = parent.get('id', '')
            if any(keyword in str(parent_class).lower() + str(parent_id).lower() for keyword in ['menu', 'bar', 'content', 'main', 'page']):
                menu_images.append(src)
        else:
            # If no parent context, include if it looks like a menu image
            if any(keyword in src.lower() for keyword in ['menu', 'bar', 'drink', 'wine', 'cocktail', 'food']):
                menu_images.append(src)
            # Or if it's a reasonably sized image (not a tiny icon)
            width = img.get('width', '')
            height = img.get('height', '')
            if width and height:
                try:
                    w, h = int(width), int(height)
                    if w > 200 and h > 200:  # Likely a menu image, not an icon
                        menu_images.append(src)
                except:
                    pass
    
    # Remove duplicates while preserving order
    seen = set()
    unique_images = []
    for img_url in menu_images:
        if img_url not in seen:
            seen.add(img_url)
            unique_images.append(img_url)
    
    if not unique_images:
        print("  [WARNING] No menu images found on bar menu page")
        print("  [INFO] Trying to extract all images as potential menu images...")
        # Fallback: get all images except obvious non-menu ones
        for img in images:
            src = img.get('src', '') or img.get('data-src', '') or img.get('data-lazy-src', '')
            if not src:
                continue
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = 'https://www.karavallisaratoga.com' + src
            elif not src.startswith('http'):
                continue
            if not any(skip in src.lower() for skip in ['logo', 'icon', 'avatar', 'profile']):
                if src not in seen:
                    seen.add(src)
                    unique_images.append(src)
    
    if not unique_images:
        print("  [ERROR] No images found to process")
        return []
    
    print(f"  Found {len(unique_images)} potential menu images")
    
    # Create temp directory for images
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    for idx, img_url in enumerate(unique_images):
        # Determine file extension from URL or use png
        ext = 'png'
        if '.' in img_url:
            ext = img_url.split('.')[-1].split('?')[0].lower()
            if ext not in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                ext = 'png'
        
        image_path = temp_dir / f'bar_menu_{idx + 1}.{ext}'
        
        print(f"  Downloading image {idx + 1}/{len(unique_images)}: {img_url[:80]}...")
        if download_image_with_requests(img_url, image_path):
            print(f"  Extracting menu items from image {idx + 1}...")
            items = extract_menu_from_image_with_gemini(str(image_path), "Bar Menu")
            if items:
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items from image {idx + 1}")
            else:
                print(f"  [WARNING] No items extracted from image {idx + 1}")
            
            # Clean up image file
            if image_path.exists():
                image_path.unlink()
        else:
            print(f"  [WARNING] Failed to download image {idx + 1}")
    
    return all_items


def scrape_karavallisaratoga_menu() -> List[Dict]:
    """
    Main function to scrape all menus from karavallisaratoga.com
    """
    all_items = []
    restaurant_name = "Karavalli Saratoga"
    restaurant_url = "https://www.karavallisaratoga.com/"
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    output_json = output_dir / 'karavallisaratoga_com.json'
    
    print("=" * 60)
    print("SCRAPING KARAVALLI SARATOGA MENUS")
    print("=" * 60)
    print(f"Output file: {output_json}\n")
    
    # Scrape main menu from JSON API
    print("=" * 60)
    print("Scraping Main Menu (JSON API)")
    print("=" * 60)
    
    try:
        json_url = "https://appkudos.blob.core.windows.net/menu-widget/157.json"
        print(f"Downloading JSON from: {json_url}")
        
        menu_data = download_json_with_requests(json_url)
        
        if not menu_data:
            print("[ERROR] Failed to download menu JSON")
        else:
            print(f"[OK] Downloaded menu JSON\n")
            
            print("Parsing menu items...")
            items = parse_menu_json(menu_data)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                    item['menu_name'] = "Main Menu"
                all_items.extend(items)
                print(f"[OK] Extracted {len(items)} items\n")
            else:
                print("[WARNING] No items extracted from JSON\n")
    
    except Exception as e:
        print(f"[ERROR] Error during JSON scraping: {e}")
        import traceback
        traceback.print_exc()
    
    # Scrape bar menu from images
    print("=" * 60)
    print("Scraping Bar Menu (Images)")
    print("=" * 60)
    
    try:
        bar_menu_url = "https://www.karavallisaratoga.com/bar-menu"
        print(f"Downloading HTML from: {bar_menu_url}")
        
        html = download_html_with_requests(bar_menu_url)
        
        if not html:
            print("[ERROR] Failed to download bar menu page")
        else:
            print(f"[OK] Downloaded {len(html)} characters\n")
            
            print("Extracting menu items from images...")
            items = scrape_bar_menu_images(html)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                    item['menu_name'] = "Bar Menu"
                all_items.extend(items)
                print(f"[OK] Extracted {len(items)} items from bar menu\n")
            else:
                print("[WARNING] No items extracted from bar menu\n")
    
    except Exception as e:
        print(f"[ERROR] Error during bar menu scraping: {e}")
        import traceback
        traceback.print_exc()
    
    # Post-processing
    for item in all_items:
        item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
        item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
        if item.get('menu_type'):
            item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
            if not item['menu_type']:
                item['menu_type'] = "Other"
    
    # Save to JSON
    print("=" * 60)
    print("SAVING RESULTS")
    print("=" * 60)
    
    if all_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(all_items, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved {len(all_items)} items to: {output_json}")
    else:
        print("[WARNING] No items to save")
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")
    print(f"{'='*60}")
    
    return all_items


if __name__ == '__main__':
    scrape_karavallisaratoga_menu()

