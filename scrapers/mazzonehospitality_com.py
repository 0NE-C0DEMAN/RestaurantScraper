"""
Scraper for Mazzone Hospitality (mazzonehospitality.com)
Scrapes menu from multiple sources:
- Classic Menu: Images from issuu.com (pages 6-24)
- Bakery Menu: PDF from Issuu (downloaded via Playwright)
- Corporate Menu: PDF from Issuu (downloaded via Playwright, skip first 3 pages and last page)
- Holiday Menu: PDF from Issuu (downloaded via Playwright, skip last page)
Uses Gemini Vision API to extract menu data
Uses Playwright (headless) to download PDFs from Issuu
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
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
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not installed. Install with: pip install Pillow")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed. Install with: pip install playwright && playwright install chromium")

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
RESTAURANT_NAME = "Mazzone Hospitality"
RESTAURANT_URL = "https://www.mazzonehospitality.com/"

# Menu URLs
CLASSIC_MENU_BASE_URL = "https://image.issuu.com/250717154008-0b4f61f895eb147517a20a4e32df0a62/jpg/page_{}.jpg"
# Issuu page URLs for PDF menus (will be downloaded via Playwright)
BAKERY_MENU_ISSUU_URL = "https://issuu.com/mazzonemarketing/docs/mh_bakery_2022"
CORPORATE_MENU_ISSUU_URL = "https://issuu.com/mazzonemarketing/docs/corporate_menu"
HOLIDAY_MENU_ISSUU_URL = "https://issuu.com/mazzonemarketing/docs/holidaymenu2024_new"


def download_image(image_url: str, output_path: Path) -> bool:
    """Download image from URL"""
    try:
        headers = {
            "accept": "image/*,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://issuu.com/"
        }
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download image from {image_url}: {e}")
        return False


def download_pdf_from_issuu(issuu_url: str, output_path: Path) -> bool:
    """Download PDF from Issuu using Playwright (headless mode)"""
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available. Install with: pip install playwright && playwright install chromium")
        return False
    
    try:
        print(f"[INFO] Downloading PDF from Issuu: {issuu_url}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # Navigate to the Issuu page
            page.goto(issuu_url, wait_until='networkidle', timeout=60000)
            time.sleep(5)  # Wait for page to fully load
            
            # Wait for the iframe to load
            iframe = page.frame_locator('iframe').first
            
            # Wait for the download button to be visible in the iframe
            download_button = iframe.locator('button[data-testid="download-button"]')
            download_button.wait_for(state='visible', timeout=15000)
            
            # Check if button is disabled
            is_disabled = download_button.get_attribute('aria-disabled')
            if is_disabled == 'true':
                print("[ERROR] Download button is disabled!")
                browser.close()
                return False
            
            # Set up download listener
            with page.expect_download(timeout=30000) as download_info:
                # Click the button
                download_button.click()
                
                # Wait for download to start
                download = download_info.value
                print(f"[INFO] Download started! File: {download.suggested_filename}")
                
                # Save the download
                download.save_as(output_path)
                print(f"[INFO] Successfully downloaded PDF to {output_path}")
            
            browser.close()
            return True
            
    except Exception as e:
        print(f"[ERROR] Failed to download PDF from Issuu: {e}")
        return False


def extract_menu_from_image_with_gemini(image_input, menu_name: str, page_num: Optional[int] = None) -> List[Dict]:
    """Extract menu items from image using Gemini Vision API
    image_input can be either a Path to an image file or a PIL Image object
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    if not PIL_AVAILABLE:
        print("[ERROR] PIL/Pillow not available")
        return []
    
    try:
        # Load image - handle both Path and PIL Image
        if isinstance(image_input, Path):
            image = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            image = image_input
        else:
            print(f"[ERROR] Invalid image input type: {type(image_input)}")
            return []
        
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        page_info = f" (page {page_num})" if page_num else ""
        print(f"[INFO] Processing {menu_name}{page_info}...")
        
        prompt = f"""Extract all menu items from this {menu_name} menu page. For each item, provide:
- name: The item name
- description: Any description, ingredients, or notes
- price: The price if available. Handle multi-price, multi-size, and add-ons:
  * Single price: "$X.XX"
  * Multiple sizes: "Small $X.XX | Medium $Y.YY | Large $Z.ZZ" or "6\" $X.XX | 12\" $Y.YY"
  * Multiple prices (different options): "Option1 $X.XX | Option2 $Y.YY"
  * Price ranges: "$X.XX - $Y.YY" if there's a range
  * Add-ons: Include add-on prices in the description if they are listed with the item (e.g., "Description text. Add-ons: cheese $1.00, bacon $2.00")
- section: The menu section/category (e.g., "Appetizers", "Entrees", "Desserts", "Breakfast", "Lunch", "Dinner", "Beverages", "Beer", "Wine", "Cocktails", "Salads", "Sandwiches", "Burgers", "Pizza", "Pasta", "TIER I", "TIER II", etc.)

IMPORTANT: 
- If an item has multiple sizes (Small/Medium/Large, 6\"/12\", etc.), format price as "Size1 $X.XX | Size2 $Y.YY | Size3 $Z.ZZ"
- If an item has multiple price options, format as "Option1 $X.XX | Option2 $Y.YY"
- Include add-ons in the description if they are listed with the item (e.g., "Description text. Add-ons: cheese $1.00, bacon $2.00")
- Extract all prices accurately, including decimal values
- Identify menu sections correctly
- Skip header/footer text, contact information, and disclaimers
- Only extract actual menu items, not page numbers or navigation elements

Return ONLY a valid JSON array of objects with these fields. If a field is not available, use null or empty string.
Example format:
[
  {{
    "name": "Item Name",
    "description": "Description with add-ons if any",
    "price": "$10.00",
    "section": "Section Name"
  }},
  {{
    "name": "Pizza",
    "description": "Delicious pizza",
    "price": "Small $12.00 | Medium $16.00 | Large $20.00",
    "section": "Pizza"
  }}
]"""
        
        # Add delay between API calls
        time.sleep(5)
        
        response = model.generate_content([prompt, image])
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            print(f"[INFO] Extracted {len(items)} items from {menu_name}{page_info}")
            return items
        else:
            print(f"[WARNING] No JSON array found in response for {menu_name}{page_info}")
            print(f"[DEBUG] Response preview: {response_text[:200]}")
            return []
    except Exception as e:
        print(f"[ERROR] Error processing {menu_name}{page_info}: {e}")
        return []


