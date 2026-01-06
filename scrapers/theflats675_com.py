"""
Scraper for The Flats Restaurant & Tavern (theflats675.com)
Scrapes menu from image-based menus using Gemini Vision API
Handles: Dinner Menu, Brunch Menu, Catering Menu
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


def extract_image_urls_from_html(html: str) -> List[str]:
    """Extract menu image URLs from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    image_urls = []
    
    # Find all img tags
    img_tags = soup.find_all('img')
    
    for img in img_tags:
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if src:
            # Filter for menu images (exclude logos and other non-menu images)
            src_lower = src.lower()
            # Skip logos
            if 'logo' in src_lower:
                continue
            # Look for menu-related keywords or common menu image patterns
            if any(keyword in src_lower for keyword in ['menu', 'dinner', 'brunch', 'catering', 'page', 'flats']):
                # Make sure it's a full URL
                if src.startswith('http'):
                    image_urls.append(src)
                elif src.startswith('//'):
                    image_urls.append(f"https:{src}")
                elif src.startswith('/'):
                    # Try to construct full URL (this might need adjustment based on actual site structure)
                    image_urls.append(f"https://www.theflats675.com{src}")
    
    # Also check for background images in style attributes
    style_elements = soup.find_all(attrs={"style": re.compile(r'background.*image', re.I)})
    for elem in style_elements:
        style = elem.get('style', '')
        url_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
        if url_match:
            url = url_match.group(1)
            if 'menu' in url.lower() or 'dinner' in url.lower() or 'brunch' in url.lower() or 'catering' in url.lower():
                if url.startswith('http'):
                    image_urls.append(url)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in image_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls


def extract_menu_from_image_with_gemini(image_path: Path, menu_name: str, menu_type: str) -> List[Dict]:
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
        
        prompt = f"""Analyze this {menu_name} menu image and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (NOT addon items - those should be in descriptions)
2. **description**: The description/ingredients/details for THIS specific item only. CRITICAL: If there are addons listed near this item (like "ADD CHICKEN $7.95" or "Add chicken +$6" or "with cheese | Small $6 Large $8"), include them in the description field. Format as: "Description text. Add-ons: add chicken +$7.95 / add shrimp +$10.95 / with cheese Small $6 Large $8"
3. **price**: The price. CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
   * "Small $5 | Large $7"
   * "6\" Sub or Bread $8 | 12\" Sub or Wrap $13"
   * "SM $7 | LG $13"
   * "$13" (single price)
   Always include the $ symbol. For items with size variations, use the format: "Size1 $X | Size2 $Y"
4. **section**: The section/category name (e.g., "Appetizers", "Entrees", "Salads", "Soups", "Cocktails", "Wine", "Beer", "Breakfast", "Brunch", "Lunch", "Dinner", etc.)

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
            item["restaurant_name"] = "The Flats Restaurant & Tavern"
            item["restaurant_url"] = "https://www.theflats675.com/"
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
                    # Check if it's a single number like "$125" - that's fine
                    # But if it's "$125 | 175", we need to fix it
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


def scrape_flats() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print("Scraping The Flats Restaurant & Tavern (theflats675.com)")
    print("=" * 60)
    
    all_items = []
    
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "cookie": "dm_timezone_offset=-330; dm_last_visit=1767691722533; dm_total_visits=1; _sp_id.14d1=7a80bd146e932de7.1767691723.1.1767691954.1767691723; _sp_ses.14d1=1767693753902; dm_last_page_view=1767691950958; dm_this_page_view=1767691954660",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://www.theflats675.com/",
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
    
    menus = [
        ("Dinner Menu", "https://www.theflats675.com/dinner", "Dinner"),
        ("Brunch Menu", "https://www.theflats675.com/brunch", "Brunch"),
        ("Catering Menu", "https://www.theflats675.com/catering-menu", "Catering")
    ]
    
    for menu_name, menu_url, menu_type in menus:
        print(f"\n[1] Processing {menu_name}...")
        
        # Download HTML
        print(f"  Downloading HTML from {menu_url}...")
        html = download_html(menu_url, headers)
        
        if not html:
            print(f"  [ERROR] Failed to download {menu_name}")
            continue
        
        print(f"  [OK] Downloaded {len(html)} characters")
        
        # Extract image URLs
        print(f"  Extracting image URLs...")
        image_urls = extract_image_urls_from_html(html)
        
        if not image_urls:
            print(f"  [ERROR] No menu images found")
            continue
        
        print(f"  [OK] Found {len(image_urls)} menu image(s)")
        
        # Download and process each image
        for i, image_url in enumerate(image_urls, 1):
            print(f"  Processing image {i}/{len(image_urls)}...")
            
            # Download image
            image_filename = f"flats_{menu_type.lower()}_{i}.jpg"
            image_path = Path(f"temp/flats_images/{image_filename}")
            
            if download_image(image_url, image_path):
                print(f"    [OK] Downloaded image")
                
                # Extract menu items using Gemini
                items = extract_menu_from_image_with_gemini(image_path, menu_name, menu_type)
                all_items.extend(items)
                print(f"    [OK] Extracted {len(items)} items from image")
            else:
                print(f"    [ERROR] Failed to download image")
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Save to JSON
    output_path = Path("output/theflats675_com.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(all_items)} items to {output_path}")
    
    return all_items


if __name__ == "__main__":
    scrape_flats()

