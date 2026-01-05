"""
Scraper for panzasrestaurant.com (Panza's Restaurant)
Scrapes menu from PDF files: Dinner Menu, Wine Menu, Cocktail Menu, and Happy Hour Menu
Uses Gemini Vision API to extract menu data from PDF pages
"""

import json
import re
from pathlib import Path
from typing import List, Dict
from io import BytesIO

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


# Menu PDF URLs
MENU_PDFS = [
    {
        "url": "https://www.panzasrestaurant.com/_files/ugd/6d03a4_ea1e8f46d7354ae9ad754b380a5f4a1d.pdf",
        "menu_name": "Dinner Menu",
        "menu_type": "Dinner"
    },
    {
        "url": "https://www.panzasrestaurant.com/_files/ugd/6d03a4_ea19ea1f51eb461b81ec6490bcae834c.pdf",
        "menu_name": "Wine Menu",
        "menu_type": "Wine"
    },
    {
        "url": "https://www.panzasrestaurant.com/_files/ugd/6d03a4_11babf335eec49dfa2d2b74a8d5421c8.pdf",
        "menu_name": "Cocktail Menu",
        "menu_type": "Cocktails"
    },
    {
        "url": "https://www.panzasrestaurant.com/_files/ugd/6d03a4_ad263a6eecdd407a8fef7088b0b18ccc.pdf",
        "menu_name": "Happy Hour Menu",
        "menu_type": "Happy Hour"
    }
]


