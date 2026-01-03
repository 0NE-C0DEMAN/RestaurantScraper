"""
Scraper for: https://hattiesrestaurants.com/
The menu is displayed as multiple PDFs (Brunch, Dinner, All Day Menu), so we download them and extract menu items using Gemini Vision API
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


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 120, retries: int = 3) -> bool:
    """Download PDF from URL using requests with proper headers"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'referer': 'https://hattiesrestaurants.com/menu-locations/',
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
    
    for attempt in range(retries):
        try:
            print(f"  Downloading PDF from: {pdf_url}")
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Get content length for progress reporting
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            if downloaded % (1024 * 1024) < 8192:  # Print every MB
                                print(f"  Progress: {downloaded / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB ({percent:.1f}%)")
            
            # Verify the file is a valid PDF
            with open(output_path, 'rb') as f:
                first_bytes = f.read(4)
                if first_bytes != b'%PDF':
                    print(f"  [WARNING] Downloaded file does not appear to be a valid PDF")
                    return False
            
            file_size = output_path.stat().st_size
            print(f"  [OK] PDF saved: {output_path.name} ({file_size / (1024 * 1024):.1f} MB)")
            return True
            
        except requests.exceptions.Timeout:
            print(f"  [ERROR] Attempt {attempt + 1}/{retries} timed out after {timeout}s")
            if attempt < retries - 1:
                print(f"  Retrying in 2 seconds...")
                time.sleep(2)
                continue
        except Exception as e:
            print(f"  [ERROR] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                print(f"  Retrying in 2 seconds...")
                time.sleep(2)
                continue
    
    return False


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
        
        prompt = f"""Analyze this restaurant menu PDF page ({menu_name}) and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name ONLY (e.g., "Fried Chicken", "Steak", "Burger") - DO NOT include prices or section headers in the name
2. **description**: The description/ingredients/details for THIS specific item only
3. **price**: The price MUST be in the price field (e.g., "$17", "$19", "$25") - ALWAYS extract the price, even if it appears after the name or in parentheses
4. **menu_type**: The section/category name ONLY (e.g., "STARTERS", "MAINS", "SIDES", "DESSERTS", "DRINKS", "BRUNCH", "DINNER") - DO NOT include prices in menu_type

CRITICAL PRICE EXTRACTION RULES:
- Prices can appear: after the item name (e.g., "ITEM NAME $25"), at the end of a line, in parentheses, or after bullet points
- If you see "Mocktails • 10" or "Section Name • $10", extract "$10" as the price, NOT as part of menu_type
- If price appears in parentheses like "(Mocktails • 10)", extract "$10" as the price
- ALWAYS put the price in the "price" field with "$" symbol
- If an item has no visible price, use empty string "" for price
- NEVER put prices in the menu_type field - menu_type should ONLY contain the section/category name

Important guidelines:
- Extract ALL menu items from the page
- Item names are usually in ALL CAPS or Title Case
- Each item must have: name, description (can be empty), price (can be empty if not visible), and menu_type
- Prices are usually at the end of the item name line (after dots) or on a separate line
- If an item has no description, use empty string ""
- Include section headers in the menu_type field (like "STARTERS", "MAINS", "SIDES", "BRUNCH", "DINNER", etc.) - but WITHOUT prices
- Skip footer text (address, phone, website, etc.)
- Handle items that appear on the same line correctly - each should have its own entry
- Ensure all prices have a "$" symbol
- Group items by their section/category using the menu_type field
- For this menu type ({menu_name}), common sections include: STARTERS, APPETIZERS, MAINS, ENTREES, SIDES, DESSERTS, DRINKS, BRUNCH ITEMS, etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Fried Chicken",
    "description": "Southern fried chicken with mashed potatoes and gravy",
    "price": "$22",
    "menu_type": "MAINS"
  }}
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
                        menu_type = str(item.get('menu_type', menu_type_default)).strip()
                        name = str(item.get('name', '')).strip()
                        
                        # Fix price if it's missing but appears in menu_type (e.g., "Mocktails • 10")
                        if not price or price == '':
                            # Try to extract price from menu_type (e.g., "Mocktails • 10" -> "$10")
                            price_match = re.search(r'[•·]\s*\$?(\d+(?:\.\d+)?)', menu_type)
                            if price_match:
                                price = f"${price_match.group(1)}"
                                # Clean menu_type to remove price
                                menu_type = re.sub(r'\s*[•·]\s*\$?\d+(?:\.\d+)?\s*', '', menu_type).strip()
                        
                        # Try to extract price from name if still missing
                        if not price or price == '':
                            price_match = re.search(r'\$(\d+(?:\.\d+)?)', name)
                            if price_match:
                                price = f"${price_match.group(1)}"
                                # Remove price from name
                                name = re.sub(r'\s*\$\d+(?:\.\d+)?\s*', '', name).strip()
                        
                        # Ensure price has $ symbol if it exists
                        if price and not price.startswith('$'):
                            # Check if it's a number
                            if re.match(r'^\d+(?:\.\d+)?$', price):
                                price = f"${price}"
                        
                        cleaned_item = {
                            'name': name,
                            'description': str(item.get('description', '')).strip(),
                            'price': price,
                            'menu_type': menu_type,
                            'menu_name': menu_name
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
                                menu_type = str(item.get('menu_type', menu_type_default)).strip()
                                name = str(item.get('name', '')).strip()
                                
                                # Fix price if it's missing but appears in menu_type
                                if not price or price == '':
                                    price_match = re.search(r'[•·]\s*\$?(\d+(?:\.\d+)?)', menu_type)
                                    if price_match:
                                        price = f"${price_match.group(1)}"
                                        menu_type = re.sub(r'\s*[•·]\s*\$?\d+(?:\.\d+)?\s*', '', menu_type).strip()
                                
                                # Try to extract price from name if still missing
                                if not price or price == '':
                                    price_match = re.search(r'\$(\d+(?:\.\d+)?)', name)
                                    if price_match:
                                        price = f"${price_match.group(1)}"
                                        name = re.sub(r'\s*\$\d+(?:\.\d+)?\s*', '', name).strip()
                                
                                # Ensure price has $ symbol if it exists
                                if price and not price.startswith('$'):
                                    if re.match(r'^\d+(?:\.\d+)?$', price):
                                        price = f"${price}"
                                
                                cleaned_item = {
                                    'name': name,
                                    'description': str(item.get('description', '')).strip(),
                                    'price': price,
                                    'menu_type': menu_type,
                                    'menu_name': menu_name
                                }
                                if cleaned_item['name']:
                                    all_items.append(cleaned_item)
                        print(f"  [OK] Successfully extracted {len(menu_items)} items after retry")
                    except:
                        pass
        
        print(f"  [OK] Extracted {len(all_items)} total items from {menu_name} using Gemini")
        return all_items
        
    except Exception as e:
        print(f"  [ERROR] Error processing PDF with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return []


def fix_item_prices(items: List[Dict]) -> List[Dict]:
    """
    Post-process items to fix prices that might be in menu_type or name fields.
    """
    fixed_items = []
    for item in items:
        price = str(item.get('price', '')).strip()
        menu_type = str(item.get('menu_type', '')).strip()
        name = str(item.get('name', '')).strip()
        
        # Fix price if it's missing but appears in menu_type (e.g., "Mocktails • 10")
        if not price or price == '':
            # Try to extract price from menu_type (e.g., "Mocktails • 10" -> "$10")
            price_match = re.search(r'[•·]\s*\$?(\d+(?:\.\d+)?)', menu_type)
            if price_match:
                price = f"${price_match.group(1)}"
                # Clean menu_type to remove price
                menu_type = re.sub(r'\s*[•·]\s*\$?\d+(?:\.\d+)?\s*', '', menu_type).strip()
        
        # Try to extract price from name if still missing
        if not price or price == '':
            price_match = re.search(r'\$(\d+(?:\.\d+)?)', name)
            if price_match:
                price = f"${price_match.group(1)}"
                # Remove price from name
                name = re.sub(r'\s*\$\d+(?:\.\d+)?\s*', '', name).strip()
        
        # Ensure price has $ symbol if it exists
        if price and not price.startswith('$'):
            # Check if it's a number
            if re.match(r'^\d+(?:\.\d+)?$', price):
                price = f"${price}"
        
        # Update item with fixed values
        item['price'] = price
        item['menu_type'] = menu_type
        item['name'] = name
        
        fixed_items.append(item)
    
    return fixed_items


def scrape_hatties_menu(url: str) -> List[Dict]:
    """
    Scrape menu from hattiesrestaurants.com
    The menu is displayed as multiple PDFs (Brunch, Dinner, All Day Menu)
    """
    all_items = []
    restaurant_name = "Hattie's Restaurant"
    restaurant_url = "https://hattiesrestaurants.com/"
    
    print("=" * 60)
    print(f"Scraping: {url}")
    print("=" * 60)
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output filename
    url_safe = url.replace('https://', '').replace('http://', '').replace('www.', '').replace('/', '_').replace('.', '_').rstrip('_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    # Define the three PDF menus
    pdf_menus = [
        {
            'url': 'https://hattiesrestaurants.com/wp-content/uploads/2025/12/Hatties-Saratoga-Springs-Brunch-Winter-Menu-2025.pdf',
            'name': 'Brunch Menu'
        },
        {
            'url': 'https://hattiesrestaurants.com/wp-content/uploads/2025/12/Hatties-Saratoga-Springs-Dinner-Winter-Menu-2025.pdf',
            'name': 'Dinner Menu'
        },
        {
            'url': 'https://hattiesrestaurants.com/wp-content/uploads/2025/11/Hatties-Wilton-Menu-2025.pdf',
            'name': 'All Day Menu'
        }
    ]
    
    try:
        temp_dir = Path(__file__).parent.parent / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Download and process each PDF menu
        for menu_idx, menu_info in enumerate(pdf_menus):
            pdf_url = menu_info['url']
            menu_name = menu_info['name']
            
            print(f"[{menu_idx + 1}/{len(pdf_menus)}] Processing {menu_name}...")
            
            # Download PDF
            pdf_filename = f"hatties_{menu_name.lower().replace(' ', '_')}.pdf"
            pdf_path = temp_dir / pdf_filename
            
            if not download_pdf_with_requests(pdf_url, pdf_path):
                print(f"[ERROR] Failed to download {menu_name}")
                continue
            
            print(f"[OK] {menu_name} downloaded\n")
            
            # Extract menu items from PDF using Gemini
            print(f"Extracting menu items from {menu_name} using Gemini Vision API...")
            items = extract_menu_from_pdf_with_gemini(str(pdf_path), menu_name)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                all_items.extend(items)
                print(f"[OK] Extracted {len(items)} items from {menu_name}\n")
            else:
                print(f"[WARNING] No items extracted from {menu_name}\n")
            
            # Clean up temp PDF file
            try:
                pdf_path.unlink()
            except:
                pass
            
            # Add delay between menus to avoid rate limiting
            if menu_idx < len(pdf_menus) - 1:
                time.sleep(2)
        
        # Post-process items to fix prices
        print(f"\nPost-processing items to fix price extraction issues...")
        all_items = fix_item_prices(all_items)
        fixed_count = sum(1 for item in all_items if item.get('price') and item.get('price') != '')
        print(f"[OK] Fixed prices: {fixed_count}/{len(all_items)} items now have prices")
        
        # Deduplicate items based on name, description, price, and menu_type
        unique_items = []
        seen = set()
        for item in all_items:
            item_tuple = (item['name'], item['description'], item['price'], item['menu_type'], item.get('menu_name', ''))
            if item_tuple not in seen:
                unique_items.append(item)
                seen.add(item_tuple)
        
        print(f"[OK] Extracted {len(unique_items)} unique items from all menus\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        unique_items = []
    
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
    url = "https://hattiesrestaurants.com/"
    scrape_hatties_menu(url)

