"""
Scraper for: https://www.fourseasonsnaturalfoods.com/
The menu is displayed as images, so we use Gemini Vision API to extract menu items
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
        
        # Determine MIME type based on file extension
        if image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
            mime_type = "image/jpeg"
        elif image_path.lower().endswith('.png'):
            mime_type = "image/png"
        else:
            mime_type = "image/jpeg"  # Default
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant/juice bar menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Green Smoothie", "Acai Bowl", "Fresh Juice")
2. **description**: The description/ingredients/details
3. **price**: The price (e.g., "$8.50", "$12.95")
4. **menu_type**: The section/category name (e.g., "Smoothies", "Juices", "Bowls", "Salads", "Sandwiches")

Important guidelines:
- Extract ALL menu items from the image, including smoothies, juices, bowls, salads, sandwiches, etc.
- Item names are usually in larger/bolder font
- Descriptions are usually in smaller font below the name
- Prices are usually at the end of the description line or on a separate line
- If an item has no description, use empty string ""
- Include section headers in the menu_type field (like "SMOOTHIES", "JUICES", "BOWLS", "SALADS", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- Ensure all prices have a "$" symbol
- Group items by their section/category using the menu_type field
- For juice bars, common sections include: Smoothies, Fresh Juices, Acai Bowls, Salads, Sandwiches, Wraps, etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Green Smoothie",
    "description": "Spinach, banana, mango, pineapple, coconut water",
    "price": "$8.50",
    "menu_type": "Smoothies"
  }
]"""
        
        print("  Extracting menu items using Gemini Vision API...")
        response = model.generate_content(
            [prompt, {
                "mime_type": mime_type,
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


def scrape_fourseasonsnaturalfoods_menu(url: str) -> List[Dict]:
    """
    Scrape menu from fourseasonsnaturalfoods.com
    The menu is displayed as images, so we extract them using Gemini Vision API
    """
    all_items = []
    restaurant_name = "Four Seasons Natural Foods"
    
    print(f"Scraping: {url}")
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use base URL for filename (remove /menu path)
    base_url = url.replace('/menu', '').rstrip('/')
    url_safe = base_url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    # Remove "www_" prefix if present
    if url_safe.startswith('www_'):
        url_safe = url_safe[4:]
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'cookie': 'crumb=BYSWyoILdeUyMDNiNWI1NTNhNTA0YTNlNzdlZGM5OWNmMzU2Yjcy; ss_cvr=d27274ef-6cb8-47ff-97d1-08b3cf835716|1767270784203|1767270784203|1767270784203|1; ss_cvt=1767270784203',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.fourseasonsnaturalfoods.com/buy-gift-card',
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
        
        # Parse HTML to find menu images
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find menu images - look for images with "MENU" in the URL or data-image attribute
        images = soup.find_all('img')
        menu_image_urls = []
        
        for img in images:
            # Check src attribute
            src = img.get('src', '')
            # Check data-image attribute (Squarespace uses this)
            data_image = img.get('data-image', '')
            
            # Look for menu-related images
            image_url = None
            if data_image and ('MENU' in data_image.upper() or 'menu' in data_image.lower()):
                image_url = data_image
            elif src and ('MENU' in src.upper() or 'menu' in src.lower()):
                image_url = src
            
            if image_url:
                # Make sure it's a full URL
                if image_url.startswith('http'):
                    menu_image_urls.append(image_url)
                elif image_url.startswith('//'):
                    menu_image_urls.append(f"https:{image_url}")
                else:
                    menu_image_urls.append(f"https://www.fourseasonsnaturalfoods.com{image_url}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in menu_image_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        if not unique_urls:
            print("[ERROR] Could not find menu images in HTML")
            return []
        
        print(f"Found {len(unique_urls)} menu image(s)\n")
        
        # Download and process each menu image
        temp_dir = Path(__file__).parent.parent / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        for i, menu_image_url in enumerate(unique_urls):
            print(f"Processing menu image {i+1}/{len(unique_urls)}...")
            print(f"  URL: {menu_image_url}\n")
            
            # Determine file extension
            if '.jpg' in menu_image_url.lower() or '.jpeg' in menu_image_url.lower():
                ext = '.jpg'
            elif '.png' in menu_image_url.lower():
                ext = '.png'
            else:
                ext = '.jpg'  # Default
            
            image_path = temp_dir / f'fourseasons_menu_{i+1}{ext}'
            
            if not download_image(menu_image_url, image_path):
                continue
            
            # Extract menu items from image using Gemini Vision API
            items = extract_menu_from_image(str(image_path))
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = "https://www.fourseasonsnaturalfoods.com/"
                    item['menu_name'] = f"Menu {i+1}" if len(unique_urls) > 1 else "Menu"
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items from image {i+1}\n")
            else:
                print(f"  [WARNING] No items extracted from image {i+1}\n")
            
            # Clean up temp image file
            try:
                image_path.unlink()
            except:
                pass
            
            # Add delay between API calls to avoid rate limiting
            if i < len(unique_urls) - 1:
                time.sleep(2)
        
        print(f"[OK] Extracted {len(all_items)} total items from all menu images\n")
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Deduplicate items based on name, description, price, and menu_type
    unique_items = []
    seen = set()
    for item in all_items:
        item_tuple = (item['name'], item['description'], item['price'], item['menu_type'])
        if item_tuple not in seen:
            unique_items.append(item)
            seen.add(item_tuple)
    
    # Save to JSON
    if unique_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(unique_items, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(unique_items)} unique items to: {output_json}")
    
    return unique_items


if __name__ == '__main__':
    url = "https://www.fourseasonsnaturalfoods.com/menu"
    scrape_fourseasonsnaturalfoods_menu(url)

