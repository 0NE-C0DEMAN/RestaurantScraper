"""
Scraper for Putnam Market (putnammarket.com)
"""
import json
import re
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup
from io import BytesIO

# Try to import Gemini and PDF processing libraries
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Get the project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_FILE = PROJECT_ROOT / "config.json"
TEMP_DIR = PROJECT_ROOT / "temp"

# Load Gemini API key
GEMINI_API_KEY = None
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        GEMINI_API_KEY = config.get('gemini_api_key')

if GEMINI_AVAILABLE and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MENU_PDFS = [
    {
        "url": "https://putnammarket.com/wp-content/uploads/2025/11/PutnamCafeMenu-1225.pdf",
        "menu_name": "Café Menu",
        "menu_type": "Café"
    },
    {
        "url": "https://putnammarket.com/wp-content/uploads/2025/06/HappyHourPrices.pdf",
        "menu_name": "Happy Hour Menu",
        "menu_type": "Happy Hour"
    },
    {
        "url": "https://putnammarket.com/wp-content/uploads/2025/11/LUNCH-MENU-2025-D.pdf",
        "menu_name": "Sandwich + Salad Menu",
        "menu_type": "Sandwiches & Salads"
    },
    {
        "url": "https://putnammarket.com/wp-content/uploads/2025/11/Catering2025-d.pdf",
        "menu_name": "Catering Menu",
        "menu_type": "Catering"
    },
    {
        "url": "https://putnammarket.com/wp-content/uploads/2025/07/Cakes2025.pdf",
        "menu_name": "Custom Cakes Menu",
        "menu_type": "Custom Cakes"
    }
]

