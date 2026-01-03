"""
Scraper for Kindred Saratoga
Website: https://kindredsaratoga.com/
- Food Menu: PDF format
- Brunch Menu: PDF format
- Drink Menu: PDF format
"""

import requests
import json
import re
from typing import List, Dict
from pathlib import Path
import time
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


def extract_menu_from_pdf_with_gemini(pdf_path: str, menu_name: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    Extract menu items from PDF using Gemini Vision API by converting PDF pages to images.
    """
    if not GEMINI_AVAILABLE:
        print("  [ERROR] Gemini not available")
        return []
    
    if not PDF2IMAGE_AVAILABLE:
        print("  [ERROR] pdf2image not available. Install with: pip install pdf2image")
        return []
    
    all_items = []
    
    try:
        print(f"  Converting PDF pages to images for {menu_name}...")
        # Convert PDF pages to images
        images = convert_from_path(pdf_path, dpi=200)
        print(f"  [OK] Converted {len(images)} pages to images")
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Burrata Margherita", "Kindred Burger", "Wood-Fired Maitake Mushroom")
2. **description**: The description/ingredients/details for THIS specific item only
3. **price**: The price (e.g., "$19", "$24", "$38")
4. **menu_type**: The section/category name (e.g., "Flatbreads", "Salads", "Entrees", "Snacks", "Sandwiches", "Sides", "Cocktails", "Wine", "Beer")

Important guidelines:
- Extract ALL menu items from the page
- Item names are usually in larger/bolder font
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line in the right column
- If an item has no description, use empty string ""
- Include section headers in the menu_type field (like "Flatbreads", "Salads", "Entrees", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- Ensure all prices have a "$" symbol
- Group items by their section/category using the menu_type field
- For add-ons in parentheses like "(add grilled chicken - 6)" or "(add burrata - 6) (add shrimp - 9)", ALWAYS include them in the description field
- Format add-ons as: "Add-ons: add grilled chicken - $6 / add burrata - $6 / add shrimp - $9" (include ALL add-ons if multiple are listed)
- Add-ons are important information - never skip them
- Be careful to separate items correctly - each menu item should be its own entry

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Burrata Margherita",
    "description": "fresh basil, marinara",
    "price": "$19",
    "menu_type": "Flatbreads"
  }
]"""
        
        # Process each page
        for page_num, image in enumerate(images):
            print(f"  Processing page {page_num + 1}/{len(images)} with Gemini...")
            
            # Convert PIL image to bytes
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            image_data = img_byte_arr.read()
            
            try:
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
                
            except Exception as e:
                print(f"  [ERROR] Gemini API error on page {page_num + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Parse JSON from response
            response_text = re.sub(r'```json\s*', '', response_text)
            response_text = re.sub(r'```\s*', '', response_text)
            response_text = response_text.strip()
            
            try:
                page_items = json.loads(response_text)
                if isinstance(page_items, list):
                    for item in page_items:
                        if not item.get('menu_type'):
                            item['menu_type'] = menu_type_default
                    all_items.extend(page_items)
                    print(f"  [OK] Extracted {len(page_items)} items from page {page_num + 1}")
                else:
                    print(f"  [WARNING] Unexpected response format from Gemini on page {page_num + 1}")
            except json.JSONDecodeError as e:
                print(f"  [ERROR] Failed to parse JSON from Gemini response on page {page_num + 1}: {e}")
                print(f"  Response text (first 500 chars): {response_text[:500]}")
                continue
        
    except Exception as e:
        print(f"  [ERROR] Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
    
    return all_items


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 60, retries: int = 3) -> bool:
    """
    Download PDF from URL using requests.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/octet-stream,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    for attempt in range(retries):
        try:
            print(f"  Downloading: {pdf_url}")
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  [OK] Downloaded PDF: {output_path.name}")
            return True
            
        except Exception as e:
            print(f"  [ERROR] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
    
    return False


def scrape_kindredsaratoga_menu() -> List[Dict]:
    """
    Main function to scrape Food, Brunch, and Drink menus from PDFs.
    """
    all_items = []
    
    print("=" * 60)
    print("Scraping: Kindred Saratoga")
    print("=" * 60)
    
    # Create temp directory
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    # PDF URLs
    pdfs = [
        {
            'url': 'https://kindredsaratoga.com/wp-content/uploads/2025/12/Kindred-Food-Menu-11_28.pdf',
            'name': 'Food Menu',
            'type': 'Food',
            'filename': 'kindredsaratoga_food_menu.pdf'
        },
        {
            'url': 'https://kindredsaratoga.com/wp-content/uploads/2025/12/Brunch11__28.pdf',
            'name': 'Brunch Menu',
            'type': 'Brunch',
            'filename': 'kindredsaratoga_brunch_menu.pdf'
        },
        {
            'url': 'https://kindredsaratoga.com/wp-content/uploads/2025/12/Drink-Menu-11_28.pdf',
            'name': 'Drink Menu',
            'type': 'Drink',
            'filename': 'kindredsaratoga_drink_menu.pdf'
        }
    ]
    
    for idx, pdf_info in enumerate(pdfs, 1):
        print(f"\n[{idx}/{len(pdfs)}] Scraping {pdf_info['name']} (PDF)...")
        
        pdf_path = temp_dir / pdf_info['filename']
        
        if download_pdf_with_requests(pdf_info['url'], pdf_path):
            # Use Gemini for PDF extraction
            items = extract_menu_from_pdf_with_gemini(str(pdf_path), pdf_info['name'], menu_type_default=pdf_info['type'])
            
            for item in items:
                item['restaurant_name'] = "Kindred"
                item['restaurant_url'] = "https://kindredsaratoga.com/"
                item['menu_name'] = pdf_info['name']
            
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items from {pdf_info['name']}")
            
            # Keep PDFs for inspection - don't delete yet
            print(f"  PDF saved at: {pdf_path}")
        else:
            print(f"[ERROR] Failed to download {pdf_info['name']} PDF")
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    
    url_safe = "kindredsaratoga_com"
    output_json = output_dir / f'{url_safe}.json'
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")
    print("=" * 60)
    
    return all_items


if __name__ == '__main__':
    scrape_kindredsaratoga_menu()
