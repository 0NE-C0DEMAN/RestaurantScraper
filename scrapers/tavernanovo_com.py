"""
Scraper for Taverna Novo (tavernanovo.com)
Scrapes menu from images and PDFs using Gemini Vision API
Handles: Fall and Winter Menu, Craft Cocktail Offerings, Wine and Beer Offerings (PDF)
"""

import json
import re
import requests
from pathlib import Path
from typing import List, Dict, Optional
from io import BytesIO
from bs4 import BeautifulSoup

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

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed. Install with: pip install playwright && playwright install")

from PIL import Image

# Load API Key from config.json
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
GEMINI_API_KEY = None
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GEMINI_API_KEY = config.get("gemini_api_key")
except Exception as e:
    print(f"Warning: Could not load API key from config.json: {e}")

if GEMINI_AVAILABLE and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def download_image(url: str, output_path: Path) -> bool:
    """Download image from URL"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Referer": "https://www.tavernanovo.com/"
        }
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download image from {url}: {e}")
        return False


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """Download PDF from URL"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Referer": "https://www.tavernanovo.com/"
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


def extract_menu_from_image_with_gemini(image_path: Path, menu_name: str, menu_type: str) -> List[Dict]:
    """Extract menu items from image using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    all_items = []
    
    try:
        # Load image
        image = Image.open(image_path)
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Analyze this {menu_name} menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (NOT addon items - those should be in descriptions)
2. **description**: The description/ingredients/details for THIS specific item only. CRITICAL: If there are addons listed near this item (like "ADD CHICKEN $7.95" or "Add chicken +$6" or "with cheese | Small $6 Large $8"), include them in the description field. Format as: "Description text. Add-ons: add chicken +$7.95 / add shrimp +$10.95 / with cheese Small $6 Large $8"
3. **price**: The price. CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
   * "Small $5 | Large $7"
   * "6\" Sub or Bread $8 | 12\" Sub or Wrap $13"
   * "SM $7 | LG $13"
   * "$13" (single price)
   Always include the $ symbol. For items with size variations, use the format: "Size1 $X | Size2 $Y"
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Cocktails", "Wine", "Beer", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Chicken Salad Wrap",
    "description": "House made chicken salad with thinly sliced chicken, celery, red onion, cajun seasoning, mayo with lettuce, tomato, bacon & cheddar cheese",
    "price": "$13",
    "section": "Wraps"
  }},
  {{
    "name": "House Made Soups of the Day",
    "description": "Daily selection of fresh soups",
    "price": "Small $5 | Large $7",
    "section": "Soups"
  }},
  {{
    "name": "Cold Sandwich",
    "description": "Choice of roasted turkey, roast beef, ham, chicken salad, or corned beef, comes with cheese. Add-ons: with cheese | Small $6 Large $8 / with lettuce, tomato, & onion | Small $7 Large $10",
    "price": "6\" Sub or Bread $8 | 12\" Sub or Wrap $13",
    "section": "Sandwiches"
  }}
]"""
        
        print(f"    Analyzing image with Gemini...")
        response = model.generate_content([prompt, image])
        
        # Extract JSON from response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
            response_text = re.sub(r'\s*```$', '', response_text, flags=re.MULTILINE)
        
        # Parse JSON
        items = json.loads(response_text)
        
        # Add metadata to each item and ensure prices have dollar signs
        for item in items:
            item["restaurant_name"] = "Taverna Novo"
            item["restaurant_url"] = "https://www.tavernanovo.com/"
            item["menu_type"] = menu_type
            item["menu_name"] = menu_name
            
            # Ensure price has dollar sign
            if item.get("price"):
                price_str = str(item["price"]).strip()
                
                # Check if price already has dollar signs
                if "$" not in price_str:
                    # No dollar signs at all - add them
                    if "|" in price_str:
                        # Multi-price format: "125 | 175" -> "$125 | $175"
                        parts = price_str.split("|")
                        formatted_parts = []
                        for part in parts:
                            part = part.strip()
                            if part:
                                # Extract size label if present (e.g., "Cup 6" or "Small 5")
                                size_match = re.match(r'^([A-Za-z0-9\s"]+?)\s+(\d+(?:\.\d+)?)$', part)
                                if size_match:
                                    size = size_match.group(1).strip()
                                    price = size_match.group(2)
                                    formatted_parts.append(f"{size} ${price}")
                                else:
                                    # Just a number
                                    formatted_parts.append(f"${part}")
                        item["price"] = " | ".join(formatted_parts)
                    else:
                        # Single price
                        item["price"] = f"${price_str}"
                elif price_str.startswith("$") and not any(c.isalpha() for c in price_str[1:5]):
                    # Price starts with $ but might be missing $ in multi-price format
                    # Check if it's a single number like "$125" - that's fine
                    # But if it's "$125 | 175", we need to fix it
                    if "|" in price_str:
                        parts = price_str.split("|")
                        formatted_parts = []
                        for part in parts:
                            part = part.strip()
                            if part and "$" not in part:
                                # Missing dollar sign in this part
                                size_match = re.match(r'^([A-Za-z0-9\s"]+?)\s+(\d+(?:\.\d+)?)$', part)
                                if size_match:
                                    size = size_match.group(1).strip()
                                    price = size_match.group(2)
                                    formatted_parts.append(f"{size} ${price}")
                                else:
                                    formatted_parts.append(f"${part}")
                            else:
                                formatted_parts.append(part)
                        item["price"] = " | ".join(formatted_parts)
        
        all_items.extend(items)
        print(f"    Extracted {len(items)} items from image")
        
    except json.JSONDecodeError as e:
        print(f"    [ERROR] Failed to parse JSON response: {e}")
        print(f"    Response text: {response_text[:500]}")
    except Exception as e:
        print(f"    [ERROR] Failed to extract menu from image: {e}")
    
    return all_items


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
3. **price**: The price. CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
   * "Small $5 | Large $7"
   * "6\" Sub or Bread $8 | 12\" Sub or Wrap $13"
   * "SM $7 | LG $13"
   * "$13" (single price)
   Always include the $ symbol. For items with size variations, use the format: "Size1 $X | Size2 $Y"
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Cocktails", "Wine", "Beer", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line, often after a "/" separator
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Chicken Salad Wrap",
    "description": "House made chicken salad with thinly sliced chicken, celery, red onion, cajun seasoning, mayo with lettuce, tomato, bacon & cheddar cheese",
    "price": "$13",
    "section": "Wraps"
  }},
  {{
    "name": "House Made Soups of the Day",
    "description": "Daily selection of fresh soups",
    "price": "Small $5 | Large $7",
    "section": "Soups"
  }},
  {{
    "name": "Cold Sandwich",
    "description": "Choice of roasted turkey, roast beef, ham, chicken salad, or corned beef, comes with cheese. Add-ons: with cheese | Small $6 Large $8 / with lettuce, tomato, & onion | Small $7 Large $10",
    "price": "6\" Sub or Bread $8 | 12\" Sub or Wrap $13",
    "section": "Sandwiches"
  }}
]"""
        
        for page_num, image in enumerate(images, 1):
            print(f"    Analyzing page {page_num}/{len(images)} with Gemini...")
            response = model.generate_content([prompt, image])
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r'\s*```$', '', response_text, flags=re.MULTILINE)
            
            # Parse JSON
            items = json.loads(response_text)
            
            # Add metadata to each item and ensure prices have dollar signs
            for item in items:
                item["restaurant_name"] = "Taverna Novo"
                item["restaurant_url"] = "https://www.tavernanovo.com/"
                item["menu_type"] = menu_type
                item["menu_name"] = menu_name
                
                # Ensure price has dollar sign
                if item.get("price") and not item["price"].startswith("$"):
                    # Check if it's a number
                    price_str = str(item["price"]).strip()
                    if price_str and (price_str.replace(".", "").replace("|", "").replace(" ", "").isdigit() or any(c.isdigit() for c in price_str)):
                        # Add dollar sign if missing
                        if "|" in price_str:
                            # Multi-price format: "125 | 175" -> "$125 | $175"
                            parts = price_str.split("|")
                            formatted_parts = []
                            for part in parts:
                                part = part.strip()
                                if part and not part.startswith("$"):
                                    # Extract size label if present
                                    size_match = re.match(r'^([A-Za-z0-9\s"]+?)\s+(\d+(?:\.\d+)?)$', part)
                                    if size_match:
                                        size = size_match.group(1).strip()
                                        price = size_match.group(2)
                                        formatted_parts.append(f"{size} ${price}")
                                    else:
                                        # Just a number
                                        formatted_parts.append(f"${part}")
                                else:
                                    formatted_parts.append(part)
                            item["price"] = " | ".join(formatted_parts)
                        else:
                            # Single price
                            item["price"] = f"${price_str}"
            
            all_items.extend(items)
            print(f"    Extracted {len(items)} items from page {page_num}")
        
    except json.JSONDecodeError as e:
        print(f"    [ERROR] Failed to parse JSON response: {e}")
        print(f"    Response text: {response_text[:500]}")
    except Exception as e:
        print(f"    [ERROR] Failed to extract menu from PDF: {e}")
    
    return all_items


def get_image_urls_from_page(url: str, referer: Optional[str] = None, cookies: Optional[str] = None) -> List[str]:
    """Extract menu image URLs from a page using Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available")
        return []
    
    image_urls = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            )
            
            if cookies:
                # Parse cookies
                cookie_list = []
                for cookie_str in cookies.split('; '):
                    if '=' in cookie_str:
                        name, value = cookie_str.split('=', 1)
                        cookie_list.append({
                            'name': name,
                            'value': value,
                            'domain': '.tavernanovo.com',
                            'path': '/'
                        })
                context.add_cookies(cookie_list)
            
            page = context.new_page()
            
            if referer:
                page.set_extra_http_headers({'Referer': referer})
            
            print(f"    Loading page: {url}")
            page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait a bit for images to load
            page.wait_for_timeout(3000)
            
            # Find all images - look for menu images
            # Try to find images with menu-related attributes or large images
            images = page.query_selector_all('img')
            
            for img in images:
                src = img.get_attribute('src') or img.get_attribute('data-src')
                if src:
                    # Filter for menu images (usually large images from wixstatic)
                    if 'wixstatic.com' in src and ('menu' in src.lower() or 'mv2' in src):
                        # Get full resolution URL
                        if '/v1/fit/' in src or '/v1/fill/' in src:
                            # Try to get original image URL
                            base_url = src.split('/v1/')[0]
                            # Try common high-res patterns
                            full_url = f"{base_url}/v1/fit/w_2500,h_2500,al_c,q_85,enc_auto/{base_url.split('/')[-1]}"
                            image_urls.append(full_url)
                        else:
                            image_urls.append(src)
            
            # Also check for background images
            elements = page.query_selector_all('[style*="background-image"]')
            for elem in elements:
                style = elem.get_attribute('style')
                if style and 'url(' in style:
                    match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
                    if match:
                        img_url = match.group(1)
                        if 'wixstatic.com' in img_url and ('menu' in img_url.lower() or 'mv2' in img_url):
                            image_urls.append(img_url)
            
            browser.close()
            
            # Remove duplicates
            image_urls = list(set(image_urls))
            print(f"    Found {len(image_urls)} potential menu images")
            
    except Exception as e:
        print(f"    [ERROR] Failed to extract images from page: {e}")
    
    return image_urls


