"""
Scraper for Thirsty Owl Saratoga (thirstyowlsaratoga.com)
Scrapes menu from images in HTML
Handles: multi-price, multi-size, and add-ons using Gemini Vision API
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup
import requests
import google.generativeai as genai
from PIL import Image
import io
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


RESTAURANT_NAME = "Thirsty Owl Saratoga"
RESTAURANT_URL = "http://www.thirstyowlsaratoga.com/"

MENU_URL = "https://www.thirstyowlsaratoga.com/menus"

# Load Gemini API key from config
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)
    GEMINI_API_KEY = config.get("gemini_api_key")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def fetch_menu_html() -> Optional[str]:
    """Fetch menu HTML"""
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.thirstyowlsaratoga.com/our-wines-1',
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
    
    cookies = {
        'crumb': 'BarJaDsAOSL4YTRmYWViNWFjMGNlMDg2YzA0NmRiMDAxZGRlNjli',
        'ss_cvr': 'dd2edec9-07d2-4bf7-9c61-d37164814060|1767766932968|1767766932968|1767766932968|1',
        'ss_cvt': '1767766932968',
        '_gid': 'GA1.2.1014627409.1767766933',
        '_gat_gtag_UA_139759539_1': '1',
        '_ga_2X2Y9MKM5V': 'GS2.1.s1767766933$o1$g1$t1767766977$j16$l0$h0',
        '_ga': 'GA1.2.968222235.1767766933'
    }
    
    try:
        response = requests.get(MENU_URL, headers=headers, cookies=cookies, verify=False)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to fetch menu: {e}")
        return None


def extract_menu_image_urls(html: str) -> List[str]:
    """Extract menu image URLs from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    images = soup.find_all('img')
    
    menu_image_urls = []
    seen_urls = set()
    
    for img in images:
        # Try src first, then data-src
        src = img.get('src', '') or img.get('data-src', '')
        alt = img.get('alt', '').lower()
        
        # Skip logo images
        if 'logo' in alt or 'logo' in src.lower():
            continue
        
        # Look for menu-related images (not logos)
        if src and ('squarespace-cdn.com' in src or 'static1.squarespace.com' in src) and 'logo' not in src.lower():
            # Make sure URL is complete
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = 'https://www.thirstyowlsaratoga.com' + src
            
            # Remove duplicates
            if src not in seen_urls:
                seen_urls.add(src)
                menu_image_urls.append(src)
    
    return menu_image_urls


def download_image(url: str, output_path: Path) -> bool:
    """Download an image from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download image {url}: {e}")
        return False


def extract_menu_from_images_with_gemini(image_paths: List[Path]) -> List[Dict]:
    """Extract menu items from images using Gemini Vision API"""
    if not GEMINI_API_KEY:
        print("[ERROR] Gemini API key not found in config.json")
        return []
    
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    all_items = []
    
    for image_path in image_paths:
        print(f"  Processing image: {image_path.name}")
        
        try:
            # Load image
            img = Image.open(image_path)
            
            # Create prompt
            prompt = """Extract all menu items from this restaurant menu image. Return a JSON array of menu items.

For each menu item, provide:
- name: The item name (required)
- description: The item description if available (can be null)
- price: The price(s). If there are multiple prices for different sizes (e.g., Small $X, Large $Y), format as "Small $X | Large $Y". If there are multiple prices for different options (e.g., Chicken $X, Steak $Y), format as "Chicken $X | Steak $Y". If there's only one price, just provide "$X.XX"
- section: The menu section/category this item belongs to (e.g., "Appetizers", "Entrees", "Desserts", "Lunch", "Dinner", "Cocktails", "Wine", etc.)

IMPORTANT:
- If an item has multiple sizes with different prices, include the size in the price field (e.g., "Small $5.99 | Medium $7.99 | Large $9.99")
- If an item has multiple options with different prices (like chicken vs steak), include the option in the price field (e.g., "Chicken $12.99 | Steak $15.99")
- If there are add-ons or extras available for an item, include them in the description field (e.g., "Add bacon +$2, Add cheese +$1")
- Group items by their main section/category
- Return ONLY valid JSON, no markdown formatting, no code blocks

Return format:
[
  {
    "name": "Item Name",
    "description": "Item description with any add-ons mentioned",
    "price": "$X.XX" or "Size1 $X.XX | Size2 $Y.YY" or "Option1 $X.XX | Option2 $Y.YY",
    "section": "Section Name"
  }
]"""
            
            # Generate content
            response = model.generate_content([prompt, img])
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r'\s*```\s*$', '', response_text, flags=re.MULTILINE)
            
            # Parse JSON
            items = json.loads(response_text)
            
            if isinstance(items, list):
                print(f"    Extracted {len(items)} items")
                all_items.extend(items)
            else:
                print(f"    [WARNING] Unexpected response format")
                
        except json.JSONDecodeError as e:
            print(f"    [ERROR] Failed to parse JSON: {e}")
            print(f"    Response text: {response_text[:500]}...")
        except Exception as e:
            print(f"    [ERROR] Failed to process image: {e}")
            import traceback
            traceback.print_exc()
    
    return all_items


def scrape_thirstyowlsaratoga() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
    all_items = []
    
    print("\n[1] Fetching menu HTML...")
    html = fetch_menu_html()
    
    if not html:
        print("[ERROR] Failed to fetch menu")
        return []
    
    print(f"[OK] Received {len(html)} characters")
    
    print("\n[2] Extracting menu image URLs...")
    image_urls = extract_menu_image_urls(html)
    print(f"[OK] Found {len(image_urls)} unique menu images")
    
    if not image_urls:
        print("[ERROR] No menu images found")
        return []
    
    # Download images
    print("\n[3] Downloading menu images...")
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    image_paths = []
    for i, url in enumerate(image_urls):
        print(f"  Downloading image {i+1}/{len(image_urls)}...")
        # Determine file extension from URL
        ext = '.jpg'
        if '.png' in url.lower():
            ext = '.png'
        elif '.jpeg' in url.lower():
            ext = '.jpeg'
        
        image_path = temp_dir / f"thirstyowl_menu_{i+1}{ext}"
        
        if download_image(url, image_path):
            image_paths.append(image_path)
            print(f"    [OK] Saved to {image_path.name}")
        else:
            print(f"    [ERROR] Failed to download")
    
    if not image_paths:
        print("[ERROR] No images downloaded")
        return []
    
    print(f"\n[OK] Downloaded {len(image_paths)} images")
    
    # Extract menu items using Gemini
    print("\n[4] Extracting menu items with Gemini Vision API...")
    items = extract_menu_from_images_with_gemini(image_paths)
    
    # Format items
    for item in items:
        item['restaurant_name'] = RESTAURANT_NAME
        item['restaurant_url'] = RESTAURANT_URL
        item['menu_type'] = "Menu"
        item['menu_name'] = item.get('section', 'Menu')
    
    all_items.extend(items)
    
    print(f"\n[OK] Extracted {len(all_items)} items total")
    
    return all_items


if __name__ == "__main__":
    items = scrape_thirstyowlsaratoga()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "thirstyowlsaratoga_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

