"""
Scraper for carsonswoodside.com
Extracts menu items from the full menu page using Wix restaurant menu component
"""

import json
import re
import requests
from typing import List, Dict
from bs4 import BeautifulSoup


def extract_menu_items_from_html(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract menu items from HTML soup using data-hook attributes
    
    Args:
        soup: BeautifulSoup object of the HTML
    
    Returns:
        List of dictionaries containing menu items
    """
    items = []
    
    # Find all sections using data-hook="section.container"
    sections = soup.find_all(attrs={'data-hook': 'section.container'})
    
    if not sections:
        print("  [WARNING] No menu sections found")
        return []
    
    print(f"  Found {len(sections)} menu sections")
    
    for section in sections:
        # Get section name from data-hook="section.name"
        section_name_elem = section.find(attrs={'data-hook': 'section.name'})
        if section_name_elem:
            section_name = section_name_elem.get_text(strip=True)
        else:
            section_name = "Unknown Section"
        
        if not section_name:
            continue
        
        # Find all items in this section using data-hook="item.container"
        item_containers = section.find_all(attrs={'data-hook': 'item.container'})
        
        # If no items found, check if there's a section description with items listed
        if len(item_containers) == 0:
            # Look for section description - it might be in a span or div after the section name
            # Check for any text content that might contain item listings
            section_desc_elem = section.find(attrs={'data-hook': 'section.description'})
            if not section_desc_elem:
                # Try to find description in the section structure
                # Look for spans or divs with class containing description
                for elem in section.find_all(['span', 'div']):
                    text = elem.get_text(strip=True)
                    # Check if this looks like a description with items and price
                    # Pattern: "Item1, Item2, Item3 price description"
                    if text and re.search(r'\d+\.?\d{0,2}', text) and len(text) > 50:
                        # This might be a section description with items
                        section_desc_elem = elem
                        break
            
            if section_desc_elem:
                desc_text = section_desc_elem.get_text(strip=True)
                # Parse DELI SANDWICHES format: "Baked Ham, Roast Turkey, Corned Beef, BLT, Chicken Salad, Tuna Salad 14.50 Served with..."
                # Extract price
                price_match = re.search(r'(\d+\.?\d{0,2})', desc_text)
                if price_match:
                    price = f"${price_match.group(1)}"
                    # Extract items before the price
                    price_pos = desc_text.find(price_match.group(1))
                    items_text = desc_text[:price_pos].strip()
                    # Extract description after price
                    desc_after_price = desc_text[price_pos + len(price_match.group(1)):].strip()
                    
                    # Split items by comma
                    item_names = [item.strip() for item in items_text.split(',') if item.strip()]
                    
                    # Create an item for each sandwich type
                    for item_name in item_names:
                        if item_name:
                            items.append({
                                'name': item_name,
                                'description': desc_after_price,
                                'price': price,
                                'menu_type': section_name,
                                'restaurant_name': "Carson's Woodside Tavern",
                                'restaurant_url': "https://www.carsonswoodside.com/",
                                'menu_name': "Full Menu"
                            })
            continue
        
        for item_container in item_containers:
            try:
                # Extract item name from data-hook="item.name"
                name_elem = item_container.find(attrs={'data-hook': 'item.name'})
                if not name_elem:
                    continue
                
                item_name = name_elem.get_text(strip=True)
                if not item_name:
                    continue
                
                # Extract description from data-hook="item.description"
                desc_elem = item_container.find(attrs={'data-hook': 'item.description'})
                description = ""
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                
                # Extract price from data-hook="item.price"
                price_elem = item_container.find(attrs={'data-hook': 'item.price'})
                price = ""
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Ensure price starts with $
                    if price_text:
                        if not price_text.startswith('$'):
                            # Try to extract price number and add $
                            price_match = re.search(r'(\d+\.?\d*)', price_text)
                            if price_match:
                                price = f"${price_match.group(1)}"
                            else:
                                price = price_text
                        else:
                            price = price_text
                
                # Skip items without prices
                if not price:
                    continue
                
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'menu_type': section_name,
                    'restaurant_name': "Carson's Woodside Tavern",
                    'restaurant_url': "https://www.carsonswoodside.com/",
                    'menu_name': "Full Menu"
                })
                
            except Exception as e:
                print(f"    [ERROR] Error processing item: {e}")
                continue
    
    return items


def scrape_carsonswoodside_menu(url: str) -> List[Dict]:
    """
    Main function to scrape menu from carsonswoodside.com
    
    Args:
        url: URL of the menu page
    
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
            'referer': 'https://www.carsonswoodside.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        
        print(f"Fetching menu from {url}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract items
        print(f"\nExtracting menu items...")
        items = extract_menu_items_from_html(soup)
        print(f"  Extracted {len(items)} items")
        
        return items
        
    except requests.RequestException as e:
        print(f"Error fetching menu: {e}")
        return []
    except Exception as e:
        print(f"Error scraping menu: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    url = "https://www.carsonswoodside.com/full-menu"
    items = scrape_carsonswoodside_menu(url)
    
    # Save to JSON file
    output_file = "output/carsonswoodside_com_.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(items)} items to {output_file}")

