"""
Scraper for: https://beneluxny.com/
Handles both PDF (Dinner) and HTML (Lunch) menus
"""

import json
import os
import sys
import time
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup

# Gemini Vision API setup
try:
    import google.generativeai as genai
    from pdf2image import convert_from_path
    import pdfplumber
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai, pdf2image, or pdfplumber not installed.")
    print("Install with: pip install google-generativeai pdf2image Pillow pdfplumber")

# Load API Key from config.json
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GOOGLE_API_KEY = config.get("gemini_api_key", "")
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    print(f"Warning: Could not load API key from config.json: {e}")
    GOOGLE_API_KEY = ""

# Initialize Gemini
if GEMINI_AVAILABLE and GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)  # pyright: ignore[reportPrivateImportUsage]


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 60, retries: int = 3) -> bool:
    """
    Download PDF using requests library with retries.
    """
    print(f"  Downloading: {pdf_url}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"  Retry attempt {attempt}/{retries}...")
                time.sleep(2 * (attempt - 1))
            
            response = requests.get(
                pdf_url,
                timeout=timeout,
                stream=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
                    'Accept': 'application/pdf,application/octet-stream,*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
            )
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            if output_path.exists():
                size = output_path.stat().st_size
                
                if size < 100:
                    print(f"  [ERROR] File too small ({size} bytes)")
                    output_path.unlink()
                    continue
                
                with open(output_path, 'rb') as f:
                    first_bytes = f.read(4)
                    if first_bytes == b'%PDF':
                        print(f"  [OK] Downloaded {size:,} bytes")
                        return True
                    else:
                        print(f"  [ERROR] File doesn't appear to be a PDF")
                        output_path.unlink()
                        continue
            else:
                print(f"  [ERROR] File was not created")
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Request failed: {e}")
            if attempt == retries:
                return False
            continue
        except Exception as e:
            print(f"  [ERROR] Unexpected error: {e}")
            if attempt == retries:
                return False
            continue
    
    return False


def extract_menu_from_pdf_image(pdf_path: str, page_num: int) -> List[Dict]:
    """
    Extract menu items from a single PDF page using Gemini Vision API.
    """
    if not GEMINI_AVAILABLE:
        return []
    
    try:
        # Convert PDF page to image
        images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1, dpi=300)
        if not images:
            return []
        
        image = images[0]
        
        # Convert to bytes
        from io import BytesIO
        img_buffer = BytesIO()
        image.save(img_buffer, format='PNG')
        image_data = img_buffer.getvalue()
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Steak Frites", "Mussels", "Salmon")
2. **description**: The description/ingredients
3. **price**: The price (e.g., "$28", "$15.95")

