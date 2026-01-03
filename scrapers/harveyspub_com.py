"""
Scraper for: http://harveyspub.com/
The menu is displayed as a PDF in a canvas, so we download the PDF and extract menu items using Gemini Vision API
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


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 60, retries: int = 3) -> bool:
    """Download PDF from URL using requests with the provided headers"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'cookie': 'PHPSESSID=532de832cb479cee24e1ad852d0e4321',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://harveyspub.com/',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    for attempt in range(retries):
        try:
            print(f"  Downloading PDF from: {pdf_url}")
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  [OK] PDF saved to: {output_path}")
            return True
            
        except Exception as e:
            print(f"  [ERROR] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
    
    return False


def extract_menu_from_pdf_with_gemini(pdf_path: str, menu_type_default: str = "Menu") -> List[Dict]:
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
        print("  Converting PDF pages to images...")
        # Convert PDF pages to images
        images = convert_from_path(pdf_path, dpi=200)
        print(f"  [OK] Converted {len(images)} pages to images")
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Irish Nachos", "Steak", "Burger")
2. **description**: The description/ingredients/details for THIS specific item only
3. **price**: The price (e.g., "$17", "$19", "$25")
4. **menu_type**: The section/category name (e.g., "STARTERS", "MAINS", "SIDES", "DESSERTS", "DRINKS")

Important guidelines:
- Extract ALL menu items from the page
- Item names are usually in ALL CAPS or Title Case
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line (after dots) or on a separate line
- If an item has no description, use empty string ""
- Include section headers in the menu_type field (like "STARTERS", "MAINS", "SIDES", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle items that appear on the same line correctly - each should have its own entry
- Ensure all prices have a "$" symbol
- Group items by their section/category using the menu_type field
- For pubs/restaurants, common sections include: STARTERS, APPETIZERS, MAINS, ENTREES, SIDES, DESSERTS, DRINKS, etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Irish Nachos",
    "description": "Seasoned waffle fries topped with corned beef, pepper jack cheese, jalapenos, pico de gallo. Get a half order for 12.",
    "price": "$17",
    "menu_type": "STARTERS"
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
                response_text = response_text.encode('utf-8', errors='ignore').decode('utf-8')
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
                            'menu_type': str(item.get('menu_type', menu_type_default)).strip()
                        }
                        if cleaned_item['name']:
                            all_items.append(cleaned_item)
                
                print(f"  [OK] Extracted {len(menu_items)} items from page {page_num + 1}")
                
            except json.JSONDecodeError as e:
                print(f"  [WARNING] Could not parse JSON from Gemini response on page {page_num + 1}: {e}")
                print(f"  Response text (first 500 chars): {response_text[:500]}")
                # Try to extract JSON from markdown code blocks
                json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response_text, re.DOTALL)
                if json_match:
                    try:
                        menu_items = json.loads(json_match.group(1))
                        for item in menu_items:
                            if isinstance(item, dict):
                                price = str(item.get('price', '')).strip()
                                if price and not price.startswith('$'):
                                    price = f"${price}"
                                
                                cleaned_item = {
                                    'name': str(item.get('name', '')).strip(),
                                    'description': str(item.get('description', '')).strip(),
                                    'price': price,
                                    'menu_type': str(item.get('menu_type', menu_type_default)).strip()
                                }
                                if cleaned_item['name']:
                                    all_items.append(cleaned_item)
                        print(f"  [OK] Successfully extracted {len(menu_items)} items after retry")
                    except:
                        pass
        
        print(f"  [OK] Extracted {len(all_items)} total items from PDF using Gemini")
        return all_items
        
    except Exception as e:
        print(f"  [ERROR] Error processing PDF with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_harveyspub_menu(url: str) -> List[Dict]:
    """
    Scrape menu from harveyspub.com
    The menu is displayed as a PDF in a canvas, so we download the PDF and extract menu items
    """
    all_items = []
    restaurant_name = "Harvey's Restaurant and Bar"
    restaurant_url = "https://harveyspub.com/"
    
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
        # PDF URL is known - use it directly
        pdf_url = "https://harveyspub.com/wp-content/uploads/2025/12/Harveys-Menu-Fall-Winter-25-1.pdf"
        
        print("[1/3] Downloading PDF menu...")
        temp_dir = Path(__file__).parent.parent / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_path = temp_dir / 'harveyspub_menu.pdf'
        
        if not download_pdf_with_requests(pdf_url, pdf_path):
            print("[ERROR] Failed to download PDF")
            return []
        
        print(f"[OK] PDF downloaded\n")
        
        # Extract menu items from PDF using Gemini
        print("[2/3] Extracting menu items from PDF using Gemini Vision API...")
        all_items = extract_menu_from_pdf_with_gemini(str(pdf_path))
        
        if all_items:
            for item in all_items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "Menu"
        
        print(f"[OK] Extracted {len(all_items)} items from PDF\n")
        
        # Clean up temp PDF file
        try:
            pdf_path.unlink()
        except:
            pass
        
        # Deduplicate items based on name, description, price, and menu_type
        unique_items = []
        seen = set()
        for item in all_items:
            item_tuple = (item['name'], item['description'], item['price'], item['menu_type'])
            if item_tuple not in seen:
                unique_items.append(item)
                seen.add(item_tuple)
        
        print(f"[OK] Extracted {len(unique_items)} unique items from PDF\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # If no items extracted, return empty list
    if not all_items:
        unique_items = []
    else:
        # Deduplicate items based on name, description, price, and menu_type
        unique_items = []
        seen = set()
        for item in all_items:
            item_tuple = (item['name'], item['description'], item['price'], item['menu_type'])
            if item_tuple not in seen:
                unique_items.append(item)
                seen.add(item_tuple)
    
    # Save to JSON
    print(f"[3/3] Saving results...")
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
    url = "https://harveyspub.com/"
    scrape_harveyspub_menu(url)