def download_pdf(url: str, output_path: Path) -> bool:
    """Download PDF from URL using requests"""
    try:
        headers = {
            "accept": "application/pdf,*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
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
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Pasta", "Pizza", "Cocktails", "Wine", "Happy Hour", "Coffee", "Tea", "Beverages", etc.)

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
- For coffee/tea menus, include the drink name and any key details in the description
- For happy hour menus, include the time/availability info if shown

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {{
    "name": "Item Name",
    "description": "Description text. Add-ons: add chicken +$7.95",
    "price": "$12 | $30",
    "section": "Section Name"
  }}
]"""
        
        # Process each page
        for page_num, image in enumerate(images):
            print(f"    Processing page {page_num + 1}/{len(images)} with Gemini...")
            
            # Convert PIL image to bytes
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            image_data = img_byte_arr.read()
            
            try:
                response = model.generate_content(
                    [prompt, {
                        "mime_type": "image/png",
                        "data": image_data
                    }],
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 8000,
                    }
                )
                response_text = response.text.strip()
                
            except Exception as e:
                print(f"    [ERROR] Gemini API error on page {page_num + 1}: {e}")
                continue
            
            # Parse JSON from response
            response_text = re.sub(r'```json\s*', '', response_text)
            response_text = re.sub(r'```\s*', '', response_text)
            response_text = response_text.strip()
            
            try:
                page_items = json.loads(response_text)
                if isinstance(page_items, list):
                    for item in page_items:
                        item['restaurant_name'] = "Putnam Market"
                        item['restaurant_url'] = "https://putnammarket.com/"
                        item['menu_type'] = menu_type
                        item['menu_name'] = item.get('section', menu_name)
                        
                        # Format price if needed
                        price = item.get('price', '')
                        if price and not price.startswith('$'):
                            # Try to format prices like "5.5/6" or "12/15"
                            if '/' in price:
                                parts = price.split('/')
                                if len(parts) == 2:
                                    try:
                                        p1 = float(parts[0].strip())
                                        p2 = float(parts[1].strip())
                                        item['price'] = f"${p1:.2f} | ${p2:.2f}".replace('.00', '')
                                    except ValueError:
                                        item['price'] = f"${price}"
                            elif price.replace('.', '').replace('-', '').isdigit():
                                try:
                                    p = float(price)
                                    item['price'] = f"${p:.2f}".replace('.00', '')
                                except ValueError:
                                    item['price'] = f"${price}"
                            else:
                                item['price'] = price
                    all_items.extend(page_items)
                    print(f"      [OK] Extracted {len(page_items)} items from page {page_num + 1}")
                else:
                    print(f"      [WARNING] Expected list, got {type(page_items)}")
            except json.JSONDecodeError as e:
                print(f"      [ERROR] Failed to parse JSON from Gemini response for page {page_num + 1}: {e}")
                print(f"      Response preview: {response_text[:200]}...")
                continue
        
    except Exception as e:
        print(f"    [ERROR] Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
    
    return all_items

def parse_sandwiches_salads_html(html_content: str) -> List[Dict]:
    """Parse menu items from Sandwiches & Salads HTML page"""
    items = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all section headings (h3)
    sections = soup.find_all('h3')
    
    for section in sections:
        section_name = section.get_text(strip=True)
        if not section_name or section_name.lower() in ['menu', 'weekly specials']:
            continue
        
        # Find the next sibling paragraph with items
        next_elem = section.find_next_sibling()
        while next_elem:
            if next_elem.name == 'h3':
                break
            
            if next_elem.name == 'p':
                # Parse items from paragraph
                # Items are in format: "NAME:" description
                text = next_elem.get_text()
                
                # Find all strong tags (item names)
                strong_tags = next_elem.find_all('strong')
                for strong in strong_tags:
                    item_name = strong.get_text(strip=True)
                    # Remove quotes if present
                    item_name = item_name.strip('"').strip("'")
                    if not item_name or ':' not in item_name:
                        continue
                    
                    # Extract name (before colon)
                    name_parts = item_name.split(':', 1)
                    if len(name_parts) < 2:
                        continue
                    
                    name = name_parts[0].strip()
                    # Get description (after colon, from strong tag to end of paragraph or next strong)
                    desc_text = ""
                    current = strong.next_sibling
                    while current:
                        if isinstance(current, str):
                            desc_text += current
                        elif current.name == 'strong':
                            break
                        elif current.name in ['em', 'span']:
                            desc_text += current.get_text()
                        current = current.next_sibling
                    
                    description = desc_text.strip()
                    
                    # Skip if no name or description
                    if not name or not description:
                        continue
                    
                    items.append({
                        "name": name,
                        "description": description,
                        "price": "",  # No prices in HTML
                        "restaurant_name": "Putnam Market",
                        "restaurant_url": "https://putnammarket.com/",
                        "menu_type": "Sandwiches & Salads",
                        "menu_name": section_name
                    })
            
            next_elem = next_elem.find_next_sibling()
    
    return items

def scrape_putnammarket() -> List[Dict]:
    """Scrape menu from Putnam Market website"""
    print("=" * 60)
    print("Scraping Putnam Market (putnammarket.com)")
    print("=" * 60)
    
    all_items = []
    TEMP_DIR.mkdir(exist_ok=True)
    
    # Note: We skip the HTML version of Sandwiches & Salads since the PDF version has prices
    # The PDF version will be processed in step 2 below
    
    # 2. Download and process PDF menus
    print(f"\n[2] Downloading and processing PDF menus...")
    for menu_info in MENU_PDFS:
        print(f"\n  Processing {menu_info['menu_name']}...")
        pdf_path = TEMP_DIR / f"putnam_{menu_info['menu_name'].lower().replace(' ', '_')}.pdf"
        
        # Download PDF
        print(f"    Downloading PDF from {menu_info['url']}...")
        if not download_pdf(menu_info['url'], pdf_path):
            continue
        
        # Extract items using Gemini
        pdf_items = extract_menu_from_pdf_with_gemini(
            pdf_path, 
            menu_info['menu_name'], 
            menu_info['menu_type']
        )
        all_items.extend(pdf_items)
        print(f"    [OK] Extracted {len(pdf_items)} items from {menu_info['menu_name']}")
    
    # Filter out items with no price and no description
    filtered_items = []
    for item in all_items:
        if item.get('price') or item.get('description'):
            filtered_items.append(item)
    
    print(f"\n[3] Filtered {len(all_items) - len(filtered_items)} items with no price and no description")
    all_items = filtered_items
    
    # Save to JSON
    output_file = OUTPUT_DIR / "putnammarket_com.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved {len(all_items)} items to {output_file}")
    
    # Show sample items
    if all_items:
        print(f"\n[4] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            price_str = item.get('price', 'N/A')
            section = item.get('menu_name', 'Menu')
            print(f"  {i}. {item.get('name', 'N/A')} - {price_str} ({section})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items

if __name__ == "__main__":
    scrape_putnammarket()

