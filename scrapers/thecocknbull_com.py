"""
Scraper for: https://www.thecocknbull.com/
The menu is displayed as an image, so we use Gemini Vision API to extract menu items
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


def download_image(image_url: str, output_path: Path, timeout: int = 60) -> bool:
    """Download menu image from URL"""
    try:
        print(f"  Downloading menu image from: {image_url}")
        response = requests.get(image_url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"  [OK] Image saved to: {output_path}")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download image: {e}")
        return False


def extract_menu_from_image(image_path: str) -> List[Dict]:
    """
    Extract menu items from menu image using Gemini Vision API.
    """
    if not GEMINI_AVAILABLE:
        return []
    
    try:
        # Read image file
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Steak", "Salmon", "Chicken")
2. **description**: The description/ingredients/details
3. **price**: The price (e.g., "$28", "$15.95")
4. **menu_type**: The section/category name (e.g., "Appetizers", "Entrees", "Desserts", "Drinks")

Important guidelines:
- Extract ALL menu items from the image, including appetizers, entrees, sides, desserts, drinks, etc.
- Item names are usually in larger/bolder font
- Descriptions are usually in smaller font below the name
- Prices are usually at the end of the description line or on a separate line
- If an item has no description, use empty string ""
- Include section headers in the menu_type field (like "APPETIZERS", "ENTRÉES", "DINNER", "DESSERTS", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- Ensure all prices have a "$" symbol
- Group items by their section/category using the menu_type field

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Steak Frites",
    "description": "Grilled steak with french fries",
    "price": "$28",
    "menu_type": "Entrees"
  }
]"""
        
        print("  Extracting menu items using Gemini Vision API...")
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
            
            cleaned_items = []
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
                        cleaned_items.append(cleaned_item)
            
            return cleaned_items
            
        except json.JSONDecodeError as e:
            print(f"  [WARNING] Could not parse JSON from Gemini response: {e}")
            print(f"  Response text: {response_text[:500]}")
            return []
        
    except Exception as e:
        print(f"  [ERROR] Error processing image: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_thecocknbull_menu(url: str) -> List[Dict]:
    """
    Scrape menu from thecocknbull.com
    The menu is displayed as an image, so we extract it using Gemini Vision API
    """
    all_items = []
    restaurant_name = "The Cock 'n Bull"
    
    print(f"Scraping: {url}")
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    # Remove 'www_' prefix and 'menu' if present
    if url_safe.startswith('www_'):
        url_safe = url_safe[4:]
    url_safe = url_safe.replace('_menu', '')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'cookie': 'crumb=BUyrtUsImytDOWU2ODNhYWFkODY2ZGU5ZDBlMTZiNjhkY2M5YTRj; ss_cvr=ad9dfd39-cf27-4368-a272-1dab43d5858e|1767251186883|1767251186883|1767253145111|2; ss_cvt=1767253145111',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.thecocknbull.com/',
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
        # Fetch HTML page
        print("Fetching menu page HTML...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        print(f"[OK] Received HTML content\n")
        
        # Parse HTML to find menu image
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find menu images - look for images with "menu" or "dinner" in the URL
        images = soup.find_all('img')
        menu_image_url = None
        
        for img in images:
            src = img.get('src', '')
            if src and ('menu' in src.lower() or 'dinner' in src.lower() or 'Menu' in src):
                # Make sure it's a full URL
                if src.startswith('http'):
                    menu_image_url = src
                elif src.startswith('//'):
                    menu_image_url = f"https:{src}"
                else:
                    menu_image_url = f"https://www.thecocknbull.com{src}"
                break
        
        if not menu_image_url:
            print("[ERROR] Could not find menu image in HTML")
            return []
        
        print(f"Found menu image: {menu_image_url}\n")
        
        # Download the image
        temp_dir = Path(__file__).parent.parent / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        image_path = temp_dir / 'cocknbull_menu.png'
        
        if not download_image(menu_image_url, image_path):
            return []
        
        # Extract menu items from image using Gemini Vision API
        items = extract_menu_from_image(str(image_path))
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = url
                item['menu_name'] = "Menu"
            all_items.extend(items)
        
        print(f"\n[OK] Extracted {len(all_items)} items from menu\n")
        
        # Clean up temp image file
        try:
            image_path.unlink()
        except:
            pass
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Save to JSON
    print(f"Saved {len(all_items)} items to: {output_json}\n")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    return all_items


if __name__ == '__main__':
    menu_url = "https://www.thecocknbull.com/menu"
    scrape_thecocknbull_menu(menu_url)

