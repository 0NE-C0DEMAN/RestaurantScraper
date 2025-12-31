"""
Scraper for: https://amigoscantina.net/
Uses requests-based PDF download and Gemini Vision API for PDF extraction
All code consolidated in a single file
"""

import json
import os
import sys
import time
import re
import requests
from pathlib import Path
from typing import Dict, List
from io import BytesIO

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
    genai.configure(api_key=GOOGLE_API_KEY)


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 60, retries: int = 3) -> bool:
    """
    Download PDF using requests library with retries.
    
    Args:
        pdf_url: URL of the PDF to download
        output_path: Path where PDF should be saved
        timeout: Request timeout in seconds (default: 60)
        retries: Number of retry attempts (default: 3)
    
    Returns:
        True if download successful, False otherwise
    """
    print(f"  Downloading: {pdf_url}")
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"  Retry attempt {attempt}/{retries}...")
                time.sleep(2 * (attempt - 1))  # Exponential backoff
            
            # Download with proper headers (from curl command)
            response = requests.get(
                pdf_url,
                timeout=timeout,
                stream=True,
                headers={
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
                    'cache-control': 'no-cache',
                    'pragma': 'no-cache',
                    'priority': 'u=0, i',
                    'referer': 'https://amigoscantina.net/',
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
            )
            response.raise_for_status()
            
            # Download file in chunks
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify it's a valid PDF
            if output_path.exists():
                size = output_path.stat().st_size
                
                if size < 100:
                    print(f"  [ERROR] File too small ({size} bytes), likely not a PDF")
                    output_path.unlink()
                    continue
                
                # Check PDF magic bytes
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
                
        except requests.exceptions.Timeout as e:
            print(f"  [ERROR] Timeout after {timeout}s: {e}")
            if attempt < retries:
                continue
        except requests.exceptions.ConnectionError as e:
            print(f"  [ERROR] Connection error: {e}")
            if attempt < retries:
                continue
        except requests.exceptions.HTTPError as e:
            print(f"  [ERROR] HTTP error {e.response.status_code}: {e}")
            if e.response.status_code == 404:
                print(f"  PDF not found at URL")
                return False
            if attempt < retries:
                continue
        except Exception as e:
            print(f"  [ERROR] Unexpected error: {e}")
            if attempt < retries:
                continue
    
    print(f"  [FAILED] All {retries} attempts failed")
    return False


def extract_menu_from_pdf_image(pdf_path: str, page_num: int = 0) -> List[Dict]:
    """
    Extract menu items from a PDF page using Gemini Vision API.
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number to extract (0-indexed)
    
    Returns:
        List of menu items with name, description, and price
    """
    if not GEMINI_AVAILABLE:
        return []
    
    try:
        # Convert PDF page to image
        images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1)
        if not images:
            return []
        
        image = images[0]
        
        # Convert PIL image to bytes
        img_bytes = BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        image_data = img_bytes.read()
        
        # Initialize the vision model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Create prompt for menu extraction
        prompt = """Analyze this restaurant menu PDF page and extract all menu items in JSON format.

For each menu item, extract:
1. **name**: The dish/item name (e.g., "Tacos", "Burrito", "Quesadilla")
2. **description**: The description/ingredients (e.g., "chicken, cheese, salsa")
3. **price**: The price (e.g., "$12", "$15")

CRITICAL PRICING RULES:
- If a section header has a price (e.g., "TACOS $12"), ALL items in that section should have that price
- If an item doesn't have an individual price but is under a section with a price, use the section price
- Look for prices at section headers and apply them to all items below until the next section
- Individual item prices override section prices if present
- If an item has no price and no section price, use empty string ""

Important guidelines:
- Extract ALL menu items from the page, including appetizers, entrees, sides, desserts, drinks, etc.
- Item names are usually in larger/bolder font
- Descriptions are usually in smaller font below the name
- Prices are usually at the end of the description line, on a separate line, or in section headers
- If an item has no description, use empty string ""
- Skip section headers as items (like "APPETIZERS", "ENTRÉES", "TACOS", etc.) but note their prices
- Skip footer text (address, phone, website, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- If text spans both columns, treat it as one item

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.

Example output format:
[
  {
    "name": "Chicken Tacos",
    "description": "grilled chicken, lettuce, tomato, cheese",
    "price": "$12"
  },
  {
    "name": "Beef Burrito",
    "description": "seasoned ground beef, rice, beans, cheese, salsa",
    "price": "$15"
  },
  {
    "name": "Quesadilla",
    "description": "",
    "price": "$10"
  }
]"""

        # Generate response
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
            # Sometimes Gemini adds extra text, so find the JSON array
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            menu_items = json.loads(response_text)
            
            # Validate and clean items
            cleaned_items = []
            for item in menu_items:
                if isinstance(item, dict):
                    price = str(item.get('price', '')).strip()
                    
                    # Handle Market Price (MP) - set to empty string
                    if price.upper() in ['MP', 'MARKET PRICE', 'MARKET', 'M.P.', 'M.P']:
                        price = ""
                    # If price contains "MP" (like "$MP"), set to empty
                    elif price and 'MP' in price.upper() and not re.search(r'\d', price):
                        price = ""
                    # Replace abbreviations with full words and format prices
                    elif price:
                        # Replace SM with Small, LG with Large, etc.
                        price = re.sub(r'\bSM\b', 'Small', price, flags=re.IGNORECASE)
                        price = re.sub(r'\bLG\b', 'Large', price, flags=re.IGNORECASE)
                        price = re.sub(r'\bONE\b', 'One', price, flags=re.IGNORECASE)
                        price = re.sub(r'\bTWO\b', 'Two', price, flags=re.IGNORECASE)
                        
                        # Ensure all prices have $ symbol
                        # Handle patterns like "SM 9 | LG 12" -> "$9 (Small) | $12 (Large)"
                        if '|' in price:
                            # Split by | and format each part
                            parts = price.split('|')
                            formatted_parts = []
                            for part in parts:
                                part = part.strip()
                                # Extract size word and price number
                                size_match = re.search(r'\b(Small|Large|One|Two)\b', part, re.IGNORECASE)
                                price_match = re.search(r'(\d+\.?\d*)', part)
                                
                                if size_match and price_match:
                                    size = size_match.group(1)
                                    price_val = price_match.group(1)
                                    formatted_parts.append(f"${price_val} ({size})")
                                elif price_match:
                                    # Just a price, add $ if not present
                                    price_val = price_match.group(1)
                                    if not part.startswith('$'):
                                        formatted_parts.append(f"${price_val}")
                                    else:
                                        formatted_parts.append(part)
                                else:
                                    formatted_parts.append(part)
                            price = " | ".join(formatted_parts)
                        else:
                            # Single price - ensure it has $ symbol
                            if not price.startswith('$'):
                                # Check if it's a number or number with decimals
                                if re.match(r'^\d+\.?\d*$', price):
                                    price = f"${price}"
                                elif re.search(r'\d', price):
                                    # Has numbers, add $ at the start
                                    price = f"${price}"
                    
                    cleaned_item = {
                        'name': str(item.get('name', '')).strip(),
                        'description': str(item.get('description', '')).strip(),
                        'price': price
                    }
                    # Only add if name is not empty
                    if cleaned_item['name']:
                        cleaned_items.append(cleaned_item)
            
            return cleaned_items
            
        except json.JSONDecodeError as e:
            print(f"  [ERROR] Failed to parse JSON: {e}")
            print(f"  Response text (first 500 chars): {response_text[:500]}")
            print(f"  Full response length: {len(response_text)}")
            return []
            
    except Exception as e:
        print(f"  [ERROR] Error processing PDF page {page_num + 1}: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_amigoscantina_menu(url: str) -> List[Dict]:
    """Scrape menu items from amigoscantina.net"""
    all_items = []
    restaurant_name = "Amigos Cantina"
    menu_pdf_url = "https://amigoscantina.net/Amigos%20Cantina%20Menu.pdf"
    
    print(f"Scraping: {url}")
    print(f"Menu PDF: {menu_pdf_url}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    if not GEMINI_AVAILABLE:
        print("ERROR: google-generativeai and pdf2image are required for PDF extraction.")
        print("Please install them with: pip install google-generativeai pdf2image Pillow pdfplumber")
        return []
    
    try:
        # Create temp directory for PDFs
        temp_dir = Path(__file__).parent.parent / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Download PDF
        pdf_filename = "Amigos_Cantina_Menu.pdf"
        pdf_path = temp_dir / pdf_filename
        
        print("Downloading PDF menu...")
        if not download_pdf_with_requests(menu_pdf_url, pdf_path):
            print("Failed to download PDF")
            return []
        
        print("\nExtracting menu items from PDF using Gemini Vision API...")
        
        # Check how many pages the PDF has
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                num_pages = len(pdf.pages)
                print(f"  PDF has {num_pages} page(s)")
        except:
            num_pages = 1
            print(f"  Assuming PDF has 1 page")
        
        # Extract from all pages
        for page_num in range(num_pages):
            print(f"  Processing page {page_num + 1}/{num_pages}...")
            items = extract_menu_from_pdf_image(str(pdf_path), page_num=page_num)
            
            if items:
                print(f"  [OK] Extracted {len(items)} items from page {page_num + 1}")
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = url
                    item['menu_type'] = "Menu"  # Single menu type
                all_items.extend(items)
            else:
                print(f"  [WARNING] No items extracted from page {page_num + 1}")
        
        if all_items:
            print(f"\n[OK] Extracted {len(all_items)} total items from menu\n")
        else:
            print(f"\n[WARNING] No items extracted from menu\n")
        
        # Clean up temp PDF
        if pdf_path.exists():
            pdf_path.unlink()
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
    
    # Save JSON file with menu items
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Restaurant: {restaurant_name}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")
    
    return all_items


def main():
    url = "https://amigoscantina.net/"
    scrape_amigoscantina_menu(url)


if __name__ == "__main__":
    main()

