"""
Scraper for cardonasmarket.com
Extracts menu items from Albany, Latham, and Saratoga locations
"""

import json
import re
import requests
from typing import List, Dict
from bs4 import BeautifulSoup


def extract_menu_items_from_html(soup: BeautifulSoup, menu_name: str = "Albany") -> List[Dict]:
    """
    Extract menu items from HTML soup
    
    Args:
        soup: BeautifulSoup object of the HTML
        menu_name: Name of the menu location ("Albany", "Latham", or "Saratoga")
    
    Returns:
        List of dictionaries containing menu items
    """
    items = []
    
    # Find all menu sections
    menu_sections = soup.find_all('section', class_='menu-section')
    
    if not menu_sections:
        print(f"  [WARNING] No menu sections found for {menu_name}")
        return []
    
    print(f"  Found {len(menu_sections)} menu sections")
    
    for section in menu_sections:
        # Get section name from h2
        section_header = section.find('div', class_='menu-section__header')
        if section_header:
            h2 = section_header.find('h2')
            if h2:
                section_name = h2.get_text(strip=True)
            else:
                section_name = "Unknown Section"
        else:
            section_name = "Unknown Section"
        
        if not section_name:
            continue
        
        # Find all menu items in this section
        menu_items = section.find_all('li', class_='menu-item')
        
        for item in menu_items:
            try:
                # Extract item name
                name_elem = item.find('p', class_='menu-item__heading--name')
                if not name_elem:
                    continue
                
                item_name = name_elem.get_text(strip=True)
                if not item_name:
                    continue
                
                # Extract description
                desc_elem = item.find('p', class_='menu-item__details--description')
                description = ""
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                
                # Extract prices
                price_elems = item.find_all('p', class_='menu-item__details--price')
                prices = []
                sub_items = []  # For items that list sub-items instead of prices
                
                for price_elem in price_elems:
                    # Get all text from the price element
                    price_text = price_elem.get_text(strip=True)
                    
                    if not price_text:
                        continue
                    
                    # Check if this element contains a price (has $ and number)
                    # If not, it might be a sub-item name
                    has_price = bool(re.search(r'\$\s*\d+\.?\d*', price_text))
                    
                    if has_price:
                        # Extract size label and price
                        # Format: "Small $9" or "Large $13" or "8 oz $3.99" or "$4.49 per 1/2 pint"
                        # Look for pattern: size label (optional) followed by $ and price, possibly with additional text
                        price_match = re.search(r'\$\s*(\d+\.?\d*)(.*?)$', price_text)
                        if price_match:
                            price_value = price_match.group(1)
                            additional_text = price_match.group(2).strip()
                            
                            # Get the size label (everything before the $)
                            size_label = price_text[:price_match.start()].strip()
                            # Remove any trailing $ or currency symbols
                            size_label = re.sub(r'\$\s*$', '', size_label).strip()
                            
                            # Build price string
                            if size_label:
                                if additional_text:
                                    prices.append(f"{size_label}: ${price_value} {additional_text}")
                                else:
                                    prices.append(f"{size_label}: ${price_value}")
                            else:
                                if additional_text:
                                    prices.append(f"${price_value} {additional_text}")
                                else:
                                    prices.append(f"${price_value}")
                        else:
                            # Try alternative pattern without $ symbol (fallback)
                            alt_match = re.search(r'(\d+\.?\d*)(.*?)$', price_text)
                            if alt_match:
                                price_value = alt_match.group(1)
                                additional_text = alt_match.group(2).strip()
                                size_label = price_text[:alt_match.start()].strip()
                                # Remove any trailing $ or currency symbols
                                size_label = re.sub(r'\$\s*$', '', size_label).strip()
                                
                                if size_label:
                                    if additional_text:
                                        prices.append(f"{size_label}: ${price_value} {additional_text}")
                                    else:
                                        prices.append(f"{size_label}: ${price_value}")
                                else:
                                    if additional_text:
                                        prices.append(f"${price_value} {additional_text}")
                                    else:
                                        prices.append(f"${price_value}")
                    else:
                        # This is a sub-item name, not a price
                        # Check if it's in a strong tag (likely a sub-item)
                        strong_tag = price_elem.find('strong')
                        if strong_tag:
                            sub_item_name = strong_tag.get_text(strip=True)
                            if sub_item_name:
                                sub_items.append(sub_item_name)
                
                # Format price string
                if prices:
                    if len(prices) == 1:
                        price = prices[0]
                    else:
                        price = " | ".join(prices)
                else:
                    price = ""
                
                # If no prices but has sub-items, add them to description
                if not price and sub_items:
                    if description:
                        description += f" | Includes: {', '.join(sub_items)}"
                    else:
                        description = f"Includes: {', '.join(sub_items)}"
                
                # Skip items that have no price (category headers or informational items)
                # These items are not purchasable menu items
                if not price:
                    continue
                
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'menu_type': section_name,
                    'restaurant_name': "Cardona's Market",
                    'restaurant_url': "https://www.cardonasmarket.com/",
                    'menu_name': menu_name
                })
                
            except Exception as e:
                print(f"    [ERROR] Error processing item: {e}")
                continue
    
    return items


def scrape_cardonasmarket_menu(url: str, menu_name: str) -> List[Dict]:
    """
    Main function to scrape menu from a specific location
    
    Args:
        url: URL of the menu page
        menu_name: Name of the menu location ("Albany", "Latham", or "Saratoga")
    
    Returns:
        List of dictionaries containing all menu items
    """
    try:
        # Fetch the HTML
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.cardonasmarket.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        print(f"Fetching {menu_name} menu from {url}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract items
        print(f"\nExtracting {menu_name} menu items...")
        items = extract_menu_items_from_html(soup, menu_name)
        print(f"  Extracted {len(items)} items from {menu_name}")
        
        return items
        
    except requests.RequestException as e:
        print(f"Error fetching {menu_name} menu: {e}")
        return []
    except Exception as e:
        print(f"Error scraping {menu_name} menu: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_all_cardonasmarket_menus() -> List[Dict]:
    """
    Scrape all three menu locations
    
    Returns:
        List of dictionaries containing all menu items from all locations
    """
    all_items = []
    
    # Menu configurations: (url, menu_name)
    menus = [
        ("https://www.cardonasmarket.com/albany-menu/", "Albany"),
        ("https://www.cardonasmarket.com/latham-menu/", "Latham"),
        ("https://www.cardonasmarket.com/saratoga/", "Saratoga")
    ]
    
    for url, menu_name in menus:
        items = scrape_cardonasmarket_menu(url, menu_name)
        all_items.extend(items)
        print()
    
    print(f"Total items extracted: {len(all_items)}")
    return all_items


if __name__ == "__main__":
    items = scrape_all_cardonasmarket_menus()
    
    # Save to JSON file
    output_file = "output/cardonasmarket_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(items)} items to {output_file}")

