"""
Scraper for The Night Owl Saratoga (saratoganightowl.com)
Scrapes menu from image-based menu pages
Uses Gemini Vision API to extract menu data from images
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from io import BytesIO
import requests

# Check for optional dependencies
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed. Install with: pip install google-generativeai")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed. Install with: pip install playwright")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not installed. Install with: pip install Pillow")

# Load API Key from config.json
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
GEMINI_API_KEY = None
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GEMINI_API_KEY = config.get("gemini_api_key") or config.get("GEMINI_API_KEY")
except Exception as e:
    print(f"Warning: Could not load API key from config.json: {e}")

if GEMINI_AVAILABLE and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# Restaurant configuration
RESTAURANT_NAME = "The Night Owl Saratoga"
RESTAURANT_URL = "http://www.saratoganightowl.com/"

MENU_URL = "https://www.saratoganightowl.com/menu"


def fetch_menu_images() -> List[str]:
    """Fetch menu page and extract menu image URLs"""
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available")
        return []
    
    print("  Loading page with Playwright...")
    image_urls = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set headers and cookies
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            }
            
            context = browser.new_context(extra_http_headers=headers)
            
            # Add cookies
            cookies = [
                {
                    'name': 'server-session-bind',
                    'value': 'bc24145a-2c0f-46ca-bdeb-352d7345423e',
                    'domain': '.saratoganightowl.com',
                    'path': '/'
                },
                {
                    'name': 'XSRF-TOKEN',
                    'value': '1767757964|4TeTfmyhu0OD',
                    'domain': '.saratoganightowl.com',
                    'path': '/'
                },
                {
                    'name': 'hs',
                    'value': '1315850988',
                    'domain': '.saratoganightowl.com',
                    'path': '/'
                },
                {
                    'name': 'svSession',
                    'value': 'c1c8b30c56ba48f77eea30a0a7a018d716e0f3231aafa849517a1a4173e0d134805420b9bc29ed45b6fed662a248f73b1e60994d53964e647acf431e4f798bcdbbc38daf409d18dd4b375cc15c3217edecb84de47333ae93eb341a58a453fc77c12107511330e67f259f22df9886b4a998d51e6bc34cdf100eda0d85f681ab139139234e9000d5252697ec6baeba8c2d',
                    'domain': '.saratoganightowl.com',
                    'path': '/'
                },
                {
                    'name': 'bSession',
                    'value': '2fcbe883-45da-4fad-82db-7156c425147b|4',
                    'domain': '.saratoganightowl.com',
                    'path': '/'
                }
            ]
            
            page = context.new_page()
            page.goto(MENU_URL, wait_until="networkidle", timeout=60000)
            
            # Add cookies after navigation
            context.add_cookies(cookies)
            
            # Wait a bit for images to load
            import time
            time.sleep(3)
            
            # Find all images on the page
            images = page.query_selector_all('img')
            
            for img in images:
                src = img.get_attribute('src') or img.get_attribute('data-src') or img.get_attribute('data-image')
                alt = img.get_attribute('alt') or ''
                
                if not src:
                    continue
                
                # Look for menu images (fall/winter menu or summer menu)
                # Check alt text and src URL for menu indicators
                src_lower = src.lower()
                alt_lower = alt.lower()
                
                is_menu_image = (
                    'fallwinter' in src_lower or 'fall-winter' in src_lower or
                    'nightowl' in src_lower and ('menu' in src_lower or '25' in src_lower) or
                    'menu' in alt_lower or 
                    ('fall' in alt_lower and 'winter' in alt_lower) or
                    ('summer' in alt_lower and 'menu' in alt_lower)
                )
                
                if is_menu_image:
                    # Get full URL
                    if src.startswith('http'):
                        full_url = src
                    elif src.startswith('//'):
                        full_url = 'https:' + src
                    elif src.startswith('/'):
                        full_url = 'https://www.saratoganightowl.com' + src
                    else:
                        # Relative URL
                        full_url = f"{MENU_URL}/{src}"
                    
                    image_urls.append(full_url)
            
            browser.close()
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in image_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            print(f"  Found {len(unique_urls)} menu images")
            return unique_urls
            
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu images: {e}")
        return []


def download_image(image_url: str, output_path: Path) -> Optional[Image.Image]:
    """Download image from URL and return PIL Image"""
    if not PIL_AVAILABLE:
        print(f"  [ERROR] PIL not available for {image_url}")
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        print(f"  [ERROR] Failed to download image {image_url}: {e}")
        return None


def extract_menu_from_images_with_gemini(images: List[Image.Image], menu_name: str) -> List[Dict]:
    """Extract menu items from images using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    if not images:
        print("[ERROR] No images provided")
        return []
    
    all_items = []
    
    try:
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Analyze this {menu_name} menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (NOT addon items like "ADD CHICKEN" - those should be in descriptions)
2. **description**: The description/ingredients/details for THIS specific item only. CRITICAL: If there are addons listed near this item (like "ADD CHICKEN $7.95" or "Add chicken +$6" or "with cheese | Small $6 Large $8"), include them in the description field. Format as: "Description text. Add-ons: add chicken +$7.95 / add shrimp +$10.95 / with cheese Small $6 Large $8"
3. **price**: The price. CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
   * "Small $5 | Large $7"
   * "6\" Sub or Bread $8 | 12\" Sub or Wrap $13"
   * "SM $7 | LG $13"
   * "$13" (single price)
   Always include the $ symbol. For items with size variations, use the format: "Size1 $X | Size2 $Y"
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Cocktails", "Wine", "Beer", "Breakfast", "Brunch", "Lunch", "Dinner", "Desserts", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line, often after a "/" separator
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap", "Cup", "Bowl", "Pint", "Glass", "Bottle")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field
- For combined food & drinks menus, sections might include: "Appetizers", "Entrees", "Salads", "Soups", "Sandwiches", "Burgers", "Pizza", "Desserts", "Cocktails", "Wine", "Beer", "Non-Alcoholic Beverages", etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Item Name",
    "description": "Item description with ingredients. Add-ons: add chicken +$5 / add shrimp +$8",
    "price": "Small $5 | Large $7",
    "section": "Appetizers"
  }}
]"""
        
        # Process images
        for i, image in enumerate(images):
            print(f"    Processing image {i + 1}/{len(images)}...", end=" ")
            
            try:
                response = model.generate_content([prompt, image])
                response_text = response.text.strip()
            except Exception as e:
                print(f"[ERROR] {e}")
                continue
            
            # Parse JSON from response
            response_text = re.sub(r'```json\s*', '', response_text)
            response_text = re.sub(r'```\s*', '', response_text)
            response_text = response_text.strip()
            
            # Remove any non-JSON content at the beginning
            json_start = -1
            for j, char in enumerate(response_text):
                if char in ['[', '{']:
                    json_start = j
                    break
            
            if json_start > 0:
                response_text = response_text[json_start:]
            
            # Remove any trailing non-JSON content
            json_end = -1
            for j in range(len(response_text) - 1, -1, -1):
                if response_text[j] in [']', '}']:
                    json_end = j + 1
                    break
            
            if json_end > 0 and json_end < len(response_text):
                response_text = response_text[:json_end]
            
            try:
                items = json.loads(response_text)
                if isinstance(items, list):
                    # Add restaurant info to each item
                    for item in items:
                        item['restaurant_name'] = RESTAURANT_NAME
                        item['restaurant_url'] = RESTAURANT_URL
                        item['menu_type'] = menu_name
                        item['menu_name'] = item.get('section', 'Menu')
                    all_items.extend(items)
                    print(f"[OK] Extracted {len(items)} items")
                else:
                    print(f"[WARNING] Expected list, got {type(items)}")
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse JSON: {e}")
                print(f"Response text (first 500 chars): {response_text[:500]}")
        
    except Exception as e:
        print(f"[ERROR] Failed to extract menu: {e}")
    
    return all_items


def scrape_nightowl() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Fetch menu image URLs
    print("\n[1] Fetching menu image URLs...")
    image_urls = fetch_menu_images()
    
    if not image_urls:
        print("[ERROR] No menu images found")
        return []
    
    print(f"[OK] Found {len(image_urls)} menu images")
    
    # Download images
    print("\n[2] Downloading menu images...")
    images = []
    for i, url in enumerate(image_urls):
        print(f"  Downloading image {i + 1}/{len(image_urls)}: {url[:80]}...")
        img = download_image(url, None)
        if img:
            images.append(img)
            print(f"    [OK] Downloaded {img.size[0]}x{img.size[1]} image")
        else:
            print(f"    [ERROR] Failed to download")
    
    if not images:
        print("[ERROR] No images downloaded")
        return []
    
    print(f"[OK] Downloaded {len(images)} images")
    
    # Extract menu items from images using Gemini
    print("\n[3] Extracting menu items from images using Gemini Vision API...")
    menu_name = "Fall & Winter Menu '25-'26"
    items = extract_menu_from_images_with_gemini(images, menu_name)
    
    print(f"\n[OK] Extracted {len(items)} items total")
    
    return items


if __name__ == "__main__":
    items = scrape_nightowl()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "saratoganightowl_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

