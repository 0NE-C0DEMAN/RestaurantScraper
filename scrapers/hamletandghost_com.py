"""
Scraper for Hamlet & Ghost
Website: http://www.hamletandghost.com/
- Dinner Menu: PDF format
- Beverage Menu: PDF format
"""

import requests
import json
import re
from typing import List, Dict
from pathlib import Path
import time

# Check for optional dependencies
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("Warning: pdfplumber not installed. Install with: pip install pdfplumber")


def download_pdf_with_requests(pdf_url: str, output_path: Path, timeout: int = 60, retries: int = 3) -> bool:
    """
    Download PDF from URL using requests.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/octet-stream,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    for attempt in range(retries):
        try:
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"  [OK] Downloaded PDF: {output_path.name}")
            return True
            
        except Exception as e:
            print(f"  [ERROR] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
    
    return False


def extract_menu_from_pdf(pdf_path: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    Extract menu items from PDF by parsing text directly.
    Format: ALL CAPS name, then description, then $price
    Sections: -SHARED-, -DESSERT-, -ENTREE-, -SMALL-
    """
    if not PDFPLUMBER_AVAILABLE:
        return []
    
    items = []
    current_section = menu_type_default
    last_item_index = -1  # Track the last item added to append add-ons
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        
        lines = full_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for section headers (e.g., -SHARED-, -DESSERT-, -ENTREE-, -SMALL-)
            section_match = re.match(r'^-([A-Z\s]+)-$', line)
            if section_match:
                section_name = section_match.group(1).strip()
                # Handle reversed text (PDF encoding issue)
                if section_name == 'LLAMS':
                    current_section = 'SMALL'
                elif section_name == 'EERTNE':
                    current_section = 'ENTREE'
                elif section_name == 'TRESSED':
                    current_section = 'DESSERT'
                elif section_name == 'DERAHS':
                    current_section = 'SHARED'
                else:
                    current_section = section_name
                print(f"    Found section: {current_section}")
                continue
            
            # Also check for section headers without dashes (like "DINNER" as a standalone line)
            # Handle reversed text
            if line == 'LLAMS' or line == 'SMALL':
                current_section = 'SMALL'
                print(f"    Found section: {current_section}")
                continue
            elif line == 'EERTNE' or line == 'ENTREE':
                current_section = 'ENTREE'
                print(f"    Found section: {current_section}")
                continue
            elif line == 'TRESSED' or line == 'DESSERT':
                current_section = 'DESSERT'
                print(f"    Found section: {current_section}")
                continue
            elif line == 'DERAHS' or line == 'SHARED':
                current_section = 'SHARED'
                print(f"    Found section: {current_section}")
                continue
            elif line.isupper() and len(line.split()) <= 2 and line in ['DINNER', 'DRINKS', 'COCKTAILS', 'WINE', 'BEER']:
                current_section = line
                print(f"    Found section: {current_section}")
                continue
            
            # Skip lines that are clearly not menu items
            if line.startswith('Hamlet & Ghost') or 'Kitchen Administration Fee' in line or 'Please inform' in line or 'Consuming raw' in line:
                continue
            
            # Pattern: ALL CAPS name, description, $price
            # Example: "FIRE LAKE OYSTERS salted huckleberries, trout roe, elderflower mignonette $27"
            
            # Find all prices at the end (handle multiple prices like $8/$15)
            # Look for pattern like "$8/$15" or "$8" at the end
            price_pattern = r'\$\d+(?:\.\d+)?(?:\s*/\s*\$\d+(?:\.\d+)?)*\s*$'
            price_match = re.search(price_pattern, line)
            if not price_match:
                continue
            
            price_text = price_match.group(0).strip()
            # Clean up price text (remove extra spaces around /)
            price = re.sub(r'\s*/\s*', '/', price_text)
            
            # Remove all prices from line
            line_without_price = re.sub(price_pattern, '', line).strip()
            
            # Find where the ALL CAPS name ends and description begins
            # Look for transition from ALL CAPS to lowercase
            name_match = re.match(r'^([A-Z][A-Z\s&]+?)(?=\s+[a-z])', line_without_price)
            if name_match:
                name = name_match.group(1).strip()
                description = line_without_price[len(name):].strip()
            else:
                # Fallback: if no clear transition, try to find first word(s) in caps
                words = line_without_price.split()
                if not words:
                    continue
                
                # Find consecutive ALL CAPS words at the start
                name_parts = []
                desc_start = 0
                for i, word in enumerate(words):
                    if word.isupper() and len(word) > 1:
                        name_parts.append(word)
                        desc_start = i + 1
                    else:
                        break
                
                if name_parts:
                    name = ' '.join(name_parts)
                    description = ' '.join(words[desc_start:]) if desc_start < len(words) else ""
                else:
                    # Last resort: first word as name, rest as description
                    name = words[0] if words else ""
                    description = ' '.join(words[1:]) if len(words) > 1 else ""
            
            # Clean up name and description
            name = name.strip()
            description = description.strip()
            
            # Skip if name is too short or looks like a section header
            if len(name) < 3 or name == "DINNER" or name == "MENU":
                continue
            
            # Handle "ADD" lines (add-ons for the previous item)
            if name == "ADD" or (line.strip().startswith("ADD") and not price_match):
                # This is an add-on line, append to previous item's description
                if last_item_index >= 0 and last_item_index < len(items):
                    addon_text = line.strip()
                    # Remove "ADD" prefix and clean up
                    if addon_text.startswith("ADD"):
                        addon_text = addon_text[3:].strip()
                    # Append to description
                    if items[last_item_index]['description']:
                        items[last_item_index]['description'] += f" | Add-ons: {addon_text}"
                    else:
                        items[last_item_index]['description'] = f"Add-ons: {addon_text}"
                continue
            
            # Skip if it's clearly not a menu item (all caps single words that are section-like)
            if name.isupper() and len(name.split()) == 1 and name in ['SHARED', 'DESSERT', 'ENTREE', 'SMALL', 'DRINKS', 'COCKTAILS', 'WINE', 'BEER']:
                continue
            
            items.append({
                'name': name,
                'description': description,
                'price': price,
                'menu_type': current_section
            })
            last_item_index = len(items) - 1  # Update last item index
        
        print(f"    Extracted {len(items)} items from PDF")
        return items
        
    except Exception as e:
        print(f"    [ERROR] Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_hamletandghost_menu() -> List[Dict]:
    """
    Main function to scrape both Dinner (PDF) and Beverage (PDF) menus.
    """
    all_items = []
    
    print("=" * 60)
    print("Scraping: Hamlet & Ghost")
    print("=" * 60)
    
    # Create temp directory
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    # ===== DINNER MENU (PDF) =====
    print("\n[1/2] Scraping Dinner Menu (PDF)...")
    dinner_pdf_url = "https://dl.dropboxusercontent.com/s/zph70ju5nx6gwx6/Hamlet%20Dinner%20Final.pdf?dl=0"
    
    dinner_pdf_path = temp_dir / 'hamletandghost_dinner_menu.pdf'
    
    if download_pdf_with_requests(dinner_pdf_url, dinner_pdf_path):
        dinner_items = extract_menu_from_pdf(str(dinner_pdf_path), menu_type_default="Dinner")
        
        for item in dinner_items:
            item['restaurant_name'] = "Hamlet & Ghost"
            item['restaurant_url'] = "http://www.hamletandghost.com/"
            item['menu_name'] = "Dinner Menu"
        
        all_items.extend(dinner_items)
        print(f"[OK] Extracted {len(dinner_items)} items from Dinner Menu")
        
        # Clean up
        if dinner_pdf_path.exists():
            dinner_pdf_path.unlink()
    else:
        print("[ERROR] Failed to download Dinner PDF")
    
    # ===== BEVERAGE MENU (PDF) =====
    print("\n[2/2] Scraping Beverage Menu (PDF)...")
    beverage_pdf_url = "https://dl.dropboxusercontent.com/s/h1e1nzwrbnja6as/dinner%20beverage%20long%20new.pdf?dl=0"
    
    beverage_pdf_path = temp_dir / 'hamletandghost_beverage_menu.pdf'
    
    if download_pdf_with_requests(beverage_pdf_url, beverage_pdf_path):
        beverage_items = extract_menu_from_pdf(str(beverage_pdf_path), menu_type_default="Beverage")
        
        for item in beverage_items:
            item['restaurant_name'] = "Hamlet & Ghost"
            item['restaurant_url'] = "http://www.hamletandghost.com/"
            item['menu_name'] = "Beverage Menu"
        
        all_items.extend(beverage_items)
        print(f"[OK] Extracted {len(beverage_items)} items from Beverage Menu")
        
        # Clean up
        if beverage_pdf_path.exists():
            beverage_pdf_path.unlink()
    else:
        print("[ERROR] Failed to download Beverage PDF")
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    
    url_safe = "hamletandghost_com"
    output_json = output_dir / f'{url_safe}.json'
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")
    print("=" * 60)
    
    return all_items


if __name__ == '__main__':
    scrape_hamletandghost_menu()

