"""
Scraper for Salt & Char Saratoga (saltandcharsaratoga.com)
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os


def fetch_menu_html() -> str:
    """Download the menu HTML from Salt & Char website."""
    url = "https://saltandcharsaratoga.com/menus/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://saltandcharsaratoga.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    cookies = {
        "cookieyes-consent": "consentid:VHdOS1JSeGZhc21oSGlNYmMyNFg4eDM3cUVrbWxLOVQ,consent:no,action:yes,necessary:yes,functional:no,analytics:no,performance:no,advertisement:no"
    }
    
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    return response.text


def parse_menu_items(html_content: str) -> List[Dict]:
    """Parse menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all tab panels (Dinner and Dessert)
    # Tabs can have id starting with "tab-" or id="tab-dessert"
    tab_panels = soup.find_all('div', class_='wpb_tab')
    
    for tab_panel in tab_panels:
        # Determine menu type from tab ID
        tab_id = tab_panel.get('id', '').lower()
        menu_type = "Dinner"  # default
        menu_name = "Dinner Menu"
        
        # Check if this is the dessert tab
        if 'dessert' in tab_id:
            menu_type = "Dessert"
            menu_name = "Dessert Menu"
        
        # Find all section headers (h5 tags) within this tab
        current_section = None
        
        # Find all h5 section headers in this tab
        section_headers = tab_panel.find_all('h5')
        
        # Find all menu items in this tab
        menu_items = tab_panel.find_all('div', class_='nectar_food_menu_item')
        
        # Process items and track sections
        for item_div in menu_items:
            # Check if there's a section header before this item
            # Look backwards from the item to find the nearest h5
            prev_elements = item_div.find_all_previous(['h5'], limit=20)
            for elem in prev_elements:
                # Make sure this h5 is within the same tab panel
                if elem in tab_panel.find_all('h5'):
                    current_section = elem.get_text(strip=True)
                    break
            
            # Extract item name
            name_elem = item_div.find('div', class_='item_name')
            if not name_elem:
                continue
            name_h4 = name_elem.find('h4')
            if not name_h4:
                continue
            name = name_h4.get_text(strip=True)
            
            # Extract price
            price_elem = item_div.find('div', class_='item_price')
            price = None
            if price_elem:
                price_h4 = price_elem.find('h4')
                if price_h4:
                    price = price_h4.get_text(strip=True)
                    # Format price - keep multiple prices as-is
                    if price and not price.startswith('$') and price != 'MP':
                        # If it's just a number, add $ sign
                        if re.match(r'^\d+', price):
                            price = f"${price}"
            
            # Extract description
            desc_elem = item_div.find('div', class_='item_description')
            description = None
            if desc_elem:
                # Get text and replace <br> tags with spaces
                # First replace <br> and <br/> with spaces
                for br in desc_elem.find_all('br'):
                    br.replace_with(' ')
                description = desc_elem.get_text(separator=' ', strip=True)
                # Clean up multiple spaces
                description = re.sub(r'\s+', ' ', description)
                if not description or description.strip() == '':
                    description = None
            
            # Use default section if none found
            if not current_section:
                current_section = "Main"
            
            items.append({
                "name": name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "Salt & Char",
                "restaurant_url": "https://saltandcharsaratoga.com/",
                "menu_type": menu_type,
                "menu_name": menu_name
            })
    
    return items


def scrape_saltandcharsaratoga() -> List[Dict]:
    """Main scraping function for Salt & Char Saratoga."""
    print("Scraping Salt & Char Saratoga menu...")
    
    # Download menu HTML
    html_content = fetch_menu_html()
    
    # Parse menu items
    items = parse_menu_items(html_content)
    
    print(f"Scraped {len(items)} items from Salt & Char Saratoga")
    
    return items


if __name__ == "__main__":
    items = scrape_saltandcharsaratoga()
    
    # Save to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "saltandcharsaratoga_com.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(items)} items to {output_file}")

