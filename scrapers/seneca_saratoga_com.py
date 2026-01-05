"""
Scraper for Seneca Saratoga (seneca-saratoga.com)
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os


def fetch_menu_html(url: str, referer: str, headers: dict, cookies: dict) -> str:
    """Download menu HTML from Seneca website."""
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    return response.text


def parse_dinner_menu_items(html_content: str) -> List[Dict]:
    """Parse dinner menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all section headers (h2 tags)
    current_section = None
    
    # Find all menu items
    menu_items = soup.find_all('div', class_='db-restaurant-menu')
    
    for item_div in menu_items:
        # Check if there's a section header before this item
        prev_h2 = item_div.find_previous('h2')
        if prev_h2:
            section_text = prev_h2.get_text(strip=True)
            if section_text and len(section_text) > 0:
                current_section = section_text
        
        # Extract item name
        name_elem = item_div.find('span', class_='db-restaurant-menu-name-with-price')
        if not name_elem:
            continue
        
        # Get all text from the name span, excluding the label and price spans
        name_text = name_elem.get_text(strip=True)
        # Remove the price span text if it's in the name
        price_span = name_elem.find('span', class_='db-restaurant-menu-price')
        if price_span:
            price_text = price_span.get_text(strip=True)
            name_text = name_text.replace(price_text, '').strip()
        
        # Remove label text if present
        label_span = name_elem.find('span', class_='db-restaurant-menu-label')
        if label_span:
            label_text = label_span.get_text(strip=True)
            name_text = name_text.replace(label_text, '').strip()
        
        name = name_text.strip()
        if not name:
            continue
        
        # Extract price
        price_elem = item_div.find('span', class_='db-restaurant-menu-price')
        price = None
        if price_elem:
            price = price_elem.get_text(strip=True)
            # Format price - ensure it starts with $ if it's a number
            if price and not price.startswith('$') and price != 'MP':
                # Remove &nbsp; and other HTML entities
                price = price.replace('&nbsp;', '').strip()
                if re.match(r'^\d+', price):
                    price = f"${price}"
        
        # Extract description
        desc_elem = item_div.find('div', class_='db-restaurant-menu-description')
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
            "restaurant_name": "Seneca",
            "restaurant_url": "https://seneca-saratoga.com/",
            "menu_type": "Dinner",
            "menu_name": "Dinner Menu"
        })
    
    return items


def parse_cocktails_menu_items(html_content: str) -> List[Dict]:
    """Parse cocktails menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all text columns that contain cocktail items
    text_columns = soup.find_all('div', class_='wpb_text_column')
    
    for column in text_columns:
        # Find h5 tags that contain name and price
        h5_tags = column.find_all('h5')
        
        for h5 in h5_tags:
            h5_text = h5.get_text(strip=True)
            if not h5_text or '|' not in h5_text:
                continue
            
            # Parse name and price from format like "cinnamon & cranberry 75 | $16"
            parts = h5_text.split('|')
            if len(parts) < 2:
                continue
            
            name = parts[0].strip()
            price_text = parts[1].strip()
            
            # Extract price
            price_match = re.search(r'\$?\d+', price_text)
            price = None
            if price_match:
                price = price_match.group(0)
                if not price.startswith('$'):
                    price = f"${price}"
            
            # Find description in next h6 tag
            description = None
            next_h6 = h5.find_next_sibling('h6')
            if next_h6:
                description = next_h6.get_text(strip=True)
                description = re.sub(r'\s+', ' ', description)
                if not description or description.strip() == '':
                    description = None
            
            # Also check if there's an h5 after that might be description
            if not description:
                next_h5 = h5.find_next_sibling('h5')
                if next_h5 and not re.search(r'\$', next_h5.get_text()):
                    description = next_h5.get_text(strip=True)
                    description = re.sub(r'\s+', ' ', description)
                    if not description or description.strip() == '':
                        description = None
            
            items.append({
                "name": name,
                "description": description,
                "price": price,
                "section": "Cocktails",
                "restaurant_name": "Seneca",
                "restaurant_url": "https://seneca-saratoga.com/",
                "menu_type": "Cocktails",
                "menu_name": "Cocktail Menu"
            })
    
    return items


def parse_wine_menu_items(html_content: str) -> List[Dict]:
    """Parse wine menu items from the HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    current_section = None
    
    # Find all paragraph elements with wine items
    wine_paragraphs = soup.find_all('p', class_='cvGsUA')
    
    for p in wine_paragraphs:
        p_text = p.get_text(strip=True)
        
        # Check if this is a section header
        if p_text.startswith('—') and p_text.endswith('—'):
            # This is a section header
            current_section = p_text.replace('—', '').strip()
            continue
        
        # Skip empty paragraphs
        if not p_text or len(p_text) < 5:
            continue
        
        # Parse wine item from format like:
        # "CHAMPAGNE | geoffroy, champagne blend, champagne, france | 2021 …$75"
        # Extract price - it should be at the end after the ellipsis
        price = None
        # Look for price pattern: …$XX or … $XX or just $XX at the end
        price_match = re.search(r'…\s*\$?\d+|\$\d+(?=\s*$)', p_text)
        if price_match:
            price = price_match.group(0).replace('…', '').strip()
            if not price.startswith('$'):
                price = f"${price}"
        
        # Extract name (first part before |)
        parts = p_text.split('|')
        if len(parts) > 0:
            name = parts[0].strip()
            
            # Description is the rest (wine details)
            description = None
            if len(parts) > 1:
                description = '|'.join(parts[1:]).strip()
                # Remove price from description if it's there
                if price:
                    # Remove the price and ellipsis from description
                    description = re.sub(r'…\s*\$?\d+|\$\d+(?=\s*$)', '', description).strip()
                    description = re.sub(r'\s+', ' ', description)
                description = re.sub(r'\s+', ' ', description)
                if not description or description.strip() == '':
                    description = None
            
            # Use default section if none found
            if not current_section:
                current_section = "Wine"
            
            items.append({
                "name": name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "Seneca",
                "restaurant_url": "https://seneca-saratoga.com/",
                "menu_type": "Wine",
                "menu_name": "Wine Menu"
            })
    
    return items


