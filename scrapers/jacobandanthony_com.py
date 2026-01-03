"""
Scraper for Jacob and Anthony's Italian menu
https://www.jacobandanthony.com/menus-italian/

IMPORTANT: This scraper follows the standard pattern for handling:
1. Size variations: Multiple prices with size labels (e.g., "Small - $11 / Entree - $15")
2. Add-ons: Items with multiple add-on options, each with its own price and label
   (e.g., "Grilled Chicken - $7 / Tuscan Chicken - $8 / ...")
3. Single prices: Items with one price (e.g., "$16")

All prices with size/type variations MUST include labels in the price field.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup
from io import BytesIO

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
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GOOGLE_API_KEY = config.get("gemini_api_key", "")
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    print(f"Warning: Could not load API key from config.json: {e}")
    GOOGLE_API_KEY = ""

if GEMINI_AVAILABLE and GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)  # pyright: ignore[reportPrivateImportUsage]


def download_html_with_requests(url: str) -> str:
    """Download HTML content using requests"""
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "referer": "https://www.jacobandanthony.com/location/italian/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML: {e}")
        return ""


def parse_brunch_menu_page(html: str) -> List[Dict]:
    """
    Parse brunch menu items from HTML
    Structure is the same as regular menu but without tabs - just sections with h2 headings
    Uses the same class structure: menu-item, menu-item__heading--name, menu-item__details--description, menu-item__details--price
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find all menu sections (no tabs, just sections)
    menu_sections = soup.find_all('section', class_='menu-section')
    
    for menu_section in menu_sections:
        # Get section name from h2
        section_header = menu_section.find('div', class_='menu-section__header')
        if section_header:
            section_name = section_header.find('h2')
            if section_name:
                menu_type = section_name.get_text(strip=True)
            else:
                menu_type = "Other"
        else:
            menu_type = "Other"
        
        # Find all menu items in this section
        menu_items = menu_section.find_all('li', class_='menu-item')
        
        for item_elem in menu_items:
            # Get item name
            name_elem = item_elem.find('p', class_='menu-item__heading--name')
            if not name_elem:
                continue
            
            item_name = name_elem.get_text(strip=True)
            if not item_name:
                continue
            
            # Get description
            desc_elem = item_elem.find('p', class_='menu-item__details--description')
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            # Get all prices (some items have multiple prices - bottomless cocktails have 2)
            price_elems = item_elem.find_all('p', class_='menu-item__details--price')
            
            prices = []
            for price_elem in price_elems:
                # Get price value
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'\$(\d+(?:\.\d{2})?)', price_text)
                if price_match:
                    price_value = price_match.group(1)
                    prices.append(price_value)
            
            # Format prices with labels
            # For bottomless cocktails, first price is single, second is bottomless
            if len(prices) == 0:
                price = ""
            elif len(prices) == 1:
                price = f"${prices[0]}"
            elif len(prices) == 2 and menu_type.lower() in ['bottomless cocktails', 'cocktails']:
                # Bottomless cocktails have two prices: single and bottomless
                price = f"Single - ${prices[0]} / Bottomless - ${prices[1]}"
            else:
                # Multiple prices - format with labels if we can determine them
                price = " / ".join([f"${p}" for p in prices])
            
            # Get dietary info from description
            if "(GF)" in description or "gluten free" in description.lower():
                if "(GF)" in description:
                    description = description.replace("(GF)", "(gluten free)")
                elif "gluten free" not in description.lower():
                    description += " (gluten free)"
            
            items.append({
                'name': item_name,
                'description': description,
                'price': price,
                'menu_type': menu_type
            })
    
    return items


