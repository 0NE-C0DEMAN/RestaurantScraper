"""
Scraper for The Hideaway (hideawaysaratoga.com)
Scrapes menu from image-based menus using Gemini Vision API
Handles: Main Menu (multiple image sections), Beverages Menu (HTML via Playwright)
"""

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pathlib import Path
from PIL import Image
import google.generativeai as genai

# Check if Gemini is available
try:
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[WARNING] Gemini API not available")

# Check if Playwright is available
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[WARNING] Playwright not available. Install with: pip install playwright && playwright install")

# Load API Key from config.json
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
GEMINI_API_KEY = None
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GEMINI_API_KEY = config.get("gemini_api_key") or config.get("GEMINI_API_KEY")
        if GEMINI_API_KEY and GEMINI_AVAILABLE:
            genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"[WARNING] Could not load Gemini API key: {e}")


def download_html(url: str, headers: dict) -> Optional[str]:
    """Download HTML content from URL"""
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return None


def download_image(image_url: str, output_path: Path) -> bool:
    """Download image from URL"""
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download image from {image_url}: {e}")
        return False


def extract_image_urls_from_html(html: str) -> List[Dict[str, str]]:
    """Extract menu image URLs from HTML, returning list of dicts with url and section name"""
    soup = BeautifulSoup(html, 'html.parser')
    image_data = []
    
    # Find all img tags
    img_tags = soup.find_all('img')
    
    for img in img_tags:
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if src:
            # Filter for menu images (exclude logos and other non-menu images)
            src_lower = src.lower()
            # Skip logos
            if 'logo' in src_lower or 'cover' in src_lower:
                continue
            
            # Look for menu-related keywords
            if any(keyword in src_lower for keyword in ['menu', 'app', 'soup', 'salad', 'sandwich', 'entree', 'dessert']):
                # Make sure it's a full URL
                if src.startswith('http'):
                    # Try to extract section name from URL or alt text
                    section_name = "Menu"
                    if 'app' in src_lower:
                        section_name = "Appetizers"
                    elif 'soup' in src_lower or 'salad' in src_lower:
                        section_name = "Soup & Salad"
                    elif 'sandwich' in src_lower:
                        section_name = "Sandwiches"
                    elif 'entree' in src_lower:
                        section_name = "Entrees"
                    elif 'dessert' in src_lower:
                        section_name = "Desserts"
                    
                    image_data.append({"url": src, "section": section_name})
                elif src.startswith('//'):
                    image_data.append({"url": f"https:{src}", "section": "Menu"})
                elif src.startswith('/'):
                    image_data.append({"url": f"https://www.hideawaysaratoga.com{src}", "section": "Menu"})
    
    # Remove duplicates while preserving order
    seen = set()
    unique_images = []
    for img_data in image_data:
        if img_data["url"] not in seen:
            seen.add(img_data["url"])
            unique_images.append(img_data)
    
    return unique_images


def extract_menu_from_image_with_gemini(image_path: Path, menu_name: str, menu_type: str, section_hint: str = None) -> List[Dict]:
    """Extract menu items from image using Gemini Vision API"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("[ERROR] Gemini not available or API key not configured")
        return []
    
    all_items = []
    
    try:
        # Load image
        image = Image.open(image_path)
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        section_context = f" (likely in the {section_hint} section)" if section_hint else ""
        
        prompt = f"""Analyze this {menu_name} menu image{section_context} and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (NOT addon items - those should be in descriptions)
2. **description**: The description/ingredients/details for THIS specific item only. CRITICAL: If there are addons listed near this item (like "ADD CHICKEN $7.95" or "Add chicken +$6" or "with cheese | Small $6 Large $8"), include them in the description field. Format as: "Description text. Add-ons: add chicken +$7.95 / add shrimp +$10.95 / with cheese Small $6 Large $8"
3. **price**: The price. CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
   * "Small $5 | Large $7"
   * "6\" Sub or Bread $8 | 12\" Sub or Wrap $13"
   * "SM $7 | LG $13"
   * "$13" (single price)
   Always include the $ symbol. For items with size variations, use the format: "Size1 $X | Size2 $Y"
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Sandwiches", "Desserts", etc.){f" This image is likely from the {section_hint} section, so use that as the section name." if section_hint else ""}