def scrape_seneca_saratoga() -> List[Dict]:
    """Main scraping function for Seneca Saratoga."""
    print("Scraping Seneca Saratoga menu...")
    
    items = []
    
    # Common cookies
    cookies = {
        "__cf_bm": "TUjvms7R3tsiMie5UK3qjSdNQu5PV2MJfx.4vADJlEc-1767627176-1.0.1.1-pugSd7hcttCQ4yiPvM_eiukmHBzlm2jWQu2573n1lKiYkML68qKLPk5wfy_HIXA7ubJR8MWYC4kscKaMPqQ5uH_U80gKCjYCVD.EGroxxoU",
        "_gid": "GA1.2.628392851.1767627179",
        "cf_clearance": "cWPX9RAjuSfmyEgBWt.xHyA.GVJYuiNkqhIKIEMzh2s-1767627180-1.2.1.1-htAnx647c0vd_vcc8tNwZ5dadnTKKNWKRycwXyHSaFXyllZCakSMrmdAmiCbf2J0kuNwQ48n4uMzppra9Zk8NjGMEcLwiMBDb.9CraCB7unJqFyqzX.rJ9v7RcunC6_NfABqaphXd0cXZk074C74Y1Sjmms8lZmcp1kOgjMDTD71KHXaX.dSNv7lBm07egSoa4.TZjMwMpsJWVrtIjgZMf9GR.0xP3k3PqaEnar2BGg",
        "_hjSessionUser_1428416": "eyJpZCI6Ijg2MDZjODhjLTdmNDgtNWQ0My1hYWMxLWNlYThmNTJlNTUwMSIsImNyZWF0ZWQiOjE3Njc2MjcxNzk5MzksImV4aXN0aW5nIjp0cnVlfQ==",
        "_hjSession_1428416": "eyJpZCI6ImEzNzM0MGEwLTlmMGEtNDJkOS1hNDk2LTI3NzE3YjU0MGY3YiIsImMiOjE3Njc2MjcxNzk5NDEsInMiOjEsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjoxLCJzcCI6MH0=",
        "_ga": "GA1.2.440870229.1767627179",
        "_ga_Q5K9CFVW5T": "GS2.1.s1767627179$o1$g1$t1767627199$j40$l0$h0"
    }
    
    # Dinner menu
    dinner_url = "https://seneca-saratoga.com/menu/"
    dinner_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://seneca-saratoga.com/",
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
    
    dinner_html = fetch_menu_html(dinner_url, "https://seneca-saratoga.com/", dinner_headers, cookies)
    dinner_items = parse_dinner_menu_items(dinner_html)
    items.extend(dinner_items)
    print(f"Scraped {len(dinner_items)} dinner items")
    
    # Cocktails menu
    cocktails_url = "https://seneca-saratoga.com/menu/cocktails/"
    cocktails_headers = {
        "Referer": "https://seneca-saratoga.com/menu/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    cocktails_html = fetch_menu_html(cocktails_url, "https://seneca-saratoga.com/menu/", cocktails_headers, cookies)
    cocktails_items = parse_cocktails_menu_items(cocktails_html)
    items.extend(cocktails_items)
    print(f"Scraped {len(cocktails_items)} cocktail items")
    
    # Wine menu
    wine_url = "https://seneca-saratoga.com/menu/wine/"
    wine_headers = {
        "Referer": "https://seneca-saratoga.com/menu/cocktails/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    wine_html = fetch_menu_html(wine_url, "https://seneca-saratoga.com/menu/cocktails/", wine_headers, cookies)
    wine_items = parse_wine_menu_items(wine_html)
    items.extend(wine_items)
    print(f"Scraped {len(wine_items)} wine items")
    
    print(f"Total: {len(items)} items scraped from Seneca Saratoga")
    
    return items


if __name__ == "__main__":
    items = scrape_seneca_saratoga()
    
    # Save to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "seneca_saratoga_com.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(items)} items to {output_file}")

