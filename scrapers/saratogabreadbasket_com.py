"""
Scraper for: https://saratogabreadbasket.com/
Handles both HTML (Bakery Menu) and PDF (Cake Orders)
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

# API Key
GOOGLE_API_KEY = 'AIzaSyD2rneYIn8ahscrSTRJlKhqJg_NUoRiqjQ'

# Initialize Gemini
if GEMINI_AVAILABLE:
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
        
        prompt = """Analyze this bakery menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The item name (e.g., "Chocolate Cake", "Vanilla Cupcake", "Birthday Cake")
2. **description**: The description/details (e.g., "8 inch round cake", "Serves 8-10 people")
3. **price**: The price (e.g., "$35", "$15.99")

Important guidelines:
- Extract ALL menu items from the page, including cakes, cupcakes, cookies, pastries, etc.
- Item names are usually in larger/bolder font
- Descriptions are usually in smaller font below the name
- Prices are usually at the end of the description line or on a separate line
- If an item has no description, use empty string ""
- Skip section headers as items (like "CAKES", "CUPCAKES", "COOKIES", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- Ensure all prices have a "$" symbol

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Chocolate Cake",
    "description": "8 inch round cake, serves 8-10",
    "price": "$35"
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
    Extract menu items from HTML soup for bakery menu.
    Structure: h3 for sections, h4 for item names, p for descriptions/prices
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
        
        for i, section in enumerate(sections):
            section_text = section.get_text(strip=True)
            
            # Skip empty sections
            if not section_text:
                continue
            
            # This is a section header
            current_section = section_text
            
            # Find the next h3 section (boundary)
            next_section = None
            if i + 1 < len(sections):
                next_section = sections[i + 1]
            
            # Find all h4 elements (item names) after this h3 until next h3
            h4_elements = []
            current_h4 = section.find_next('h4')
            while current_h4:
                # Find the previous h3 before this h4
                prev_h3 = current_h4.find_previous('h3')
                
                # Stop if we've reached the next section
                if next_section:
                    # Check if there's an h3 between section and current_h4 that is the next_section
                    if prev_h3 == next_section:
                        break
                
                # Only include h4 if its previous h3 is our current section
                if prev_h3 == section:
                    h4_text = current_h4.get_text(strip=True)
                    if h4_text and len(h4_text) > 1:
                        h4_elements.append(current_h4)
                else:
                    # We've gone past our section
                    break
                
                current_h4 = current_h4.find_next('h4')
            
            # Process each h4 element
            for h4 in h4_elements:
                item_name = h4.get_text(strip=True)
                
                if not item_name or len(item_name) < 2:
                    continue
                
                # Look for description and price in following elements
                description = ""
                price = ""
                
                # Find next p element after this h4
                next_p = h4.find_next('p')
                if next_p:
                    # Check if this p is before the next h4 or h3
                    next_h4_after = h4.find_next('h4')
                    next_h3_after = h4.find_next('h3')
                    
                    # Only use this p if it's before the next h4/h3
                    if (not next_h4_after or (next_p.find_previous('h4') == h4 and (not next_h4_after or next_p.find_previous('h4') != next_h4_after))) and \
                       (not next_h3_after or (next_p.find_previous('h3') == section or next_p.find_previous('h3') != next_h3_after)):
                        text = next_p.get_text(strip=True)
                        
                        if text:
                            # Look for price pattern
                            price_match = re.search(r'(\$?\d+\.?\d*)', text)
                            if price_match:
                                price = price_match.group(1)
                                if not price.startswith('$'):
                                    price = f"${price}"
                                
                                # Description is text before price
                                desc_text = text[:price_match.start()].strip()
                                if desc_text:
                                    description = desc_text
                            else:
                                # No price, might be description only
                                description = text
                
                # If no price found, check if price is in the h4 text itself
                if not price:
                    price_match = re.search(r'(\$?\d+\.?\d*)', item_name)
                    if price_match:
                        price = price_match.group(1)
                        if not price.startswith('$'):
                            price = f"${price}"
                        item_name = item_name[:price_match.start()].strip()
                
                if item_name and len(item_name) > 1:
                    items.append({
                        'name': item_name,
                        'description': description,
                        'price': price,
                        'section': current_section
                    })
        
        # Also check for items in paragraph format (name and price in same paragraph)
        paragraphs = main_content.find_all('p')  # pyright: ignore[reportAttributeAccessIssue]
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            
            # Look for price pattern
            price_match = re.search(r'(\$?\d+\.?\d*)$', text)
            if price_match:
                price = price_match.group(1)
                if not price.startswith('$'):
                    price = f"${price}"
                
                # Name and description before price
                name_desc = text[:price_match.start()].strip()
                
                # Try to find if this item was already added
                # Check if name_desc matches any existing item name
                already_added = False
                for existing_item in items:
                    if existing_item['name'].lower() in name_desc.lower() or name_desc.lower() in existing_item['name'].lower():
                        # Update description if needed
                        if not existing_item['description'] and name_desc != existing_item['name']:
                            existing_item['description'] = name_desc.replace(existing_item['name'], '').strip()
                        already_added = True
                        break
                
                if not already_added and name_desc:
                    # Try to find section from parent
                    section = ""
                    parent = p.find_parent(['div', 'section'])
                    if parent:
                        section_h3 = parent.find('h3')
                        if section_h3:
                            section = section_h3.get_text(strip=True)
                    
                    # Split name and description if possible
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
                            'section': section
                        })
        
    except Exception as e:
        print(f"  Error extracting HTML menu items: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_saratogabreadbasket_menu():
    """
    Main function to scrape both bakery menu (HTML) and cake orders (PDF) from saratogabreadbasket.com
    """
    url = "https://saratogabreadbasket.com/"
    restaurant_name = "Bread Basket Bakery"
    
    print(f"Scraping: {url}")
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    all_items = []
    
    # ===== BAKERY MENU (HTML) =====
    print("\n[1/2] Processing Bakery Menu (HTML)...")
    bakery_url = "https://saratogabreadbasket.com/bakery/"
    
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://saratogabreadbasket.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get(bakery_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        bakery_items = extract_menu_items_from_html(soup)
        
        for item in bakery_items:
            section = item.get('section', '').upper() if item.get('section') else 'BAKERY'
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': f'BAKERY - {section}',
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Bakery'
            })
        
        print(f"[OK] Extracted {len(bakery_items)} items from Bakery Menu")
        
    except Exception as e:
        print(f"[ERROR] Failed to scrape Bakery Menu: {e}")
    
    # ===== CAKE ORDERS (PDF) =====
    print("\n[2/2] Processing Cake Orders (PDF)...")
    cake_pdf_url = "https://saratogabreadbasket.com/wp-content/uploads/2025/09/Bread-Basket-Bakery-Cake-Orders-2025.pdf"
    
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    pdf_path = temp_dir / "saratogabreadbasket_cake_orders.pdf"
    
    if download_pdf_with_requests(cake_pdf_url, pdf_path):
        cake_items = extract_menu_from_pdf(str(pdf_path))
        
        for item in cake_items:
            all_items.append({
                'name': item.get('name', ''),
                'description': item.get('description', ''),
                'price': item.get('price', ''),
                'menu_type': 'CAKE ORDERS',
                'restaurant_name': restaurant_name,
                'restaurant_url': url,
                'menu_name': 'Cake Orders'
            })
        
        print(f"[OK] Extracted {len(cake_items)} items from Cake Orders PDF")
    else:
        print("[ERROR] Failed to download Cake Orders PDF")
    
    # Save to JSON
    output_file = output_dir / "saratogabreadbasket_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Extracted {len(all_items)} total items from all menus")
    print(f"Saved to: {output_file}")
    
    return all_items


if __name__ == "__main__":
    scrape_saratogabreadbasket_menu()