def parse_menu_page(html: str, is_brunch: bool = False) -> List[Dict]:
    """
    Parse menu items from HTML
    Structure:
    - For regular menu: Menu sections are in <section class="menu-section"> with <h2> for section name
    - For brunch menu: Sections are in <div> with <h2> headings
    - Items are in <li class="menu-item"> or just <li> for brunch
    - Item name: <p class="menu-item__heading menu-item__heading--name"> or first <p> for brunch
    - Description: <p class="menu-item__details--description"> or second <p> for brunch
    - Prices: <p class="menu-item__details menu-item__details--price"> with size labels
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    if is_brunch:
        # Brunch menu structure - simpler, no tabs
        # Find all sections (divs with h2 headings)
        sections = soup.find_all(['div', 'section'])
        
        for section in sections:
            # Look for h2 headings to identify sections
            h2 = section.find('h2')
            if not h2:
                continue
            
            menu_type = h2.get_text(strip=True)
            # Remove "menu" keyword if present
            menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
            
            # Find all list items in this section
            list_items = section.find_all('li')
            
            for item_elem in list_items:
                # Get all paragraphs
                paragraphs = item_elem.find_all('p')
                if len(paragraphs) < 1:
                    continue
                
                # First paragraph is usually the item name
                item_name = paragraphs[0].get_text(strip=True)
                if not item_name:
                    continue
                
                # Second paragraph is usually the description
                description = paragraphs[1].get_text(strip=True) if len(paragraphs) > 1 else ""
                
                # Remaining paragraphs contain prices
                prices = []
                for p in paragraphs[2:]:
                    # Extract price from paragraph
                    price_text = p.get_text(strip=True)
                    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', price_text)
                    if price_match:
                        price_value = price_match.group(1)
                        # Check if there's a size label in the paragraph
                        # For brunch cocktails, first price is usually single, second is bottomless
                        if len(prices) == 0 and len(paragraphs) > 3:
                            # This might be a single price
                            prices.append(f"Single - ${price_value}")
                        elif len(prices) == 1:
                            # Second price is usually bottomless
                            prices.append(f"Bottomless - ${price_value}")
                        else:
                            prices.append(f"${price_value}")
                
                # Format price string
                if len(prices) == 0:
                    price = ""
                elif len(prices) == 1:
                    price = prices[0]
                else:
                    price = " / ".join(prices)
                
                # Get dietary info from description
                dietary_info = ""
                if "(GF)" in description or "gluten free" in description.lower():
                    dietary_info = "gluten free"
                
                if dietary_info and dietary_info not in description:
                    if description:
                        description += f" ({dietary_info})"
                    else:
                        description = dietary_info
                
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'menu_type': menu_type
                })
    else:
        # Regular menu structure with tabs
        # Find all tabpanels (menu sections)
        tabpanels = soup.find_all('section', {'role': 'tabpanel'})
        
        for tabpanel in tabpanels:
            # Get the tab name from the tabpanel id or aria-labelledby
            tab_id = tabpanel.get('id', '')
            tab_name = tab_id.replace('-', ' ').title() if tab_id else 'Unknown'
            
            # Find all menu sections within this tabpanel
            menu_sections = tabpanel.find_all('section', class_='menu-section')
            
            for menu_section in menu_sections:
                # Get section name from h2
                section_header = menu_section.find('div', class_='menu-section__header')
                if section_header:
                    section_name = section_header.find('h2')
                    if section_name:
                        menu_type = section_name.get_text(strip=True)
                    else:
                        menu_type = tab_name
                else:
                    menu_type = tab_name
                
                # Find all menu items in this section
                menu_items = menu_section.find_all('li', class_='menu-item')
            
            for item_elem in menu_items:
                # Get item name
                name_elem = item_elem.find('p', class_='menu-item__heading--name')
                if not name_elem:
                    continue
                
                item_name = name_elem.get_text(strip=True)
                if not item_name:
                    continue
                
                # Get description
                desc_elem = item_elem.find('p', class_='menu-item__details--description')
                description = desc_elem.get_text(strip=True) if desc_elem else ""
                
                # Get all prices (some items have multiple prices with size labels)
                price_elems = item_elem.find_all('p', class_='menu-item__details--price')
                
                prices = []
                for price_elem in price_elems:
                    # Get size label (first strong tag)
                    size_label = ""
                    strong_tags = price_elem.find_all('strong')
                    if strong_tags:
                        # First strong tag is usually the size label
                        first_strong = strong_tags[0].get_text(strip=True)
                        if first_strong and not first_strong.startswith('$'):
                            size_label = first_strong
                    
                    # Get price value (from span with menu-item__currency or second strong)
                    price_text = price_elem.get_text(strip=True)
                    # Extract price using regex
                    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', price_text)
                    if price_match:
                        price_value = price_match.group(1)
                        if size_label:
                            prices.append(f"{size_label} - ${price_value}")
                        else:
                            prices.append(f"${price_value}")
                
                # Format price string
                if len(prices) == 0:
                    price = ""
                elif len(prices) == 1:
                    price = prices[0]
                else:
                    # Multiple prices - join with " / "
                    price = " / ".join(prices)
                
                # Special handling for add-on items (items with multiple add-on options)
                # If item name suggests it's an add-on section and has multiple prices with different labels
                if item_name.lower() in ['add to salad', 'add to', 'add-on', 'add ons', 'addons'] or 'add' in item_name.lower():
                    # Check if we have multiple prices with different labels (not just size variations)
                    if len(prices) > 1:
                        # This is an add-on section - format each option clearly
                        # Prices are already formatted with labels, so we're good
                        pass
                
                # Get dietary info
                dietary_info = ""
                info_elem = item_elem.find('p', class_='menu-item__details--info')
                if info_elem:
                    dietary_info = info_elem.get_text(strip=True)
                
                # Add dietary info to description if present
                if dietary_info and dietary_info not in description:
                    if description:
                        description += f" ({dietary_info})"
                    else:
                        description = dietary_info
                
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'menu_type': menu_type
                })
    
    return items


def scrape_jacobandanthony_italian_menu(url: str) -> List[Dict]:
    """
    Scrape menu from jacobandanthony.com/menus-italian/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's Italian"
    restaurant_url = "https://www.jacobandanthony.com/menus-italian/"
    
    print("=" * 60)
    print(f"Scraping Italian Menu: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing menu items...")
        items = parse_menu_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "Italian Menu"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing: Format prices with size labels
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_brunch_menu(url: str) -> List[Dict]:
    """
    Scrape brunch menu from jacobandanthony.com/menu/brunch/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's Italian"
    restaurant_url = "https://www.jacobandanthony.com/menu/brunch/"
    
    print("=" * 60)
    print(f"Scraping Brunch Menu: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.jacobandanthony.com/weekly-features-italian/"
        }
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing menu items...")
        items = parse_brunch_menu_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "Brunch"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing: Format prices with size labels
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 120, retries: int = 3) -> bool:
    """Download PDF from URL using requests with proper headers"""
    headers = {
        'accept': '*/*',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'referer': 'https://www.jacobandanthony.com/'
    }
    
    for attempt in range(retries):
        try:
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  [OK] Downloaded PDF: {output_path.name} ({output_path.stat().st_size / 1024:.1f} KB)")
            return True
            
        except Exception as e:
            print(f"  [WARNING] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
    
    return False


def extract_menu_from_pdf_with_gemini(pdf_path: str, menu_name: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    Extract menu items from PDF using Gemini Vision API by converting PDF pages to images.
    """
    if not GEMINI_AVAILABLE:
        print("  [ERROR] Gemini not available")
        return []
    
    if not PDF2IMAGE_AVAILABLE:
        print("  [ERROR] pdf2image not available. Install with: pip install pdf2image")
        return []
    
    all_items = []
    
    try:
        print(f"  Converting PDF pages to images for {menu_name}...")
        # Convert PDF pages to images
        images = convert_from_path(pdf_path, dpi=200)
        print(f"  [OK] Converted {len(images)} pages to images")
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')  # pyright: ignore[reportPrivateImportUsage]
        
        prompt = """Analyze this restaurant menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Chicken Parmesan", "Meatball Platter", "Antipasto")
2. **description**: The description/ingredients/details for THIS specific item only
3. **price**: The price (e.g., "$25", "$35.99", "$12.95")
4. **menu_type**: The section/category name (e.g., "Platters", "Appetizers", "Entrees", "Sides")

Important guidelines:
- Extract ALL menu items from the page
- Item names are usually in larger/bolder font
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line
- If an item has multiple prices with size variations (e.g., "Small - $X / Large - $Y"), format as "Size1 - $X / Size2 - $Y"
- If an item has no description, use empty string ""
- Include section headers in the menu_type field (like "Platters", "Appetizers", "Entrees", etc.)
- Skip footer text (address, phone, website, etc.)
- Handle items that appear on the same line correctly - each should have its own entry
- Ensure all prices have a "$" symbol
- Group items by their section/category using the menu_type field
- For platters/catering menus, common sections include: Platters, Appetizers, Entrees, Sides, Desserts, etc.

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.
Example format:
[
  {
    "name": "Chicken Parmesan Platter",
    "description": "Breaded chicken with marinara and mozzarella, serves 8-10",
    "price": "$45",
    "menu_type": "Platters"
  }
]"""
        
        # Process each page
        for page_num, image in enumerate(images):
            print(f"  Processing page {page_num + 1}/{len(images)} with Gemini...")
            
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
                print(f"  [ERROR] Gemini API error on page {page_num + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Parse JSON from response
            response_text = re.sub(r'```json\s*', '', response_text)
            response_text = re.sub(r'```\s*', '', response_text)
            response_text = response_text.strip()
            
            try:
                page_items = json.loads(response_text)
                if isinstance(page_items, list):
                    for item in page_items:
                        if not item.get('menu_type'):
                            item['menu_type'] = menu_type_default
                    all_items.extend(page_items)
                    print(f"  [OK] Extracted {len(page_items)} items from page {page_num + 1}")
                else:
                    print(f"  [WARNING] Unexpected response format from Gemini on page {page_num + 1}")
            except json.JSONDecodeError as e:
                print(f"  [ERROR] Failed to parse JSON from Gemini response on page {page_num + 1}: {e}")
                print(f"  Response text (first 500 chars): {response_text[:500]}")
                continue
        
    except Exception as e:
        print(f"  [ERROR] Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
    
    return all_items


def parse_weekly_features_page(html: str) -> List[Dict]:
    """
    Parse weekly features from HTML
    Structure: sections with h2 headings containing specials
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find all sections with h2 headings
    main_content = soup.find('main')
    if not main_content:
        return items
    
    # Find all h2 headings to identify sections
    sections = main_content.find_all(['section', 'div'], class_=lambda x: x and ('c-split' in x or 'content' in x))  # pyright: ignore[reportAttributeAccessIssue, reportArgumentType]
    
    for section in sections:
        # Find h2 heading
        h2 = section.find('h2')
        if not h2:
            continue
        
        # Skip if it's just an image
        if h2.find('img'):
            # Look for next h2 that's not an image
            next_h2 = h2.find_next_sibling('h2')
            if next_h2 and not next_h2.find('img'):
                menu_type = next_h2.get_text(strip=True)
            else:
                continue
        else:
            menu_type = h2.get_text(strip=True)
        
        # Remove "menu" keyword if present
        menu_type = re.sub(r'\bmenu\b', '', menu_type, flags=re.IGNORECASE).strip()
        
        # Get all paragraphs in this section
        content_div = section.find('div', class_='c-split__content')
        if not content_div:
            content_div = section
        
        paragraphs = content_div.find_all('p')
        
        # Extract items based on section type
        if 'Monday Special' in menu_type:
            # Monday Special: $12.95 Chicken Parmesan
            for p in paragraphs:
                text = p.get_text(strip=True)
                if '$' in text:
                    # Extract price and item name
                    price_match = re.search(r'\$(\d+\.?\d*)', text)
                    if price_match:
                        price = f"${price_match.group(1)}"
                        # Remove price from text to get item name
                        item_name = re.sub(r'\$\d+\.?\d*', '', text).strip()
                        if item_name:
                            items.append({
                                'name': item_name,
                                'description': paragraphs[1].get_text(strip=True) if len(paragraphs) > 1 else "",
                                'price': price,
                                'menu_type': menu_type
                            })
                            break
        
        elif 'Dinner Table Tuesdays' in menu_type:
            # Dinner Table Tuesdays: Family of four platter: $20.25 | With salad platter: $35.25
            # Options: Nino's Meatballs & Sausage, Chicken a la Vodka, Rigatoni Bolognese
            price_text = ""
            options = []
            
            for p in paragraphs:
                text = p.get_text(strip=True)
                if 'platter:' in text.lower() or '|' in text:
                    price_text = text
                elif 'Choose from' in text or '<br>' in str(p):
                    # Extract options
                    options_text = p.get_text(separator='\n', strip=True)
                    # Split by newlines and filter out empty/instructional text
                    for line in options_text.split('\n'):
                        line = line.strip()
                        if line and 'Choose from' not in line and len(line) > 3:
                            options.append(line)
            
            # Extract prices
            if price_text:
                prices = re.findall(r'\$(\d+\.?\d*)', price_text)
                if len(prices) == 2:
                    price = f"Family of four - ${prices[0]} / With salad platter - ${prices[1]}"
                else:
                    price = price_text
            else:
                price = ""
            
            # Create items for each option
            if options:
                for option in options:
                    items.append({
                        'name': option,
                        'description': price_text if price_text else "",
                        'price': price,
                        'menu_type': menu_type
                    })
            else:
                # If no options found, create a single item
                items.append({
                    'name': menu_type,
                    'description': price_text if price_text else "",
                    'price': price,
                    'menu_type': menu_type
                })
        
        elif 'Wine Wednesdays' in menu_type:
            # Wine Wednesdays: Half off select bottles up to $75!
            description = ""
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and 'Wine' not in text:
                    description += text + " "
            
            items.append({
                'name': menu_type,
                'description': description.strip(),
                'price': "",  # No specific price, it's a discount
                'menu_type': menu_type
            })
        
        elif 'Social Hour' in menu_type:
            # Social Hour: Monday through Friday from 4PM - 6PM (has PDF link)
            description = ""
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and 'View Menu' not in text:
                    description += text + " "
            
            items.append({
                'name': menu_type,
                'description': description.strip(),
                'price': "",
                'menu_type': menu_type
            })
    
    return items


def scrape_jacobandanthony_weekly_features(url: str) -> List[Dict]:
    """
    Scrape weekly features from jacobandanthony.com/weekly-features-italian/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's Italian"
    restaurant_url = "https://www.jacobandanthony.com/weekly-features-italian/"
    
    print("=" * 60)
    print(f"Scraping Weekly Features: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.jacobandanthony.com/menu/brunch/"
        }
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing weekly features...")
        items = parse_weekly_features_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "Weekly Features"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_platters_pdf(pdf_url: str) -> List[Dict]:
    """
    Scrape take-home platters from PDF
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's Italian"
    restaurant_url = "https://www.jacobandanthony.com/take-home-platters-at-janda-italian/"
    
    print("=" * 60)
    print(f"Scraping Take Home Platters PDF: {pdf_url}")
    print("=" * 60)
    
    # Create temp directory for PDFs
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / 'jacob_platters.pdf'
    
    try:
        # Download PDF
        print(f"Downloading PDF...")
        if not download_pdf_with_requests(pdf_url, pdf_path):
            print(f"[ERROR] Failed to download PDF")
            return []
        
        print(f"\nExtracting menu items from PDF...")
        items = extract_menu_from_pdf_with_gemini(str(pdf_path), "Take Home Platters", "Platters")
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "Take Home Platters"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Platters"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    finally:
        # Clean up PDF file
        if pdf_path.exists():
            pdf_path.unlink()
    
    return all_items


def scrape_jacobandanthony_grille_menu(url: str) -> List[Dict]:
    """
    Scrape menu from jacobandanthony.com/menus-grille/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's The Grille"
    restaurant_url = "https://www.jacobandanthony.com/menus-grille/"
    
    print("=" * 60)
    print(f"Scraping The Grille Menu: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing menu items...")
        items = parse_menu_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "The Grille Menu"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing: Format prices with size labels
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_grille_brunch_menu(url: str) -> List[Dict]:
    """
    Scrape brunch menu from jacobandanthony.com/menu/brunch-the-grille/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's The Grille"
    restaurant_url = "https://www.jacobandanthony.com/menu/brunch-the-grille/"
    
    print("=" * 60)
    print(f"Scraping The Grille Brunch Menu: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.jacobandanthony.com/menus-grille/"
        }
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing menu items...")
        items = parse_brunch_menu_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "The Grille Brunch"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing: Format prices with size labels
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_grille_weekly_features(url: str) -> List[Dict]:
    """
    Scrape weekly features from jacobandanthony.com/weekly-features-grille/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's The Grille"
    restaurant_url = "https://www.jacobandanthony.com/weekly-features-grille/"
    
    print("=" * 60)
    print(f"Scraping The Grille Weekly Features: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.jacobandanthony.com/menu/brunch-the-grille/"
        }
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing weekly features...")
        items = parse_weekly_features_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "The Grille Weekly Features"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_grille_platters_pdf(pdf_url: str) -> List[Dict]:
    """
    Scrape take-home platters from PDF for The Grille
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's The Grille"
    restaurant_url = "https://www.jacobandanthony.com/take-home-platters-at-janda-italian/"
    
    print("=" * 60)
    print(f"Scraping The Grille Take Home Platters PDF: {pdf_url}")
    print("=" * 60)
    
    # Create temp directory for PDFs
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / 'jacob_grille_platters.pdf'
    
    try:
        # Download PDF
        print(f"Downloading PDF...")
        if not download_pdf_with_requests(pdf_url, pdf_path):
            print(f"[ERROR] Failed to download PDF")
            return []
        
        print(f"\nExtracting menu items from PDF...")
        items = extract_menu_from_pdf_with_gemini(str(pdf_path), "Take Home Platters", "Platters")
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "The Grille Take Home Platters"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Platters"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    finally:
        # Clean up PDF file
        if pdf_path.exists():
            pdf_path.unlink()
    
    return all_items


def scrape_jacobandanthony_american_grille_menu(url: str) -> List[Dict]:
    """
    Scrape menu from jacobandanthony.com/menus-american/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's American Grille"
    restaurant_url = "https://www.jacobandanthony.com/menus-american/"
    
    print("=" * 60)
    print(f"Scraping American Grille Menu: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing menu items...")
        items = parse_menu_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "American Grille Menu"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing: Format prices with size labels
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_american_grille_weekly_features(url: str) -> List[Dict]:
    """
    Scrape weekly features from jacobandanthony.com/weekly-features-american/
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's American Grille"
    restaurant_url = "https://www.jacobandanthony.com/weekly-features-american/"
    
    print("=" * 60)
    print(f"Scraping American Grille Weekly Features: {url}")
    print("=" * 60)
    
    try:
        # Download HTML
        print(f"Downloading HTML...")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.jacobandanthony.com/menus-american/"
        }
        html = download_html_with_requests(url)
        
        if not html:
            print(f"[ERROR] Failed to download page")
            return []
        
        print(f"[OK] Downloaded {len(html)} characters\n")
        
        # Parse menu items
        print(f"Parsing weekly features...")
        items = parse_weekly_features_page(html)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "American Grille Weekly Features"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Other"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    
    return all_items


def scrape_jacobandanthony_american_grille_platters_pdf(pdf_url: str) -> List[Dict]:
    """
    Scrape take-home platters from PDF for American Grille
    """
    all_items = []
    restaurant_name = "Jacob and Anthony's American Grille"
    restaurant_url = "https://www.jacobandanthony.com/take-home-platters-at-janda-italian/"
    
    print("=" * 60)
    print(f"Scraping American Grille Take Home Platters PDF: {pdf_url}")
    print("=" * 60)
    
    # Create temp directory for PDFs
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    pdf_path = temp_dir / 'jacob_american_grille_platters.pdf'
    
    try:
        # Download PDF
        print(f"Downloading PDF...")
        if not download_pdf_with_requests(pdf_url, pdf_path):
            print(f"[ERROR] Failed to download PDF")
            return []
        
        print(f"\nExtracting menu items from PDF...")
        items = extract_menu_from_pdf_with_gemini(str(pdf_path), "Take Home Platters", "Platters")
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = "American Grille Take Home Platters"
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items\n")
        else:
            print(f"[WARNING] No items extracted\n")
        
        # Post-processing
        for item in all_items:
            # Clean up item names and descriptions
            item['name'] = re.sub(r'\s+', ' ', item['name']).strip()
            item['description'] = re.sub(r'\s+', ' ', item['description']).strip()
            
            # Ensure menu_type doesn't contain "menu" keyword
            if item['menu_type']:
                item['menu_type'] = re.sub(r'\bmenu\b', '', item['menu_type'], flags=re.IGNORECASE).strip()
                if not item['menu_type']:
                    item['menu_type'] = "Platters"
        
        print(f"[OK] Extracted {len(all_items)} unique items from all sections\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        all_items = []
    finally:
        # Clean up PDF file
        if pdf_path.exists():
            pdf_path.unlink()
    
    return all_items


if __name__ == '__main__':
    # Combine all menus into a single output file
    all_items = []
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    output_json = output_dir / 'jacobandanthony_com.json'
    
    print("\n" + "=" * 60)
    print("SCRAPING ALL JACOB AND ANTHONY'S MENUS")
    print("=" * 60 + "\n")
    
    # Scrape Italian menu
    italian_url = "https://www.jacobandanthony.com/menus-italian/"
    italian_items = scrape_jacobandanthony_italian_menu(italian_url)
    all_items.extend(italian_items)
    print(f"\n[OK] Italian Menu: {len(italian_items)} items\n")
    
    # Scrape Brunch menu
    brunch_url = "https://www.jacobandanthony.com/menu/brunch/"
    brunch_items = scrape_jacobandanthony_brunch_menu(brunch_url)
    all_items.extend(brunch_items)
    print(f"\n[OK] Brunch Menu: {len(brunch_items)} items\n")
    
    # Scrape Weekly Features
    weekly_url = "https://www.jacobandanthony.com/weekly-features-italian/"
    weekly_items = scrape_jacobandanthony_weekly_features(weekly_url)
    all_items.extend(weekly_items)
    print(f"\n[OK] Weekly Features: {len(weekly_items)} items\n")
    
    # Scrape Take Home Platters PDF
    platter_pdf_url = "https://images.getbento.com/accounts/3ac696ed82fbd0d1ecc4712859045669/media/KE23ukxfRqKCAcgVzaqy_J%26A%20Platter%20Menus%20(Italian).pdf"
    platter_items = scrape_jacobandanthony_platters_pdf(platter_pdf_url)
    all_items.extend(platter_items)
    print(f"\n[OK] Take Home Platters: {len(platter_items)} items\n")
    
    # Scrape The Grille menu
    grille_url = "https://www.jacobandanthony.com/menus-grille/"
    grille_items = scrape_jacobandanthony_grille_menu(grille_url)
    all_items.extend(grille_items)
    print(f"\n[OK] The Grille Menu: {len(grille_items)} items\n")
    
    # Scrape The Grille Brunch menu
    grille_brunch_url = "https://www.jacobandanthony.com/menu/brunch-the-grille/"
    grille_brunch_items = scrape_jacobandanthony_grille_brunch_menu(grille_brunch_url)
    all_items.extend(grille_brunch_items)
    print(f"\n[OK] The Grille Brunch Menu: {len(grille_brunch_items)} items\n")
    
    # Scrape The Grille Weekly Features
    grille_weekly_url = "https://www.jacobandanthony.com/weekly-features-grille/"
    grille_weekly_items = scrape_jacobandanthony_grille_weekly_features(grille_weekly_url)
    all_items.extend(grille_weekly_items)
    print(f"\n[OK] The Grille Weekly Features: {len(grille_weekly_items)} items\n")
    
    # Scrape The Grille Take Home Platters PDF
    grille_platter_pdf_url = "https://images.getbento.com/accounts/3ac696ed82fbd0d1ecc4712859045669/media/VjTGiWSdKWCw7Bt05wDf_J%26A%20Platter%20Menus%20%28The%20Grille%29.pdf"
    grille_platter_items = scrape_jacobandanthony_grille_platters_pdf(grille_platter_pdf_url)
    all_items.extend(grille_platter_items)
    print(f"\n[OK] The Grille Take Home Platters: {len(grille_platter_items)} items\n")
    
    # Scrape American Grille menu
    american_grille_url = "https://www.jacobandanthony.com/menus-american/"
    american_grille_items = scrape_jacobandanthony_american_grille_menu(american_grille_url)
    all_items.extend(american_grille_items)
    print(f"\n[OK] American Grille Menu: {len(american_grille_items)} items\n")
    
    # Scrape American Grille Weekly Features
    american_grille_weekly_url = "https://www.jacobandanthony.com/weekly-features-american/"
    american_grille_weekly_items = scrape_jacobandanthony_american_grille_weekly_features(american_grille_weekly_url)
    all_items.extend(american_grille_weekly_items)
    print(f"\n[OK] American Grille Weekly Features: {len(american_grille_weekly_items)} items\n")
    
    # Scrape American Grille Take Home Platters PDF
    american_grille_platter_pdf_url = "https://images.getbento.com/accounts/3ac696ed82fbd0d1ecc4712859045669/media/mUjTCVlnRZme9Zffbvew_J%26A%20Platter%20Menus%20%28American%29.pdf"
    american_grille_platter_items = scrape_jacobandanthony_american_grille_platters_pdf(american_grille_platter_pdf_url)
    all_items.extend(american_grille_platter_items)
    print(f"\n[OK] American Grille Take Home Platters: {len(american_grille_platter_items)} items\n")
    
    # Save all items to a single JSON file
    print("=" * 60)
    print("SAVING ALL ITEMS TO SINGLE FILE")
    print("=" * 60)
    print(f"Output file: {output_json}\n")
    
    if all_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(all_items, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved {len(all_items)} total items to: {output_json}")
    else:
        print(f"[WARNING] No items to save")
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(all_items)}")
    print(f"  - Italian Menu: {len(italian_items)}")
    print(f"  - Brunch Menu: {len(brunch_items)}")
    print(f"  - Weekly Features: {len(weekly_items)}")
    print(f"  - Take Home Platters: {len(platter_items)}")
    print(f"  - The Grille Menu: {len(grille_items)}")
    print(f"  - The Grille Brunch Menu: {len(grille_brunch_items)}")
    print(f"  - The Grille Weekly Features: {len(grille_weekly_items)}")
    print(f"  - The Grille Take Home Platters: {len(grille_platter_items)}")
    print(f"  - American Grille Menu: {len(american_grille_items)}")
    print(f"  - American Grille Weekly Features: {len(american_grille_weekly_items)}")
    print(f"  - American Grille Take Home Platters: {len(american_grille_platter_items)}")
    print(f"Saved to: {output_json}")
    print(f"{'='*60}")