Important guidelines:
- Extract ALL menu items from the page, including appetizers, entrees, sides, desserts, drinks, etc.
- Item names are usually in larger/bolder font
- Descriptions are usually in smaller font below the name
- Prices are usually at the end of the description line or on a separate line
- If an item has no description, use empty string ""
- Skip section headers as items (like "APPETIZERS", "ENTRÉES", "DINNER", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- Ensure all prices have a "$" symbol

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Steak Frites",
    "description": "Grilled steak with french fries",
    "price": "$28"
  }
]"""
        
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
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        try:
            response_text = response_text.encode('utf-8', errors='ignore').decode('utf-8')
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            menu_items = json.loads(response_text)
            
            cleaned_items = []
            for item in menu_items:
                if isinstance(item, dict):
                    price = str(item.get('price', '')).strip()
                    if price and not price.startswith('$'):
                        price = f"${price}"
                    
                    cleaned_item = {
                        'name': str(item.get('name', '')).strip(),
                        'description': str(item.get('description', '')).strip(),
                        'price': price
                    }
                    if cleaned_item['name']:
                        cleaned_items.append(cleaned_item)
            
            return cleaned_items
            
        except json.JSONDecodeError as e:
            print(f"    Warning: Could not parse JSON from Gemini response: {e}")
            return []
        
    except Exception as e:
        print(f"    Error processing PDF page {page_num}: {e}")
        return []


def extract_menu_from_pdf(pdf_path: str) -> List[Dict]:
    """
    Extract menu items from all pages of a PDF using Gemini Vision API.
    """
    if not GEMINI_AVAILABLE:
        print("Gemini not available. Install: pip install google-generativeai pdf2image Pillow pdfplumber")
        return []
    
    all_items = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
        
        print(f"  Processing {num_pages} page(s) with Gemini Vision API...")
        
        for page_num in range(num_pages):
            print(f"  Processing page {page_num + 1}/{num_pages}...")
            items = extract_menu_from_pdf_image(pdf_path, page_num)
            all_items.extend(items)
            print(f"    Found {len(items)} items on page {page_num + 1}")
            
            if page_num < num_pages - 1:
                time.sleep(1)
        
        print(f"  Total items extracted: {len(all_items)}")
        
    except Exception as e:
        print(f"  Error processing PDF: {e}")
    
    return all_items


def extract_menu_items_from_html(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract menu items from HTML soup for lunch menu.
    Format: "ITEM NAME | PRICE Description" or "ITEM NAME | PRICE\nDescription"
    """
    items = []
    
    try:
        # Find the main content area
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
        if not main_content:
            main_content = soup
        
        # Find all h3 headings which are section headers
        sections = main_content.find_all('h3')  # pyright: ignore[reportAttributeAccessIssue]
        
        current_section = ""
        
        # Process each section
        for i, section in enumerate(sections):
            section_text = section.get_text(strip=True)
            
            # Skip if it's just "LUNCH MENU:" header
            if section_text.upper() == "LUNCH MENU:":
                continue
            
            # Check if this is a section header (all caps or has specific patterns)
            if section_text and (section_text.isupper() or len(section_text.split()) <= 5):
                current_section = section_text
                
                # Find all paragraphs after this section header until next h3
                next_section = None
                if i + 1 < len(sections):
                    next_section = sections[i + 1]
                
                # Get all elements between this h3 and next h3
                current_elem = section.next_sibling
                while current_elem:
                    if current_elem == next_section:
                        break
                    
                    if hasattr(current_elem, 'name') and current_elem.name == 'h3':
                        break
                    
                    # Process paragraph elements
                    if hasattr(current_elem, 'name') and current_elem.name == 'p':
                        text = current_elem.get_text(strip=True)
                        if not text or len(text) < 5:
                            current_elem = current_elem.next_sibling
                            continue
                        
                        # Format: "ITEM NAME | PRICE Description" or "ITEM NAME | PRICE\nDescription"
                        # Look for pattern with pipe separator
                        if '|' in text:
                            parts = text.split('|', 1)
                            name_part = parts[0].strip()
                            price_desc_part = parts[1].strip() if len(parts) > 1 else ""
                            
                            # Extract price (number at start of price_desc_part)
                            price_match = re.search(r'^(\d+\.?\d*)', price_desc_part)
                            if price_match:
                                price = price_match.group(1)
                                if not price.startswith('$'):
                                    price = f"${price}"
                                
                                # Description is everything after the price
                                description = price_desc_part[price_match.end():].strip()
                                
                                if name_part and len(name_part) > 2:
                                    items.append({
                                        'name': name_part,
                                        'description': description,
                                        'price': price,
                                        'section': current_section
                                    })
                        else:
                            # Try to find price at end of line
                            price_match = re.search(r'(\$?\d+\.?\d*)$', text)
                            if price_match:
                                price = price_match.group(1)
                                if not price.startswith('$'):
                                    price = f"${price}"
                                
                                name_desc = text[:price_match.start()].strip()
                                
                                # Try to split name and description
                                if ' - ' in name_desc:
                                    parts = name_desc.split(' - ', 1)
                                    name = parts[0].strip()
                                    description = parts[1].strip() if len(parts) > 1 else ""
                                else:
                                    name = name_desc
                                    description = ""
                                
                                if name and len(name) > 2:
                                    items.append({
                                        'name': name,
                                        'description': description,
                                        'price': price,
                                        'section': current_section
                                    })
                    
                    current_elem = current_elem.next_sibling
        
        # Also try to find items in list format (ul/li)
        list_items = main_content.find_all('li')  # pyright: ignore[reportAttributeAccessIssue]
        for li in list_items:
            text = li.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            
            # Look for price pattern
            if '|' in text:
                parts = text.split('|', 1)
                name_part = parts[0].strip()
                price_desc_part = parts[1].strip() if len(parts) > 1 else ""
                
                price_match = re.search(r'^(\d+\.?\d*)', price_desc_part)
                if price_match:
                    price = price_match.group(1)
                    if not price.startswith('$'):
                        price = f"${price}"
                    
                    description = price_desc_part[price_match.end():].strip()
                    
                    if name_part and len(name_part) > 2:
                        # Try to find section from parent
                        section = ""
                        parent = li.find_parent(['div', 'section'])
                        if parent:
                            section_h3 = parent.find('h3')
                            if section_h3:
                                section = section_h3.get_text(strip=True)
                        
                        items.append({
                            'name': name_part,
                            'description': description,
                            'price': price,
                            'section': section
                        })
            else:
                # Try price at end
                price_match = re.search(r'(\$?\d+\.?\d*)$', text)
                if price_match:
                    price = price_match.group(1)
                    if not price.startswith('$'):
                        price = f"${price}"
                    
                    name_desc = text[:price_match.start()].strip()
                    
                    if ' - ' in name_desc:
                        parts = name_desc.split(' - ', 1)
                        name = parts[0].strip()
                        description = parts[1].strip() if len(parts) > 1 else ""
                    else:
                        name = name_desc
                        description = ""
                    
                    if name and len(name) > 2:
                        section = ""
                        parent = li.find_parent(['div', 'section'])
                        if parent:
                            section_h3 = parent.find('h3')
                            if section_h3:
                                section = section_h3.get_text(strip=True)
                        
                        items.append({
                            'name': name,
                            'description': description,
                            'price': price,
                            'section': section
                        })
        
    except Exception as e:
        print(f"  Error extracting HTML menu items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_beneluxny_menu():
    """
    Main function to scrape both dinner (PDF) and lunch (HTML) menus from beneluxny.com
    """
    url = "https://beneluxny.com/"
    restaurant_name = "Brasserie Benelux"
    
    print(f"Scraping: {url}")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    all_items = []
    
    # ===== DINNER MENU (PDF) =====
    print("\n[1/2] Processing Dinner Menu (PDF)...")
    dinner_pdf_url = "https://beneluxny.com/wp-content/uploads/2024/07/belmont-menu-brasserie-pdf.pdf"
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    pdf_path = temp_dir / "benelux_dinner_menu.pdf"
    
    if download_pdf_with_requests(dinner_pdf_url, pdf_path):
        dinner_items = extract_menu_from_pdf(str(pdf_path))
        
        for item in dinner_items:
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': 'DINNER',
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Dinner'
            })
        
        print(f"[OK] Extracted {len(dinner_items)} items from Dinner Menu")
    else:
        print("[ERROR] Failed to download Dinner Menu PDF")
    
    # ===== LUNCH MENU (HTML) =====
    print("\n[2/2] Processing Lunch Menu (HTML)...")
    lunch_url = "https://beneluxny.com/benelux-menu/"
    
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get(lunch_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        lunch_items = extract_menu_items_from_html(soup)
        
        for item in lunch_items:
            section = item.get('section', '').upper() if item.get('section') else 'LUNCH'
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': f'LUNCH - {section}',
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Lunch'
            })
        
        print(f"[OK] Extracted {len(lunch_items)} items from Lunch Menu")
        
    except Exception as e:
        print(f"[ERROR] Failed to scrape Lunch Menu: {e}")
    
    # Save to JSON
    output_file = output_dir / "beneluxny_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Extracted {len(all_items)} total items from all menus")
    print(f"Saved to: {output_file}")
    
    return all_items


if __name__ == "__main__":
    scrape_beneluxny_menu()

