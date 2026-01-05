"""
Scraper for Sushi Thai Garden Saratoga (sushithaigardensaratoga.com)
Scrapes menu from online ordering system
Fetches detailed item information including descriptions and add-ons via API calls
"""

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pathlib import Path
import time


def get_headers() -> Dict[str, str]:
    """Get headers for API requests"""
    return {
        "accept": "text/html, */*; q=0.01",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://order.sushithaigardensaratoga.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest"
    }


def get_cookies() -> Dict[str, str]:
    """Get cookies for API requests"""
    return {
        "SushithaigardensaratogaProd": "hv36i0l9kb35jdlt55j05cme8f"
    }


def fetch_menu_html() -> Optional[str]:
    """Download menu HTML from online ordering system"""
    url = "https://order.sushithaigardensaratoga.com/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://www.sushithaigardensaratoga.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-site",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    cookies = get_cookies()
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download menu HTML: {e}")
        return None


def fetch_item_details(item_id: str, save_data: bool = True) -> Optional[str]:
    """Fetch detailed item information via API call and optionally save it"""
    url = f"https://order.sushithaigardensaratoga.com/menu/65590/{item_id}"
    headers = get_headers()
    cookies = get_cookies()
    
    # Check if we already have cached data
    cache_dir = Path(__file__).parent.parent / "temp" / "sushithai_items"
    if save_data:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{item_id}.html"
        if cache_file.exists():
            print(f"    [CACHE] Using cached data for item {item_id}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        html_content = response.text
        
        # Save the HTML data
        if save_data:
            cache_file = cache_dir / f"{item_id}.html"
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Also save parsed JSON data
            parsed_data = parse_item_details(html_content, item_id)
            json_file = cache_dir / f"{item_id}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(parsed_data, f, indent=2, ensure_ascii=False)
        
        return html_content
    except Exception as e:
        print(f"    [WARNING] Failed to fetch details for item {item_id}: {e}")
        return None


def parse_item_details(detail_html: str, item_id: str) -> Dict[str, any]:
    """Parse detailed item information from modal HTML"""
    soup = BeautifulSoup(detail_html, 'html.parser')
    
    result = {
        "description": None,
        "addons": []
    }
    
    # Extract description from modal-header (it's in the header, not body)
    modal_header = soup.find('div', class_='modal-header')
    if modal_header:
        # Look for description in text-gray-light div with class m-t-5 m-b-10
        desc_divs = modal_header.find_all('div', class_='text-gray-light')
        for desc_div in desc_divs:
            text = desc_div.get_text(strip=True)
            if text and len(text) > 20:  # Likely a description, not just spacing
                result["description"] = text
                break
    
    # Extract add-ons from options-block
    options_blocks = soup.find_all('div', class_='options-block')
    for block in options_blocks:
        # Check if this is an add-ons block (look for "You May Want to..." or similar)
        h4 = block.find('h4')
        if h4 and ('want' in h4.get_text().lower() or 'add' in h4.get_text().lower()):
            # Find all checkboxes with add-on information
            checkboxes = block.find_all('input', type='checkbox')
            for checkbox in checkboxes:
                # The checkbox is inside a label, so find the parent label
                label = checkbox.find_parent('label')
                if not label:
                    # Fallback: try find_next
                    label = checkbox.find_next('label')
                
                if label:
                    # Get the span containing add-on text
                    span = label.find('span')
                    if span:
                        # The structure is: <span>add Name <span class="text-muted">(+$X.XX)</span></span>
                        # Extract price from data-incprice attribute (most reliable)
                        inc_price = checkbox.get('data-incprice', '')
                        if inc_price:
                            price_text = f"+${inc_price}"
                        else:
                            # Fallback: try to extract from text
                            addon_full_text = span.get_text(strip=True)
                            price_match = re.search(r'\(\+\$([\d.]+)\)', addon_full_text)
                            if price_match:
                                price_text = f"+${price_match.group(1)}"
                            else:
                                price_text = ""
                        
                        # Clean up addon name - remove the price part
                        # The text-muted span contains the price, so we need to get text before it
                        text_muted_span = span.find('span', class_='text-muted')
                        if text_muted_span:
                            # Get all text, then remove the text-muted span's text
                            full_text = span.get_text()
                            muted_text = text_muted_span.get_text()
                            addon_name = full_text.replace(muted_text, '').strip()
                        else:
                            # No nested span, just remove price pattern if present
                            addon_full_text = span.get_text(strip=True)
                            addon_name = re.sub(r'\s*\(\+\$[\d.]+\)\s*', '', addon_full_text).strip()
                        
                        if addon_name:
                            result["addons"].append({
                                "name": addon_name,
                                "price": price_text
                            })
    
    return result


def format_price(price_text: str) -> str:
    """Format price text to handle multiple prices"""
    if not price_text:
        return ""
    
    price_text = price_text.strip()
    
    # Check if there are multiple prices (separated by /, |, or comma)
    if '/' in price_text or '|' in price_text or ',' in price_text:
        # Split by common separators
        parts = re.split(r'[/|,]', price_text)
        formatted_parts = []
        for part in parts:
            part = part.strip()
            # Extract price with $ symbol
            price_match = re.search(r'\$?([\d.]+)', part)
            if price_match:
                price_val = price_match.group(1)
                # Check if there's a size label before the price
                size_match = re.search(r'^([A-Za-z\s]+?)\s+\$?[\d.]+', part)
                if size_match:
                    size_label = size_match.group(1).strip()
                    formatted_parts.append(f"{size_label} ${price_val}")
                else:
                    formatted_parts.append(f"${price_val}")
        
        if formatted_parts:
            return " | ".join(formatted_parts)
    
    # Single price - ensure $ symbol
    price_match = re.search(r'\$?([\d.]+)', price_text)
    if price_match:
        return f"${price_match.group(1)}"
    
    return price_text


def parse_menu_items(soup: BeautifulSoup, fetch_details: bool = True) -> List[Dict]:
    """Parse menu items from HTML and optionally fetch detailed information"""
    items = []
    
    # Find all menu sections
    sections = soup.find_all('div', class_='menu-section')
    
    total_items = 0
    for section in sections:
        menu_items = section.find_all('a', class_='menu-item')
        total_items += len(menu_items)
    
    print(f"    Found {total_items} items, fetching details..." if fetch_details else f"    Found {total_items} items")
    
    item_count = 0
    for section in sections:
        # Get section name
        section_header = section.find('div', class_='menu-section-header')
        if section_header:
            h2 = section_header.find('h2')
            if h2:
                # Remove count and arrow elements
                for span in h2.find_all('span'):
                    span.decompose()
                section_name = h2.get_text(strip=True)
            else:
                section_name = section.get('data-category-name', 'Unknown')
        else:
            section_name = section.get('data-category-name', 'Unknown')
        
        if not section_name or section_name == 'Unknown':
            continue
        
        # Get section description if available
        section_desc = section.find('div', class_='menu-section-desc')
        section_description = section_desc.get_text(strip=True) if section_desc else None
        
        # Find all menu items in this section
        menu_items = section.find_all('a', class_='menu-item')
        
        for item_link in menu_items:
            item_count += 1
            
            # Get item name
            menu_desc = item_link.find('div', class_='menu-desc')
            if not menu_desc:
                continue
            
            h4 = menu_desc.find('h4')
            if not h4:
                continue
            
            item_name = h4.get_text(strip=True)
            
            # Get price
            price_elem = menu_desc.find('h5', class_='item-price')
            price = ""
            if price_elem:
                price_span = price_elem.find('span', class_='price')
                if price_span:
                    price = price_span.get_text(strip=True)
                else:
                    # Sometimes price is directly in h5
                    price = price_elem.get_text(strip=True)
            
            # Get description from main page
            description = ""
            desc_elem = menu_desc.find('p', class_=lambda x: x and 'description' in str(x).lower())
            if desc_elem:
                description = desc_elem.get_text(strip=True)
            
            # Get data-id for fetching detailed information
            item_id = item_link.get('data-id')
            
            # Fetch detailed information if requested
            detailed_description = description
            addons_list = []
            
            if fetch_details and item_id:
                # Show progress every 5 items
                if item_count % 5 == 0 or item_count == 1:
                    print(f"    Processing item {item_count}/{total_items} (ID: {item_id})...")
                
                try:
                    detail_html = fetch_item_details(item_id, save_data=True)
                    if detail_html:
                        details = parse_item_details(detail_html, item_id)
                        if details["description"]:
                            detailed_description = details["description"]
                        if details["addons"]:
                            addons_list = details["addons"]
                    
                    # Small delay to avoid overwhelming the server (only if not cached)
                    cache_file = Path(__file__).parent.parent / "temp" / "sushithai_items" / f"{item_id}.html"
                    if not cache_file.exists():
                        time.sleep(0.1)
                except Exception as e:
                    print(f"    [ERROR] Failed to process item {item_id}: {e}")
                    # Continue with basic info if detailed fetch fails
            
            # Format price
            formatted_price = format_price(price) if price else ""
            
            # Combine section description with item description if available
            full_description = detailed_description
            if section_description and section_description not in (detailed_description or ""):
                if full_description:
                    full_description = f"{section_description}. {full_description}"
                else:
                    full_description = section_description
            
            # Add add-ons to description
            if addons_list:
                addons_text = " / ".join([f"{addon['name']} {addon['price']}" for addon in addons_list])
                if full_description:
                    full_description = f"{full_description}. Add-ons: {addons_text}"
                else:
                    full_description = f"Add-ons: {addons_text}"
            
            # Skip if no price and no description
            if not formatted_price and not full_description:
                continue
            
            items.append({
                "name": item_name,
                "description": full_description if full_description else None,
                "price": formatted_price,
                "section": section_name,
                "restaurant_name": "Sushi Thai Garden",
                "restaurant_url": "https://www.sushithaigardensaratoga.com/",
                "menu_type": "Online Order",
                "menu_name": "Online Order Menu"
            })
    
    return items


def scrape_sushithaigarden() -> List[Dict]:
    """Main scraping function for Sushi Thai Garden"""
    print("=" * 60)
    print("Scraping Sushi Thai Garden (sushithaigardensaratoga.com)")
    print("=" * 60)
    
    print("\n[1] Downloading menu HTML...")
    html_content = fetch_menu_html()
    
    if not html_content:
        print("[ERROR] Failed to download menu HTML")
        return []
    
    print(f"[OK] Downloaded {len(html_content)} characters")
    
    print("\n[2] Parsing menu items...")
    soup = BeautifulSoup(html_content, 'html.parser')
    items = parse_menu_items(soup)
    
    print(f"[OK] Extracted {len(items)} items")
    
    return items


if __name__ == "__main__":
    items = scrape_sushithaigarden()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "sushithaigardensaratoga_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

