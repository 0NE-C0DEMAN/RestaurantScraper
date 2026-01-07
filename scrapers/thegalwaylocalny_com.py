"""
Scraper for The Galway Local (thegalwaylocalny.com)
Scrapes menu from multiple HTML pages
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

# Restaurant configuration
RESTAURANT_NAME = "The Galway Local"
RESTAURANT_URL = "https://www.thegalwaylocalny.com/"

# Menu URLs
MENU_URLS = [
    {
        'url': 'https://www.thegalwaylocalny.com/breakfast-menu',
        'name': 'Breakfast Menu'
    },
    {
        'url': 'https://www.thegalwaylocalny.com/drink-menu',
        'name': 'Drink Menu'
    },
    {
        'url': 'https://www.thegalwaylocalny.com/lunch-menu',
        'name': 'Lunch Menu'
    },
    {
        'url': 'https://www.thegalwaylocalny.com/dessert-menu',
        'name': 'Dessert Menu'
    }
]

# Cookies from the curl commands
COOKIES = {
    'crumb': 'BREWkzYvVQToNzdmODExNTc1MTVhMWU2ZTQ5MzEzNTY2YzJjNTdh',
    '_ga': 'GA1.1.196110217.1767799579',
    'ss_cvr': '2e74bf25-8e36-4815-852d-5d96a65bfd91|1767799579783|1767799579783|1767799579783|1',
    'ss_cvt': '1767799579783',
    '_ga_N38ZCS0N3B': 'GS2.1.s1767799579$o1$g1$t1767799649$j59$l0$h0'
}

HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://www.thegalwaylocalny.com/',
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


def fetch_menu_html(url: str) -> Optional[str]:
    """Fetch HTML content from a menu URL"""
    try:
        print(f"[INFO] Fetching {url}...")
        response = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None


def extract_items_from_html(html: str, menu_name: str) -> List[Dict]:
    """Extract menu items from HTML"""
    items = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all sqs-block-content divs
    block_contents = soup.find_all('div', class_='sqs-block-content')
    
    current_section = menu_name
    section_price = None  # Store price from section header if available
    
    for block in block_contents:
        # Look for sqs-html-content inside
        html_content = block.find('div', class_='sqs-html-content')
        if not html_content:
            continue
        
        # Check if this is a section header (h3 or h2)
        section_header = html_content.find(['h2', 'h3'])
        if section_header:
            section_text = section_header.get_text(strip=True)
            if section_text and section_text.lower() not in ['menu', '']:
                # Check if section header contains a price (e.g., "Sandwiches | $9")
                if '|' in section_text:
                    parts = section_text.split('|')
                    if len(parts) >= 2:
                        section_name = parts[0].strip()
                        section_price_text = parts[1].strip()
                        current_section = section_name
                        # Store section price for items without individual prices
                        # Format the price
                        if section_price_text:
                            if not section_price_text.startswith('$'):
                                price_match = re.search(r'(\d+(?:\.\d{2})?)', section_price_text)
                                if price_match:
                                    section_price = f"${price_match.group(1)}"
                                else:
                                    section_price = section_price_text
                            else:
                                section_price = section_price_text
                    else:
                        current_section = section_text
                        section_price = None
                else:
                    current_section = section_text
                    section_price = None
            continue
        
        # Look for menu items - they have sqsrte-large class for name/price
        name_price_ps = html_content.find_all('p', class_='sqsrte-large')
        
        for name_price_p in name_price_ps:
            # Get the text which contains name and possibly price
            name_price_text = name_price_p.get_text(strip=True)
            if not name_price_text:
                continue
            
            # Check if price is in the same line (has | separator)
            name = ""
            price_text = ""
            
            if '|' in name_price_text:
                # Split name and price
                parts = name_price_text.split('|')
                if len(parts) >= 2:
                    name = parts[0].strip()
                    price_text = parts[1].strip()
            else:
                # Price might be in a separate <p> tag
                name = name_price_text.strip()
            
            # Clean up name (remove extra formatting)
            name = re.sub(r'\s+', ' ', name).strip()
            
            if not name:
                continue
            
            # Get description from the next <p> tag(s)
            description = ""
            next_p = name_price_p.find_next_sibling('p')
            
            # Look for price in following <p> tags if not found in name line
            if not price_text and next_p:
                # Check if next <p> contains only a price
                next_text = next_p.get_text(strip=True)
                # Check if it looks like a price (starts with $ or contains $ and numbers)
                if re.match(r'^\$?\d+(?:\s*\|\s*\$\d+)?', next_text):
                    price_text = next_text
                    # Get description from the <p> before the price (which should be the description)
                    # Actually, description comes before price in this case
                    # So we need to check the previous sibling or the current next_p
                    # Wait, let me re-read the structure: name -> description -> price
                    # So if next_p is the price, then the description should be... hmm
                    # Actually looking at the HTML: name (sqsrte-large) -> description -> price
                    # So if we found price in next_p, description should be... wait, that doesn't make sense
                    # Let me check the actual structure again
                    # Actually, I think the structure is: name -> description -> price
                    # So if next_p is price, we need to go back or check differently
                    # For now, let's just get the description from before the price
                    prev_p = name_price_p.find_next_sibling('p')
                    if prev_p and prev_p != next_p:
                        prev_text = prev_p.get_text(strip=True)
                        if not re.match(r'^\$?\d+(?:\s*\|\s*\$\d+)?', prev_text):
                            description = prev_text
                else:
                    # Next <p> is description, check if there's a price after it
                    description = next_text
                    price_p = next_p.find_next_sibling('p')
                    if price_p:
                        price_text_check = price_p.get_text(strip=True)
                        if re.match(r'^\$?\d+(?:\s*\|\s*\$\d+)?', price_text_check):
                            price_text = price_text_check
            elif next_p and 'sqsrte-large' not in next_p.get('class', []):
                # Next <p> is likely description
                next_text = next_p.get_text(strip=True)
                # Skip if it's just a price
                if not re.match(r'^\$?\d+(?:\s*\|\s*\$\d+)?', next_text):
                    description = next_text
                    # Check if there's a price in the next <p> after description
                    price_p = next_p.find_next_sibling('p')
                    if price_p:
                        price_text_check = price_p.get_text(strip=True)
                        if re.match(r'^\$?\d+(?:\s*\|\s*\$\d+)?', price_text_check):
                            price_text = price_text_check
            
            # Format price - handle multi-price and add-ons
            price = price_text
            
            # Check if description contains add-ons (look for +$ patterns)
            if description:
                # Find add-on patterns like "+$2", "+$1", "AND/OR make it a double +$2", "add chicken +$2"
                # More specific pattern to avoid false matches
                addon_pattern = r'(\+?\$?\d+(?:\.\d{2})?|add\s+[^+]+?\+\$?\d+(?:\.\d{2})?|make\s+it\s+a\s+double\s+\+?\$?\d+(?:\.\d{2})?)'
                addon_matches = re.findall(addon_pattern, description, re.IGNORECASE)
                if addon_matches:
                    # Format add-ons nicely
                    formatted_addons = []
                    for match in addon_matches:
                        # Skip if it's part of a larger price (like "$3/$4")
                        if '/' in match and '$' in match:
                            continue
                        # Skip if it's clearly not an add-on (like "20 oz" or "12 oz")
                        if re.search(r'\d+\s*(oz|oz\.)', match, re.IGNORECASE):
                            continue
                        
                        if match.startswith('+') or match.startswith('$'):
                            # Clean up the match
                            clean_match = match.strip()
                            if clean_match.startswith('$') and not clean_match.startswith('+$'):
                                clean_match = f"+{clean_match}"
                            formatted_addons.append(clean_match)
                        else:
                            # Extract the price part from phrases like "add chicken +$2"
                            price_match = re.search(r'\+?\$?(\d+(?:\.\d{2})?)', match, re.IGNORECASE)
                            if price_match:
                                formatted_addons.append(f"+${price_match.group(1)}")
                    
                    # Remove duplicates and filter out invalid ones
                    formatted_addons = list(dict.fromkeys(formatted_addons))  # Remove duplicates while preserving order
                    formatted_addons = [a for a in formatted_addons if re.match(r'\+?\$?\d+(?:\.\d{2})?', a)]
                    
                    if formatted_addons:
                        addons_text = " | ".join(formatted_addons)
                        description = f"{description}. Add-ons: {addons_text}"
            
            # Use section price as fallback if item doesn't have its own price
            if not price_text and section_price:
                price_text = section_price
            
            # Format price - handle multi-price formats
            if price_text:
                price = price_text
                # Check if price contains multiple prices (e.g., "Small $5 | Large $7" or "$4 | $6")
                if '|' in price:
                    # Already formatted as multi-price, but ensure all have $
                    price_parts = [p.strip() for p in price.split('|')]
                    formatted_parts = []
                    for part in price_parts:
                        if not part.startswith('$'):
                            price_match = re.search(r'(\d+(?:\.\d{2})?)', part)
                            if price_match:
                                formatted_parts.append(f"${price_match.group(1)}")
                            else:
                                formatted_parts.append(part)
                        else:
                            formatted_parts.append(part)
                    price = " | ".join(formatted_parts)
                else:
                    # Ensure price starts with $
                    if not price.startswith('$'):
                        price_match = re.search(r'(\d+(?:\.\d{2})?)', price)
                        if price_match:
                            price = f"${price_match.group(1)}"
            else:
                price = ""
            
            # Only add items that have a name and a price
            if name and price:
                # Skip items that look like section headers or descriptive text
                if name.lower() in ['menu', 'served', 'made', 'fresh', 'daily', 'local', 'love']:
                    continue
                # Skip if name is too short (likely not a menu item)
                if len(name) < 3:
                    continue
                
                items.append({
                    'name': name,
                    'description': description,
                    'price': price,
                    'section': current_section,
                    'restaurant_name': RESTAURANT_NAME,
                    'restaurant_url': RESTAURANT_URL
                })
    
    return items


def scrape_menu() -> List[Dict]:
    """Main function to scrape the menu"""
    print(f"[INFO] Scraping menu from {RESTAURANT_NAME}")
    all_items = []
    
    # Process each menu
    for menu_info in MENU_URLS:
        menu_url = menu_info['url']
        menu_name = menu_info['name']
        
        print(f"\n[INFO] Processing {menu_name}...")
        
        # Fetch HTML
        html = fetch_menu_html(menu_url)
        if not html:
            print(f"[ERROR] Failed to fetch {menu_name}, skipping...")
            continue
        
        # Extract items
        items = extract_items_from_html(html, menu_name)
        
        # Ensure section has menu name prefix if needed
        for item in items:
            section = item.get('section', '')
            if section and menu_name.lower() not in section.lower():
                item['section'] = f"{menu_name} - {section}" if section else menu_name
            elif not section:
                item['section'] = menu_name
        
        all_items.extend(items)
        print(f"[INFO] Extracted {len(items)} items from {menu_name}")
    
    print(f"\n[INFO] Extracted {len(all_items)} menu items total from all menus")
    
    return all_items


def main():
    """Main entry point"""
    items = scrape_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "thegalwaylocalny_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Scraped {len(items)} items total")
    print(f"[SUCCESS] Saved to {output_file}")
    return items


if __name__ == "__main__":
    main()

