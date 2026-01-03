"""
Scraper for kickstartcoffeecompany.com
Menu is provided as images on the menu page
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


def download_html_with_requests(url: str) -> str:
    """Download HTML from URL"""
    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://kickstartcoffeecompany.com/"
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
            "Referer": "https://kickstartcoffeecompany.com/"
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


def extract_menu_from_image_with_gemini(image_path: str, menu_type: str = "Menu") -> List[Dict]:
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
1. **name**: The dish/item name (e.g., "Drip", "Latte", "Avocado Toast", "Classic BLT")
2. **description**: The description/ingredients/notes (e.g., "Scrambled eggs, shaved steak, peppers & onions, swiss cheese & chipotle aioli served on ciabatta")
3. **price**: The price (e.g., "$1.75", "$4.00", "$10", "Starting at $7")
4. **menu_type**: The category/section (e.g., "Coffee", "Espresso", "Breakfast", "Lunch", "Teas", "Other")

CRITICAL PRICING RULES:
- Extract prices exactly as shown (e.g., "$1.75", "$4.00", "MP" for market price)
- If multiple prices exist (e.g., "8oz - $4.00 / 12oz - $4.25"), create separate items or combine with labels
- If a section has a general price note (e.g., "Starting at $7", "All pricing starts at 8oz & increases by 25c each size"), include this in the description or as a note
- Handle size variations (e.g., "8oz, 12oz, 16oz, 20oz") - these should be noted in the description or price field
- Handle add-ons with prices (e.g., "Croissant (+$2.50)", "Steak (+$1)") - include the add-on price in the item description

Important guidelines:
- Extract ALL menu items from the image, including drinks, food items, flavors, sizes, etc.
- Item names are usually in larger/bolder font
- Descriptions include ingredients, preparation notes, etc.
- Prices are usually at the end of the line or in a separate column
- If an item has no description, use empty string ""
- Skip section headers as items (like "COFFEE", "BREAKFAST", "LUNCH") but note them as menu_type
- Handle "Build Your Own" sections - extract the base price and list options in description
- For flavor lists, create items for each flavor with appropriate pricing notes
- Handle seasonal specials separately

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.

Example output format:
[
  {
    "name": "Drip",
    "description": "",
    "price": "$1.75",
    "menu_type": "Coffee"
  },
  {
    "name": "Latte",
    "description": "",
    "price": "$4.00",
    "menu_type": "Espresso"
  },
  {
    "name": "At The Steak",
    "description": "Scrambled eggs, shaved steak, peppers & onions, swiss cheese & chipotle aioli served on ciabatta",
    "price": "$10",
    "menu_type": "Breakfast"
  },
  {
    "name": "Vanilla",
    "description": "Flavor option (+35c)",
    "price": "",
    "menu_type": "Flavors"
  }
]"""
        
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