def extract_menu_from_pdf_with_gemini(pdf_path: Path, menu_name: str, skip_first: int = 0, skip_last: int = 0) -> List[Dict]:
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
        
        # Determine which pages to process
        start_page = skip_first
        end_page = len(images) - skip_last
        
        print(f"[INFO] Processing pages {start_page + 1} to {end_page} (skipping first {skip_first} and last {skip_last} pages)")
        
        for page_idx in range(start_page, end_page):
            page_num = page_idx + 1
            image = images[page_idx]
            
            items = extract_menu_from_image_with_gemini(image, menu_name, page_num)
            all_items.extend(items)
        
        return all_items
    except Exception as e:
        print(f"[ERROR] Error extracting from {menu_name} PDF: {e}")
        return []


def scrape_classic_menu() -> List[Dict]:
    """Scrape Classic Menu from images (pages 6-24)"""
    print("\n[CLASSIC MENU] Scraping Classic Menu from images (pages 6-24)...")
    all_items = []
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    for page_num in range(6, 25):
        image_url = CLASSIC_MENU_BASE_URL.format(page_num)
        image_path = temp_dir / f"classic_menu_page_{page_num}.jpg"
        
        if not download_image(image_url, image_path):
            print(f"[WARNING] Failed to download page {page_num}, skipping...")
            continue
        
        items = extract_menu_from_image_with_gemini(image_path, "Classic Menu", page_num)
        
        # Add restaurant info
        for item in items:
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
            item['menu_name'] = "Classic Menu"
        
        all_items.extend(items)
        print(f"[INFO] Extracted {len(items)} items from Classic Menu page {page_num}")
    
    print(f"[INFO] Total Classic Menu items: {len(all_items)}")
    return all_items


def scrape_bakery_menu() -> List[Dict]:
    """Scrape Bakery Menu from PDF"""
    print("\n[BAKERY MENU] Scraping Bakery Menu from PDF...")
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / "bakery_menu.pdf"
    
    if not download_pdf_from_issuu(BAKERY_MENU_ISSUU_URL, pdf_path):
        print("[ERROR] Failed to download Bakery Menu PDF, skipping...")
        return []
    
    items = extract_menu_from_pdf_with_gemini(pdf_path, "Bakery Menu", skip_first=0, skip_last=0)
    
    # Add restaurant info
    for item in items:
        item['restaurant_name'] = RESTAURANT_NAME
        item['restaurant_url'] = RESTAURANT_URL
        item['menu_name'] = "Bakery Menu"
    
    print(f"[INFO] Total Bakery Menu items: {len(items)}")
    return items


