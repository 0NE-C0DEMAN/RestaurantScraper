"""
Scraper for Kindred Saratoga
Website: https://kindredsaratoga.com/
- Food Menu: PDF format
- Brunch Menu: PDF format
- Drink Menu: PDF format
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


def extract_font_info_from_pdf(pdf_path: str) -> List[Dict]:
    """
    Extract text with font size and bold/italic information from PDF.
    Returns a list of dictionaries with text, font_size, is_bold, is_italic, and position info.
    """
    if not PDFPLUMBER_AVAILABLE:
        print("  [ERROR] pdfplumber not available")
        return []
    
    font_data = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  PDF has {len(pdf.pages)} pages")
            
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"\n  Page {page_num}:")
                print("  " + "=" * 60)
                
                # Get character-level information
                chars = page.chars
                
                if not chars:
                    print("  No character data found on this page")
                    continue
                
                # Group characters by font properties and position
                current_text = ""
                current_font_size = None
                current_is_bold = None
                current_is_italic = None
                current_y = None
                current_x0 = None
                
                for char in chars:
                    font_size = char.get('size', 0)
                    # Check if bold (font name often contains "Bold" or weight is > 500)
                    font_name = char.get('fontname', '').lower()
                    is_bold = 'bold' in font_name or char.get('fontname', '').endswith('-Bold')
                    # Check if italic (font name often contains "Italic" or "Oblique")
                    is_italic = 'italic' in font_name or 'oblique' in font_name
                    
                    x0 = char.get('x0', 0)
                    y = char.get('top', 0)
                    
                    # Check if we should start a new text block
                    # (different font size, bold/italic status, or significant position change)
                    if (current_font_size is not None and 
                        (abs(font_size - current_font_size) > 0.5 or
                         is_bold != current_is_bold or
                         is_italic != current_is_italic or
                         (current_y is not None and abs(y - current_y) > 2))):
                        # Save previous text block
                        if current_text.strip():
                            font_data.append({
                            'text': current_text.strip(),
                            'font_size': current_font_size,
                            'is_bold': current_is_bold,
                            'is_italic': current_is_italic,
                            'x0': current_x0,
                            'y': current_y,
                            'page': page_num
                        })
                        # Start new block
                        current_text = char.get('text', '')
                        current_font_size = font_size
                        current_is_bold = is_bold
                        current_is_italic = is_italic
                        current_x0 = x0
                        current_y = y
                    else:
                        # Continue current block
                        if current_text:
                            current_text += char.get('text', '')
                        else:
                            current_text = char.get('text', '')
                            current_font_size = font_size
                            current_is_bold = is_bold
                            current_is_italic = is_italic
                            current_x0 = x0
                            current_y = y
                
                # Save last block
                if current_text.strip():
                    font_data.append({
                        'text': current_text.strip(),
                        'font_size': current_font_size,
                        'is_bold': current_is_bold,
                        'is_italic': current_is_italic,
                        'x0': current_x0,
                        'y': current_y,
                        'page': page_num
                    })
                
                # Print summary for this page
                print(f"  Found {len([d for d in font_data if d['page'] == page_num])} text blocks")
                
                # Show unique font sizes and styles
                page_fonts = [d for d in font_data if d['page'] == page_num]
                unique_fonts = {}
                for item in page_fonts:
                    key = (item['font_size'], item['is_bold'], item['is_italic'])
                    if key not in unique_fonts:
                        unique_fonts[key] = []
                    unique_fonts[key].append(item['text'][:50])  # First 50 chars
                
                print(f"\n  Unique font styles on page {page_num}:")
                for (size, bold, italic), texts in sorted(unique_fonts.items(), key=lambda x: x[0][0], reverse=True):
                    style = []
                    if bold:
                        style.append("BOLD")
                    if italic:
                        style.append("ITALIC")
                    style_str = " ".join(style) if style else "regular"
                    print(f"    Size: {size:.1f}, Style: {style_str}")
                    print(f"      Examples: {texts[0]}")
                    if len(texts) > 1:
                        print(f"               ... and {len(texts)-1} more")
                
                # Show first 20 text blocks with their font info
                print(f"\n  First 20 text blocks with font info:")
                for i, item in enumerate(page_fonts[:20], 1):
                    style = []
                    if item['is_bold']:
                        style.append("BOLD")
                    if item['is_italic']:
                        style.append("ITALIC")
                    style_str = " ".join(style) if style else "regular"
                    text_preview = item['text'][:60] + "..." if len(item['text']) > 60 else item['text']
                    print(f"    {i}. [{item['font_size']:.1f}pt, {style_str}] {text_preview}")
        
        print("\n  " + "=" * 60)
        print(f"  Total text blocks extracted: {len(font_data)}")
        
        return font_data
        
    except Exception as e:
        print(f"  [ERROR] Error extracting font info: {e}")
        import traceback
        traceback.print_exc()
        return []


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
            print(f"  Downloading: {pdf_url}")
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


def extract_menu_from_pdf_with_fonts(pdf_path: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    Extract menu items using font information and 2-column layout detection.
    Uses font size and bold/italic status to identify:
    - Section headers: 20pt regular
    - Item names: 10pt BOLD
    - Descriptions: 10pt regular
    - Prices: 9pt regular
    """
    if not PDFPLUMBER_AVAILABLE:
        print("  [ERROR] pdfplumber not available")
        return []
    
    # First extract font information
    font_data = extract_font_info_from_pdf(pdf_path)
    if not font_data:
        print("  [ERROR] Could not extract font information")
        return []
    
    items = []
    current_section = menu_type_default
    
    # Determine column boundaries by analyzing x0 positions
    all_x_positions = [item['x0'] for item in font_data]
    if all_x_positions:
        # Find clusters of x positions (columns)
        sorted_x = sorted(set(all_x_positions))
        # Look for a gap that indicates column separation
        gaps = []
        for i in range(len(sorted_x) - 1):
            gap = sorted_x[i+1] - sorted_x[i]
            if gap > 50:  # Significant gap indicates column boundary
                gaps.append((sorted_x[i], sorted_x[i+1], gap))
        
        if gaps:
            # Use the largest gap as column boundary
            largest_gap = max(gaps, key=lambda x: x[2])
            mid_x = (largest_gap[0] + largest_gap[1]) / 2
            print(f"  Column detection: left column < {mid_x:.1f} < right column (gap: {largest_gap[2]:.1f})")
        else:
            # No clear gap, use midpoint
            mid_x = (min(all_x_positions) + max(all_x_positions)) / 2
            print(f"  Column detection: using midpoint {mid_x:.1f}")
    else:
        mid_x = 500  # Default midpoint
    
    # Process by page
    pages = {}
    for item in font_data:
        page_num = item['page']
        if page_num not in pages:
            pages[page_num] = []
        pages[page_num].append(item)
    
    # Process each page
    for page_num in sorted(pages.keys()):
        page_items = pages[page_num]
        # Sort by y (top to bottom), then by x (left to right)
        page_items.sort(key=lambda x: (x['y'], x['x0']))
        
        # Process items in order, handling 2 columns
        # Track items separately for left and right columns
        left_column_items = []  # List of (name, description_lines, price, section)
        right_column_items = []
        
        current_section = menu_type_default
        current_name = None
        current_desc = []
        current_price = None
        current_x = None
        current_column = None  # 'left' or 'right'
        
        i = 0
        while i < len(page_items):
            item = page_items[i]
            text = item['text'].strip()
            font_size = item['font_size']
            is_bold = item['is_bold']
            x0 = item['x0']
            y = item['y']
            
            # Determine which column
            column = 'left' if x0 < mid_x else 'right'
            
            # Skip empty text
            if not text:
                i += 1
                continue
            
            # Section headers: 20pt regular
            if font_size >= 18 and not is_bold:
                # Save previous item if exists
                if current_name and current_price:
                    item_data = (current_name, current_desc.copy(), current_price, current_section)
                    if current_column == 'left':
                        left_column_items.append(item_data)
                    else:
                        right_column_items.append(item_data)
                
                # New section (applies to both columns)
                current_section = text
                current_name = None
                current_desc = []
                current_price = None
                current_x = None
                current_column = None
                print(f"    Found section: {current_section}")
                i += 1
                continue
            
            # Prices: 9pt regular, usually just numbers
            if font_size <= 9.5 and not is_bold:
                price_match = re.search(r'(\d+(?:\.\d+)?)', text)
                if price_match:
                    price_value = price_match.group(1)
                    
                    # Look backwards to find the associated name
                    # Check if previous item in same column was a name
                    if i > 0:
                        prev_item = page_items[i-1]
                        prev_column = 'left' if prev_item['x0'] < mid_x else 'right'
                        
                        # If previous item is a name in the same column and close in y
                        if (prev_column == column and 
                            prev_item['font_size'] == 10.0 and prev_item['is_bold'] and
                            abs(prev_item['y'] - y) < 5):  # Very close vertically
                            
                            # Save any previous item
                            if current_name and current_price:
                                item_data = (current_name, current_desc.copy(), current_price, current_section)
                                if current_column == 'left':
                                    left_column_items.append(item_data)
                                else:
                                    right_column_items.append(item_data)
                            
                            # Start new item with this name and price
                            current_name = prev_item['text'].strip()
                            current_desc = []
                            current_price = price_value
                            current_x = prev_item['x0']
                            current_column = column
                            i += 1
                            continue
                    
                    # If we have a current item, assign price and save it
                    if current_name:
                        current_price = price_value
                        item_data = (current_name, current_desc.copy(), current_price, current_section)
                        if current_column == 'left':
                            left_column_items.append(item_data)
                        else:
                            right_column_items.append(item_data)
                        current_name = None
                        current_desc = []
                        current_price = None
                        current_x = None
                        current_column = None
                    i += 1
                    continue
            
            # Item names: 10pt BOLD
            if font_size == 10.0 and is_bold:
                # Save previous item if exists
                if current_name and current_price:
                    item_data = (current_name, current_desc.copy(), current_price, current_section)
                    if current_column == 'left':
                        left_column_items.append(item_data)
                    else:
                        right_column_items.append(item_data)
                
                # New item name
                current_name = text
                current_desc = []
                current_price = None
                current_x = x0
                current_column = column
                i += 1
                continue
            
            # Descriptions: 10pt regular (non-bold)
            if font_size == 10.0 and not is_bold:
                # Check if this belongs to current item (same column)
                if current_name and current_column == column:
                    # Check if it's close in x position (same column)
                    if current_x is None or abs(x0 - current_x) < 100:
                        # Check for add-ons in parentheses
                        if text.startswith('(') and 'add' in text.lower():
                            # Extract add-ons
                            addon_matches = re.findall(r'\(([^)]+)\)', text)
                            if addon_matches:
                                addons_list = []
                                for addon in addon_matches:
                                    if ' - ' in addon:
                                        parts = addon.split(' - ', 1)
                                        addon_name = parts[0].strip()
                                        addon_price = parts[1].strip()
                                        addons_list.append(f"{addon_name} - ${addon_price}")
                                    else:
                                        addons_list.append(addon.strip())
                                if addons_list:
                                    current_desc.append("Add-ons: " + " / ".join(addons_list))
                        else:
                            current_desc.append(text)
                        i += 1
                        continue
                
                # If we have a name but different column, save it and start new
                if current_name and current_column != column:
                    if current_price:
                        item_data = (current_name, current_desc.copy(), current_price, current_section)
                        if current_column == 'left':
                            left_column_items.append(item_data)
                        else:
                            right_column_items.append(item_data)
                    current_name = None
                    current_desc = []
                    current_price = None
                    current_x = None
                    current_column = None
                    # Don't increment i, reprocess
                    continue
                
                # Orphaned description, skip
                i += 1
                continue
            
            # Other text - skip
            i += 1
        
        # Save last item if exists
        if current_name and current_price:
            item_data = (current_name, current_desc.copy(), current_price, current_section)
            if current_column == 'left':
                left_column_items.append(item_data)
            else:
                right_column_items.append(item_data)
        
        # Combine left and right column items, interleaving by y position
        all_column_items = []
        for name, desc, price, section in left_column_items + right_column_items:
            description_text = ' '.join(desc).strip()
            items.append({
                'name': name,
                'description': description_text,
                'price': f"${price}",
                'menu_type': section
            })
    
    print(f"  Extracted {len(items)} items using font-based extraction")
    return items


