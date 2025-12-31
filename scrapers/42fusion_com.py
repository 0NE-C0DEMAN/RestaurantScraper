import json
import sys
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup

# Add parent directory to path to import modules
sys.path.append(str(Path(__file__).parent.parent))

def scrape_42fusion_menu(url: str) -> List[Dict]:
    """Scrape menu items from 42fusion.com"""
    all_items = []
    restaurant_name = "42 Fusion"
    
    print(f"Scraping: {url}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    # Common headers
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    # Pages to scrape
    pages = [
        {
            "url": "https://42fusion.com/happy-hour-menu",
            "menu_type": "Happy Hour Menu",
            "referer": "https://42fusion.com/catering",
            "cookies": "dps_site_id=ap-south-1; _tccl_visitor=6679e439-e1ce-4e2f-996f-184d75a4edeb; _tccl_visit=6679e439-e1ce-4e2f-996f-184d75a4edeb; _scc_session=pc=9&C_TOUCH=2025-12-31T11:53:36.373Z"
        },
        {
            "url": "https://42fusion.com/happy-hour-drinks",
            "menu_type": "Happy Hour Drinks",
            "referer": "https://42fusion.com/happy-hour-menu",
            "cookies": "dps_site_id=ap-south-1; _tccl_visitor=6679e439-e1ce-4e2f-996f-184d75a4edeb; _tccl_visit=6679e439-e1ce-4e2f-996f-184d75a4edeb; _scc_session=pc=10&C_TOUCH=2025-12-31T11:53:41.687Z"
        },
        {
            "url": "https://42fusion.com/menu",
            "menu_type": "Menu",
            "referer": "https://42fusion.com/happy-hour-drinks",
            "cookies": "dps_site_id=ap-south-1; _tccl_visitor=6679e439-e1ce-4e2f-996f-184d75a4edeb; _tccl_visit=6679e439-e1ce-4e2f-996f-184d75a4edeb; _scc_session=pc=11&C_TOUCH=2025-12-31T11:54:55.818Z"
        },
        {
            "url": "https://42fusion.com/catering",
            "menu_type": "Catering",
            "referer": "https://42fusion.com/menu",
            "cookies": "dps_site_id=ap-south-1; _tccl_visitor=6679e439-e1ce-4e2f-996f-184d75a4edeb; _tccl_visit=6679e439-e1ce-4e2f-996f-184d75a4edeb; _scc_session=pc=12&C_TOUCH=2025-12-31T11:55:14.488Z"
        }
    ]
    
    for i, page_info in enumerate(pages, 1):
        page_url = page_info["url"]
        menu_type = page_info["menu_type"]
        referer = page_info["referer"]
        cookies_str = page_info["cookies"]
        
        print(f"[{i}/{len(pages)}] Processing: {menu_type}")
        print(f"  URL: {page_url}")
        
        try:
            # Parse cookies
            cookies = {}
            for cookie in cookies_str.split('; '):
                if '=' in cookie:
                    key, value = cookie.split('=', 1)
                    cookies[key.strip()] = value.strip()
            
            # Add referer to headers
            page_headers = headers.copy()
            page_headers["Referer"] = referer
            
            # Fetch the page
            response = requests.get(page_url, headers=page_headers, cookies=cookies, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract items from this page
            items = extract_items_from_page(soup, menu_type)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = url
                    item['menu_type'] = menu_type
                all_items.extend(items)
                print(f"  [OK] Extracted {len(items)} items from {menu_type}\n")
            else:
                print(f"  [WARNING] No items extracted from {menu_type}\n")
                
        except Exception as e:
            print(f"  [ERROR] Error processing {menu_type}: {e}\n")
            continue
    
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

def extract_items_from_page(soup: BeautifulSoup, menu_type: str) -> List[Dict]:
    """Extracts menu items from a page using BeautifulSoup."""
    items = []
    
    # Handle special cases first
    
    # Draft beers in Happy Hour Drinks
    if menu_type == "Happy Hour Drinks":
        # Find "DRAFTS BEERS" heading
        drafts_heading = soup.find('h4', string=re.compile(r'DRAFTS?\s+BEERS?', re.IGNORECASE))
        if drafts_heading:
            # Find price near the heading
            price = ""
            price_elem = drafts_heading.find_next(['div', 'span', 'generic'])
            if price_elem:
                price_text = price_elem.get_text().strip()
                if re.match(r'^\d+$', price_text):
                    price = f"${price_text}"
            
            # Find the list of beers
            ul = drafts_heading.find_next('ul')
            if ul:
                list_items = ul.find_all('li')  # pyright: ignore[reportAttributeAccessIssue]
                for li in list_items:
                    beer_name = li.get_text().strip()
                    if beer_name:
                        items.append({
                            'name': beer_name.upper(),
                            'description': "",
                            'price': price
                        })
    
    # Sides in Catering menu
    if menu_type == "Catering":
        sides_heading = soup.find('h4', string=re.compile(r'^SIDES$', re.IGNORECASE))
        if sides_heading:
            ul = sides_heading.find_next('ul')
            if ul:
                list_items = ul.find_all('li')  # pyright: ignore[reportAttributeAccessIssue]
                for li in list_items:
                    side_text = li.get_text().strip()
                    # Extract name and price (e.g., "Roasted Potatoes 25/40")
                    side_match = re.match(r'^(.+?)\s+(\d+\/\d+)$', side_text)
                    if side_match:
                        side_name = side_match.group(1).strip()
                        side_price = format_price(side_match.group(2), menu_type)
                        items.append({
                            'name': side_name.upper(),
                            'description': "",
                            'price': side_price
                        })
    
    # Kids menu items
    kids_heading = soup.find('h3', string=re.compile(r'KIDS?\s+MENU', re.IGNORECASE))
    if kids_heading:
        ul = kids_heading.find_next('ul')
        if ul:
            list_items = ul.find_all('li')  # pyright: ignore[reportAttributeAccessIssue]
            for li in list_items:
                item_text = li.get_text().strip()
                # Extract name and price (e.g., "Cheese Ravioli 10")
                item_match = re.match(r'^(.+?)\s+(\d+)$', item_text)
                if item_match:
                    item_name = item_match.group(1).strip()
                    item_price = f"${item_match.group(2).strip()}"
                    items.append({
                        'name': item_name.upper(),
                        'description': "",
                        'price': item_price
                    })
    
    # Regular menu items - find all h4 headings (item names)
    item_headings = soup.find_all('h4')
    
    for heading in item_headings:
        try:
            name = heading.get_text().strip()
            if not name or len(name) < 2:
                continue
            
            # Skip section headings
            skip_names = ['SERVED WITH', 'CHOICE OF MEAT', 'CHOICES OF MEAT', 'SIDES', 'DRAFTS BEERS', 'DRAFTS BEER']
            if name.upper() in skip_names:
                continue
            
            # Find the parent container
            parent = heading.parent
            if not parent:
                continue
            
            price = ""
            description = ""
            
            # Look for price in generic/div/span elements within the parent
            # The price is usually in a generic element right after the heading
            for elem in parent.find_all(['div', 'span', 'generic'], recursive=False):
                text = elem.get_text().strip()
                # Check if this is a price (numbers, MP, or slash-separated)
                if re.match(r'^(\d+(?:\/\d+)?|\d+\s*l\s*\d+|MP|\d+)$', text):
                    price = format_price(text, menu_type)
                    break
            
            # If not found, check siblings
            if not price:
                current = heading.next_sibling
                while current:
                    if hasattr(current, 'get_text'):
                        text = current.get_text().strip()
                        if re.match(r'^(\d+(?:\/\d+)?|\d+\s*l\s*\d+|MP|\d+)$', text):
                            price = format_price(text, menu_type)
                            break
                    current = current.next_sibling if hasattr(current, 'next_sibling') else None
            
            # Get description from paragraph - look in parent container and siblings
            # The description is usually in a <p> tag within the same container as the heading
            desc_elem = None
            
            # First, try to find paragraph in the parent container
            if parent:
                # Look for paragraph in the parent
                desc_elem = parent.find('p')
                
                # If not found, look in the parent's parent (sometimes items are nested)
                if not desc_elem and parent.parent:
                    desc_elem = parent.parent.find('p')
            
            # If still not found, look for paragraph after the heading in siblings
            if not desc_elem:
                current = heading
                for _ in range(5):  # Limit search to avoid going too far
                    current = current.next_sibling if hasattr(current, 'next_sibling') else None
                    if not current:
                        break
                    if hasattr(current, 'name'):
                        if current.name == 'p':
                            desc_elem = current
                            break
                        elif hasattr(current, 'find'):
                            desc_elem = current.find('p')
                            if desc_elem:
                                break
            
            # If still not found, try finding next paragraph element
            if not desc_elem:
                desc_elem = heading.find_next('p')
            
            if desc_elem:
                description = desc_elem.get_text().strip()
                # Clean up description - remove any price info that might have leaked in
                description = re.sub(r'\$\d+.*$', '', description).strip()
            
            # Skip if no price found
            if not price:
                continue
            
            # Clean up name - remove price if it's in the name
            # Handle cases like "HOUSE SALAD Small 10 l Large 14"
            name = re.sub(r'\s+Small\s+\d+\s*l\s*Large\s+\d+.*$', '', name, flags=re.IGNORECASE).strip()
            name = re.sub(r'\s+\d+(?:\/\d+)?\s*$', '', name).strip()
            name = re.sub(r'\s+\d+\s*l\s*\d+.*$', '', name).strip()
            
            items.append({
                'name': name.upper(),
                'description': description,
                'price': price
            })
            
        except Exception as e:
            print(f"    Error extracting item: {e}")
            continue
    
    return items

def format_price(price_text: str, menu_type: str) -> str:
    """Formats price text based on menu type and format."""
    price_text = price_text.strip()
    
    # Market price
    if price_text.upper() == 'MP':
        return "MP"
    
    # Catering format: "35/60" -> "$35 (half tray) | $60 (full tray)"
    if '/' in price_text and menu_type == "Catering":
        parts = price_text.split('/')
        if len(parts) == 2:
            return f"${parts[0].strip()} (half tray) | ${parts[1].strip()} (full tray)"
    
    # Dual price format: "10 l 14" -> "$10 (small) | $14 (large)"
    if 'l' in price_text.lower():
        parts = re.split(r'\s*l\s*', price_text, flags=re.IGNORECASE)
        if len(parts) == 2:
            return f"${parts[0].strip()} (small) | ${parts[1].strip()} (large)"
    
    # Single price: just add dollar sign
    if re.match(r'^\d+$', price_text):
        return f"${price_text}"
    
    # If it's already formatted or has slash but not catering, return as is
    return price_text

def main():
    url = "https://42fusion.com/"
    scrape_42fusion_menu(url)

if __name__ == '__main__':
    main()

