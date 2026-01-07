"""
Scraper for The Ugly Rooster (theuglyrooster.com)
Scrapes menu from PDF file
Uses Gemini Vision API to extract menu data from PDF pages
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from io import BytesIO

# Check for optional dependencies
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed. Install with: pip install google-generativeai")

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    print("Warning: pdf2image not installed. Install with: pip install pdf2image")

from PIL import Image

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
RESTAURANT_NAME = "The Ugly Rooster"
RESTAURANT_URL = "https://www.theuglyrooster.com/"

# Menu PDF URLs
MENU_PDFS = [
    {
        "url": "https://www.theuglyrooster.com/_files/ugd/6775d2_5cabd99818364a16a1ada4960821cb00.pdf",
        "menu_name": "Full Menu",
        "menu_type": "Cafe Menu"
    },
    {
        "url": "https://www.theuglyrooster.com/_files/ugd/6775d2_6d651e4fdd944f9ea3b5e3f870c3c29d.pdf",
        "menu_name": "Full Menu",
        "menu_type": "Cafe Menu"
    }
]

# Ice Cream Menu Image URL
ICE_CREAM_MENU_IMAGE_URL = "https://static.wixstatic.com/media/6775d2_d8a1c4bb529d4e319ad732579da2d79b~mv2.png/v1/fill/w_980,h_560,al_c,q_90,usm_0.66_1.00_0.01,enc_avif,quality_auto/UICMenu.png"


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """Download PDF from URL using requests"""
    try:
        import requests
        headers = {
            "accept": "application/pdf,*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": RESTAURANT_URL
        }
        response = requests.get(pdf_url, headers=headers, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download PDF from {pdf_url}: {e}")
        return False


def extract_menu_from_pdf_with_gemini(pdf_path: Path, menu_name: str, menu_type: str) -> List[Dict]:
    """Extract menu items from PDF using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    if not PDF2IMAGE_AVAILABLE:
        print("[ERROR] pdf2image not available. Install with: pip install pdf2image")
        return []
    
    all_items = []
    
    try:
        # Convert PDF pages to images
        images = convert_from_path(str(pdf_path), dpi=300)
        print(f"    Converted {len(images)} pages to images")
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Analyze this {menu_name} PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (NOT addon items like "ADD CHICKEN" - those should be in descriptions)
2. **description**: The description/ingredients/details for THIS specific item only. CRITICAL: If there are addons listed near this item (like "ADD CHICKEN $7.95" or "Add chicken +$6" or "with cheese | Small $6 Large $8"), include them in the description field. Format as: "Description text. Add-ons: add chicken +$7.95 / add shrimp +$10.95 / with cheese Small $6 Large $8"
3. **price**: The price. CRITICAL: 
   - If a sub-section or section header shows a pricing structure with columns (like "1/2 PAN" and "FULL PAN" or "SMALL" and "LARGE"), ALL items listed under that sub-section MUST use that same pricing structure
   - Look for pricing columns at the sub-section level - if you see "1/2 PAN" and "FULL PAN" columns with serving sizes, each item in that sub-section should have BOTH prices
   - If there are multiple prices for different sizes, you MUST include the size labels AND serving information. Examples:
     * "1/2 PAN (serves 12) $40 | FULL PAN (serves 25) $75"
     * "SMALL (serves 15) $35 | LARGE (serves 25) $50"
     * "Small $5 | Large $7"
     * "6\" Sub or Bread $8 | 12\" Sub or Wrap $13"
   - If prices are per person with minimum quantity, include that: "$22 per person (10 minimum)"
   - For single prices: "$13" or "$45 (serves 15-20)"
   - If prices show a range like "$95 30-40", format as "$95 (serves 30-40)"
   - Always include the $ symbol. For items with size variations, use the format: "Size1 (serves X) $X | Size2 (serves Y) $Y"
   - IMPORTANT: If the menu shows serving sizes (e.g., "serves 12", "serves 15-20"), ALWAYS include them in the price field
   - CRITICAL: When you see a pricing table or columns at a sub-section level, apply that pricing structure to ALL items in that sub-section
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Sandwiches", "Burgers", "Pizza", "Breakfast", "Brunch", "Lunch", "Dinner", "Desserts", "Beverages", "Coffee", etc.). Use the main section name, not sub-section headers.

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- DO NOT extract sub-section headers (like "Breakfast Bonanza Sides & Platters") as menu items - these are just organizational headers
- If a sub-section has a pricing structure (e.g., "1/2 PAN" and "FULL PAN" columns), apply that pricing structure to ALL items listed under that sub-section
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line, often after a "/" separator
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels AND serving information if shown: "6\" Sub $8 | 12\" Sub $13" or "SMALL (serves 15) $35 | LARGE (serves 25) $50"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "1/2 PAN", "FULL PAN", "6\"", "12\"", "Sub", "Bread", "Wrap", "Cup", "Bowl", "Pint", "Glass", "Bottle", "Half", "Full")
- CRITICAL: If serving sizes are indicated (e.g., "serves 12", "serves 15-20", "15-20 people"), include them in the price field: "SMALL (serves 15) $35 | LARGE (serves 25) $50"
- CRITICAL: If a section has a pricing structure with columns (like "1/2 PAN" and "FULL PAN"), each item in that section should have BOTH prices: "1/2 PAN (serves 12) $40 | FULL PAN (serves 25) $75"
- If prices show a range like "$95 30-40", format as "$95 (serves 30-40)"
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Skip sub-section headers - only extract actual menu items
- Group items by their section/category using the section field
- For cafe/breakfast menus, sections might include: "Breakfast", "Brunch", "Lunch", "Sandwiches", "Salads", "Soups", "Sides", "Beverages", "Coffee", "Desserts", etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Item Name",
    "description": "Item description with ingredients. Add-ons: add chicken +$5 / add shrimp +$8",
    "price": "Small $5 | Large $7",
    "section": "Breakfast"
  }}
]"""
        
        # Process pages in pairs for efficiency
        for i in range(0, len(images), 2):
            if i + 1 < len(images):
                # Two pages to process together
                page1 = images[i]
                page2 = images[i + 1]
                print(f"    Processing pages {i + 1} and {i + 2}...", end=" ")
                
                try:
                    response = model.generate_content([prompt, page1, page2])
                    response_text = response.text.strip()
                except Exception as e:
                    print(f"[ERROR] {e}")
                    continue
            else:
                # Only one page left
                page1 = images[i]
                print(f"    Processing page {i + 1}...", end=" ")
                
                try:
                    response = model.generate_content([prompt, page1])
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
                        item['menu_type'] = menu_type
                        item['menu_name'] = item.get('section', menu_name)
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


def download_image(image_url: str) -> Optional[Image.Image]:
    """Download image from URL and return PIL Image"""
    try:
        import requests
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


def extract_menu_from_image_with_gemini(image: Image.Image, menu_name: str, menu_type: str) -> List[Dict]:
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
4. **section**: The section/category name (e.g., "Ice Cream", "Flavors", "Sundaes", "Shakes", "Cones", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line, often after a "/" separator
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap", "Cup", "Bowl", "Pint", "Glass", "Bottle", "Half", "Full", "Single", "Double", "Scoop", "Scoops")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Item Name",
    "description": "Item description with ingredients. Add-ons: add chicken +$5 / add shrimp +$8",
    "price": "Small $5 | Large $7",
    "section": "Ice Cream"
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
                    item['menu_type'] = menu_type
                    item['menu_name'] = item.get('section', menu_name)
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


def scrape_uglyrooster() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    # Download and process PDFs
    print("\n[1] Downloading and processing menu PDFs...")
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    for i, pdf_info in enumerate(MENU_PDFS):
        print(f"\n  Processing PDF {i + 1}/{len(MENU_PDFS)}: {pdf_info['menu_name']}")
        pdf_path = temp_dir / f"uglyrooster_menu_{i + 1}.pdf"
        
        if download_pdf(pdf_info['url'], pdf_path):
            print(f"    [OK] Downloaded PDF to {pdf_path}")
            
            # Extract menu items from PDF using Gemini
            print(f"    Extracting menu items from PDF...")
            items = extract_menu_from_pdf_with_gemini(pdf_path, pdf_info['menu_name'], pdf_info['menu_type'])
            all_items.extend(items)
            print(f"    [OK] Extracted {len(items)} items from PDF {i + 1}")
        else:
            print(f"    [ERROR] Failed to download PDF {i + 1}")
    
    # Download and process ice cream menu image
    print("\n[2] Downloading and processing ice cream menu image...")
    print(f"  URL: {ICE_CREAM_MENU_IMAGE_URL}")
    image = download_image(ICE_CREAM_MENU_IMAGE_URL)
    
    if image:
        print(f"  [OK] Downloaded {image.size[0]}x{image.size[1]} image")
        print(f"  Extracting menu items from image...")
        items = extract_menu_from_image_with_gemini(image, "Ice Cream Menu", "Ice Cream Menu")
        all_items.extend(items)
        print(f"  [OK] Extracted {len(items)} items from ice cream menu")
    else:
        print("  [ERROR] Failed to download ice cream menu image")
    
    print(f"\n[OK] Extracted {len(all_items)} items total from all sources")
    
    return all_items


if __name__ == "__main__":
    items = scrape_uglyrooster()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "theuglyrooster_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