IMPORTANT RULES:
- Extract ONLY actual menu items (dishes, drinks, etc.) - DO NOT extract standalone addon items like "ADD CHICKEN" as separate items
- If an item has addons listed nearby (like "with cheese | Small $6 Large $8" or "Add chicken +$4"), include them in that item's description field
- Item names are usually in larger/bolder font or ALL CAPS
- Each item has its OWN description - do not mix descriptions between items
- Prices are usually at the end of the item name line or on a separate line
- If an item has multiple prices (e.g., "6\" $8 | 12\" $13" or "SMALL $5 LARGE $7"), ALWAYS include the size labels: "6\" Sub $8 | 12\" Sub $13" or "Small $5 | Large $7"
- Look carefully at the menu - size labels are often shown near the prices (e.g., "Small", "Large", "SM", "LG", "6\"", "12\"", "Sub", "Bread", "Wrap")
- Handle two-column layouts correctly - items in left column and right column should be separate
- Skip footer text (address, phone, website, etc.)
- Skip standalone addon listings - they should be included in the description of the items they apply to
- Group items by their section/category using the section field

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
  }}
]"""
        
        print(f"    Analyzing image with Gemini...")
        response = model.generate_content([prompt, image])
        
        # Extract JSON from response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
            response_text = re.sub(r'\s*```$', '', response_text, flags=re.MULTILINE)
        
        # Parse JSON
        items = json.loads(response_text)
        
        # Add metadata to each item and ensure prices have dollar signs
        for item in items:
            item["restaurant_name"] = "The Hideaway"
            item["restaurant_url"] = "https://www.hideawaysaratoga.com/"
            item["menu_type"] = menu_type
            item["menu_name"] = menu_name
            
            # Ensure price has dollar sign
            if item.get("price"):
                price_str = str(item["price"]).strip()
                
                # Check if price already has dollar signs
                if "$" not in price_str:
                    # No dollar signs at all - add them
                    if "|" in price_str:
                        # Multi-price format: "125 | 175" -> "$125 | $175"
                        parts = price_str.split("|")
                        formatted_parts = []
                        for part in parts:
                            part = part.strip()
                            if part:
                                # Extract size label if present (e.g., "Cup 6" or "Small 5")
                                size_match = re.match(r'^([A-Za-z0-9\s"]+?)\s+(\d+(?:\.\d+)?)$', part)
                                if size_match:
                                    size = size_match.group(1).strip()
                                    price = size_match.group(2)
                                    formatted_parts.append(f"{size} ${price}")
                                else:
                                    # Just a number
                                    formatted_parts.append(f"${part}")
                        item["price"] = " | ".join(formatted_parts)
                    else:
                        # Single price
                        item["price"] = f"${price_str}"
                elif price_str.startswith("$") and not any(c.isalpha() for c in price_str[1:5]):
                    # Price starts with $ but might be missing $ in multi-price format
                    if "|" in price_str:
                        parts = price_str.split("|")
                        formatted_parts = []
                        for part in parts:
                            part = part.strip()
                            if part and "$" not in part:
                                # Missing dollar sign in this part
                                size_match = re.match(r'^([A-Za-z0-9\s"]+?)\s+(\d+(?:\.\d+)?)$', part)
                                if size_match:
                                    size = size_match.group(1).strip()
                                    price = size_match.group(2)
                                    formatted_parts.append(f"{size} ${price}")
                                else:
                                    formatted_parts.append(f"${part}")
                            else:
                                formatted_parts.append(part)
                        item["price"] = " | ".join(formatted_parts)
        
        all_items.extend(items)
        print(f"    Extracted {len(items)} items from image")
        
    except json.JSONDecodeError as e:
        print(f"    [ERROR] Failed to parse JSON response: {e}")
        print(f"    Response text: {response_text[:500]}")
    except Exception as e:
        print(f"    [ERROR] Failed to process image: {e}")
    
    return all_items


def fetch_beverages_html_with_playwright(url: str) -> Optional[str]:
    """Fetch beverages page HTML using Playwright"""
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available")
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            print(f"    Loading page: {url}")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Wait a bit for any dynamic content to load
            page.wait_for_timeout(2000)
            
            # Get the HTML
            html = page.content()
            
            browser.close()
            return html
    except Exception as e:
        print(f"[ERROR] Failed to fetch beverages page with Playwright: {e}")
        return None


def parse_beverages_html(html: str) -> List[Dict]:
    """Parse beverages menu from HTML (structured Untappd data)"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # The beverages page uses Untappd integration with structured HTML
    # Structure: div.menu-item > div.item > div.item-details
    # Section headers: h3.section-name
    # Beer name: h4.item-name > a > span
    # Beer type: span.item-category
    # ABV: span.item-abv
    # Brewery: span.brewery > a
    # Size: span.type (inside div.container-list)
    # Price: span.price (contains text like "4.00")
    
    # Find all menu items
    menu_items = soup.find_all('div', class_='menu-item')
    
    if menu_items:
        print(f"    Found {len(menu_items)} menu items - parsing structured data...")
        
        current_section = "Beverages"  # Default section
        
        for menu_item in menu_items:
            # Find section - look for nearest h3.section-name before this item
            section_header = menu_item.find_previous('h3', class_='section-name')
            if section_header:
                current_section = section_header.get_text(strip=True)
            
            # Find item-details div
            item_details = menu_item.find('div', class_='item-details')
            if not item_details:
                continue
            
            # Extract beer name from h4.item-name > a > span
            h4_name = item_details.find('h4', class_='item-name')
            if not h4_name:
                continue
            
            # Get the span inside the link
            name_link = h4_name.find('a')
            if not name_link:
                continue
            
            name_span = name_link.find('span')
            if not name_span:
                continue
            
            beer_name = name_span.get_text(strip=True)
            if not beer_name:
                continue
            
            # Extract beer type from span.item-category
            category_span = h4_name.find('span', class_='item-category')
            beer_type = category_span.get_text(strip=True) if category_span else None
            
            # Extract ABV from span.item-abv
            abv_span = item_details.find('span', class_='item-abv')
            abv_text = abv_span.get_text(strip=True) if abv_span else None
            
            # Extract brewery from span.brewery > a
            brewery_span = item_details.find('span', class_='brewery')
            brewery_name = None
            if brewery_span:
                brewery_link = brewery_span.find('a')
                if brewery_link:
                    brewery_name = brewery_link.get_text(strip=True)
            
            # Build description
            description_parts = []
            if beer_type:
                description_parts.append(beer_type)
            if abv_text:
                description_parts.append(abv_text)
            if brewery_name:
                description_parts.append(f"Brewery: {brewery_name}")
            description = " | ".join(description_parts) if description_parts else None
            
            # Extract size and price from div.container-list
            container_list = item_details.find('div', class_='container-list')
            size = None
            price_value = None
            
            if container_list:
                # Find size from span.type
                type_span = container_list.find('span', class_='type')
                if type_span:
                    size = type_span.get_text(strip=True)
                
                # Find price from span.price
                price_span = container_list.find('span', class_='price')
                if price_span:
                    # Get all text from price span (e.g., "4.00" or "$4.00")
                    price_text = price_span.get_text(strip=True)
                    # Extract number (might have $ or other text)
                    price_match = re.search(r'(\d+\.?\d*)', price_text)
                    if price_match:
                        price_value = price_match.group(1)
            
            # Format price
            if price_value:
                if size:
                    price = f"{size} ${price_value}"
                else:
                    price = f"${price_value}"
            else:
                price = "Price not listed"
            
            item = {
                "name": beer_name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "The Hideaway",
                "restaurant_url": "https://www.hideawaysaratoga.com/",
                "menu_type": "Beverages",
                "menu_name": "Beverages Menu"
            }
            
            items.append(item)
    
    print(f"      [OK] Extracted {len(items)} items from structured HTML")
    
    # If no structured items found, check for images as fallback
    if not items:
        img_tags = soup.find_all('img')
        beverage_images = []
        for img in img_tags:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                src_lower = src.lower()
                if any(keyword in src_lower for keyword in ['beverage', 'beer', 'wine', 'cocktail', 'drink', 'menu']):
                    if 'logo' not in src_lower:
                        if src.startswith('http'):
                            beverage_images.append(src)
                        elif src.startswith('//'):
                            beverage_images.append(f"https:{src}")
                        elif src.startswith('/'):
                            beverage_images.append(f"https://www.hideawaysaratoga.com{src}")
        
        # If we found beverage images, process them with Gemini
        if beverage_images and GEMINI_AVAILABLE and GEMINI_API_KEY:
            print(f"    Found {len(beverage_images)} beverage menu image(s) - using Gemini as fallback")
            for i, image_url in enumerate(beverage_images, 1):
                print(f"    Processing beverage image {i}/{len(beverage_images)}...")
                
                # Download image
                image_filename = f"hideaway_beverages_{i}.jpg"
                image_path = Path(f"temp/hideaway_images/{image_filename}")
                
                if download_image(image_url, image_path):
                    print(f"      [OK] Downloaded image")
                    
                    # Extract menu items using Gemini
                    beverage_items = extract_menu_from_image_with_gemini(
                        image_path,
                        "Beverages Menu",
                        "Beverages",
                        "Beverages"
                    )
                    items.extend(beverage_items)
                    print(f"      [OK] Extracted {len(beverage_items)} items from image")
                else:
                    print(f"      [ERROR] Failed to download image")
    
    return items
                # Get the first span that's not a category span
                for span in name_spans:
                    span_text = span.get_text(strip=True)
                    # Skip if it's a category or style span
                    if span.get('class') and ('item-category' in span.get('class') or 'item-style' in span.get('class')):
                        continue
                    if span_text and len(span_text) > 2:
                        beer_name = span_text
                        break
            
            # Method 2: From link's direct text content (excluding nested elements)
            if not beer_name:
                # Get text directly from link, but exclude nested span texts
                link_direct_text = []
                for child in link.children:
                    if isinstance(child, str):
                        text = child.strip()
                        if text:
                            link_direct_text.append(text)
                if link_direct_text:
                    beer_name = ' '.join(link_direct_text).strip()
            
            # Method 3: From link's full text (fallback)
            if not beer_name:
                link_text = link.get_text(strip=True)
                if link_text and len(link_text) > 2:
                    beer_name = link_text
            
            # Method 4: From h4 - extract text from the link part only
            if not beer_name and h4_item:
                # Find the link in h4 and get its text
                h4_link = h4_item.find('a')
                if h4_link:
                    h4_link_text = h4_link.get_text(strip=True)
                    if h4_link_text:
                        beer_name = h4_link_text
                else:
                    # Fallback: get all h4 text except category
                    h4_text = h4_item.get_text(separator=' ', strip=True)
                    # Remove category spans
                    for cat_span in h4_item.find_all('span', class_='item-category'):
                        cat_text = cat_span.get_text(strip=True)
                        if cat_text in h4_text:
                            h4_text = h4_text.replace(cat_text, '').strip()
                    if h4_text:
                        beer_name = h4_text
            
            item = {
                "name": beer_name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "The Hideaway",
                "restaurant_url": "https://www.hideawaysaratoga.com/",
                "menu_type": "Beverages",
                "menu_name": "Beverages Menu"
            }
            
            items.append(item)
    
    # If no structured items found, check for images as fallback
    if not items:
        img_tags = soup.find_all('img')
        beverage_images = []
        for img in img_tags:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                src_lower = src.lower()
                if any(keyword in src_lower for keyword in ['beverage', 'beer', 'wine', 'cocktail', 'drink', 'menu']):
                    if 'logo' not in src_lower:
                        if src.startswith('http'):
                            beverage_images.append(src)
                        elif src.startswith('//'):
                            beverage_images.append(f"https:{src}")
                        elif src.startswith('/'):
                            beverage_images.append(f"https://www.hideawaysaratoga.com{src}")
        
        # If we found beverage images, process them with Gemini
        if beverage_images and GEMINI_AVAILABLE and GEMINI_API_KEY:
            print(f"    Found {len(beverage_images)} beverage menu image(s) - using Gemini as fallback")
            for i, image_url in enumerate(beverage_images, 1):
                print(f"    Processing beverage image {i}/{len(beverage_images)}...")
                
                # Download image
                image_filename = f"hideaway_beverages_{i}.jpg"
                image_path = Path(f"temp/hideaway_images/{image_filename}")
                
                if download_image(image_url, image_path):
                    print(f"      [OK] Downloaded image")
                    
                    # Extract menu items using Gemini
                    beverage_items = extract_menu_from_image_with_gemini(
                        image_path,
                        "Beverages Menu",
                        "Beverages",
                        "Beverages"
                    )
                    items.extend(beverage_items)
                    print(f"      [OK] Extracted {len(beverage_items)} items from image")
                else:
                    print(f"      [ERROR] Failed to download image")
    
    return items


