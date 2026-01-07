"""
Scraper for Village Pizzeria (villagepizzeria.com)
Scrapes menu from HTML pages and detail pages
Handles: multi-price, multi-size, and add-ons
Also handles wine menu PDF and kids menu with images
"""

import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

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
    print("Warning: playwright not installed. Install with: pip install playwright")

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
RESTAURANT_NAME = "Village Pizzeria & Ristorante"
RESTAURANT_URL = "https://villagepizzeria.com/"

# Menu URLs
MENU_URL = "https://villagepizzeria.com/menu/"
KIDS_MENU_URL = "https://villagepizzeria.com/kids-menu/"
WINE_MENU_PDF_URL = "https://villagepizzeria.com/wp-content/uploads/2023/04/EMPNO_3338550_VillagePizzeria.pdf"

# Headers for requests
HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://villagepizzeria.com/wine/',
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

DETAIL_HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://villagepizzeria.com/menu/',
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


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """Download PDF from URL"""
    try:
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


def download_image(image_url: str, output_path: Path) -> bool:
    """Download image from URL"""
    try:
        headers = {
            "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": RESTAURANT_URL
        }
        response = requests.get(image_url, headers=headers, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download image from {image_url}: {e}")
        return False


def extract_menu_from_pdf_with_gemini(pdf_path: Path) -> List[Dict]:
    """Extract menu items from PDF using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    if not PDF2IMAGE_AVAILABLE:
        print("[ERROR] pdf2image not available")
        return []
    
    all_items = []
    
    try:
        # Convert PDF pages to images
        images = convert_from_path(str(pdf_path), dpi=200)
        print(f"[INFO] Converted PDF to {len(images)} images")
        
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        for page_num, image in enumerate(images, 1):
            print(f"[INFO] Processing PDF page {page_num}/{len(images)}")
            
            prompt = """Extract all wine items from this menu page. For each wine, provide:
- name: The wine name
- description: Any description, region, or notes
- price: The price if available. Include quantity and type (glass/bottle) with the price:
  * If only one price: "Glass $X.XX" or "Bottle $Y.YY" or "$X.XX" if type is unclear
  * If multiple prices: "Glass $X.XX | Bottle $Y.YY"
  * If quantity is specified (e.g., "750ml", "1.5L"): include it: "Bottle (750ml) $Y.YY" or "Glass $X.XX | Bottle (750ml) $Y.YY"
- section: The category (e.g., "Red Wine", "White Wine", "Sparkling", etc.)

IMPORTANT: Always include the serving type (Glass/Bottle) and quantity (if available) with the price.

Return ONLY a valid JSON array of objects with these fields. If a field is not available, use null.
Example format:
[
  {
    "name": "Wine Name",
    "description": "Description or region",
    "price": "Glass $12.00 | Bottle (750ml) $45.00",
    "section": "Red Wine"
  }
]"""
            
            try:
                response = model.generate_content([prompt, image])
                response_text = response.text.strip()
                
                # Extract JSON from response
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    items = json.loads(json_match.group())
                    all_items.extend(items)
                    print(f"[INFO] Extracted {len(items)} items from page {page_num}")
                else:
                    print(f"[WARNING] No JSON array found in response for page {page_num}")
            except Exception as e:
                print(f"[ERROR] Error processing page {page_num}: {e}")
                continue
        
        return all_items
    except Exception as e:
        print(f"[ERROR] Error extracting from PDF: {e}")
        return []


def extract_menu_from_images_with_gemini(image_paths: List[Path]) -> List[Dict]:
    """Extract menu items from images using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    all_items = []
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        for img_path in image_paths:
            print(f"[INFO] Processing image: {img_path.name}")
            
            image = Image.open(img_path)
            
            prompt = """Extract all menu items from this menu image. For each item, provide:
- name: The item name
- description: Any description or ingredients
- price: The price if available (format as "$X.XX" or "Small $X.XX | Large $Y.YY" for multi-size, or "Option1 $X.XX | Option2 $Y.YY" for multi-price)
- section: The menu section/category

Handle multi-price, multi-size, and add-ons:
- If an item has multiple sizes (e.g., Small/Large), format price as "Small $X.XX | Large $Y.YY"
- If an item has multiple price options, format as "Option1 $X.XX | Option2 $Y.YY"
- Include add-ons in the description if they are listed with the item

Return ONLY a valid JSON array of objects with these fields. If a field is not available, use null.
Example format:
[
  {
    "name": "Item Name",
    "description": "Description with add-ons if any",
    "price": "$10.00",
    "section": "Section Name"
  }
]"""
            
            try:
                response = model.generate_content([prompt, image])
                response_text = response.text.strip()
                
                # Extract JSON from response
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    items = json.loads(json_match.group())
                    all_items.extend(items)
                    print(f"[INFO] Extracted {len(items)} items from {img_path.name}")
                else:
                    print(f"[WARNING] No JSON array found in response for {img_path.name}")
            except Exception as e:
                print(f"[ERROR] Error processing {img_path.name}: {e}")
                continue
        
        return all_items
    except Exception as e:
        print(f"[ERROR] Error extracting from images: {e}")
        return []


def fetch_menu_html() -> Optional[str]:
    """Fetch the main menu HTML using Playwright in headful mode"""
    if not PLAYWRIGHT_AVAILABLE:
        # Fallback to requests
        try:
            print("[INFO] Fetching menu HTML with requests...")
            response = requests.get(MENU_URL, headers=HEADERS, timeout=30)
            response.raise_for_status()
            print(f"[INFO] Successfully fetched menu HTML ({len(response.text)} chars)")
            return response.text
        except Exception as e:
            print(f"[ERROR] Failed to fetch menu HTML: {e}")
            return None
    
    try:
        print("[INFO] Fetching menu HTML with Playwright (headful mode)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # headful mode
            context = browser.new_context(extra_http_headers=HEADERS)
            page = context.new_page()
            print(f"[INFO] Navigating to {MENU_URL}...")
            page.goto(MENU_URL, wait_until="networkidle", timeout=60000)
            print("[INFO] Waiting for content to load...")
            time.sleep(3)  # Wait for content to load
            html = page.content()
            print(f"[INFO] Successfully fetched menu HTML ({len(html)} chars)")
            browser.close()
            return html
    except Exception as e:
        print(f"[ERROR] Failed to fetch menu HTML with Playwright: {e}")
        # Fallback to requests
        try:
            print("[INFO] Falling back to requests...")
            response = requests.get(MENU_URL, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e2:
            print(f"[ERROR] Failed to fetch menu HTML: {e2}")
            return None


def fetch_item_detail(item_url: str) -> Optional[Dict]:
    """Fetch item detail page and extract information"""
    try:
        response = requests.get(item_url, headers=DETAIL_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract name
        name_elem = soup.find('h1')
        name = name_elem.get_text(strip=True) if name_elem else None
        
        # Extract category/section
        category_link = soup.find('a', href=lambda x: x and '/project_category/' in str(x))
        section = category_link.get_text(strip=True).title() if category_link else None
        
        # Extract description - look for paragraphs with content
        description = None
        content_div = soup.find('div', class_=lambda x: x and 'content' in str(x).lower()) or soup.find('article')
        if content_div:
            paragraphs = content_div.find_all('p')
            desc_texts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                # Skip empty paragraphs and metadata
                if text and len(text) > 5 and 'Posted on' not in text and 'Skills' not in text:
                    desc_texts.append(text)
            if desc_texts:
                description = ' '.join(desc_texts)
        
        # Look for price in the page
        price = None
        price_pattern = re.compile(r'\$[\d.]+')
        page_text = soup.get_text()
        prices = price_pattern.findall(page_text)
        if prices:
            # Try to find price context
            price_elem = soup.find(string=price_pattern)
            if price_elem:
                price_text = price_elem.strip()
                # Check for multi-price patterns
                if len(prices) > 1:
                    price = ' | '.join(prices)
                else:
                    price = prices[0]
        
        return {
            'name': name,
            'description': description,
            'price': price,
            'section': section
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch item detail {item_url}: {e}")
        return None


def extract_menu_items_from_html(html: str) -> List[Dict]:
    """Extract menu items from the main menu HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Track sections - look for h2 headings that are sections (not items)
    sections_map = {}
    
    # Find all h2 elements and identify sections
    all_h2s = soup.find_all('h2')
    for h2 in all_h2s:
        # Check if this h2 is a section heading (no link to /project/)
        has_item_link = h2.find('a', href=lambda x: x and '/project/' in str(x))
        if not has_item_link:
            section_name = h2.get_text(strip=True)
            sections_map[h2] = section_name
    
    # Find all links to /project/ pages
    item_links = soup.find_all('a', href=lambda x: x and '/project/' in str(x))
    
    # Extract items with their sections
    seen_urls = set()
    for link in item_links:
        item_url = link.get('href', '')
        if not item_url:
            continue
        if not item_url.startswith('http'):
            item_url = f"https://villagepizzeria.com{item_url}"
        
        # Skip duplicates
        if item_url in seen_urls:
            continue
        seen_urls.add(item_url)
        
        # Get item name - try multiple methods
        item_name = link.get_text(strip=True)
        if not item_name:
            # Try to get name from parent h2
            parent_h2 = link.find_parent('h2')
            if parent_h2:
                item_name = parent_h2.get_text(strip=True)
        
        # If still no name, try getting from img alt or title
        if not item_name:
            img = link.find('img')
            if img:
                item_name = img.get('alt') or img.get('title') or ''
        
        # Skip if still no name
        if not item_name or len(item_name.strip()) < 2:
            continue
        
        # Find the section for this item
        section = None
        # Find the h2 that contains this link
        item_h2 = link.find_parent('h2')
        if item_h2:
            # Look backwards for the most recent section h2
            for prev_elem in item_h2.find_all_previous(['h2']):
                if prev_elem in sections_map:
                    section = sections_map[prev_elem]
                    break
        
        all_items.append({
            'url': item_url,
            'name': item_name.strip(),
            'section': section or 'Menu'
        })
    
    return all_items


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    all_items = []
    
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME}")
    
    # 1. Scrape main menu items
    print("[INFO] Fetching main menu HTML...")
    menu_html = fetch_menu_html()
    if not menu_html:
        print("[ERROR] Failed to fetch menu HTML")
        return []
    
    print("[INFO] Extracting menu items from HTML...")
    menu_items = extract_menu_items_from_html(menu_html)
    print(f"[INFO] Found {len(menu_items)} menu items")
    
    # 2. Fetch detail pages for each item to get descriptions
    print(f"[INFO] Fetching item detail pages for {len(menu_items)} items...")
    print("[INFO] This will take a few minutes. Processing items...")
    
    for i, item in enumerate(menu_items, 1):
        print(f"[INFO] Processing item {i}/{len(menu_items)}: {item['name'][:60]}...")
        try:
            detail = fetch_item_detail(item['url'])
            if detail:
                all_items.append({
                    'name': detail.get('name') or item['name'],
                    'description': detail.get('description'),
                    'price': detail.get('price'),
                    'section': detail.get('section') or item.get('section') or 'Menu',
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                })
            else:
                # Fallback to basic info
                all_items.append({
                    'name': item['name'],
                    'description': None,
                    'price': None,
                    'section': item.get('section') or 'Menu',
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                })
        except Exception as e:
            print(f"[WARNING] Error processing {item['name']}: {e}")
            # Fallback to basic info
            all_items.append({
                'name': item['name'],
                'description': None,
                'price': None,
                'section': item.get('section') or 'Menu',
                'restaurant_name': RESTAURANT_NAME,
                'restaurant_url': RESTAURANT_URL
            })
        
        # Throttle requests
        time.sleep(0.5)
        
        # Progress update every 10 items
        if i % 10 == 0:
            print(f"[INFO] Progress: {i}/{len(menu_items)} items processed ({len(all_items)} total so far)")
    
    print(f"[INFO] Completed processing {len(all_items)} menu items")
    
    # 3. Scrape wine menu PDF
    print("[INFO] Scraping wine menu PDF...")
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    wine_pdf_path = temp_dir / "villagepizzeria_wine_menu.pdf"
    
    if download_pdf(WINE_MENU_PDF_URL, wine_pdf_path):
        wine_items = extract_menu_from_pdf_with_gemini(wine_pdf_path)
        for item in wine_items:
            item['section'] = item.get('section') or 'Wine List'
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
        all_items.extend(wine_items)
        print(f"[INFO] Extracted {len(wine_items)} wine items")
    
    # 4. Scrape kids menu (with images)
    print("[INFO] Scraping kids menu...")
    try:
        kids_response = requests.get(KIDS_MENU_URL, headers=HEADERS, timeout=30)
        kids_response.raise_for_status()
        kids_soup = BeautifulSoup(kids_response.text, 'html.parser')
        
        # Find all images in the kids menu
        image_urls = []
        for img in kids_soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            if src:
                if not src.startswith('http'):
                    src = f"https://villagepizzeria.com{src}"
                image_urls.append(src)
        
        # Download and process images
        if image_urls:
            image_paths = []
            for img_url in image_urls:
                img_name = img_url.split('/')[-1].split('?')[0]
                img_path = temp_dir / f"villagepizzeria_kids_{img_name}"
                if download_image(img_url, img_path):
                    image_paths.append(img_path)
            
            if image_paths:
                kids_items = extract_menu_from_images_with_gemini(image_paths)
                for item in kids_items:
                    item['section'] = item.get('section') or 'Kids Menu'
                    item['restaurant_name'] = RESTAURANT_NAME
                    item['restaurant_url'] = RESTAURANT_URL
                all_items.extend(kids_items)
                print(f"[INFO] Extracted {len(kids_items)} kids menu items")
    except Exception as e:
        print(f"[ERROR] Failed to scrape kids menu: {e}")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "villagepizzeria_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items")
    print(f"[SUCCESS] Saved to {output_file}")


if __name__ == "__main__":
    main()

