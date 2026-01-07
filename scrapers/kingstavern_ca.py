"""
Scraper for King's Tavern (kingstavern.ca)
Scrapes menu from multiple PDFs using Gemini Vision API
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
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
RESTAURANT_NAME = "King's Tavern"
RESTAURANT_URL = "https://kingstavern.ca/"

# PDF URLs
PDF_URLS = [
    {
        'url': 'https://kingstavern.ca/storage/2024/03/kings-tavern-Main-Menu_Web.pdf',
        'name': 'Main Menu'
    },
    {
        'url': 'https://kingstavern.ca/storage/2024/08/ktaugbreakfast.-pdf.pdf',
        'name': 'Breakfast Menu'
    },
    {
        'url': 'https://kingstavern.ca/storage/2024/08/ktaugLunch.pdf',
        'name': 'Lunch Menu'
    },
    {
        'url': 'https://kingstavern.ca/storage/2023/12/Desserts.pdf',
        'name': 'Desserts Menu'
    },
    {
        'url': 'https://kingstavern.ca/storage/2022/01/Kids_Menu.pdf',
        'name': 'Kids Menu'
    },
    {
        'url': 'https://kingstavern.ca/storage/2024/04/Daily-Specials_v2_web.pdf',
        'name': 'Daily Specials'
    },
    {
        'url': 'https://kingstavern.ca/storage/2023/12/BAR_MENU.pdf',
        'name': 'Bar Menu'
    }
]


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


def extract_menu_from_pdf_with_gemini(pdf_path: Path, menu_name: str) -> List[Dict]:
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
            print(f"[INFO] Processing {menu_name} PDF page {page_num}/{len(images)}")
            
            prompt = f"""Extract all menu items from this {menu_name} page. For each item, provide:
- name: The item name
- description: Any description, ingredients, or notes
- price: The price if available. Handle multi-price, multi-size, and add-ons:
  * Single price: "$X.XX"
  * Multiple sizes: "Small $X.XX | Medium $Y.YY | Large $Z.ZZ" or "20oz Pint $X.XX | 60oz Pitcher $Y.YY"
  * Multiple prices (different options): "Option1 $X.XX | Option2 $Y.YY"
  * Price ranges: "$X.XX - $Y.YY" if there's a range
  * Add-ons: Include add-on prices in the description if they are listed with the item (e.g., "Description text. Add-ons: cheese $1.00, bacon $2.00")
- section: The menu section/category (e.g., "Appetizers", "Entrees", "Desserts", "Breakfast", "Lunch", "Dinner", "Beverages", "Beer", "Wine", "Cocktails", "Kids Menu", "Daily Specials", etc.)

IMPORTANT: 
- If an item has multiple sizes (Small/Medium/Large, 20oz/60oz, 6oz/9oz/Bottle, etc.), format price as "Size1 $X.XX | Size2 $Y.YY | Size3 $Z.ZZ"
- If an item has multiple price options, format as "Option1 $X.XX | Option2 $Y.YY"
- Include add-ons in the description if they are listed with the item (e.g., "Description text. Add-ons: cheese $1.00, bacon $2.00")
- Extract all prices accurately, including decimal values
- Identify menu sections correctly (Breakfast, Lunch, Dinner, Appetizers, Entrees, Desserts, Beverages, Beer, Wine, Cocktails, Kids Menu, Daily Specials, etc.)
- For bar menu items, include size information in the price (e.g., "20oz Pint $6.50 | 60oz Pitcher $19.00")
- For wine, include size options (6oz, 9oz, Bottle) in the price format
- For daily specials, include the day in the section name (e.g., "Daily Specials - Monday", "Daily Specials - Friday")

Return ONLY a valid JSON array of objects with these fields. If a field is not available, use null.
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
    "section": "Main Course"
  }},
  {{
    "name": "Beer",
    "description": "Domestic beer",
    "price": "20oz Pint $6.50 | 60oz Pitcher $19.00",
    "section": "Beer"
  }}
]"""
            
            try:
                response = model.generate_content([prompt, image])
                response_text = response.text.strip()
                
                # Extract JSON from response
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    items = json.loads(json_match.group())
                    all_items.extend(items)
                    print(f"[INFO] Extracted {len(items)} items from {menu_name} page {page_num}")
                else:
                    print(f"[WARNING] No JSON array found in response for {menu_name} page {page_num}")
                    print(f"[DEBUG] Response preview: {response_text[:200]}")
            except Exception as e:
                print(f"[ERROR] Error processing {menu_name} page {page_num}: {e}")
                continue
        
        return all_items
    except Exception as e:
        print(f"[ERROR] Error extracting from {menu_name} PDF: {e}")
        return []


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME}")
    all_items = []
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Process each PDF
    for pdf_info in PDF_URLS:
        pdf_url = pdf_info['url']
        menu_name = pdf_info['name']
        
        print(f"\n[INFO] Processing {menu_name}...")
        
        # Download PDF
        pdf_filename = pdf_url.split('/')[-1]
        pdf_path = temp_dir / pdf_filename
        
        if not download_pdf(pdf_url, pdf_path):
            print(f"[ERROR] Failed to download {menu_name} PDF, skipping...")
            continue
        
        # Extract menu items from PDF using Gemini
        items = extract_menu_from_pdf_with_gemini(pdf_path, menu_name)
        
        # Add restaurant info and ensure section has menu name prefix
        for item in items:
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
            
            # If section doesn't already include menu name, prefix it
            section = item.get('section', '')
            if section and menu_name.lower() not in section.lower():
                item['section'] = f"{menu_name} - {section}" if section else menu_name
            elif not section:
                item['section'] = menu_name
        
        all_items.extend(items)
        print(f"[INFO] Extracted {len(items)} items from {menu_name}")
    
    print(f"\n[INFO] Extracted {len(all_items)} menu items total from all PDFs")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "kingstavern_ca.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

