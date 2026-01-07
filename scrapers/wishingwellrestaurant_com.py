"""
Scraper for Wishing Well Restaurant (wishingwellrestaurant.com)
Scrapes menu from PDF (using Gemini) and HTML pages (wine, cocktails, specials, happy hour)
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
RESTAURANT_NAME = "Wishing Well Restaurant"
RESTAURANT_URL = "https://www.wishingwellrestaurant.com/"

# Menu URLs
MENU_PDF_URL = "https://www.wishingwellrestaurant.com/wp-content/uploads/2025/10/WW-New-Menu-10.27.25.pdf"
WINE_MENU_URL = "https://www.wishingwellrestaurant.com/menus/wine/"
COCKTAIL_MENU_URL = "https://www.wishingwellrestaurant.com/menus/cocktails/"
SPECIALS_MENU_URL = "https://www.wishingwellrestaurant.com/menus/specials/"
HAPPY_HOUR_MENU_URL = "https://www.wishingwellrestaurant.com/menus/happy-hour/"

# Headers for requests
HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://www.wishingwellrestaurant.com/menus/dining-room/',
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
    """Extract menu items from PDF using Gemini Vision API (skip first page)"""
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
        
        # Skip first page (index 0)
        if len(images) > 1:
            images = images[1:]
            print(f"[INFO] Skipping first page, processing {len(images)} pages")
        
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        for page_num, image in enumerate(images, 2):  # Start from page 2
            print(f"[INFO] Processing PDF page {page_num}/{len(images) + 1}")
            
            prompt = """Extract all menu items from this menu page. For each item, provide:
- name: The item name
- description: Any description, ingredients, or notes
- price: The price if available. Handle multi-price, multi-size, and add-ons:
  * Single price: "$X.XX"
  * Multiple sizes: "Small $X.XX | Medium $Y.YY | Large $Z.ZZ"
  * Multiple prices (different options): "Option1 $X.XX | Option2 $Y.YY"
  * Add-ons: Include add-on prices in the description if they are listed with the item (e.g., "add cheese $1.00")
- section: The menu section/category (e.g., "Appetizers", "Entrees", "Desserts", etc.)

IMPORTANT: 
- If an item has multiple sizes (Small/Medium/Large, etc.), format price as "Small $X.XX | Medium $Y.YY | Large $Z.ZZ"
- If an item has multiple price options, format as "Option1 $X.XX | Option2 $Y.YY"
- Include add-ons in the description if they are listed with the item (e.g., "Description text. Add-ons: cheese $1.00, bacon $2.00")
- Extract all prices accurately, including decimal values

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


def fetch_html(url: str, headers: Dict) -> Optional[str]:
    """Fetch HTML from URL"""
    try:
        print(f"[INFO] Fetching HTML from {url}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"[INFO] Successfully fetched HTML ({len(response.text)} chars)")
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch HTML: {e}")
        return None


def extract_wine_items_from_html(html: str) -> List[Dict]:
    """Extract wine items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all menu blocks
    menu_blocks = soup.find_all('div', class_='menu-block')
    
    for block in menu_blocks:
        # Get section heading
        h2 = block.find('h2')
        section = h2.get_text(strip=True) if h2 else "Wine"
        
        # Find all paragraphs (items)
        paragraphs = block.find_all('p')
        
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 3:
                continue
            
            # Skip if it's a section description (contains "by the glass" or similar)
            text_lower = text.lower()
            if text_lower in ['white wines by the glass', 'red wines by the glass', 'wines by the glass']:
                continue
            
            # Skip if it's bold text that's just a heading
            strong = p.find('strong')
            if strong:
                strong_text = strong.get_text(strip=True).lower()
                if strong_text in ['white wines by the glass', 'red wines by the glass']:
                    continue
            
            # Skip italic descriptions (wine notes)
            if p.find('em') and not re.search(r'\d+', text):
                continue
            
            # Parse wine item
            # Format 1: "Wine Name, Producer, Region, Country, Price"
            # Format 2: "Wine Name, Details, Price/Price" (glass/bottle)
            # Format 3: "Bin #XXX Wine Name, Details, Price" (with bin number)
            # Format 4: "XXX       Wine Name, Details, Price" (bin number at start)
            
            # Extract bin number if present (at start, like "101" or "Bin #117")
            bin_match = re.match(r'^(?:Bin\s*#?\s*)?(\d+)\s+', text)
            bin_num = None
            if bin_match:
                bin_num = bin_match.group(1)
                text = text[bin_match.end():].strip()
            
            # Extract price(s) - look for numbers at the end, possibly separated by /
            # Handle both "18/72" (glass/bottle) and single prices
            price_match = re.search(r'([\d/]+)\s*$', text)
            if price_match:
                price_str = price_match.group(1).strip()
                # Check for multi-price (e.g., "18/72" means glass/bottle)
                if '/' in price_str:
                    prices = price_str.split('/')
                    if len(prices) == 2:
                        # Format as "Glass $X | Bottle $Y"
                        price = f"Glass ${prices[0]} | Bottle ${prices[1]}"
                    else:
                        formatted_prices = [f"${p}" for p in prices]
                        price = " | ".join(formatted_prices)
                else:
                    price = f"${price_str}"
                
                # Remove price from text to get name and description
                name_desc = text[:price_match.start()].strip().rstrip(',').strip()
                
                # Clean up extra whitespace
                name_desc = re.sub(r'\s+', ' ', name_desc)
                
                # Split name and description (usually comma-separated)
                parts = [p.strip() for p in name_desc.split(',')]
                if parts:
                    name = parts[0]
                    if bin_num:
                        name = f"Bin #{bin_num} {name}"
                    description = ', '.join(parts[1:]) if len(parts) > 1 else None
                else:
                    name = name_desc
                    if bin_num:
                        name = f"Bin #{bin_num} {name}"
                    description = None
                
                # Only add if we have a valid name
                if name and len(name) > 2:
                    all_items.append({
                        'name': name,
                        'description': description,
                        'price': price,
                        'section': section,
                        'restaurant_name': RESTAURANT_NAME,
                        'restaurant_url': RESTAURANT_URL
                    })
    
    return all_items


def extract_cocktail_items_from_html(html: str) -> List[Dict]:
    """Extract cocktail items from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all menu blocks
    menu_blocks = soup.find_all('div', class_='menu-block')
    
    for block in menu_blocks:
        # Get section heading
        h2 = block.find('h2')
        section = h2.get_text(strip=True) if h2 else "Cocktails"
        
        # Find all paragraphs (items)
        paragraphs = block.find_all('p')
        
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 3:
                continue
            
            # Parse cocktail item - similar to wine
            price_match = re.search(r'([\d/]+)\s*$', text)
            if price_match:
                price_str = price_match.group(1)
                if '/' in price_str:
                    prices = price_str.split('/')
                    formatted_prices = [f"${p}" for p in prices]
                    price = " | ".join(formatted_prices)
                else:
                    price = f"${price_str}"
                
                name_desc = text[:price_match.start()].strip().rstrip(',').strip()
                parts = [p.strip() for p in name_desc.split(',')]
                if parts:
                    name = parts[0]
                    description = ', '.join(parts[1:]) if len(parts) > 1 else None
                else:
                    name = name_desc
                    description = None
                
                all_items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'section': section,
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                })
    
    return all_items


