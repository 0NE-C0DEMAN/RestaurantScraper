"""
Scraper for: https://www.30parkcp.com/ using Gemini Vision API
Takes screenshots of menu sections and uses Gemini to extract data
"""

import json
import sys
import asyncio
import re
import requests
from pathlib import Path
from playwright.async_api import async_playwright
from io import BytesIO

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Gemini Vision API setup
try:
    import google.generativeai as genai
    from PIL import Image
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai or Pillow not installed.")
    print("Install with: pip install google-generativeai Pillow")

# API Key
GOOGLE_API_KEY = 'AIzaSyD2rneYIn8ahscrSTRJlKhqJg_NUoRiqjQ'

# Initialize Gemini
if GEMINI_AVAILABLE:
    genai.configure(api_key=GOOGLE_API_KEY)


def extract_menu_from_image(image_bytes: bytes, tab_name: str) -> list:
    """
    Extract menu items from an image using Gemini Vision API.
    
    Args:
        image_bytes: Image bytes (PNG format)
        tab_name: Name of the menu section
    
    Returns:
        List of menu items with name, description, and price
    """
    if not GEMINI_AVAILABLE:
        return []
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Analyze this restaurant menu section ({tab_name}) and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "SOUTHWEST ROLLS", "GARDEN SALAD")
2. **description**: The description/ingredients (if available)
3. **price**: The price (e.g., "$8", "$6 | $10"). For dual prices, format as "$X (small) | $Y (large)"

CRITICAL RULES:
- Extract ALL menu items from the image
- Remove any numbers or price text from the end of item names - keep names clean
- For items with two prices separated by |, label them as (small) and (large)
- If an item has no description, use empty string ""
- If price is not found, use empty string ""
- Skip section headers (like "Food Specials", "Drink Specials", etc.)
- Skip footer text (address, phone, website, allergy warnings, etc.)
- Handle items that say "2 FOR $X" - extract price as "$X" and name without the "2 FOR" part

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.

