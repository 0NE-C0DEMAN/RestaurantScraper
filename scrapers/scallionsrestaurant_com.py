"""
Scraper for Scallions Restaurant (scallionsrestaurant.com)
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os


def fetch_menu_html(url: str, referer: str, cookies: dict) -> str:
    """Download menu HTML from Scallions website."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Referer": referer,
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
    
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    return response.text


def parse_food_menu_items(html_content: str) -> List[Dict]:
    """Parse food menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all menu tabs (Lunch, Dinner, Kids, Desserts)
    menu_tabs = soup.find_all('div', class_='food-menu-grid')
    
    for tab in menu_tabs:
        # Determine menu type from tab class or navigation
        tab_class = ' '.join(tab.get('class', []))
        menu_type = "Food"  # default
        menu_name = "Food Menu"
        
        # Check if this tab has a specific menu ID
        if 'menu_798149' in tab_class:
            menu_type = "Lunch"
            menu_name = "Lunch Menu"
        elif 'menu_798150' in tab_class:
            menu_type = "Dinner"
            menu_name = "Dinner Menu"
        elif 'menu_798151' in tab_class:
            menu_type = "Kids"
            menu_name = "Kids Menu"
        elif 'menu_909095' in tab_class:
            menu_type = "Dessert"
            menu_name = "Dessert Menu"
        
        # Find all section headers (h2 tags) within this tab
        current_section = None
        
        # Find all sections in this tab
        sections = tab.find_all('section')
        
        for section in sections:
            # Find section header (h2)
            section_header = section.find('h2')
            if section_header:
                current_section = section_header.get_text(strip=True)
            
            # Find all menu items in this section
            menu_items = section.find_all('div', class_='food-item-holder')
            
            for item_div in menu_items:
                # Extract item name
                name_elem = item_div.find('div', class_='food-item-title')
                if not name_elem:
                    continue
                name_h3 = name_elem.find('h3')
                if not name_h3:
                    continue
                name = name_h3.get_text(strip=True)
                
                # Extract price
                price_elem = item_div.find('div', class_='food-price')
                price = None
                if price_elem:
                    price = price_elem.get_text(strip=True)
                    # Format price - ensure it starts with $ if it's a number
                    if price and not price.startswith('$') and price != 'MP':
                        if re.match(r'^\d+', price):
                            price = f"${price}"
                
                # Extract description
                desc_elem = item_div.find('div', class_='food-item-description')
                description = None
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
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
                    "restaurant_name": "Scallions",
                    "restaurant_url": "https://scallionsrestaurant.com/",
                    "menu_type": menu_type,
                    "menu_name": menu_name
                })
    
    return items


def parse_drink_menu_items(html_content: str) -> List[Dict]:
    """Parse drink menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all menu tabs
    menu_tabs = soup.find_all('div', class_='food-menu-grid')
    
    for tab in menu_tabs:
        # Find all sections in this tab
        sections = tab.find_all('section')
        
        for section in sections:
            # Find section header (h2)
            section_header = section.find('h2')
            current_section = section_header.get_text(strip=True) if section_header else "Drinks"
            
            # Find all menu items in this section
            menu_items = section.find_all('div', class_='food-item-holder')
            
            for item_div in menu_items:
                # Extract item name
                name_elem = item_div.find('div', class_='food-item-title')
                if not name_elem:
                    continue
                name_h3 = name_elem.find('h3')
                if not name_h3:
                    continue
                name = name_h3.get_text(strip=True)
                
                # Extract price
                price_elem = item_div.find('div', class_='food-price')
                price = None
                if price_elem:
                    price = price_elem.get_text(strip=True)
                    if price and not price.startswith('$') and price != 'MP':
                        if re.match(r'^\d+', price):
                            price = f"${price}"
                
                # Extract description
                desc_elem = item_div.find('div', class_='food-item-description')
                description = None
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                    description = re.sub(r'\s+', ' ', description)
                    if not description or description.strip() == '':
                        description = None
                
                items.append({
                    "name": name,
                    "description": description,
                    "price": price,
                    "section": current_section,
                    "restaurant_name": "Scallions",
                    "restaurant_url": "https://scallionsrestaurant.com/",
                    "menu_type": "Drinks",
                    "menu_name": "Drink Menu"
                })
    
    return items


def scrape_scallionsrestaurant() -> List[Dict]:
    """Main scraping function for Scallions Restaurant."""
    print("Scraping Scallions Restaurant menu...")
    
    items = []
    
    # Food menu
    food_url = "https://scallionsrestaurant.com/saratoga-springs-scallions-food-menu"
    food_referer = "https://scallionsrestaurant.com/"
    food_cookies = {
        "resolution": "1536,1.25",
        "_ga": "GA1.1.268651778.1767626901",
        "_ga_VG24VK2VKT": "GS2.1.s1767626900$o1$g1$t1767626912$j48$l0$h0",
        "_ga_PW3M2X3KG5": "GS2.1.s1767626907$o1$g1$t1767626912$j55$l0$h0"
    }
    
    food_html = fetch_menu_html(food_url, food_referer, food_cookies)
    food_items = parse_food_menu_items(food_html)
    items.extend(food_items)
    print(f"Scraped {len(food_items)} food items")
    
    # Drink menu
    drink_url = "https://scallionsrestaurant.com/saratoga-springs-scallions-drink-menu"
    drink_referer = "https://scallionsrestaurant.com/saratoga-springs-scallions-food-menu"
    drink_cookies = {
        "resolution": "1536,1.25",
        "_ga": "GA1.1.268651778.1767626901",
        "_ga_VG24VK2VKT": "GS2.1.s1767626900$o1$g1$t1767627085$j60$l0$h0",
        "_ga_PW3M2X3KG5": "GS2.1.s1767626907$o1$g1$t1767627085$j60$l0$h0"
    }
    
    drink_html = fetch_menu_html(drink_url, drink_referer, drink_cookies)
    drink_items = parse_drink_menu_items(drink_html)
    items.extend(drink_items)
    print(f"Scraped {len(drink_items)} drink items")
    
    print(f"Total: {len(items)} items scraped from Scallions Restaurant")
    
    return items


if __name__ == "__main__":
    items = scrape_scallionsrestaurant()
    
    # Save to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "scallionsrestaurant_com.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(items)} items to {output_file}")