def extract_specials_items_from_html(html: str) -> List[Dict]:
    """Extract specials items from HTML (ignore random content)"""
    soup = BeautifulSoup(html, 'html.parser')
    all_items = []
    
    # Find all menu blocks
    menu_blocks = soup.find_all('div', class_='menu-block')
    
    for block in menu_blocks:
        # Get section heading
        h2 = block.find('h2')
        section = h2.get_text(strip=True) if h2 else "Specials"
        
        # Find all paragraphs (items)
        paragraphs = block.find_all('p')
        
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 3:
                continue
            
            # Skip obvious non-menu content (very long text, contains URLs, etc.)
            if len(text) > 500 or 'http' in text.lower() or '@' in text:
                continue
            
            # Try to extract price
            price_match = re.search(r'\$?([\d.]+)', text)
            if price_match:
                price = f"${price_match.group(1)}"
                # Remove price from text
                name_desc = text.replace(price, '').strip()
            else:
                price = None
                name_desc = text
            
            # Split name and description
            if ' - ' in name_desc:
                parts = name_desc.split(' - ', 1)
                name = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else None
            elif ':' in name_desc:
                parts = name_desc.split(':', 1)
                name = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else None
            else:
                name = name_desc
                description = None
            
            # Only add if we have a reasonable name
            if name and len(name) > 2 and len(name) < 200:
                all_items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'section': section,
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                })
    
    return all_items


def extract_happy_hour_items_from_html(html: str) -> List[Dict]:
    """Extract happy hour items from HTML"""
    # Similar to specials
    return extract_specials_items_from_html(html)


def scrape_menu() -> List[Dict]:
    """Main function to scrape all menus"""
    print(f"[INFO] Scraping menus from {RESTAURANT_NAME}")
    all_items = []
    
    # 1. Scrape main menu PDF (skip first page)
    print(f"\n[1] Scraping main menu PDF...")
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    pdf_path = temp_dir / "wishingwell_menu.pdf"
    
    if download_pdf(MENU_PDF_URL, pdf_path):
        pdf_items = extract_menu_from_pdf_with_gemini(pdf_path)
        for item in pdf_items:
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
            if not item.get('section'):
                item['section'] = 'Menu'
        all_items.extend(pdf_items)
        print(f"[INFO] Extracted {len(pdf_items)} items from PDF")
    else:
        print("[WARNING] Failed to download menu PDF")
    
    # 2. Scrape wine menu
    print(f"\n[2] Scraping wine menu...")
    wine_html = fetch_html(WINE_MENU_URL, HEADERS)
    if wine_html:
        wine_items = extract_wine_items_from_html(wine_html)
        all_items.extend(wine_items)
        print(f"[INFO] Extracted {len(wine_items)} items from wine menu")
    
    # 3. Scrape cocktail menu
    print(f"\n[3] Scraping cocktail menu...")
    cocktail_html = fetch_html(COCKTAIL_MENU_URL, HEADERS)
    if cocktail_html:
        cocktail_items = extract_cocktail_items_from_html(cocktail_html)
        all_items.extend(cocktail_items)
        print(f"[INFO] Extracted {len(cocktail_items)} items from cocktail menu")
    
    # 4. Scrape specials menu
    print(f"\n[4] Scraping specials menu...")
    specials_html = fetch_html(SPECIALS_MENU_URL, HEADERS)
    if specials_html:
        specials_items = extract_specials_items_from_html(specials_html)
        all_items.extend(specials_items)
        print(f"[INFO] Extracted {len(specials_items)} items from specials menu")
    
    # 5. Scrape happy hour menu
    print(f"\n[5] Scraping happy hour menu...")
    happy_hour_html = fetch_html(HAPPY_HOUR_MENU_URL, HEADERS)
    if happy_hour_html:
        happy_hour_items = extract_happy_hour_items_from_html(happy_hour_html)
        all_items.extend(happy_hour_items)
        print(f"[INFO] Extracted {len(happy_hour_items)} items from happy hour menu")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "wishingwellrestaurant_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

