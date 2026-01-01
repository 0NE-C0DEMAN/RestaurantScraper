"""
Scraper for: https://www.henrystreettaproom.com/
The menu is displayed as HTML pages for Drink Menu and Food Menu
"""

import json
import re
import time
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup


def download_html_with_requests(url: str, headers: dict = None) -> str:
    """Download HTML from URL using requests"""
    if headers is None:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.henrystreettaproom.com/',
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
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  [ERROR] Failed to download HTML: {e}")
        return ""


def extract_drink_menu_items(html: str) -> List[Dict]:
    """Extract menu items from drink menu HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find all h2 tags (section headers)
    all_elements = soup.find_all(['h2', 'p'])
    current_section = None
    
    for elem in all_elements:
        if elem.name == 'h2':
            section_text = elem.get_text(strip=True)
            # Skip long descriptive text (not section headers)
            if len(section_text) < 50 and not any(skip in section_text.lower() for skip in ['ever-changing', 'we\'re more than']):
                current_section = section_text
            continue
        
        if elem.name == 'p':
            strong_tag = elem.find('strong')
            if not strong_tag:
                continue
            
            # Get full text
            full_text = elem.get_text(strip=True)
            name_text = strong_tag.get_text(strip=True)
            
            # Extract price (usually at the end like "/ 9" or "/ $9")
            price_match = re.search(r'/\s*\$?(\d+(?:\.\d+)?)\s*$', full_text)
            if price_match:
                price = f"${price_match.group(1)}"
                # Remove price from text
                text_without_price = re.sub(r'/\s*\$?\d+(?:\.\d+)?\s*$', '', full_text).strip()
            else:
                price = ""
                text_without_price = full_text
            
            # For beers: format is "NameLocation • ABV • Size"
            # The name in strong tag might be concatenated with location
            # Try to split: look for pattern where location starts (capital letter after lowercase)
            # Example: "Industrial Arts WrenchGarnerville" -> "Industrial Arts Wrench" + "Garnerville"
            name_match = re.match(r'^(.+?)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})', name_text)
            if name_match:
                name = name_match.group(1).strip()
                location = name_match.group(2)
                # Get description (everything after name_text in full text)
                remaining = text_without_price.replace(name_text, '', 1).strip()
                if remaining:
                    description = f"{location} {remaining}"
                else:
                    description = location
            else:
                # Name doesn't have concatenated location, use as is
                name = name_text
                description = text_without_price.replace(name, '', 1).strip()
            
            if name and current_section:
                items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'menu_type': current_section,
                    'menu_name': 'Drink Menu'
                })
    
    return items


def extract_food_menu_items(html: str) -> List[Dict]:
    """Extract menu items from food menu HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Find all elements (h2, h3, h4, p)
    all_elements = soup.find_all(['h2', 'h3', 'h4', 'p'])
    current_section = None
    
    for elem in all_elements:
        if elem.name in ['h2', 'h3']:
            section_text = elem.get_text(strip=True)
            # Skip long descriptive text
            if len(section_text) < 50 and not any(skip in section_text.lower() for skip in ['everything is made', 'all cheese is served']):
                current_section = section_text
            continue
        
        # For cheese and charcuterie, h4 tags are item names
        if elem.name == 'h4' and current_section:
            name = elem.get_text(strip=True)
            # Get description from next paragraph
            next_p = elem.find_next_sibling('p')
            description = ""
            price = ""
            
            if next_p:
                p_text = next_p.get_text(strip=True)
                # Extract price from description (usually at the end like "/ 10" or "/ $10")
                price_match = re.search(r'/\s*\$?(\d+(?:\.\d+)?)\s*$', p_text)
                if price_match:
                    price = f"${price_match.group(1)}"
                    description = re.sub(r'/\s*\$?\d+(?:\.\d+)?\s*$', '', p_text).strip()
                else:
                    description = p_text
            
            if name:
                items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'menu_type': current_section,
                    'menu_name': 'Food Menu'
                })
        
        # Regular food items in paragraphs with strong tags
        if elem.name == 'p':
            strong_tag = elem.find('strong')
            if not strong_tag:
                continue
            
            p_text = elem.get_text(strip=True)
            name_with_price = strong_tag.get_text(strip=True)
            
            # Check for multiple prices (format: "NAME – 10/18" or "NAME - 10/18")
            multi_price_match = re.match(r'^(.+?)\s*[–-]\s*\$?(\d+(?:\.\d+)?)\s*/\s*\$?(\d+(?:\.\d+)?)\s*$', name_with_price)
            if multi_price_match:
                name = multi_price_match.group(1).strip()
                price_small = f"${multi_price_match.group(2)}"
                price_large = f"${multi_price_match.group(3)}"
                price = f"{price_small}/{price_large}"
                # Add size info to description
                size_info = f"Small: {price_small} | Large: {price_large}"
            else:
                # Extract name and single price (format: "NAME – 16" or "NAME -16")
                name_price_match = re.match(r'^(.+?)\s*[–-]\s*\$?(\d+(?:\.\d+)?)\s*$', name_with_price)
                if name_price_match:
                    name = name_price_match.group(1).strip()
                    price = f"${name_price_match.group(2)}"
                    size_info = None
                else:
                    name = name_with_price
                    price = ""
                    size_info = None
            
            # Get description from the rest of the paragraph
            # Remove the name and price from the description
            if multi_price_match or name_price_match:
                # Remove the entire strong tag content (name + price)
                description = p_text.replace(name_with_price, '', 1).strip()
            else:
                description = p_text.replace(strong_tag.get_text(), '', 1).strip()
            
            # Check for multiple prices in description (format: "/ 16/28")
            desc_multi_price = re.search(r'/\s*\$?(\d+(?:\.\d+)?)\s*/\s*\$?(\d+(?:\.\d+)?)\s*$', description)
            if desc_multi_price and not multi_price_match:
                price_small = f"${desc_multi_price.group(1)}"
                price_large = f"${desc_multi_price.group(2)}"
                price = f"{price_small}/{price_large}"
                size_info = f"Small: {price_small} | Large: {price_large}"
                # Remove price from description
                description = re.sub(r'/\s*\$?\d+(?:\.\d+)?\s*/\s*\$?\d+(?:\.\d+)?\s*$', '', description).strip()
                # Remove duplicate name if it appears at the start of description
                description = re.sub(r'^' + re.escape(name) + r'\s*', '', description, flags=re.IGNORECASE).strip()
            
            # Extract add-ons from description (format: "(add item – 5)")
            addons = re.findall(r'\(add\s+([^)]+?)\s*[–-]\s*\$?(\d+(?:\.\d+)?)\)', description, re.IGNORECASE)
            if addons:
                addon_text = " | ".join([f"Add {addon[0].strip()}: ${addon[1]}" for addon in addons])
                # Remove add-ons from description
                description = re.sub(r'\(add\s+[^)]+?\)', '', description, flags=re.IGNORECASE).strip()
                description = re.sub(r'\s+', ' ', description)  # Clean up extra spaces
                if description:
                    description = f"{description} | {addon_text}"
                else:
                    description = addon_text
            
            # Add size info to description if we have multiple prices
            if size_info:
                if description:
                    description = f"{description} | {size_info}"
                else:
                    description = size_info
            
            if name and current_section:
                items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'menu_type': current_section,
                    'menu_name': 'Food Menu'
                })
    
    return items


