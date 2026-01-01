"""
Scraper for: https://www.coffeeplanetcafe.com/
Scrapes menu items from the menu page
"""

import json
import re
import requests
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup


def extract_menu_items_from_html(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract menu items from HTML soup.
    Structure: <p><img /></p><h3>Item Name</h3><h4>$ Price</h4>
    """
    items = []
    
    # Find the main content area
    main_content = soup.find('div', class_='cntt-w')
    if not main_content:
        main_content = soup.find('main') or soup.find('article') or soup
    
    # Find all h3 tags (item names)
    h3_tags = main_content.find_all('h3')
    
    for h3 in h3_tags:
        item_name = h3.get_text(strip=True)
        
        # Skip if it's not a menu item (like "@COFEECAFE" or "Instagram")
        if not item_name or item_name.startswith('@') or item_name.lower() in ['instagram', 'follow us']:
            continue
        
        # Find the price (h4 tag after h3)
        price = ""
        h4 = h3.find_next_sibling('h4')
        if h4:
            price_text = h4.get_text(strip=True)
            # Extract price, handle format like "$ 2.9" or "$2.9"
            price_match = re.search(r'\$?\s*(\d+\.?\d*)', price_text)
            if price_match:
                price = f"${price_match.group(1)}"
        
        # Find description (p tag before h3, or text after image)
        description = ""
        # Look for p tag before h3 that might contain description
        prev_p = h3.find_previous_sibling('p')
        if prev_p:
            # Check if it has an image (if so, description might be in next p or empty)
            img = prev_p.find('img')
            if img:
                # Description might be in the same p tag after image, or in next p
                desc_text = prev_p.get_text(strip=True)
                if desc_text and not desc_text.startswith('http'):  # Not just image URL
                    description = desc_text
            else:
                description = prev_p.get_text(strip=True)
        
        # Find image URL if available
        img_url = ""
        prev_p = h3.find_previous_sibling('p')
        if prev_p:
            img = prev_p.find('img')
            if img:
                # Try data-src first (lazy loading), then src
                img_url = img.get('data-src') or img.get('src', '')
                if img_url and not img_url.startswith('http'):
                    if img_url.startswith('//'):
                        img_url = f"https:{img_url}"
                    else:
                        img_url = f"https://www.coffeeplanetcafe.com{img_url}"
        
        if item_name:
            items.append({
                'name': item_name,
                'description': description,
                'price': price,
                'menu_type': 'Menu',
                'image_url': img_url
            })
    
    return items


def scrape_coffeeplanetcafe_menu(url: str) -> List[Dict]:
    """
    Scrape menu from coffeeplanetcafe.com
    """
    all_items = []
    restaurant_name = "Coffee Planet Cafe"
    
    print(f"Scraping: {url}")
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    headers = {
        'Referer': 'https://www.coffeeplanetcafe.com/',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
    
    try:
        # Fetch HTML page
        print("Fetching menu page HTML...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        print(f"[OK] Received HTML content\n")
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract menu items
        print("Extracting menu items...")
        items = extract_menu_items_from_html(soup)
        
        if items:
            for item in items:
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = url
                item['menu_name'] = "Menu"
                # Remove image_url from final output (or keep it if needed)
                # For now, we'll keep it but it's optional
            all_items.extend(items)
        
        print(f"[OK] Extracted {len(all_items)} items from menu\n")
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Save to JSON
    print(f"Saved {len(all_items)} items to: {output_json}\n")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    return all_items


if __name__ == '__main__':
    menu_url = "https://www.coffeeplanetcafe.com/menu-2/"
    scrape_coffeeplanetcafe_menu(menu_url)

