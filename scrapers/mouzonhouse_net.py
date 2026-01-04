"""
Scraper for mouzonhouse.net
Scrapes menu from images (December Supper Club and New Year's Eve Supper Club)
Uses Gemini Vision API to extract menu data from images
"""

import json
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image
import io


# Load API Key from config.json
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
GEMINI_API_KEY = None
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        GEMINI_API_KEY = config.get("gemini_api_key")
except Exception as e:
    print(f"Warning: Could not load API key from config.json: {e}")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def download_html(url: str) -> str:
    """Download HTML from URL"""
    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://mouzonhouse.net/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        cookies = {
            "_lscache_vary": "7e5da2b0429ea172b9d7d660b144ed72",
            "_ga": "GA1.1.558878186.1767532201",
            "pum-3358": "true",
            "_ga_XQN11VRLZH": "GS2.1.s1767532201$o1$g1$t1767534443$j57$l0$h0"
        }
        response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def download_image(url: str) -> Image.Image:
    """Download image from URL and return as PIL Image"""
    try:
        headers = {
            "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content))
    except Exception as e:
        print(f"[ERROR] Failed to download image from {url}: {e}")
        return None


def extract_menu_from_image_with_gemini(image: Image.Image, menu_name: str) -> List[Dict]:
    """Extract menu items from image using Gemini Vision API"""
    if not GEMINI_API_KEY:
        print("[ERROR] Gemini API key not configured")
        return []
    
    try:
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Extract all menu items from this {menu_name} menu image. For each item, provide:
- name: The item name
- description: The item description (if any)
- price: The price (if shown)
- section: The section/category name (if any, e.g., "Appetizer", "Entree", "Dessert", "Course 1", "Course 2", etc.)

Return the data as a JSON array of objects with these fields: name, description, price, section.
If a field is not available, use an empty string.
Only extract actual menu items, not headers, footers, or other non-menu content.
Make sure to extract all courses and items from the menu.
"""
        
        # Generate content
        response = model.generate_content([prompt, image])
        
        # Parse JSON from response
        response_text = response.text.strip()
        
        # Try to extract JSON from markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # Remove any non-JSON content at the beginning (like Scala code, comments, etc.)
        # Look for the first '[' or '{' that starts a JSON array/object
        json_start = -1
        for i, char in enumerate(response_text):
            if char in ['[', '{']:
                json_start = i
                break
        
        if json_start > 0:
            response_text = response_text[json_start:]
        
        # Also remove any trailing non-JSON content
        # Find the last ']' or '}' that closes the JSON
        json_end = -1
        for i in range(len(response_text) - 1, -1, -1):
            if response_text[i] in [']', '}']:
                json_end = i + 1
                break
        
        if json_end > 0 and json_end < len(response_text):
            response_text = response_text[:json_end]
        
        items = json.loads(response_text)
        
        return items
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON from Gemini response for {menu_name}: {e}")
        print(f"[DEBUG] Response text: {response_text[:500]}")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to extract menu from {menu_name}: {e}")
        return []


def extract_menu_image_urls(html: str) -> List[Dict]:
    """Extract menu image URLs from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    menu_images = []
    
    # Find all images in the page
    images = soup.find_all('img')
    
    # Look for specific menu images by URL patterns
    # December menu: whatsapp-image-2025-11-25 (November upload)
    # New Year menu: ee66ef00-3762-460c-87f1-86dd75bf2c49 (December upload)
    for img in images:
        src = img.get('src', '')
        if not src:
            continue
        
        # Check for December Supper Club menu
        if 'whatsapp-image-2025-11-25' in src:
            # Make sure URL is complete (not a srcset)
            if src.startswith('http'):
                menu_images.append({
                    'url': src,
                    'menu_name': 'December Supper Club'
                })
        
        # Check for New Year's Eve Supper Club menu
        elif 'ee66ef00-3762-460c-87f1-86dd75bf2c49' in src:
            # Make sure URL is complete (not a srcset)
            if src.startswith('http'):
                menu_images.append({
                    'url': src,
                    'menu_name': "New Year's Eve Supper Club"
                })
    
    # If we still don't have both, try finding by looking for headings near images
    if len(menu_images) < 2:
        # Find all headings
        headings = soup.find_all(['h2', 'h3', 'h4'])
        for heading in headings:
            heading_text = heading.get_text(strip=True).lower()
            
            # Find images near this heading
            # Look for images in the same container or nearby
            container = heading.find_parent()
            if container:
                nearby_images = container.find_all('img')
                for img in nearby_images:
                    src = img.get('src', '')
                    if not src or not src.startswith('http'):
                        continue
                    
                    # Check if it's a menu image
                    if 'wp-content/uploads/2025/11' in src or 'wp-content/uploads/2025/12' in src:
                        menu_name = ""
                        if 'december' in heading_text and 'supper' in heading_text:
                            menu_name = "December Supper Club"
                        elif 'new year' in heading_text and 'supper' in heading_text:
                            menu_name = "New Year's Eve Supper Club"
                        
                        if menu_name:
                            # Check if we already have this menu
                            if not any(m['menu_name'] == menu_name for m in menu_images):
                                menu_images.append({
                                    'url': src,
                                    'menu_name': menu_name
                                })
    
    return menu_images


def scrape_mouzonhouse_menu() -> List[Dict]:
    """Scrape menu from Mouzon House"""
    print("=" * 60)
    print("Scraping The Mouzon House (mouzonhouse.net)")
    print("=" * 60)
    
    restaurant_name = "The Mouzon House"
    restaurant_url = "http://www.mouzonhouse.com/"
    url = "https://mouzonhouse.net/our-supper-club/"
    
    # Download HTML
    print(f"\n[1] Downloading HTML...")
    html = download_html(url)
    if not html:
        print("[ERROR] Failed to download HTML")
        return []
    
    print(f"[OK] Downloaded {len(html)} characters")
    
    # Extract menu image URLs
    print(f"\n[2] Extracting menu image URLs...")
    menu_images = extract_menu_image_urls(html)
    print(f"[OK] Found {len(menu_images)} menu images")
    
    if not menu_images:
        print("[ERROR] No menu images found")
        return []
    
    all_items = []
    
    # Download and process each menu image
    print(f"\n[3] Processing menu images with Gemini...")
    for menu_info in menu_images:
        image_url = menu_info['url']
        menu_name = menu_info['menu_name']
        
        print(f"    Downloading {menu_name} image...", end=" ")
        image = download_image(image_url)
        if not image:
            print("[SKIP]")
            continue
        print(f"[OK]")
        
        print(f"    Extracting menu items from {menu_name}...", end=" ")
        items = extract_menu_from_image_with_gemini(image, menu_name)
        print(f"[OK] Found {len(items)} items")
        
        # Add restaurant info to each item
        for item in items:
            item['restaurant_name'] = restaurant_name
            item['restaurant_url'] = restaurant_url
            item['menu_type'] = 'Supper Club'
            # Use the menu name (December Supper Club or New Year's Eve Supper Club)
            # If there's a section, append it to menu_name for better organization
            section = item.get('section', '')
            if section:
                item['menu_name'] = f"{menu_name} - {section}"
            else:
                item['menu_name'] = menu_name
            # Remove the 'section' field as it's not in our standard format
            if 'section' in item:
                del item['section']
        
        all_items.extend(items)
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Display sample
    if all_items:
        print(f"\n[4] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            try:
                price_str = item.get('price', '') if item.get('price') else "No price"
                print(f"  {i}. {item.get('name', 'Unknown')} - {price_str} ({item.get('menu_name', 'Unknown')})")
            except Exception as e:
                print(f"  {i}. [Error displaying item: {e}]")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items


if __name__ == "__main__":
    items = scrape_mouzonhouse_menu()
    
    # Save to JSON
    if items:
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "mouzonhouse_net.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Saved {len(items)} items to {output_file}")

