"""
Scraper for Simply Food by Maura (simplyfoodbymaura.com)
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os


def fetch_menu_html(url: str, headers: dict, cookies: dict) -> str:
    """Download menu HTML from Simply Food by Maura website."""
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    return response.text


def parse_menu_items(html_content: str) -> List[Dict]:
    """Parse menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all section headers (h2 and h3 tags)
    current_section = None
    
    # Find all list elements that contain menu items
    menu_lists = soup.find_all('ul', class_='wp-block-list')
    
    for menu_list in menu_lists:
        # Check if there's a section header before this list
        prev_h2 = menu_list.find_previous('h2')
        prev_h3 = menu_list.find_previous('h3')
        
        if prev_h3:
            section_text = prev_h3.get_text(strip=True)
            # Remove HTML entities and clean up
            section_text = section_text.replace('&#8211;', '-').replace('&nbsp;', ' ')
            if section_text and len(section_text) > 0:
                current_section = section_text
        elif prev_h2:
            section_text = prev_h2.get_text(strip=True)
            section_text = section_text.replace('&#8211;', '-').replace('&nbsp;', ' ')
            if section_text and len(section_text) > 0:
                current_section = section_text
        
        # Find all list items in this list
        list_items = menu_list.find_all('li', recursive=False)  # Only direct children
        
        for li in list_items:
            # Clone the li element to work with it without nested lists
            li_clone = BeautifulSoup(str(li), 'html.parser').find('li')
            
            # Remove nested lists before extracting text
            nested_ul = li_clone.find('ul', class_='wp-block-list')
            nested_text_content = None
            if nested_ul:
                nested_text_content = nested_ul.extract()
            
            # Get the text of the list item (without nested lists)
            li_text = li_clone.get_text(separator=' ', strip=True)
            
            # Skip if it's empty or too short
            if not li_text or len(li_text) < 3:
                continue
            
            # Extract price(s) from strong tags
            price_elements = li.find_all('strong')
            prices = []
            for price_elem in price_elements:
                price_text = price_elem.get_text(strip=True)
                # Look for price patterns
                price_matches = re.findall(r'\$[\d,]+\.?\d*', price_text)
                prices.extend(price_matches)
            
            # If no prices found in strong tags, look in the text
            if not prices:
                price_matches = re.findall(r'\$[\d,]+\.?\d*', li_text)
                prices = price_matches
            
            # Format prices
            price = None
            if prices:
                # Join multiple prices with " / "
                price = ' / '.join(prices)
            
            # Extract item name - everything before the price or before "–" or "—"
            name = li_text
            # Remove price from name
            if prices:
                for p in prices:
                    name = name.replace(p, '').strip()
            
            # Remove common separators
            name = re.sub(r'\s*[–—]\s*', ' ', name).strip()
            name = re.sub(r'\s*/\s*$', '', name).strip()  # Remove trailing "/"
            
            # Extract description from nested lists
            description = None
            if nested_text_content:
                nested_items = nested_text_content.find_all('li')
                descriptions = []
                for nested_li in nested_items:
                    nested_text = nested_li.get_text(strip=True)
                    # Skip if it's just a price addon
                    if nested_text.startswith('++'):
                        # This is an addon, include it in description
                        descriptions.append(nested_text)
                    elif not re.search(r'^\$', nested_text):
                        # Not a price, it's a description
                        descriptions.append(nested_text)
                
                if descriptions:
                    description = '; '.join(descriptions)
            
            # Clean up name - remove extra spaces
            name = re.sub(r'\s+', ' ', name).strip()
            
            # Skip if name is empty or just punctuation
            if not name or len(name) < 2:
                continue
            
            # Skip items without prices - these are not actual menu items
            # (e.g., service descriptions, informational text)
            if not price:
                continue
            
            # Use default section if none found
            if not current_section:
                current_section = "Main"
            
            items.append({
                "name": name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "Simply Food by Maura",
                "restaurant_url": "https://simplyfoodbymaura.com/",
                "menu_type": "Catering",
                "menu_name": "Catering Menu"
            })
    
    return items


def scrape_simplyfoodbymaura() -> List[Dict]:
    """Main scraping function for Simply Food by Maura."""
    print("Scraping Simply Food by Maura menu...")
    
    url = "https://simplyfoodbymaura.com/catering/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://simplyfoodbymaura.com/",
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
        "__cf_bm": "XrGK583iLrNC1WLZfSkvYa47OoEqkSUHhsoLDTsHyKg-1767627559-1.0.1.1-39qoK.Yag1tMN.9TgJLke2epmI.uwf8NlqL1m3HbpqXq9YKgoJEN5NgB5pF9ohdOQ2nHm1kDwNlwMgOA7buGu3BJmF5VTXIhgrMYkGOZuxo",
        "_tccl_visitor": "cf6befbc-ebb3-46c8-a874-ffd24a8095c9",
        "_tccl_visit": "cf6befbc-ebb3-46c8-a874-ffd24a8095c9",
        "_scc_session": "pc=7&C_TOUCH=2026-01-05T15:47:48.398Z"
    }
    
    html = fetch_menu_html(url, headers, cookies)
    items = parse_menu_items(html)
    
    print(f"Total: {len(items)} items scraped from Simply Food by Maura")
    
    return items


if __name__ == "__main__":
    items = scrape_simplyfoodbymaura()
    
    # Save to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "simplyfoodbymaura_com.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(items)} items to {output_file}")