def scrape_henrystreettaproom_menu(url: str) -> List[Dict]:
    """
    Scrape menus from henrystreettaproom.com
    The menu is displayed as HTML pages for Drink Menu and Food Menu
    """
    all_items = []
    restaurant_name = "Henry Street Taproom"
    restaurant_url = "https://www.henrystreettaproom.com/"
    
    print("=" * 60)
    print(f"Scraping: {url}")
    print("=" * 60)
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output filename
    url_safe = url.replace('https://', '').replace('http://', '').replace('www.', '').replace('/', '_').replace('.', '_').rstrip('_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    # Define the two menu URLs
    menu_urls = [
        {
            'url': 'https://www.henrystreettaproom.com/drink-menu/',
            'name': 'Drink Menu',
            'headers': {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
                'cache-control': 'no-cache',
                'pragma': 'no-cache',
                'referer': 'https://www.henrystreettaproom.com/',
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
        },
        {
            'url': 'https://www.henrystreettaproom.com/food-menu/',
            'name': 'Food Menu',
            'headers': {
                'Referer': 'https://www.henrystreettaproom.com/',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
        }
    ]
    
    try:
        # Download and process each menu
        for menu_idx, menu_info in enumerate(menu_urls):
            menu_url = menu_info['url']
            menu_name = menu_info['name']
            headers = menu_info['headers']
            
            print(f"[{menu_idx + 1}/{len(menu_urls)}] Processing {menu_name}...")
            print(f"  Downloading HTML from: {menu_url}")
            
            html = download_html_with_requests(menu_url, headers)
            
            if not html:
                print(f"[ERROR] Failed to download {menu_name}")
                continue
            
            print(f"[OK] {menu_name} HTML downloaded\n")
            
            # Extract menu items
            print(f"Extracting menu items from {menu_name}...")
            if menu_name == 'Drink Menu':
                items = extract_drink_menu_items(html)
            else:
                items = extract_food_menu_items(html)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = restaurant_url
                all_items.extend(items)
                print(f"[OK] Extracted {len(items)} items from {menu_name}\n")
            else:
                print(f"[WARNING] No items extracted from {menu_name}\n")
            
            # Add delay between menus
            if menu_idx < len(menu_urls) - 1:
                time.sleep(2)
        
        # Deduplicate items
        unique_items = []
        seen = set()
        for item in all_items:
            item_tuple = (item['name'], item['description'], item['price'], item['menu_type'], item.get('menu_name', ''))
            if item_tuple not in seen:
                unique_items.append(item)
                seen.add(item_tuple)
        
        print(f"[OK] Extracted {len(unique_items)} unique items from all menus\n")
        
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        unique_items = []
    
    # Save to JSON
    print(f"[3/3] Saving results...")
    if unique_items:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(unique_items, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved {len(unique_items)} unique items to: {output_json}")
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(unique_items)}")
    print(f"Saved to: {output_json}")
    print(f"{'='*60}")
    
    return unique_items


if __name__ == '__main__':
    url = "https://www.henrystreettaproom.com/"
    scrape_henrystreettaproom_menu(url)

