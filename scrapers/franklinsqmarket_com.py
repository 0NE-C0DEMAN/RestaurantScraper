"""
Scraper for Franklin Square Market
Website: http://www.franklinsqmarket.com/
- Deli Menu: PDF format
- Market Bar & Restaurant Menu: HTML format
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict
from pathlib import Path
import time
import os
from io import BytesIO

# Check for optional dependencies
try:
    import google.generativeai as genai
    from pdf2image import convert_from_path
    import pdfplumber
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Gemini API key
GOOGLE_API_KEY = 'AIzaSyD2rneYIn8ahscrSTRJlKhqJg_NUoRiqjQ'

if GEMINI_AVAILABLE:
    genai.configure(api_key=GOOGLE_API_KEY)  # pyright: ignore[reportPrivateImportUsage]

def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 60, retries: int = 3) -> bool:
    """
    Download PDF from URL using requests.
    """
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.franklinsqmarket.com/',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'cross-site',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    for attempt in range(retries):
        try:
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  [OK] Downloaded PDF: {output_path.name}")
            return True
            
        except Exception as e:
            print(f"  [ERROR] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
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
        img_buffer = BytesIO()
        image.save(img_buffer, format='PNG')
        image_data = img_buffer.getvalue()
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this deli menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The item name (e.g., "Turkey Sandwich", "Italian Sub", "Chicken Salad")
2. **description**: The description/ingredients/details
3. **price**: The price (e.g., "$8.99", "$12.50")

Important guidelines:
- Extract ALL menu items from the page, including sandwiches, subs, salads, sides, etc.
- Item names are usually in larger/bolder font
- Descriptions are usually in smaller font below the name
- Prices are usually at the end of the description line or on a separate line
- If an item has no description, use empty string ""
- Skip section headers as items (like "SANDWICHES", "SUBS", "SALADS", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- Ensure all prices have a "$" symbol

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Turkey Sandwich",
    "description": "Sliced turkey, lettuce, tomato, mayo",
    "price": "$8.99"
  }
]"""
        
        print("  Extracting menu items using Gemini Vision API...")
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
        
        # Extract JSON from response - use same pattern as fourseasonsnaturalfoods_com.py
        response_text = response.text.strip()
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        try:
            response_text = response_text.encode('utf-8', errors='ignore').decode('utf-8')
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            items = json.loads(response_text)
            
            if not isinstance(items, list):
                items = [items]
            
            # Clean items
            cleaned_items = []
            for item in items:
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
            
            print(f"    Extracted {len(cleaned_items)} items from page")
            return cleaned_items
            
        except json.JSONDecodeError as e:
            print(f"    [WARNING] Could not parse JSON from Gemini response: {e}")
            print(f"    Response text (first 500 chars): {response_text[:500]}")
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
    Extract menu items from Market Bar & Restaurant HTML menu.
    Structure: Items use CSS classes:
    - menu-item: container for each item
    - menu-item-title: item name
    - menu-item-description: item description
    - menu-item-price-top or menu-item-price-bottom: item price (with currency-sign span)
    """
    items = []
    
    try:
        # Find main content
        main = soup.find('main') or soup.find('article')
        if not main:
            print("  [WARNING] Could not find main content")
            return []
        
        # Find all menu-item containers
        menu_items = main.find_all('div', class_='menu-item')
        print(f"  Found {len(menu_items)} menu-item containers")
        
        processed_items = set()
        known_subsections = ['smalls', 'shares', 'salads', 'seafood + raw', 'mains', 'desserts', 'COCKTAILS', 'MOCKTAILS']
        
        for item_container in menu_items:
            # Find title
            title_elem = item_container.find('div', class_='menu-item-title')
            if not title_elem:
                continue
            
            name = title_elem.get_text(strip=True)
            
            # Skip if name is empty or looks like a section header
            if not name or (name.isupper() and ('MENU' in name or name in ['SMALLS', 'SHARES', 'SALADS', 'SEAFOOD + RAW', 'MAINS', 'DESSERTS', 'COCKTAILS', 'MOCKTAILS'])):
                continue
            
            # Find description
            desc_elem = item_container.find('div', class_='menu-item-description')
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            # Find price - check both price-top and price-bottom
            price = ""
            price_elem = item_container.find('span', class_='menu-item-price-top')
            if not price_elem:
                price_elem = item_container.find('div', class_='menu-item-price-bottom')
            
            if price_elem:
                # Price is split: currency-sign span with "$" and then the number
                price_text = price_elem.get_text(strip=True)
                # Extract price - handle formats like "$6", "$ 6", "$18 / half dozen $34 / dozen"
                price_match = re.search(r'\$\s*[\d]+(?:\.[\d]{2})?', price_text)
                if price_match:
                    price = price_match.group(0).replace(' ', '')
                    
                    # Handle multiple prices
                    all_prices = re.findall(r'\$\s*[\d]+(?:\.[\d]{2})?', price_text)
                    if len(all_prices) >= 2:
                        clean_prices = [p.replace(' ', '') for p in all_prices]
                        if 'half dozen' in price_text.lower() and 'dozen' in price_text.lower():
                            price = f"{clean_prices[0]} / half dozen {clean_prices[1]} / dozen"
                        elif ' / ' in price_text or '/' in price_text:
                            price = f"{clean_prices[0]} / {clean_prices[1]}"
                        else:
                            price = f"{clean_prices[0]} / {clean_prices[1]}"
            
            # If still no price, check if it's in description (for items like "half shell oysters")
            if not price:
                # Some items have price in description like "18/half dozen 36/dozen"
                desc_price_match = re.search(r'(\d+)/half dozen (\d+)/dozen', description)
                if desc_price_match:
                    price = f"${desc_price_match.group(1)} / half dozen ${desc_price_match.group(2)} / dozen"
                    # Remove price from description
                    description = re.sub(r'\d+/half dozen \d+/dozen', '', description).strip()
                else:
                    # Try simple price pattern
                    simple_price = re.search(r'\$[\d]+(?:\.[\d]{2})?', description)
                    if simple_price:
                        price = simple_price.group(0)
                        description = re.sub(r'\s+\$[\d]+.*$', '', description).strip()
            
            # Determine menu type by finding the parent menu-section
            menu_type = ""
            
            # Find the parent menu-section
            menu_section = item_container.find_parent('div', class_='menu-section')
            if menu_section:
                # Find the section title
                section_title_elem = menu_section.find('div', class_='menu-section-title')
                if section_title_elem:
                    section_title = section_title_elem.get_text(strip=True)
                    if section_title:
                        menu_type = section_title
                        print(f"    Item '{name[:30]}...' -> section: {menu_type}")
            
            # If no section found, look for subsection headers before this item
            if not menu_type or menu_type == "MENU":
                # Look for subsection headers in previous siblings
                parent_menu_items = item_container.find_parent('div', class_='menu-items')
                if parent_menu_items:
                    # Find previous divs that might be subsection headers
                    prev_elem = parent_menu_items.find_previous_sibling('div')
                    if prev_elem:
                        prev_text = prev_elem.get_text(strip=True)
                        if prev_text.lower() in [s.lower() for s in known_subsections] or prev_text.upper() in [s.upper() for s in known_subsections]:
                            menu_type = prev_text
                            print(f"    Item '{name[:30]}...' -> subsection: {menu_type}")
                
                # If still no menu_type, look backwards for section headers
                if not menu_type or menu_type == "MENU":
                    all_prev = item_container.find_all_previous(['div'], limit=100)
                    for prev_elem in all_prev:
                        prev_text = prev_elem.get_text(strip=True)
                        # Check for menu-section-title
                        if prev_elem.get('class') and 'menu-section-title' in prev_elem.get('class'):
                            menu_type = prev_text
                            break
                        # Check for subsection
                        if prev_text.lower() in [s.lower() for s in known_subsections] or prev_text.upper() in [s.upper() for s in known_subsections]:
                            menu_type = prev_text
                            # Continue to find section
                            continue
                        # Check for section header
                        if prev_text.isupper() and 'MENU' in prev_text:
                            if menu_type and menu_type not in known_subsections:
                                # We already have a subsection, combine them
                                menu_type = f"{prev_text} - {menu_type}"
                            else:
                                menu_type = prev_text
                            break
            
            # Final fallback
            if not menu_type or menu_type == "MENU":
                menu_type = "Menu"
            
            # Create unique key to avoid duplicates
            item_key = (name, price, menu_type)
            if item_key not in processed_items and name and price:
                processed_items.add(item_key)
                items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'menu_type': menu_type
                })
        
        print(f"  Extracted {len(items)} items from HTML menu")
        
    except Exception as e:
        print(f"  [ERROR] Error extracting HTML menu: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_franklinsqmarket_menu() -> List[Dict]:
    """
    Main function to scrape both Deli (PDF) and Market Bar & Restaurant (HTML) menus.
    """
    all_items = []
    
    print("=" * 60)
    print("Scraping: Franklin Square Market")
    print("=" * 60)
    
    # ===== DELI MENU (PDF) =====
    print("\n[1/2] Scraping Deli Menu (PDF)...")
    deli_pdf_url = "https://static1.squarespace.com/static/650c5435e40b2f3565159a35/t/66bb9bd32d66df00f93f5e90/1723571155813/Deli+Trifold_Aug5.pdf"
    
    # Create temp directory
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / 'franklinsqmarket_deli_menu.pdf'
    
    if download_pdf_with_requests(deli_pdf_url, pdf_path):
        deli_items = extract_menu_from_pdf(str(pdf_path))
        
        for item in deli_items:
            item['menu_type'] = item.get('menu_type', 'Deli')
            item['restaurant_name'] = "Franklin Square Market"
            item['restaurant_url'] = "http://www.franklinsqmarket.com/"
            item['menu_name'] = "Deli Menu"
        
        all_items.extend(deli_items)
        print(f"[OK] Extracted {len(deli_items)} items from Deli Menu")
        
        # Clean up
        if pdf_path.exists():
            pdf_path.unlink()
    else:
        print("[ERROR] Failed to download Deli PDF")
    
    # ===== MARKET BAR & RESTAURANT MENU (HTML) =====
    print("\n[2/2] Scraping Market Bar & Restaurant Menu (HTML)...")
    restaurant_menu_url = "https://www.marketbarandrestaurant.com/menu"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Referer': 'https://www.marketbarandrestaurant.com/'
        }
        
        response = requests.get(restaurant_menu_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        restaurant_items = extract_menu_items_from_html(soup)
        
        for item in restaurant_items:
            item['restaurant_name'] = "Market Bar & Restaurant"
            item['restaurant_url'] = "https://www.marketbarandrestaurant.com/"
            item['menu_name'] = item.get('menu_type', 'Menu')
        
        all_items.extend(restaurant_items)
        print(f"[OK] Extracted {len(restaurant_items)} items from Market Bar & Restaurant Menu")
        
    except Exception as e:
        print(f"[ERROR] Error scraping restaurant menu: {e}")
        import traceback
        traceback.print_exc()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    
    url_safe = "franklinsqmarket_com"
    output_json = output_dir / f'{url_safe}.json'
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(all_items)}")
    print(f"  - Deli Menu: {len([i for i in all_items if i.get('menu_name') == 'Deli Menu'])} items")
    print(f"  - Market Bar & Restaurant: {len([i for i in all_items if i.get('menu_name') != 'Deli Menu'])} items")
    print(f"Saved to: {output_json}")
    print("=" * 60)
    
    return all_items


if __name__ == "__main__":
    scrape_franklinsqmarket_menu()

