"""
Scraper for Holiday Inn (ihg.com/holidayinn)
Scrapes menu from PDF using Gemini Vision API
Finds PDF link from dining page HTML
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
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
RESTAURANT_NAME = "Holiday Inn Saratoga Springs"
RESTAURANT_URL = "https://www.ihg.com/holidayinn/hotels/us/en/saratoga-springs/sgany/hoteldetail/dining"

# Dining page URL
DINING_PAGE_URL = "https://www.ihg.com/holidayinn/hotels/us/en/saratoga-springs/sgany/hoteldetail/dining"

# Headers for requests
HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://www.ihg.com/holidayinn/hotels/us/en/saratoga-springs/sgany/hoteldetail/dining',
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


def fetch_dining_page_html() -> Optional[str]:
    """Fetch the dining page HTML"""
    try:
        print(f"[INFO] Fetching dining page HTML from {DINING_PAGE_URL}...")
        response = requests.get(DINING_PAGE_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        print(f"[INFO] Successfully fetched HTML ({len(response.text)} chars)")
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch dining page HTML: {e}")
        return None


def find_menu_pdf_url(html: str) -> Optional[str]:
    """Find the menu PDF URL from the HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Method 1: Look for JSON data with menu URL
    script_tags = soup.find_all('script')
    for script in script_tags:
        if script.string:
            # Look for JSON with "menu" key
            menu_match = re.search(r'"menu"\s*:\s*"([^"]+\.pdf[^"]*)"', script.string)
            if menu_match:
                pdf_url = menu_match.group(1)
                # Unescape URL if needed
                pdf_url = pdf_url.replace('\\/', '/')
                print(f"[INFO] Found PDF URL in JSON: {pdf_url}")
                return pdf_url
    
    # Method 2: Look for anchor tag with "Download menu" text or aria-label
    download_link = soup.find('a', href=True, string=re.compile(r'Download\s+menu', re.I))
    if not download_link:
        download_link = soup.find('a', {'aria-label': re.compile(r'Download\s+menu', re.I)}, href=True)
    
    if download_link:
        pdf_url = download_link.get('href')
        if pdf_url:
            # Make absolute URL if relative
            if pdf_url.startswith('//'):
                pdf_url = 'https:' + pdf_url
            elif pdf_url.startswith('/'):
                pdf_url = 'https://www.ihg.com' + pdf_url
            elif not pdf_url.startswith('http'):
                pdf_url = 'https://www.ihg.com/' + pdf_url
            
            print(f"[INFO] Found PDF URL in link: {pdf_url}")
            return pdf_url
    
    # Method 3: Look for any link containing .pdf and "menu" in the text or href
    pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
    for link in pdf_links:
        href = link.get('href', '')
        text = link.get_text(strip=True).lower()
        if 'menu' in text or 'menu' in href.lower():
            pdf_url = href
            if pdf_url.startswith('//'):
                pdf_url = 'https:' + pdf_url
            elif pdf_url.startswith('/'):
                pdf_url = 'https://www.ihg.com' + pdf_url
            elif not pdf_url.startswith('http'):
                pdf_url = 'https://www.ihg.com/' + pdf_url
            
            print(f"[INFO] Found PDF URL: {pdf_url}")
            return pdf_url
    
    print("[WARNING] Could not find menu PDF URL in HTML")
    return None


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """Download PDF from URL"""
    try:
        headers = {
            "accept": "application/pdf,*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": DINING_PAGE_URL
        }
        print(f"[INFO] Downloading PDF from {pdf_url}...")
        response = requests.get(pdf_url, headers=headers, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        print(f"[INFO] Successfully downloaded PDF ({len(response.content)} bytes)")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download PDF from {pdf_url}: {e}")
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
            
            prompt = """Extract all menu items from this menu page. For each item, provide:
- name: The item name
- description: Any description, ingredients, or notes
- price: The price if available. Handle multi-price, multi-size, and add-ons:
  * Single price: "$X.XX"
  * Multiple sizes: "Small $X.XX | Medium $Y.YY | Large $Z.ZZ"
  * Multiple prices (different options): "Option1 $X.XX | Option2 $Y.YY"
  * Add-ons: Include add-on prices in the description if they are listed with the item (e.g., "add cheese $1.00")
- section: The menu section/category (e.g., "Appetizers", "Entrees", "Desserts", "Breakfast", "Lunch", "Dinner", etc.)

IMPORTANT: 
- If an item has multiple sizes (Small/Medium/Large, etc.), format price as "Small $X.XX | Medium $Y.YY | Large $Z.ZZ"
- If an item has multiple price options, format as "Option1 $X.XX | Option2 $Y.YY"
- Include add-ons in the description if they are listed with the item (e.g., "Description text. Add-ons: cheese $1.00, bacon $2.00")
- Extract all prices accurately, including decimal values
- Identify menu sections correctly (Breakfast, Lunch, Dinner, Appetizers, Entrees, Desserts, Beverages, etc.)

Return ONLY a valid JSON array of objects with these fields. If a field is not available, use null.
Example format:
[
  {
    "name": "Item Name",
    "description": "Description with add-ons if any",
    "price": "$10.00",
    "section": "Section Name"
  },
  {
    "name": "Pizza",
    "description": "Delicious pizza",
    "price": "Small $12.00 | Medium $16.00 | Large $20.00",
    "section": "Main Course"
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
                    print(f"[DEBUG] Response preview: {response_text[:200]}")
            except Exception as e:
                print(f"[ERROR] Error processing page {page_num}: {e}")
                continue
        
        return all_items
    except Exception as e:
        print(f"[ERROR] Error extracting from PDF: {e}")
        return []


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME}")
    all_items = []
    
    # 1. Fetch dining page HTML
    html = fetch_dining_page_html()
    if not html:
        print("[ERROR] Failed to fetch dining page HTML")
        return []
    
    # 2. Find menu PDF URL
    pdf_url = find_menu_pdf_url(html)
    if not pdf_url:
        print("[ERROR] Could not find menu PDF URL")
        return []
    
    # 3. Download PDF
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    pdf_path = temp_dir / "holidayinn_menu.pdf"
    
    if not download_pdf(pdf_url, pdf_path):
        print("[ERROR] Failed to download menu PDF")
        return []
    
    # 4. Extract menu items from PDF using Gemini
    items = extract_menu_from_pdf_with_gemini(pdf_path)
    for item in items:
        item['restaurant_name'] = RESTAURANT_NAME
        item['restaurant_url'] = RESTAURANT_URL
        # Ensure section has a default value
        if not item.get('section'):
            item['section'] = 'Menu'
    
    all_items.extend(items)
    print(f"[INFO] Extracted {len(items)} menu items from PDF")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "holidayinn_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