Example output format:
[
  {{
    "name": "SOUTHWEST ROLLS",
    "description": "",
    "price": "$8"
  }},
  {{
    "name": "GARDEN SALAD",
    "description": "Spring Mixed Greens, Fresh Cut Vegetables, Choice of Dressing",
    "price": "$6 (small) | $10 (large)"
  }},
  {{
    "name": "NEW ENGLAND CLAM CHOWDER",
    "description": "Creamy soup featuring claims & potatoes",
    "price": "$7"
  }}
]"""

        # Generate response
        response = model.generate_content(
            [prompt, {
                "mime_type": "image/png",
                "data": image_bytes
            }],
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 8000,
            }
        )
        
        # Extract JSON from response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        # Try to parse JSON
        try:
            # Handle encoding issues
            response_text = response_text.encode('utf-8', errors='ignore').decode('utf-8')
            
            # Try to extract JSON array from response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            menu_items = json.loads(response_text)
            
            # Validate and clean items
            cleaned_items = []
            for item in menu_items:
                if isinstance(item, dict):
                    cleaned_item = {
                        'name': str(item.get('name', '')).strip(),
                        'description': str(item.get('description', '')).strip(),
                        'price': str(item.get('price', '')).strip()
                    }
                    # Only add if name is not empty
                    if cleaned_item['name']:
                        cleaned_items.append(cleaned_item)
            
            return cleaned_items
            
        except json.JSONDecodeError as e:
            print(f"    Warning: Could not parse JSON from Gemini response: {e}")
            print(f"    Response preview: {response_text[:300]}...")
            return []
        
    except Exception as e:
        print(f"    Error processing image with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return []


async def scrape_30park_menu_gemini():
    """Scrape menu from 30 Park website using Gemini Vision API"""
    
    url = "https://www.30parkcp.com/"
    menu_url = "https://www.30parkcp.com/restaurant/"
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = Path(__file__).parent.parent / 'output' / f'{url_safe}_gemini.json'
    
    print(f"Scraping with Gemini Vision API: {url}")
    print(f"Menu page: {menu_url}")
    print(f"Output file: {output_json}")
    print()
    
    if not GEMINI_AVAILABLE:
        print("Gemini not available. Install: pip install google-generativeai Pillow")
        return
    
    restaurant_name = "30 Park"
    all_items = []
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080}
    )
    page = await context.new_page()
    
    try:
        # Navigate to menu page
        print(f"Navigating to menu page...")
        await page.goto(menu_url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)
        
        # Find all menu tabs
        tabs = await page.query_selector_all('[role="tab"]')
        tab_names = []
        for tab in tabs:
            name = await tab.inner_text()
            if name and name.strip():
                tab_names.append(name.strip())
        
        # If no tabs found, use hardcoded list
        if not tab_names:
            tab_names = ['Happy Hour', 'Snacks', 'Soup & Salad', 'Appetizers', 'Handful', 'Knife & Fork', 'Drinks', 'Sweet Treats']
            print("Using hardcoded tab list")
        
        print(f"Found {len(tab_names)} menu sections: {', '.join(tab_names)}")
        print()
        
        # Process each tab
        for i, tab_name in enumerate(tab_names, 1):
            print(f"[{i}/{len(tab_names)}] Processing: {tab_name}")
            
            try:
                # Click on the tab
                tab_clicked = False
                selectors = [
                    f'[role="tab"]:has-text("{tab_name}")',
                    f'button:has-text("{tab_name}")',
                ]
                
                for selector in selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await element.click()
                            tab_clicked = True
                            break
                    except:
                        continue
                
                # If still not clicked, try by index
                if not tab_clicked:
                    try:
                        all_tabs = await page.query_selector_all('[role="tab"]')
                        if i <= len(all_tabs):
                            await all_tabs[i-1].click()
                            tab_clicked = True
                    except:
                        pass
                
                if tab_clicked:
                    await asyncio.sleep(2)  # Wait for content to load
                
                # Find the menu content area - try multiple selectors
                menu_panel = None
                
                # Try to find active tabpanel
                try:
                    tabpanels = await page.query_selector_all('[role="tabpanel"]')
                    for panel in tabpanels:
                        hidden = await panel.get_attribute('aria-hidden')
                        if hidden != 'true':
                            menu_panel = panel
                            break
                except:
                    pass
                
                # If not found, try main/article
                if not menu_panel:
                    try:
                        menu_panel = await page.query_selector('main')
                    except:
                        pass
                
                if not menu_panel:
                    try:
                        menu_panel = await page.query_selector('article')
                    except:
                        pass
                
                # If still not found, take screenshot of visible area
                if menu_panel:
                    try:
                        # Take screenshot of the menu section
                        screenshot_bytes = await menu_panel.screenshot(type='png')
                    except:
                        # Fallback: screenshot the whole page
                        screenshot_bytes = await page.screenshot(type='png', full_page=False)
                else:
                    # Take screenshot of the whole page
                    screenshot_bytes = await page.screenshot(type='png', full_page=False)
                    
                    # Extract menu items using Gemini
                    print(f"  Extracting menu items with Gemini Vision API...")
                    items = extract_menu_from_image(screenshot_bytes, tab_name)
                    
                    if items:
                        # Add restaurant info and menu type to each item
                        for item in items:
                            item['restaurant_name'] = restaurant_name
                            item['restaurant_url'] = url
                            item['menu_type'] = tab_name
                        
                        all_items.extend(items)
                        print(f"  [OK] Extracted {len(items)} items from {tab_name}")
                    else:
                        print(f"  [WARNING] No items extracted from {tab_name}")
                else:
                    print(f"  [ERROR] Could not find menu panel for {tab_name}")
                
            except Exception as e:
                print(f"  [ERROR] Failed to process {tab_name}: {e}")
                import traceback
                traceback.print_exc()
            
            print()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await browser.close()
        await playwright.stop()
    
    # Save JSON file with menu items
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE (Gemini Vision API)")
    print(f"{'='*60}")
    print(f"Restaurant: {restaurant_name}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")


if __name__ == '__main__':
    asyncio.run(scrape_30park_menu_gemini())

