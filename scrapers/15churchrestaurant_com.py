"""
Scraper for: https://www.15churchrestaurant.com/
Uses requests-based PDF download and Gemini Vision API for PDF extraction
All code consolidated in a single file
"""

import json
import os
import sys
import asyncio
import time
import re
import requests
from pathlib import Path
from typing import Dict, List
from io import BytesIO
from playwright.async_api import async_playwright

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
            
            # Download with proper headers
            response = requests.get(
                pdf_url,
                timeout=timeout,
                stream=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/pdf,application/octet-stream,*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
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
1. **name**: The dish/item name (e.g., "Warm French Bâtard", "Foie Gras Bratwurst")
2. **description**: The description/ingredients (e.g., "chives, grana padano, olive oil, saba")
3. **price**: The price (e.g., "$5", "$27")

CRITICAL PRICING RULES:
- If a section header has a price (e.g., "MOCKTAILS & OTHER REFRESHMENTS $8"), ALL items in that section should have that price
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
- Skip section headers as items (like "APPETIZERS", "ENTRÉES", "RAW BAR", etc.) but note their prices
- Skip footer text (address, phone, website, allergy warnings, etc.)
- Handle two-column layouts correctly - items in left column and right column should be separate
- If text spans both columns, treat it as one item

Return ONLY a valid JSON array of objects, no markdown, no code blocks, no explanations.

Example output format:
[
  {
    "name": "Warm French Bâtard",
    "description": "chives, grana padano, olive oil, saba",
    "price": "$5"
  },
  {
    "name": "Foie Gras Bratwurst",
    "description": "soppressata jam, gruyére mornay, onion frilly, brioche bun",
    "price": "$27"
  },
  {
    "name": "Virgin Mojito",
    "description": "fresh lime, fresh mint, simple syrup, seltzer",
    "price": "$8"
  },
  {
    "name": "Fever Tree Ginger Beer",
    "description": "",
    "price": "$8"
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
        print(f"    Error processing PDF page {page_num}: {e}")
        return []


def extract_menu_from_pdf(pdf_path: str) -> List[Dict]:
    """
    Extract menu items from all pages of a PDF using Gemini Vision API.
    
    Args:
        pdf_path: Path to PDF file
    
    Returns:
        List of all menu items from all pages
    """
    if not GEMINI_AVAILABLE:
        print("Gemini not available. Install: pip install google-generativeai pdf2image Pillow pdfplumber")
        return []
    
    all_items = []
    
    try:
        # Get number of pages
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = len(pdf.pages)
        
        print(f"  Processing {num_pages} page(s) with Gemini Vision API...")
        
        for page_num in range(num_pages):
            print(f"  Processing page {page_num + 1}/{num_pages}...")
            items = extract_menu_from_pdf_image(pdf_path, page_num)
            all_items.extend(items)
            print(f"    Found {len(items)} items on page {page_num + 1}")
            
            # Rate limiting - small delay between pages
            if page_num < num_pages - 1:
                time.sleep(1)
        
        print(f"  Total items extracted: {len(all_items)}")
        
    except Exception as e:
        print(f"  Error processing PDF: {e}")
    
    return all_items


async def find_all_menu_pdfs(page):
    """Find all PDF menu links on the menus page"""
    menus_url = "https://www.15churchrestaurant.com/saratoga-springs/menus/"
    print(f"Visiting menus page: {menus_url}")
    await page.goto(menus_url, wait_until='networkidle', timeout=60000)
    await asyncio.sleep(2)
    
    # Find all PDF links
    pdf_links = []
    seen_urls = set()  # Track URLs to avoid duplicates
    links = await page.query_selector_all('a[href$=".pdf"]')
    
    for link in links:
        href = await link.get_attribute('href')
        if href and href.endswith('.pdf'):
            # Make absolute URL if relative
            if href.startswith('/'):
                href = f"https://www.15churchrestaurant.com{href}"
            elif not href.startswith('http'):
                href = f"https://www.15churchrestaurant.com/{href}"
            
            # Skip if we've already seen this URL
            if href in seen_urls:
                continue
            seen_urls.add(href)
            
            # Get link text for menu name
            text = await link.inner_text()
            menu_name = text.strip() if text else href.split('/')[-1]
            
            pdf_links.append({
                'url': href,
                'name': menu_name
            })
            print(f"  Found menu: {menu_name} -> {href}")
    
    return pdf_links


async def main():
    """Scrape menu for 15 Church Restaurant"""
    
    url = "https://www.15churchrestaurant.com/"
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = Path(__file__).parent.parent / 'output' / f'{url_safe}.json'
    
    print(f"Scraping: {url}")
    print(f"Output file: {output_json}")
    print()
    
    restaurant_name = "15 Church Restaurant"
    all_items = []
    
    if GEMINI_AVAILABLE:
        # Find all menu PDFs
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            pdf_links = await find_all_menu_pdfs(page)
            
            if not pdf_links:
                print("No PDF menus found on the website")
            else:
                print(f"\nFound {len(pdf_links)} menu(s) to process\n")
                
                # Process each PDF one by one
                for i, menu_info in enumerate(pdf_links, 1):
                    pdf_url = menu_info['url']
                    menu_name = menu_info['name']
                    
                    print(f"[{i}/{len(pdf_links)}] Processing: {menu_name}")
                    
                    # Download PDF using requests-based approach
                    temp_pdf = Path(__file__).parent.parent / f'temp_menu_{i}.pdf'
                    success = download_pdf_with_requests(pdf_url, temp_pdf, timeout=60, retries=3)
                    
                    if success and temp_pdf.exists():
                        # Use Gemini to extract menu items
                        print(f"  Extracting menu items with Gemini Vision API...")
                        gemini_items = extract_menu_from_pdf(str(temp_pdf))
                        
                        if gemini_items:
                            # Add restaurant info and menu type to each item
                            for item in gemini_items:
                                item['restaurant_name'] = restaurant_name
                                item['restaurant_url'] = url
                                item['menu_type'] = menu_name
                            
                            all_items.extend(gemini_items)
                            print(f"  [OK] Extracted {len(gemini_items)} items from {menu_name}")
                        else:
                            print(f"  [WARNING] No items extracted from {menu_name}")
                        
                        # Clean up temp file
                        if temp_pdf.exists():
                            temp_pdf.unlink()
                    else:
                        print(f"  [ERROR] Failed to download {menu_name}")
                    
                    print()
        
        finally:
            await browser.close()
            await playwright.stop()
    else:
        print("Gemini not available. Install: pip install google-generativeai pdf2image Pillow pdfplumber")
    
    # Save JSON file with menu items only
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Restaurant: {restaurant_name}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")


if __name__ == '__main__':
    asyncio.run(main())