def extract_menu_from_pdf_improved(pdf_path: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    Improved extraction using table detection and better multi-line handling.
    """
    if not PDFPLUMBER_AVAILABLE:
        print("  [ERROR] pdfplumber not available")
        return []
    
    items = []
    current_section = menu_type_default
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  PDF has {len(pdf.pages)} pages")
            
            # Try to extract tables first
            all_tables = []
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)
            
            if all_tables:
                print(f"  Found {len(all_tables)} tables, using table extraction")
                # Process tables if found
                for table in all_tables:
                    for row in table:
                        if row and len(row) >= 2:
                            # Table format: [name/description, price] or similar
                            name_desc = str(row[0]).strip() if row[0] else ""
                            price = str(row[-1]).strip() if row[-1] else ""
                            
                            if name_desc and price:
                                # Extract price
                                price_match = re.search(r'(\d+(?:\.\d+)?)', price)
                                if price_match:
                                    price_value = f"${price_match.group(1)}"
                                    
                                    # Try to split name and description
                                    if ' - ' in name_desc:
                                        parts = name_desc.split(' - ', 1)
                                        name = parts[0].strip()
                                        description = parts[1].strip()
                                    else:
                                        # First line or first few words as name
                                        lines = name_desc.split('\n')
                                        name = lines[0].strip() if lines else name_desc
                                        description = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
                                    
                                    if name and len(name) > 1:
                                        items.append({
                                            'name': name,
                                            'description': description,
                                            'price': price_value,
                                            'menu_type': current_section
                                        })
            
            # If no tables or table extraction didn't work well, fall back to text extraction
            if not items:
                print("  No tables found or table extraction failed, using improved text extraction")
                # Use the new improved text extraction
                return extract_menu_from_pdf(pdf_path, menu_type_default)
            
            print(f"  Extracted {len(items)} items from PDF using table extraction")
            return items
            
    except Exception as e:
        print(f"  [ERROR] Error in improved extraction: {e}")
        # Fall back to text extraction
        return extract_menu_from_pdf(pdf_path, menu_type_default)


def extract_menu_from_pdf(pdf_path: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    Extract menu items from PDF using pdfplumber.
    Format observed: item name, description, price (numeric without $)
    Sections: lowercase headers like "shareables", "flatbreads", "salads", "entrees"
    Add-ons: in parentheses like "(add grilled chicken - 6)"
    """
    if not PDFPLUMBER_AVAILABLE:
        print("  [ERROR] pdfplumber not available")
        return []
    
    items = []
    current_section = menu_type_default
    last_item_index = -1
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  PDF has {len(pdf.pages)} pages")
            
            # Extract text from all pages
            full_text = ""
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            # Print first 2000 characters for inspection
            print("\n  First 2000 characters of extracted text:")
            print("  " + "=" * 60)
            print(full_text[:2000])
            print("  " + "=" * 60)
            
            # Try to parse the text - collect multi-line items
            lines = full_text.split('\n')
            
            # Collect lines into potential items
            current_item_lines = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for section headers (lowercase, single word or short phrases)
                # Common sections: shareables, flatbreads, salads, entrees, snacks, sandwiches, etc.
                line_lower = line.lower()
                if (line_lower in ['shareables', 'flatbreads', 'salads', 'entrees', 'snacks', 'sandwiches', 
                                   'toasts', 'sides', 'cocktails', 'wine', 'beer', 'zero-proof', 'brunch',
                                   'breakfast classics', 'omelettes', 'mimosas', 'happy hour', 'cocktails'] or
                    any(keyword in line_lower for keyword in ['and greens', 'and toasts', 'classics'])):
                    # Process any accumulated item lines before changing section
                    if current_item_lines:
                        item = process_item_lines(current_item_lines, current_section)
                        if item:
                            items.append(item)
                        current_item_lines = []
                    current_section = line
                    print(f"    Found section: {current_section}")
                    continue
                
                # Look for price patterns - numeric prices at the end (with or without $)
                # Pattern: number at end of line, possibly preceded by space
                price_pattern = r'(?:\$)?(\d+(?:\.\d+)?)\s*$'
                price_match = re.search(price_pattern, line)
                
                if price_match:
                    # Found a price - this line completes the current item
                    current_item_lines.append(line)
                    item = process_item_lines(current_item_lines, current_section)
                    if item:
                        items.append(item)
                        last_item_index = len(items) - 1
                    current_item_lines = []  # Reset for next item
                else:
                    # No price yet - accumulate lines for current item
                    # But check if this looks like the start of a new item
                    # (e.g., capitalized first word, or very short line that might be a name)
                    if current_item_lines and len(line) > 0:
                        # Check if this might be a new item starting
                        words = line.split()
                        if (len(words) <= 3 and words[0][0].isupper() and 
                            not any(char.isdigit() for char in line)):
                            # Might be a new item name - process previous item first
                            item = process_item_lines(current_item_lines, current_section)
                            if item:
                                items.append(item)
                                last_item_index = len(items) - 1
                            current_item_lines = [line]  # Start new item
                        else:
                            # Continuation of current item
                            current_item_lines.append(line)
                    else:
                        # Starting a new item
                        current_item_lines = [line]
            
            # Process any remaining item lines
            if current_item_lines:
                item = process_item_lines(current_item_lines, current_section)
                if item:
                    items.append(item)
            
            print(f"  Extracted {len(items)} items from PDF")
            return items
        
    except Exception as e:
        print(f"  [ERROR] Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
        return []


def process_item_lines(item_lines: List[str], current_section: str) -> Dict:
    """
    Process accumulated lines for a single menu item.
    """
    if not item_lines:
        return None
    
    # Combine all lines
    full_text = ' '.join(item_lines)
    
    # Look for price at the end
    price_pattern = r'(?:\$)?(\d+(?:\.\d+)?)\s*$'
    price_match = re.search(price_pattern, full_text)
    
    if not price_match:
        return None
    
    price_value = f"${price_match.group(1)}"
    line_without_price = re.sub(price_pattern, '', full_text).strip()
    
    # Check for add-ons in parentheses
    addon_pattern = r'\(([^)]+)\)'
    addon_matches = re.findall(addon_pattern, line_without_price)
    addons_text = ""
    if addon_matches:
        line_without_price = re.sub(addon_pattern, '', line_without_price).strip()
        addons_list = []
        for addon in addon_matches:
            if ' - ' in addon:
                addon_parts = addon.split(' - ', 1)
                addon_name = addon_parts[0].strip()
                addon_price = addon_parts[1].strip()
                addons_list.append(f"{addon_name} - ${addon_price}")
            else:
                addons_list.append(addon.strip())
        addons_text = " | Add-ons: " + " / ".join(addons_list)
    
    # Split name and description
    # Name is typically the first part, description follows
    words = line_without_price.split()
    if len(words) <= 2:
        name = line_without_price
        description = ""
    else:
        # Try to find where name ends - look for common patterns
        # Name is usually 1-4 words, often capitalized or all lowercase
        name_parts = []
        desc_start = 0
        
        # Look for first comma or first few words
        if ',' in line_without_price:
            parts = line_without_price.split(',', 1)
            name = parts[0].strip()
            description = parts[1].strip()
        else:
            # First 2-3 words as name
            name = ' '.join(words[:2]) if len(words) >= 2 else words[0]
            description = ' '.join(words[2:]) if len(words) > 2 else ""
    
    name = name.strip()
    description = description.strip()
    
    if len(name) < 2:
        return None
    
    # Skip obvious non-items
    if name.lower() in ['brunch', 'menu', 'kindred', 'happy hour', 'tuesday', 'friday', '4pm', '6pm', '@ the bar']:
        return None
    
    full_description = description
    if addons_text:
        if full_description:
            full_description += addons_text
        else:
            full_description = addons_text.strip()
    
    return {
        'name': name,
        'description': full_description,
        'price': price_value,
        'menu_type': current_section
    }


def extract_menu_from_pdf_old(pdf_path: str, menu_type_default: str = "Menu") -> List[Dict]:
    """
    OLD VERSION - kept for reference
    """
    if not PDFPLUMBER_AVAILABLE:
        print("  [ERROR] pdfplumber not available")
        return []
    
    items = []
    current_section = menu_type_default
    last_item_index = -1
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  PDF has {len(pdf.pages)} pages")
            
            # Extract text from all pages
            full_text = ""
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            # Print first 2000 characters for inspection
            print("\n  First 2000 characters of extracted text:")
            print("  " + "=" * 60)
            print(full_text[:2000])
            print("  " + "=" * 60)
            
            # Try to parse the text
            lines = full_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for section headers (lowercase, single word or short phrases)
                line_lower = line.lower()
                if (line_lower in ['shareables', 'flatbreads', 'salads', 'entrees', 'snacks', 'sandwiches', 
                                   'toasts', 'sides', 'cocktails', 'wine', 'beer', 'zero-proof', 'brunch',
                                   'breakfast classics', 'omelettes', 'mimosas', 'happy hour', 'cocktails'] or
                    any(keyword in line_lower for keyword in ['and greens', 'and toasts', 'classics'])):
                    current_section = line
                    print(f"    Found section: {current_section}")
                    continue
                
                # Look for price patterns - numeric prices at the end (with or without $)
                price_pattern = r'(?:\$)?(\d+(?:\.\d+)?)\s*$'
                price_match = re.search(price_pattern, line)
                
                if price_match:
                    # Found a line with a price - likely a menu item
                    price_value = price_match.group(1)
                    price = f"${price_value}"
                    
                    # Remove price from line
                    line_without_price = re.sub(price_pattern, '', line).strip()
                    
                    # Check for add-ons in parentheses
                    addon_pattern = r'\(([^)]+)\)'
                    addon_matches = re.findall(addon_pattern, line_without_price)
                    addons_text = ""
                    if addon_matches:
                        # Remove add-ons from line for name/description extraction
                        line_without_price = re.sub(addon_pattern, '', line_without_price).strip()
                        # Format add-ons
                        addons_list = []
                        for addon in addon_matches:
                            # Add-ons might have prices like "add grilled chicken - 6"
                            if ' - ' in addon:
                                addon_parts = addon.split(' - ', 1)
                                addon_name = addon_parts[0].strip()
                                addon_price = addon_parts[1].strip()
                                addons_list.append(f"{addon_name} - ${addon_price}")
                            else:
                                addons_list.append(addon.strip())
                        addons_text = " | Add-ons: " + " / ".join(addons_list)
                    
                    # Try to split name and description
                    # Common patterns:
                    # 1. "name description price" - name is usually first 2-3 words
                    # 2. "name - description price" - explicit separator
                    # 3. Multi-line items might have description on next line
                    
                    if ' - ' in line_without_price:
                        parts = line_without_price.split(' - ', 1)
                        name = parts[0].strip()
                        description = parts[1].strip() if len(parts) > 1 else ""
                    else:
                        # Split by first occurrence of common description words or patterns
                        # Name is typically 1-4 words, description follows
                        words = line_without_price.split()
                        if len(words) <= 2:
                            # Likely just a name
                            name = line_without_price
                            description = ""
                        else:
                            # First 2-3 words as name, rest as description
                            # But be smart about it - if first word is lowercase, it might be part of description
                            name_parts = []
                            desc_start = 0
                            
                            # If first word is capitalized, it's likely part of the name
                            for i, word in enumerate(words):
                                if i < 3 and (word[0].isupper() or word.islower()):
                                    name_parts.append(word)
                                    desc_start = i + 1
                                else:
                                    break
                            
                            if name_parts:
                                name = ' '.join(name_parts)
                                description = ' '.join(words[desc_start:]) if desc_start < len(words) else ""
                            else:
                                name = words[0] if words else ""
                                description = ' '.join(words[1:]) if len(words) > 1 else ""
                    
                    # Clean up name and description
                    name = name.strip()
                    description = description.strip()
                    
                    # Skip if name is too short or looks invalid
                    if len(name) < 2:
                        continue
                    
                    # Skip obvious non-items
                    if name.lower() in ['brunch', 'menu', 'kindred', 'happy hour', 'tuesday', 'friday', '4pm', '6pm']:
                        continue
                    
                    # Add description with add-ons
                    full_description = description
                    if addons_text:
                        if full_description:
                            full_description += addons_text
                        else:
                            full_description = addons_text.strip()
                    
                    items.append({
                        'name': name,
                        'description': full_description,
                        'price': price,
                        'menu_type': current_section
                    })
                    last_item_index = len(items) - 1
                else:
                    # No price found - might be a continuation line (description continues)
                    # Or might be an add-on line without price
                    if last_item_index >= 0 and items:
                        # Check if this looks like a continuation
                        if line and not line[0].isupper() and len(line) > 10:
                            # Likely a description continuation
                            if items[last_item_index]['description']:
                                items[last_item_index]['description'] += " " + line
                            else:
                                items[last_item_index]['description'] = line
        
        print(f"  Extracted {len(items)} items from PDF")
        return items
        
    except Exception as e:
        print(f"  [ERROR] Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_kindredsaratoga_menu() -> List[Dict]:
    """
    Main function to scrape Food, Brunch, and Drink menus from PDFs.
    """
    all_items = []
    
    print("=" * 60)
    print("Scraping: Kindred Saratoga")
    print("=" * 60)
    
    # Create temp directory
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    # PDF URLs
    pdfs = [
        {
            'url': 'https://kindredsaratoga.com/wp-content/uploads/2025/12/Kindred-Food-Menu-11_28.pdf',
            'name': 'Food Menu',
            'type': 'Food',
            'filename': 'kindredsaratoga_food_menu.pdf'
        },
        {
            'url': 'https://kindredsaratoga.com/wp-content/uploads/2025/12/Brunch11__28.pdf',
            'name': 'Brunch Menu',
            'type': 'Brunch',
            'filename': 'kindredsaratoga_brunch_menu.pdf'
        },
        {
            'url': 'https://kindredsaratoga.com/wp-content/uploads/2025/12/Drink-Menu-11_28.pdf',
            'name': 'Drink Menu',
            'type': 'Drink',
            'filename': 'kindredsaratoga_drink_menu.pdf'
        }
    ]
    
    for idx, pdf_info in enumerate(pdfs, 1):
        print(f"\n[{idx}/{len(pdfs)}] Scraping {pdf_info['name']} (PDF)...")
        
        pdf_path = temp_dir / pdf_info['filename']
        
        if download_pdf_with_requests(pdf_info['url'], pdf_path):
            # Use font-based extraction (handles 2-column layout and font information)
            items = extract_menu_from_pdf_with_fonts(str(pdf_path), menu_type_default=pdf_info['type'])
            
            # Fallback to improved extraction if font-based didn't work
            if not items:
                print("  Font-based extraction returned no items, trying improved extraction...")
                items = extract_menu_from_pdf_improved(str(pdf_path), menu_type_default=pdf_info['type'])
            
            for item in items:
                item['restaurant_name'] = "Kindred"
                item['restaurant_url'] = "https://kindredsaratoga.com/"
                item['menu_name'] = pdf_info['name']
            
            all_items.extend(items)
            print(f"[OK] Extracted {len(items)} items from {pdf_info['name']}")
            
            # Keep PDFs for inspection - don't delete yet
            print(f"  PDF saved at: {pdf_path}")
        else:
            print(f"[ERROR] Failed to download {pdf_info['name']} PDF")
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    
    url_safe = "kindredsaratoga_com"
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


def test_font_extraction(pdf_filename: str = None):
    """
    Test function to extract and display font information from PDFs.
    """
    temp_dir = Path(__file__).parent.parent / 'temp'
    temp_dir.mkdir(exist_ok=True)
    
    if pdf_filename:
        pdf_path = temp_dir / pdf_filename
        if not pdf_path.exists():
            print(f"PDF not found: {pdf_path}")
            return
        print(f"Extracting font info from: {pdf_filename}")
        font_data = extract_font_info_from_pdf(str(pdf_path))
        
        # Save to JSON for inspection
        output_file = temp_dir / f"{pdf_filename}_font_info.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(font_data, f, indent=2, ensure_ascii=False)
        print(f"\nFont data saved to: {output_file}")
    else:
        # Test all PDFs
        pdfs = [
            'kindredsaratoga_food_menu.pdf',
            'kindredsaratoga_brunch_menu.pdf',
            'kindredsaratoga_drink_menu.pdf'
        ]
        
        for pdf_file in pdfs:
            pdf_path = temp_dir / pdf_file
            if pdf_path.exists():
                print(f"\n{'='*60}")
                print(f"Testing: {pdf_file}")
                print('='*60)
                font_data = extract_font_info_from_pdf(str(pdf_path))
                
                # Save to JSON
                output_file = temp_dir / f"{pdf_file}_font_info.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(font_data, f, indent=2, ensure_ascii=False)
                print(f"Font data saved to: {output_file}")
            else:
                print(f"PDF not found: {pdf_path}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test-fonts':
        # Test font extraction
        pdf_file = sys.argv[2] if len(sys.argv) > 2 else None
        test_font_extraction(pdf_file)
    else:
        # Normal scraping
        scrape_kindredsaratoga_menu()