def scrape_tavernanovo() -> List[Dict]:
    """Main scraping function for Taverna Novo"""
    print("=" * 60)
    print("Scraping Taverna Novo (tavernanovo.com)")
    print("=" * 60)
    
    all_items = []
    temp_dir = Path(__file__).parent.parent / "temp" / "taverna"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Menu sources
    menus = [
        {
            "name": "Fall and Winter Menu",
            "url": "https://www.tavernanovo.com/fallandwintermenu",
            "referer": "https://www.tavernanovo.com/craft-cocktail-offerings",
            "cookies": "server-session-bind=9926434c-95dd-4d97-b814-cfb501002f3c; XSRF-TOKEN=1767678831^|iqISl5wck8oS; hs=-1551558780; svSession=c8ef69e526456b8e5f9e8a0846a4902ee64b6b6b83cc88fa16bd57b8f7577a504d97f88ad5f43da2a6b59e19f8e1de971e60994d53964e647acf431e4f798bcd360c892d01c65a5c4adc62be59ae0a977fe14dbdee71937f2424de34d1df7e20c1850682028414d034b838b64e9a1d1c06fc8b1a76469a732f011d41698a2e424df3a879c6a73fd1483d68e7cb6432e7; bSession=c60fb578-4d09-4fb9-95df-a11c3b0fbaa5^|1^",
            "type": "Fall and Winter Menu"
        },
        {
            "name": "Craft Cocktail Offerings",
            "url": "https://www.tavernanovo.com/craft-cocktail-offerings",
            "referer": "https://www.tavernanovo.com/fallandwintermenu",
            "type": "Cocktails"
        },
        {
            "name": "Wine and Beer Offerings",
            "url": "https://www.tavernanovo.com/_files/ugd/a48f60_ce15d2666e784c9bbaf8f26850186f49.pdf",
            "is_pdf": True,
            "type": "Wine and Beer"
        }
    ]
    
    for menu in menus:
        print(f"\n[1] Processing {menu['name']}...")
        
        if menu.get('is_pdf'):
            # Download PDF
            pdf_path = temp_dir / f"{menu['name'].lower().replace(' ', '_')}.pdf"
            print(f"  Downloading PDF...")
            if download_pdf(menu['url'], pdf_path):
                print(f"  [OK] Downloaded PDF")
                
                # Extract from PDF
                print(f"  Extracting menu items from PDF...")
                items = extract_menu_from_pdf_with_gemini(pdf_path, menu['name'], menu['type'])
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items from PDF")
        else:
            # Extract image URLs from page
            print(f"  Extracting image URLs from page...")
            image_urls = get_image_urls_from_page(
                menu['url'],
                referer=menu.get('referer'),
                cookies=menu.get('cookies')
            )
            
            if not image_urls:
                print(f"  [WARNING] No menu images found on page")
                continue
            
            # Download and process each image
            for idx, img_url in enumerate(image_urls, 1):
                print(f"  Processing image {idx}/{len(image_urls)}...")
                img_path = temp_dir / f"{menu['name'].lower().replace(' ', '_')}_{idx}.jpg"
                
                if download_image(img_url, img_path):
                    print(f"    [OK] Downloaded image")
                    
                    # Extract from image
                    items = extract_menu_from_image_with_gemini(img_path, menu['name'], menu['type'])
                    all_items.extend(items)
                    print(f"    [OK] Extracted {len(items)} items from image")
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    return all_items


if __name__ == "__main__":
    items = scrape_tavernanovo()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "tavernanovo_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