def scrape_hideaway() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print("Scraping The Hideaway (hideawaysaratoga.com)")
    print("=" * 60)
    
    all_items = []
    
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "cookie": "dm_timezone_offset=-330; dm_last_page_view=1767693287166; dm_last_visit=1767693287166; dm_total_visits=1; dm_this_page_view=1767693902131; _sp_id.f0b2=e514636db6977b8b.1767693580.1.1767693902.1767693580; _sp_ses.f0b2=1767695702159",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://www.hideawaysaratoga.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    
    menu_url = "https://www.hideawaysaratoga.com/menu"
    
    print(f"\n[1] Downloading menu HTML...")
    html = download_html(menu_url, headers)
    
    if not html:
        print("[ERROR] Failed to download menu HTML")
        return []
    
    print(f"[OK] Downloaded {len(html)} characters")
    
    # Extract image URLs
    print(f"\n[2] Extracting menu image URLs...")
    image_data_list = extract_image_urls_from_html(html)
    
    if not image_data_list:
        print(f"[ERROR] No menu images found")
        return []
    
    print(f"[OK] Found {len(image_data_list)} menu image(s)")
    
    # Download and process each image
    for i, img_data in enumerate(image_data_list, 1):
        image_url = img_data["url"]
        section_hint = img_data.get("section", "Menu")
        
        print(f"\n[3] Processing image {i}/{len(image_data_list)} ({section_hint})...")
        
        # Download image
        image_filename = f"hideaway_{section_hint.lower().replace(' ', '_')}_{i}.jpg"
        image_path = Path(f"temp/hideaway_images/{image_filename}")
        
        if download_image(image_url, image_path):
            print(f"    [OK] Downloaded image")
            
            # Extract menu items using Gemini
            items = extract_menu_from_image_with_gemini(
                image_path, 
                "Main Menu", 
                "Main Menu",
                section_hint
            )
            all_items.extend(items)
            print(f"    [OK] Extracted {len(items)} items from image")
        else:
            print(f"    [ERROR] Failed to download image")
    
    # Fetch and parse beverages menu using Playwright
    print(f"\n[4] Fetching beverages menu with Playwright...")
    beverages_url = "https://www.hideawaysaratoga.com/beverages"
    beverages_html = fetch_beverages_html_with_playwright(beverages_url)
    
    if beverages_html:
        print(f"    [OK] Fetched beverages HTML ({len(beverages_html)} characters)")
        beverages = parse_beverages_html(beverages_html)
        if beverages:
            all_items.extend(beverages)
            print(f"[OK] Extracted {len(beverages)} beverage items")
        else:
            print(f"[INFO] No beverage items found in beverages page")
    else:
        print(f"[ERROR] Failed to fetch beverages page")
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Save to JSON
    output_path = Path("output/hideawaysaratoga_com.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(all_items)} items to {output_path}")
    
    return all_items


if __name__ == "__main__":
    scrape_hideaway()