def scrape_menu_images(html: str) -> List[Dict]:
    """Extract menu items from menu page images"""
    all_items = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all images on the page - focus on images in figure tags or main content
    images = soup.find_all('img')
    
    # Create temp directory for images
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    menu_images = []
    for img in images:
        src = img.get('src', '') or img.get('data-src', '') or img.get('data-lazy-src', '')
        if not src:
            continue
        
        # Make URL absolute if relative
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = 'https://kickstartcoffeecompany.com' + src
        elif not src.startswith('http'):
            continue
        
        # Skip common non-menu images
        if any(skip in src.lower() for skip in ['logo', 'icon', 'avatar', 'profile', 'social', 'facebook', 'instagram', 'twitter']):
            continue
        
        # Prioritize images in figure tags (these are likely the main menu images)
        parent = img.find_parent(['figure', 'article', 'main', 'div', 'section'])
        if parent:
            parent_tag = parent.name if hasattr(parent, 'name') else ''
            # If in a figure tag, it's likely a menu image
            if parent_tag == 'figure':
                menu_images.append(src)
                continue
            
            parent_class = parent.get('class', [])
            parent_id = parent.get('id', '')
            parent_text = parent.get_text().lower()
            if any(keyword in str(parent_class).lower() + str(parent_id).lower() + parent_text for keyword in ['menu', 'content', 'main', 'page', 'coffee', 'breakfast', 'lunch', 'tea']):
                menu_images.append(src)
        else:
            # If no parent context, include if it looks like a menu image
            if any(keyword in src.lower() for keyword in ['menu', 'coffee', 'breakfast', 'lunch', 'tea', 'food', 'drink']):
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
    
    # If we found images in figure tags, use only those (they're the main menu images)
    figure_images = []
    for img in soup.find_all('img'):
        if img.find_parent('figure'):
            src = img.get('src', '') or img.get('data-src', '') or img.get('data-lazy-src', '')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = 'https://kickstartcoffeecompany.com' + src
                if src.startswith('http') and src not in seen:
                    figure_images.append(src)
    
    if figure_images:
        unique_images = figure_images
        print(f"  Found {len(unique_images)} menu images in figure tags")
    
    if not unique_images:
        print("  [WARNING] No menu images found on page")
        print("  [INFO] Trying to extract all images as potential menu images...")
        # Fallback: get all images except obvious non-menu ones
        for img in images:
            src = img.get('src', '') or img.get('data-src', '') or img.get('data-lazy-src', '')
            if not src:
                continue
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = 'https://kickstartcoffeecompany.com' + src
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
    
    # Menu type names based on image order/content (will be determined by Gemini)
    menu_types = ["Coffee Menu", "Breakfast & Lunch Menu", "Tea Menu"]
    
    for idx, img_url in enumerate(unique_images):
        # Determine file extension from URL or use png
        ext = 'png'
        if '.' in img_url:
            ext = img_url.split('.')[-1].split('?')[0].lower()
            if ext not in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                ext = 'png'
        
        image_path = temp_dir / f'menu_{idx + 1}.{ext}'
        
        menu_type = menu_types[idx] if idx < len(menu_types) else f"Menu {idx + 1}"
        
        print(f"  Downloading image {idx + 1}/{len(unique_images)}: {img_url[:80]}...")
        if download_image_with_requests(img_url, image_path):
            print(f"  Extracting menu items from image {idx + 1} ({menu_type})...")
            items = extract_menu_from_image_with_gemini(str(image_path), menu_type)
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


def scrape_kickstartcoffeecompany_menu() -> List[Dict]:
    """
    Main function to scrape all menus from kickstartcoffeecompany.com
    """
    all_items = []
    restaurant_name = "Kickstart Coffee Company"
    restaurant_url = "https://kickstartcoffeecompany.com/"
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    output_json = output_dir / 'kickstartcoffeecompany_com.json'
    
    print("=" * 60)
    print("SCRAPING KICKSTART COFFEE COMPANY MENUS")
    print("=" * 60)
    print(f"Output file: {output_json}\n")
    
    # Scrape menu from images
    print("=" * 60)
    print("Scraping Menu (Images)")
    print("=" * 60)
    
    try:
        menu_url = "https://kickstartcoffeecompany.com/menu"
        print(f"Downloading HTML from: {menu_url}")
        
        html = download_html_with_requests(menu_url)
        
        if not html:
            print("[ERROR] Failed to download menu page")
        else:
            print(f"[OK] Downloaded {len(html)} characters\n")
            
            print("Extracting menu items from images...")
            items = scrape_menu_images(html)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                    if not item.get('menu_name'):
                        item['menu_name'] = "Menu"
                all_items.extend(items)
                print(f"[OK] Extracted {len(items)} items from menu\n")
            else:
                print("[WARNING] No items extracted from menu\n")
    
    except Exception as e:
        print(f"[ERROR] Error during menu scraping: {e}")
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
    scrape_kickstartcoffeecompany_menu()