def download_pdf(url: str, output_path: Path) -> bool:
    """Download PDF from URL using requests (direct PDF links work fine with requests)"""
    try:
        import requests
        headers = {
            "accept": "application/pdf,*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.panzasrestaurant.com/"
        }
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download PDF from {url}: {e}")
        return False


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
2. **description**: The description/ingredients/details for THIS specific item only. CRITICAL: If there are addons listed near this item (like "ADD CHICKEN $7.95" or "Add chicken +$6"), include them in the description field. Format as: "Description text. Add-ons: add chicken +$7.95 / add shrimp +$10.95"
3. **price**: The price. CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
   * "Small $12 | Large $30"
   * "Half $10 | Full $18"
   * "Single $13 | Family $30"
   * "Glass $8 | Bottle $32"
   If only one price is shown, format as "$X". Always include the $ symbol.
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Pasta", "Pizza", "Cocktails", "Wine", "Happy Hour", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby, include them in that item's description field
- Item names are usually in larger/bolder font
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line
- If an item has multiple prices (e.g., "12 | 30" or "Small 12, Large 30"), ALWAYS include the size labels: "Small $12 | Large $30"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Glass", "Bottle", "Half", "Full", "Small", "Large", "Single", "Family")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field
- For wine menus, include the wine name, vintage (if shown), and region in the name field
- For cocktail menus, include the cocktail name and any key ingredients in the description

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Chicken Parmesan",
    "description": "Breaded chicken with marinara and mozzarella. Add-ons: add extra cheese +$3",
    "price": "$25",
    "section": "Entrees"
  }},
  {{
    "name": "Caesar Salad",
    "description": "Crisp romaine, parmesan, caesar dressing. Add-ons: add chicken +$7.95",
    "price": "Small $10 | Large $18",
    "section": "Salads"
  }},
  {{
    "name": "Chardonnay",
    "description": "Buttery, oaked, California",
    "price": "Glass $8 | Bottle $32",
    "section": "White Wine"
  }}
]"""
        
        # Process pages in pairs for efficiency
        for i in range(0, len(images), 2):
            if i + 1 < len(images):
                # Two pages to process together
                page1 = images[i]
                page2 = images[i + 1]
                print(f"    Processing pages {i + 1} and {i + 2}...", end=" ")
                
                try:
                    response = model.generate_content([prompt, page1, page2])
                    response_text = response.text.strip()
                except Exception as e:
                    print(f"[ERROR] {e}")
                    continue
            else:
                # Only one page left
                page1 = images[i]
                print(f"    Processing page {i + 1}...", end=" ")
                
                try:
                    response = model.generate_content([prompt, page1])
                    response_text = response.text.strip()
                except Exception as e:
                    print(f"[ERROR] {e}")
                    continue
            
            # Parse JSON from response
            response_text = re.sub(r'```json\s*', '', response_text)
            response_text = re.sub(r'```\s*', '', response_text)
            response_text = response_text.strip()
            
            # Remove any non-JSON content at the beginning
            json_start = -1
            for j, char in enumerate(response_text):
                if char in ['[', '{']:
                    json_start = j
                    break
            
            if json_start > 0:
                response_text = response_text[json_start:]
            
            # Remove any trailing non-JSON content
            json_end = -1
            for j in range(len(response_text) - 1, -1, -1):
                if response_text[j] in [']', '}']:
                    json_end = j + 1
                    break
            
            if json_end > 0 and json_end < len(response_text):
                response_text = response_text[:json_end]
            
            try:
                page_items = json.loads(response_text)
                if isinstance(page_items, list):
                    all_items.extend(page_items)
                    print(f"[OK] Found {len(page_items)} items")
                else:
                    print(f"[WARNING] Unexpected response format")
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse JSON: {e}")
                print(f"[DEBUG] Response text: {response_text[:500]}")
        
    except Exception as e:
        print(f"[ERROR] Failed to extract menu from {menu_name}: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return all_items


def format_price(price: str) -> str:
    """Format price to ensure $ symbol and handle sizes"""
    if not price:
        return ""
    
    price = price.strip()
    
    # Check if price already has $ symbols
    has_dollar = '$' in price
    
    # Handle multiple prices with sizes
    if '|' in price:
        price_parts = price.split('|')
        formatted_parts = []
        for i, part in enumerate(price_parts):
            part = part.strip()
            # Check if it already has a size label
            size_match = re.search(r'\b(small|large|regular|family|single|double|half|full|petite|grande|glass|bottle|cup|bowl)\b', part.lower())
            if size_match:
                # Has size label - format numbers with $ if not already present
                if not has_dollar:
                    part = re.sub(r'(\d+\.?\d*)', r'$\1', part)
                else:
                    # Remove any double $ symbols
                    part = re.sub(r'\$\$+', '$', part)
            else:
                # No size label - infer one if this is a multiple price item
                if len(price_parts) == 2:
                    if i == 0:
                        size_label = "Small"
                    else:
                        size_label = "Large"
                    
                    # Format the price part
                    if not has_dollar:
                        if part and part[0].isdigit():
                            part = f"{size_label} ${part}"
                    else:
                        if part.startswith('$'):
                            part = f"{size_label} {part}"
                        elif part and part[0].isdigit():
                            part = f"{size_label} ${part}"
                else:
                    # More than 2 prices or just formatting
                    if not has_dollar:
                        if part and part[0].isdigit():
                            part = '$' + part
                    elif not part.startswith('$') and part and part[0].isdigit():
                        part = '$' + part
            formatted_parts.append(part)
        price = ' | '.join(formatted_parts)
    else:
        # Single price
        if not has_dollar:
            if price and price[0].isdigit():
                price = '$' + price
        elif not price.startswith('$') and price and price[0].isdigit():
            price = '$' + price
    
    # Clean up any double $ symbols
    price = re.sub(r'\$\$+', '$', price)
    return price


def scrape_panzas_menu() -> List[Dict]:
    """Scrape menu from Panza's Restaurant"""
    print("=" * 60)
    print("Scraping Panza's Restaurant (panzasrestaurant.com)")
    print("=" * 60)
    
    restaurant_name = "Panza's Restaurant"
    restaurant_url = "https://www.panzasrestaurant.com/"
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    all_items = []
    
    # Download and process each PDF
    print(f"\n[1] Downloading and processing PDF menus...")
    for menu_info in MENU_PDFS:
        pdf_url = menu_info['url']
        menu_name = menu_info['menu_name']
        menu_type = menu_info['menu_type']
        
        print(f"\n  Processing {menu_name}...")
        
        # Download PDF
        pdf_filename = f"panzas_{menu_type.lower().replace(' ', '_')}.pdf"
        pdf_path = temp_dir / pdf_filename
        
        if not download_pdf(pdf_url, pdf_path):
            print(f"  [ERROR] Failed to download {menu_name}")
            continue
        
        print(f"  [OK] Downloaded {menu_name}")
        
        # Extract menu items
        items = extract_menu_from_pdf_with_gemini(pdf_path, menu_name, menu_type)
        
        # Format and add metadata
        for item in items:
            # Format price
            if 'price' in item:
                item['price'] = format_price(item.get('price', ''))
            
            # Add restaurant metadata
            item['restaurant_name'] = restaurant_name
            item['restaurant_url'] = restaurant_url
            item['menu_type'] = menu_type
            item['menu_name'] = item.get('section', menu_name)
            
            # Remove section field (we use menu_name instead)
            if 'section' in item:
                del item['section']
        
        all_items.extend(items)
        print(f"  [OK] Extracted {len(items)} items from {menu_name}")
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Save to JSON
    output_path = Path(__file__).parent.parent / "output" / "panzasrestaurant_com.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(all_items)} items to {output_path}")
    
    # Print sample items
    if all_items:
        print(f"\n[2] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            print(f"  {i}. {item['name']} - {item.get('price', 'N/A')} ({item['menu_type']} / {item['menu_name']})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items


if __name__ == "__main__":
    scrape_panzas_menu()

