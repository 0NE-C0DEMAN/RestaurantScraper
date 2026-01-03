"""
Scraper for krucoffee.com
Scrapes all product categories: Coffee, Finite Series, Microlots, Apparel, Accessories
"""

import json
import re
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup


# Coffee category only
CATEGORIES = [
    {"name": "Coffee", "url": "https://www.krucoffee.com/category/coffee", "menu_type": "Coffee"},
]


def download_html_with_requests(url: str) -> str:
    """Download HTML from URL"""
    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.krucoffee.com/"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_products_from_html(html: str, menu_name: str) -> List[Dict]:
    """Parse products from HTML using BeautifulSoup"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    restaurant_name = "Kru Coffee"
    restaurant_url = "https://www.krucoffee.com/"
    
    # Find all product items - they are in divs with class "collection-item"
    product_items = soup.find_all('div', class_='collection-item')
    
    for item in product_items:
        # Look for product link
        product_link = item.find('a', href=re.compile(r'/product/'))
        if not product_link:
            continue
        
        # Get product name from div with class "product-name-text"
        name_elem = item.find('div', class_='product-name-text')
        if not name_elem:
            continue
        
        name = name_elem.get_text(strip=True)
        if not name:
            continue
        
        # Get price from div with class "product-price-text"
        price = ""
        price_elem = item.find('div', class_='product-price-text')
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Clean up non-breaking spaces and special characters
            price_text = price_text.replace('\xa0', ' ').replace('\u00a0', ' ').replace('Â', '').strip()
            # Extract price value - format is "$ 18.00 USD" or "$ 18.00 USD"
            price_match = re.search(r'\$\s*([\d,]+\.?\d*)', price_text)
            if price_match:
                price = f"${price_match.group(1).replace(',', '')}"
            else:
                # Try alternative pattern if first one fails
                price_match = re.search(r'([\d,]+\.?\d*)', price_text)
                if price_match:
                    price = f"${price_match.group(1).replace(',', '')}"
        
        # Get description if available (usually not present in category pages)
        description = ""
        desc_elem = item.find(['p', 'div'], class_=re.compile(r'description|summary|desc', re.I))
        if desc_elem:
            description = desc_elem.get_text(separator=' ', strip=True)
        
        items.append({
            'name': name,
            'description': description,
            'price': price,
            'menu_type': menu_name,
            'restaurant_name': restaurant_name,
            'restaurant_url': restaurant_url,
            'menu_name': menu_name
        })
    
    return items


def scrape_category(category: Dict) -> List[Dict]:
    """Scrape a single category"""
    print(f"\n[1] Scraping {category['name']}...")
    print(f"    URL: {category['url']}")
    
    html = download_html_with_requests(category['url'])
    if not html:
        print(f"[ERROR] Failed to download HTML for {category['name']}")
        return []
    
    # Save HTML for debugging
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    html_file = temp_dir / f"krucoffee_com_{category['name'].lower().replace(' ', '_')}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] Saved HTML to {html_file.name}")
    
    items = parse_products_from_html(html, category['menu_type'])
    print(f"[OK] Extracted {len(items)} items from {category['name']}")
    
    if items:
        print(f"[INFO] Sample items:")
        for i, item in enumerate(items[:3], 1):
            try:
                print(f"  {i}. {item['name']} - {item['price']}")
            except UnicodeEncodeError:
                # Handle Unicode characters in names
                name = item['name'].encode('ascii', 'ignore').decode('ascii')
                print(f"  {i}. {name} - {item['price']}")
        if len(items) > 3:
            print(f"  ... and {len(items) - 3} more")
    
    return items


def scrape_krucoffee_menu() -> List[Dict]:
    """Scrape all categories from Kru Coffee"""
    print("=" * 60)
    print("Scraping Kru Coffee (krucoffee.com)")
    print("=" * 60)
    
    all_items = []
    
    for category in CATEGORIES:
        items = scrape_category(category)
        all_items.extend(items)
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    return all_items


if __name__ == '__main__':
    items = scrape_krucoffee_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "krucoffee_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

