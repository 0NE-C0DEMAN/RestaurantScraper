"""
Scraper for The Inn at Saratoga (theinnatsaratoga.com)
Scrapes menu from PDF files: Food Menu and Drinks Menu
Uses Gemini Vision API to extract menu data from PDF pages
Handles: multi-price, multi-size, and add-ons
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
        GEMINI_API_KEY = config.get("gemini_api_key") or config.get("GEMINI_API_KEY")
except Exception as e:
    print(f"Warning: Could not load API key from config.json: {e}")

if GEMINI_AVAILABLE and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# Restaurant configuration
RESTAURANT_NAME = "The Inn at Saratoga"
RESTAURANT_URL = "http://www.theinnatsaratoga.com/"

# Menu PDF URLs
MENU_PDFS = [
    {
        "url": "https://document-tc.galaxy.tf/wdpdf-alwu5jzaamn8wosww6upcm978/food-drinks_cms-document.pdf",
        "menu_name": "Food & Drinks Menu",
        "menu_type": "Food & Drinks"
    }
    # If drinks menu has a different URL, add it here:
    # {
    #     "url": "https://document-tc.galaxy.tf/wdpdf-alwu5jzaamn8wosww6upcm978/drinks-menu.pdf",
    #     "menu_name": "Drinks Menu",
    #     "menu_type": "Drinks"
    # }
]


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """Download PDF from URL using requests"""
    try:
        import requests
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
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Cocktails", "Wine", "Beer", "Breakfast", "Brunch", "Lunch", "Dinner", "Desserts", etc.)

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line, often after a "/" separator
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap", "Cup", "Bowl", "Pint", "Glass", "Bottle")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field
- For combined food & drinks menus, sections might include: "Appetizers", "Entrees", "Salads", "Soups", "Sandwiches", "Burgers", "Pizza", "Desserts", "Cocktails", "Wine", "Beer", "Non-Alcoholic Beverages", etc.

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
  }},
  {{
    "name": "Old Fashioned",
    "description": "Bourbon, sugar, bitters, orange peel",
    "price": "$12",
    "section": "Cocktails"
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
    
    # Handle multiple prices with sizes (separated by |)
    if '|' in price:
        price_parts = price.split('|')
        formatted_parts = []
        for part in price_parts:
            part = part.strip()
            # Ensure $ symbol is present
            if not has_dollar and part and part[0].isdigit():
                # Find the first number and add $ before it
                part = re.sub(r'(\d+\.?\d*)', r'$\1', part, count=1)
            formatted_parts.append(part)
        price = ' | '.join(formatted_parts)
    else:
        # Single price
        if not has_dollar:
            if price and price[0].isdigit():
                price = '$' + price
    
    return price


def scrape_innatsaratoga() -> List[Dict]:
    """Scrape menu from The Inn at Saratoga PDF menus"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME}")
    print("=" * 60)
    
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
        pdf_filename = f"restaurant_{menu_type.lower().replace(' ', '_').replace('&', 'and')}.pdf"
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
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
            item['menu_type'] = menu_type
            item['menu_name'] = item.get('section', menu_name)
            
            # Use section from item, or default to menu_name
            if 'section' not in item or not item['section']:
                item['section'] = menu_name
        
        all_items.extend(items)
        print(f"  [OK] Extracted {len(items)} items from {menu_name}")
        
        # Clean up
        try:
            pdf_path.unlink()
        except:
            pass
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    return all_items


if __name__ == "__main__":
    items = scrape_innatsaratoga()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    
    # Generate output filename
    output_filename = "theinnatsaratoga_com.json"
    output_file = output_dir_path / output_filename
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