def scrape_corporate_menu() -> List[Dict]:
    """Scrape Corporate Menu from PDF (skip first 3 pages and last page)"""
    print("\n[CORPORATE MENU] Scraping Corporate Menu from PDF (skipping first 3 pages and last page)...")
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / "corporate_menu.pdf"
    
    if not download_pdf_from_issuu(CORPORATE_MENU_ISSUU_URL, pdf_path):
        print("[ERROR] Failed to download Corporate Menu PDF, skipping...")
        return []
    
    items = extract_menu_from_pdf_with_gemini(pdf_path, "Corporate Menu", skip_first=3, skip_last=1)
    
    # Add restaurant info
    for item in items:
        item['restaurant_name'] = RESTAURANT_NAME
        item['restaurant_url'] = RESTAURANT_URL
        item['menu_name'] = "Corporate Menu"
    
    print(f"[INFO] Total Corporate Menu items: {len(items)}")
    return items


def scrape_holiday_menu() -> List[Dict]:
    """Scrape Holiday Menu from PDF (skip last page)"""
    print("\n[HOLIDAY MENU] Scraping Holiday Menu from PDF (skipping last page)...")
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / "holiday_menu.pdf"
    
    if not download_pdf_from_issuu(HOLIDAY_MENU_ISSUU_URL, pdf_path):
        print("[ERROR] Failed to download Holiday Menu PDF, skipping...")
        return []
    
    items = extract_menu_from_pdf_with_gemini(pdf_path, "Holiday Menu", skip_first=0, skip_last=1)
    
    # Add restaurant info
    for item in items:
        item['restaurant_name'] = RESTAURANT_NAME
        item['restaurant_url'] = RESTAURANT_URL
        item['menu_name'] = "Holiday Menu"
    
    print(f"[INFO] Total Holiday Menu items: {len(items)}")
    return items


def scrape_menu() -> List[Dict]:
    """Main function to scrape all menus"""
    print(f"[INFO] Scraping menus from {RESTAURANT_NAME}")
    all_items = []
    
    # Scrape Classic Menu
    classic_items = scrape_classic_menu()
    all_items.extend(classic_items)
    
    # Scrape Bakery Menu
    bakery_items = scrape_bakery_menu()
    all_items.extend(bakery_items)
    
    # Scrape Corporate Menu
    corporate_items = scrape_corporate_menu()
    all_items.extend(corporate_items)
    
    # Scrape Holiday Menu
    holiday_items = scrape_holiday_menu()
    all_items.extend(holiday_items)
    
    print(f"\n[INFO] Extracted {len(all_items)} menu items total from all menus")
    
    return all_items


def scrape_pdf_menus_only() -> List[Dict]:
    """Scrape only PDF menus (Bakery, Corporate, Holiday)"""
    print(f"[INFO] Scraping PDF menus from {RESTAURANT_NAME}")
    all_items = []
    
    # Scrape Bakery Menu
    bakery_items = scrape_bakery_menu()
    all_items.extend(bakery_items)
    
    # Scrape Corporate Menu
    corporate_items = scrape_corporate_menu()
    all_items.extend(corporate_items)
    
    # Scrape Holiday Menu
    holiday_items = scrape_holiday_menu()
    all_items.extend(holiday_items)
    
    print(f"\n[INFO] Extracted {len(all_items)} menu items total from PDF menus")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "mazzonehospitality_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


def main_pdf_only():
    """Main entry point for PDF menus only - appends to existing file"""
    # Load existing items
    output_dir = Path(__file__).parent.parent / "output"
    output_file = output_dir / "mazzonehospitality_com.json"
    
    existing_items = []
    if output_file.exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_items = json.load(f)
            print(f"[INFO] Loaded {len(existing_items)} existing items from {output_file}")
        except Exception as e:
            print(f"[WARNING] Could not load existing file: {e}")
    
    # Scrape PDF menus
    pdf_items = scrape_pdf_menus_only()
    
    # Combine with existing items
    all_items = existing_items + pdf_items
    
    # Save to JSON
    output_dir.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Total items: {len(all_items)} ({len(existing_items)} existing + {len(pdf_items)} new PDF items)")
    print(f"[SUCCESS] Saved to {output_file}")
    return all_items


if __name__ == "__main__":
    # Run PDF menus only and append to existing
    main_pdf_only()
