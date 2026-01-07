"""
Scraper for The Twisted Bagel Company (the-twisted-bagel-company.com-place.com)
Scrapes menu from image-based menu page
Uses Gemini Vision API to extract menu data from image
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
RESTAURANT_NAME = "The Twisted Bagel Company"
RESTAURANT_URL = "https://the-twisted-bagel-company.com-place.com/"

MENU_IMAGE_URL = "https://place.com-photos.com/69483/the-twisted-bagel-company-AF1QipOeRGpkzAqRt5vWZOFd6JI19S4A4S0QNtCSTXyE.jpg"


def download_image(image_url: str) -> Optional[Image.Image]:
    """Download image from URL and return PIL Image"""
    if not PIL_AVAILABLE:
        print(f"  [ERROR] PIL not available")
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Referer': RESTAURANT_URL
        }
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        print(f"  [ERROR] Failed to download image: {e}")
        return None


def extract_menu_from_image_with_gemini(image: Image.Image, menu_name: str) -> List[Dict]:
    """Extract menu items from image using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    if not image:
        print("[ERROR] No image provided")
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
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Sandwiches", "Burgers", "Bagels", "Breakfast", "Brunch", "Lunch", "Dinner", "Desserts", "Beverages", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line, often after a "/" separator
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap", "Cup", "Bowl", "Pint", "Glass", "Bottle", "Half", "Full")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field
- For bagel shops, sections might include: "Bagels", "Breakfast Sandwiches", "Lunch Sandwiches", "Salads", "Soups", "Sides", "Beverages", "Coffee", "Desserts", etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Item Name",
    "description": "Item description with ingredients. Add-ons: add chicken +$5 / add shrimp +$8",
    "price": "Small $5 | Large $7",
    "section": "Bagels"
  }}
]"""
        
        print(f"    Processing menu image ({image.size[0]}x{image.size[1]})...", end=" ")
        
        try:
            response = model.generate_content([prompt, image])
            response_text = response.text.strip()
        except Exception as e:
            print(f"[ERROR] {e}")
            return []
        
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


def scrape_twistedbagel() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Download menu image
    print("\n[1] Downloading menu image...")
    print(f"  URL: {MENU_IMAGE_URL}")
    image = download_image(MENU_IMAGE_URL)
    
    if not image:
        print("[ERROR] Failed to download menu image")
        return []
    
    print(f"[OK] Downloaded {image.size[0]}x{image.size[1]} image")
    
    # Extract menu items from image using Gemini
    print("\n[2] Extracting menu items from image using Gemini Vision API...")
    menu_name = "Menu"
    items = extract_menu_from_image_with_gemini(image, menu_name)
    
    print(f"\n[OK] Extracted {len(items)} items total")
    
    return items


if __name__ == "__main__":
    items = scrape_twistedbagel()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "thetwistedbagelcompany_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

