"""
Scraper for mazzonehospitality.com menu
Menu is embedded in SVG pages (pages 6-24) from issuu.com
Uses Gemini Vision API to extract menu data from SVG images
"""

import json
import base64
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image
import io
import cairosvg


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


def download_svg_page(page_num: int) -> str:
    """Download a single SVG page"""
    try:
        headers = {
            "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://issuu.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        url = f"https://svg.issuu.com/250717154008-0b4f61f895eb147517a20a4e32df0a62/page_{page_num}.svg"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download page {page_num}: {e}")
        return ""


def svg_to_png(svg_content: str, dpi: int = 300) -> bytes:
    """Convert SVG to PNG bytes with high resolution"""
    try:
        import cairosvg
        # Convert with high DPI for better quality
        png_data = cairosvg.svg2png(
            bytestring=svg_content.encode('utf-8'),
            dpi=dpi
        )
        return png_data
    except ImportError:
        print("[ERROR] cairosvg not installed. Please install it: pip install cairosvg")
        return b""
    except Exception as e:
        print(f"[ERROR] Failed to convert SVG to PNG: {e}")
        return b""


def combine_images(image1_bytes: bytes, image2_bytes: bytes) -> Image.Image:
    """Combine two images side by side"""
    img1 = Image.open(io.BytesIO(image1_bytes))
    img2 = Image.open(io.BytesIO(image2_bytes))
    
    # Get dimensions
    width1, height1 = img1.size
    width2, height2 = img2.size
    
    # Use the maximum height and sum of widths
    total_width = width1 + width2
    max_height = max(height1, height2)
    
    # Create new image
    combined = Image.new('RGB', (total_width, max_height), color='white')
    
    # Paste images
    combined.paste(img1, (0, 0))
    combined.paste(img2, (width1, 0))
    
    return combined


def extract_menu_from_images_with_gemini(image1: Image.Image, image2: Image.Image, page_nums: tuple) -> List[Dict]:
    """Extract menu items from combined images using Gemini Vision API"""
    if not GEMINI_API_KEY:
        print("[ERROR] Gemini API key not configured")
        return []
    
    try:
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = """Extract all menu items from these two menu page images. For each item, provide:
- name: The item name
- description: The item description (if any)
- price: The price (if shown)
- section: The section/category name (if any, e.g., "TIER I", "TIER II", "APPETIZERS", etc.)

Return the data as a JSON array of objects with these fields: name, description, price, section.
If a field is not available, use an empty string.
Only extract actual menu items, not headers, footers, or other non-menu content.
Make sure to extract items from both pages in the images.
"""
        
        # Generate content with both images
        response = model.generate_content([prompt, image1, image2])
        
        # Parse JSON from response
        response_text = response.text.strip()
        
        # Try to extract JSON from markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        items = json.loads(response_text)
        
        # Add page numbers for tracking
        for item in items:
            item['pages'] = f"{page_nums[0]}-{page_nums[1]}"
        
        return items
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON from Gemini response for pages {page_nums}: {e}")
        print(f"[DEBUG] Response text: {response_text[:500]}")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to extract menu from pages {page_nums}: {e}")
        return []


def scrape_mazzone_menu() -> List[Dict]:
    """Scrape menu from all SVG pages"""
    print("=" * 60)
    print("Scraping Mazzone Hospitality (mazzonehospitality.com)")
    print("=" * 60)
    
    restaurant_name = "Mazzone Hospitality"
    restaurant_url = "https://www.mazzonehospitality.com/"
    
    all_items = []
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Step 1: Download all SVG pages (6-24)
    print(f"\n[1] Downloading SVG pages (6-24)...")
    svg_contents = {}
    for page_num in range(6, 25):
        print(f"    Downloading page {page_num}...", end=" ")
        svg_content = download_svg_page(page_num)
        if not svg_content:
            print("[SKIP]")
            continue
        
        svg_contents[page_num] = svg_content
        # Save SVG for debugging
        svg_file = temp_dir / f"mazzone_page_{page_num}.svg"
        with open(svg_file, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"[OK]")
    
    print(f"[OK] Downloaded {len(svg_contents)} pages")
    
    # Step 2: Convert all SVGs to PNG images with high resolution
    print(f"\n[2] Converting SVGs to PNG images (300 DPI)...")
    png_images = {}
    for page_num, svg_content in svg_contents.items():
        print(f"    Converting page {page_num}...", end=" ")
        png_data = svg_to_png(svg_content, dpi=300)
        if not png_data:
            print("[SKIP]")
            continue
        
        png_images[page_num] = Image.open(io.BytesIO(png_data))
        print(f"[OK]")
    
    print(f"[OK] Converted {len(png_images)} pages to images")
    
    # Step 3: Process images in pairs with Gemini
    print(f"\n[3] Extracting menu items using Gemini (processing 2 pages at a time)...")
    page_nums = sorted(png_images.keys())
    
    for i in range(0, len(page_nums), 2):
        page1_num = page_nums[i]
        page1_img = png_images[page1_num]
        
        if i + 1 < len(page_nums):
            # Two pages to process together
            page2_num = page_nums[i + 1]
            page2_img = png_images[page2_num]
            print(f"    Processing pages {page1_num} and {page2_num}...", end=" ")
            
            items = extract_menu_from_images_with_gemini(page1_img, page2_img, (page1_num, page2_num))
        else:
            # Only one page left
            print(f"    Processing page {page1_num}...", end=" ")
            # For single page, we'll use it twice (or create a dummy white image)
            # Actually, let's just process it with a single image
            try:
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                prompt = """Extract all menu items from this menu page image. For each item, provide:
- name: The item name
- description: The item description (if any)
- price: The price (if shown)
- section: The section/category name (if any, e.g., "TIER I", "TIER II", "APPETIZERS", etc.)

Return the data as a JSON array of objects with these fields: name, description, price, section.
If a field is not available, use an empty string.
Only extract actual menu items, not headers, footers, or other non-menu content.
"""
                response = model.generate_content([prompt, page1_img])
                response_text = response.text.strip()
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                items = json.loads(response_text)
                for item in items:
                    item['pages'] = str(page1_num)
            except Exception as e:
                print(f"[ERROR] {e}")
                items = []
        
        print(f"[OK] Found {len(items)} items")
        
        # Add restaurant info to each item
        for item in items:
            item['restaurant_name'] = restaurant_name
            item['restaurant_url'] = restaurant_url
            item['menu_type'] = 'Menu'
            # Use section as menu_name, or default to page number
            item['menu_name'] = item.get('section', f'Page {item.get("pages", "Unknown")}') or f'Page {item.get("pages", "Unknown")}'
            # Remove the 'pages' and 'section' fields as they're not in our standard format
            if 'pages' in item:
                del item['pages']
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


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    items = scrape_mazzone_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "mazzonehospitality_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

