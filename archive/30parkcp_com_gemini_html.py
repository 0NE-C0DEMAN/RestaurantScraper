"""
Scraper for: https://www.30parkcp.com/ using Gemini with HTML as markdown
Fetches HTML and sends it to Gemini text model for extraction
"""

import json
import sys
import re
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Gemini API setup
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed.")
    print("Install with: pip install google-generativeai")

# API Key
GOOGLE_API_KEY = 'AIzaSyD2rneYIn8ahscrSTRJlKhqJg_NUoRiqjQ'

# Initialize Gemini
if GEMINI_AVAILABLE:
    genai.configure(api_key=GOOGLE_API_KEY)


def html_to_markdown(soup, tab_name: str) -> str:
    """
    Convert HTML to a clean markdown format for Gemini.
    Focuses on the menu content for the specific tab.
    """
    # Find the tabpanel for this tab
    tabpanels = soup.find_all('div', {'role': 'tabpanel'})
    
    # Find active panel
    active_panel = None
    for panel in tabpanels:
        if panel.get('aria-hidden') != 'true':
            heading = panel.find(['h2', 'h3'])
            if heading and tab_name.lower() in heading.get_text().lower():
                active_panel = panel
                break
    
    if not active_panel:
        for panel in tabpanels:
            if panel.get('aria-hidden') != 'true':
                active_panel = panel
                break
    
    if not active_panel:
        main = soup.find('main') or soup.find('article')
        if main:
            active_panel = main
    
    if not active_panel:
        return ""
    
    # Convert to markdown
    markdown = f"# {tab_name} Menu Section\n\n"
    
    # Extract all text content in a structured way
    for element in active_panel.find_all(['h2', 'h3', 'h4', 'strong', 'li', 'p']):
        text = element.get_text().strip()
        if text and len(text) > 1:
            tag = element.name
            if tag in ['h2', 'h3', 'h4']:
                markdown += f"\n## {text}\n\n"
            elif tag == 'strong':
                markdown += f"**{text}**\n"
            elif tag == 'li':
                markdown += f"- {text}\n"
            elif tag == 'p':
                markdown += f"{text}\n\n"
    
    return markdown


def extract_menu_from_html_markdown(markdown_text: str, tab_name: str) -> list:
    """
    Extract menu items from markdown HTML using Gemini text model.
    
    Args:
        markdown_text: Markdown representation of HTML
        tab_name: Name of the menu section
    
    Returns:
        List of menu items with name, description, and price
    """
    if not GEMINI_AVAILABLE:
        return []
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        prompt = f"""Analyze this restaurant menu section HTML (converted to markdown) for "{tab_name}" and extract all menu items in JSON format.

HTML/Markdown Content:
{markdown_text}

For each menu item, extract:
1. **name**: The dish/item name (e.g., "SOUTHWEST ROLLS", "GARDEN SALAD")
2. **description**: The description/ingredients (if available)
3. **price**: The price (e.g., "$8", "$6 | $10"). For dual prices, format as "$X (small) | $Y (large)"

CRITICAL RULES:
- Extract ALL menu items from the HTML
- Remove any numbers or price text from the end of item names - keep names clean
- For items with two prices separated by | or shown as "X | Y", label them as (small) and (large)
- If an item has no description, use empty string ""
- If price is not found, use empty string ""
- Skip section headers (like "Food Specials", "Drink Specials", "Classic Drafts", etc.)
- Skip footer text (address, phone, website, allergy warnings, etc.)
- Handle items that say "2 FOR $X" or "– 2 FOR $X" - extract price as "$X" and name without the "2 FOR" part
- Look for prices in the format: "ITEM NAME 5" or "ITEM NAME 6 | 10" or "ITEM NAME $5"
- Prices are usually at the end of the item name in the HTML

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
            prompt,
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
            print(f"    Response preview: {response_text[:500]}...")
            return []
        
    except Exception as e:
        print(f"    Error processing HTML with Gemini: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_30park_menu_gemini_html():
    """Scrape menu from 30 Park website using Gemini with HTML as markdown"""
    
    url = "https://www.30parkcp.com/"
    menu_url = "https://www.30parkcp.com/restaurant/"
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = Path(__file__).parent.parent / 'output' / f'{url_safe}_gemini.json'
    
    print(f"Scraping with Gemini (HTML as markdown): {url}")
    print(f"Menu page: {menu_url}")
    print(f"Output file: {output_json}")
    print()
    
    if not GEMINI_AVAILABLE:
        print("Gemini not available. Install: pip install google-generativeai")
        return
    
    restaurant_name = "30 Park"
    all_items = []
    
    try:
        # Fetch HTML using requests
        print(f"Fetching menu page HTML...")
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.30parkcp.com/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        response = requests.get(menu_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all tabs
        tabs = soup.find_all(['button', 'a'], {'role': 'tab'})
        tab_names = []
        for tab in tabs:
            text = tab.get_text().strip()
            if text and text in ['Happy Hour', 'Snacks', 'Soup & Salad', 'Appetizers', 'Handful', 'Knife & Fork', 'Drinks', 'Sweet Treats']:
                tab_names.append(text)
        
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
                # Convert HTML to markdown for this tab
                markdown = html_to_markdown(soup, tab_name)
                
                if markdown:
                    # Extract menu items using Gemini
                    print(f"  Extracting menu items with Gemini...")
                    items = extract_menu_from_html_markdown(markdown, tab_name)
                    
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
                    print(f"  [ERROR] Could not convert HTML to markdown for {tab_name}")
                
            except Exception as e:
                print(f"  [ERROR] Failed to process {tab_name}: {e}")
                import traceback
                traceback.print_exc()
            
            print()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Save JSON file with menu items
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE (Gemini with HTML)")
    print(f"{'='*60}")
    print(f"Restaurant: {restaurant_name}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")


if __name__ == '__main__':
    scrape_30park_menu_gemini_html()

