"""
Scraper for nkmilton.com (Neighborhood Kitchen)
Scrapes menu from two menu images
Uses Gemini Vision API to extract menu data from images
"""

import json
from pathlib import Path
from typing import List, Dict
import requests
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


# Menu image URLs
MENU_IMAGES = [
    {
        "url": "https://images.squarespace-cdn.com/content/v1/638f724fe45ff113f0433fe6/44e0d79c-b34a-49b7-900c-649738ef6992/NeighborhoodKitchen-TOGO-FALL2025-2.jpg?format=2500w",
        "menu_name": "Menu Page 2"
    },
    {
        "url": "https://images.squarespace-cdn.com/content/v1/638f724fe45ff113f0433fe6/5f876283-0b42-4dc0-90c5-8d39df63a940/NeighborhoodKitchen-TOGO-FALL2025.jpg?format=2500w",
        "menu_name": "Menu Page 1"
    }
]


def download_image(url: str) -> Image.Image:
    """Download image from URL and return as PIL Image"""
    try:
        headers = {
            "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://www.nkmilton.com/",
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
- description: The item description (if any). Include addons in the description (e.g., "ADD: CHICKEN $4 | SALMON $8" or "Add chicken +$4 | Add salmon +$8")
- price: The price (if shown). CRITICAL: If there are multiple prices for different sizes, you MUST include the size labels. Examples:
  * "Small $12 | Large $30"
  * "Single $12 | Family $30"
  * "Regular $13 | Large $25"
  * "Half $10 | Full $18"
  If only one price is shown, format as "$X". If multiple prices without explicit labels, infer common labels like "Small" and "Large" or "Regular" and "Family".
- section: The section/category name (if any, e.g., "Appetizers", "Entrees", "Sides", "Desserts", "LIGHT FARE", "GREENS", etc.)

IMPORTANT RULES:
1. ALWAYS include size labels when multiple prices are present (Small/Large, Single/Family, Regular/Large, Half/Full, etc.)
2. Include the $ symbol with all prices
3. Include addons in the description field with their prices (e.g., "ADD: CHICKEN $4 | SALMON $8")
4. Look carefully at the menu - size labels are often shown near the prices

Return the data as a JSON array of objects with these fields: name, description, price, section.
If a field is not available, use an empty string.
Only extract actual menu items, not headers, footers, or other non-menu content.
Make sure to extract all items from the menu.
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


def scrape_nkmilton_menu() -> List[Dict]:
    """Scrape menu from Neighborhood Kitchen"""
    print("=" * 60)
    print("Scraping Neighborhood Kitchen (nkmilton.com)")
    print("=" * 60)
    
    restaurant_name = "Neighborhood Kitchen"
    restaurant_url = "http://www.nkmilton.com/"
    
    all_items = []
    
    # Download and process each menu image
    print(f"\n[1] Processing menu images with Gemini...")
    for menu_info in MENU_IMAGES:
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
            # Format price - ensure $ symbol is present and handle sizes
            price = item.get('price', '').strip()
            if price:
                import re
                # Check if price already has $ symbols
                has_dollar = '$' in price
                
                # Handle multiple prices with sizes (e.g., "12 | 30" or "Small 12 | Large 30")
                if '|' in price:
                    # Split by | and format each part
                    price_parts = price.split('|')
                    formatted_parts = []
                    for i, part in enumerate(price_parts):
                        part = part.strip()
                        # Check if it already has a size label
                        size_match = re.search(r'\b(small|large|regular|family|single|double|half|full)\b', part.lower())
                        if size_match:
                            # Has size label - format numbers with $ if not already present
                            if not has_dollar:
                                # Replace numbers with $numbers, but preserve size label
                                part = re.sub(r'(\d+)', r'$\1', part)
                            else:
                                # Remove any double $ symbols
                                part = re.sub(r'\$\$+', '$', part)
                        else:
                            # No size label - infer one if this is a multiple price item
                            # Common patterns: first is usually smaller size, second is larger
                            if len(price_parts) == 2:
                                if i == 0:
                                    # First price - likely "Small" or "Regular" or "Single"
                                    size_label = "Small"
                                else:
                                    # Second price - likely "Large" or "Family"
                                    size_label = "Large"
                                
                                # Format the price part
                                if not has_dollar:
                                    if part and part[0].isdigit():
                                        part = f"{size_label} ${part}"
                                    elif part.startswith('$'):
                                        part = f"{size_label} {part}"
                                else:
                                    # Has $ but no label
                                    if part.startswith('$'):
                                        part = f"{size_label} {part}"
                                    elif part and part[0].isdigit():
                                        part = f"{size_label} ${part}"
                            else:
                                # More than 2 prices or just formatting
                                if not has_dollar:
                                    if part and part[0].isdigit():
                                        part = '$' + part
                                elif not part.startswith('$') and part[0].isdigit():
                                    part = '$' + part
                        formatted_parts.append(part)
                    price = ' | '.join(formatted_parts)
                else:
                    # Single price
                    if not has_dollar:
                        # Add $ if it's a number
                        if price and price[0].isdigit():
                            price = '$' + price
                    elif not price.startswith('$') and price[0].isdigit():
                        # Has $ elsewhere but not at start
                        price = '$' + price
                
                # Clean up any double $ symbols
                price = re.sub(r'\$\$+', '$', price)
                item['price'] = price
            
            item['restaurant_name'] = restaurant_name
            item['restaurant_url'] = restaurant_url
            item['menu_type'] = 'Menu'
            # Use section as menu_name, or default to menu name
            section = item.get('section', '')
            if section:
                item['menu_name'] = section
            else:
                item['menu_name'] = menu_name
            # Remove the 'section' field as it's not in our standard format
            if 'section' in item:
                del item['section']
        
        all_items.extend(items)
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Display sample
    if all_items:
        print(f"\n[2] Sample items:")
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
    items = scrape_nkmilton_menu()
    
    # Save to JSON
    if items:
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "nkmilton_com.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Saved {len(items)} items to {output_file}")

