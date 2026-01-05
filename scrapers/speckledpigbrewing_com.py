"""
Scraper for Speckled Pig Brewing Co. (speckledpigbrewing.com)
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import os
from playwright.sync_api import sync_playwright


def fetch_beer_menu_html(url: str, headers: dict, cookies: dict) -> str:
    """Download beer menu HTML."""
    response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_pizza_menu_html(url: str, headers: dict) -> str:
    """Download pizza menu HTML."""
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_beer_menu_items(html_content: str) -> List[Dict]:
    """Parse beer menu items from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all multicolumn-card elements
    cards = soup.find_all('div', class_='multicolumn-card')
    
    for card in cards:
        info_div = card.find('div', class_='multicolumn-card__info')
        if not info_div:
            continue
        
        # Get item name from h3
        h3 = info_div.find('h3', class_='inline-richtext')
        if not h3:
            continue
        
        name = h3.get_text(strip=True)
        if not name:
            continue
        
        # Get description and price info from rte div
        rte_div = info_div.find('div', class_='rte')
        if not rte_div:
            continue
        
        # Find all list items
        list_items = rte_div.find_all('li')
        
        price = None
        size = None
        abv = None
        description_parts = []
        
        for li in list_items:
            li_text = li.get_text(strip=True)
            if not li_text:
                continue
            
            # Check if this is the price/size/ABV line (has strong tag)
            strong = li.find('strong')
            if strong:
                strong_text = strong.get_text(strip=True)
                # Extract ABV, size, and price
                # Format: "6.2% ABV, 13oz, $7.00"
                abv_match = re.search(r'([\d.]+)%\s*ABV', strong_text)
                if abv_match:
                    abv = abv_match.group(1) + '%'
                
                size_match = re.search(r'(\d+)oz', strong_text)
                if size_match:
                    size = size_match.group(1) + 'oz'
                
                price_match = re.search(r'\$([\d.]+)', strong_text)
                if price_match:
                    price = '$' + price_match.group(1)
            else:
                # This is a description line
                description_parts.append(li_text)
        
        description = '; '.join(description_parts) if description_parts else None
        
        # Build price string with size if available
        price_str = price
        if size and price:
            price_str = f"{size} - {price}"
        elif price:
            price_str = price
        
        # Include ABV in description if available
        if abv and description:
            description = f"ABV: {abv}; {description}"
        elif abv:
            description = f"ABV: {abv}"
        
        items.append({
            "name": name,
            "description": description,
            "price": price_str,
            "section": "Beer",
            "restaurant_name": "Speckled Pig Brewing Co.",
            "restaurant_url": "https://speckledpigbrewing.com/",
            "menu_type": "Beer",
            "menu_name": "Beer Menu"
        })
    
    # Also look for wine and flights
    # Wine section
    wine_cards = soup.find_all('h3', class_='inline-richtext', string=re.compile('Wine'))
    for wine_card in wine_cards:
        parent = wine_card.find_parent('div', class_='multicolumn-card__info')
        if parent:
            rte = parent.find('div', class_='rte')
            if rte:
                wine_items = rte.find_all('li')
                for wine_li in wine_items:
                    wine_text = wine_li.get_text(strip=True)
                    strong = wine_li.find('strong')
                    if strong:
                        wine_name = strong.get_text(strip=True)
                        # Extract price
                        price_match = re.search(r'\$([\d.]+)', wine_name)
                        if price_match:
                            wine_name_clean = re.sub(r'\s*\$[\d.]+\s*', '', wine_name).strip()
                            price = '$' + price_match.group(1)
                            items.append({
                                "name": wine_name_clean,
                                "description": None,
                                "price": price,
                                "section": "Wine",
                                "restaurant_name": "Speckled Pig Brewing Co.",
                                "restaurant_url": "https://speckledpigbrewing.com/",
                                "menu_type": "Wine",
                                "menu_name": "Beer Menu"
                            })
    
    # Flights
    flight_heading = soup.find('h2', class_='image-with-text__heading', string=re.compile('Flights'))
    if flight_heading:
        flight_text = flight_heading.get_text(strip=True)
        # Extract price from "Flights of 4 (5oz.) - $10"
        price_match = re.search(r'\$([\d.]+)', flight_text)
        if price_match:
            price = '$' + price_match.group(1)
            items.append({
                "name": "Flights of 4 (5oz.)",
                "description": "Sample a few beers and/or seltzer flavors",
                "price": price,
                "section": "Flights",
                "restaurant_name": "Speckled Pig Brewing Co.",
                "restaurant_url": "https://speckledpigbrewing.com/",
                "menu_type": "Flights",
                "menu_name": "Beer Menu"
            })
    
    return items


def parse_pizza_menu_items(html_content: str) -> List[Dict]:
    """Parse pizza menu items from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    items = []
    
    # Find all multicolumn-card elements
    cards = soup.find_all('div', class_='multicolumn-card')
    
    for card in cards:
        info_div = card.find('div', class_='multicolumn-card__info')
        if not info_div:
            continue
        
        # Get item name and price from h3
        h3 = info_div.find('h3', class_='inline-richtext')
        if not h3:
            continue
        
        h3_text = h3.get_text(strip=True)
        if not h3_text:
            continue
        
        # Extract name and price from h3 (format: "The Figgy Piggy - $15.00")
        price_match = re.search(r'\$([\d.]+)', h3_text)
        if price_match:
            price = '$' + price_match.group(1)
            # Remove price from name
            name = re.sub(r'\s*-\s*\$[\d.]+\s*', '', h3_text).strip()
        else:
            name = h3_text
            price = None
        
        # Get description from rte div
        rte_div = info_div.find('div', class_='rte')
        description = None
        if rte_div:
            list_items = rte_div.find_all('li')
            descriptions = []
            for li in list_items:
                li_text = li.get_text(strip=True)
                if li_text:
                    descriptions.append(li_text)
            if descriptions:
                description = '; '.join(descriptions)
        
        # Skip if no price
        if not price:
            continue
        
        items.append({
            "name": name,
            "description": description,
            "price": price,
            "section": "Pizza",
            "restaurant_name": "Speckled Pig Brewing Co.",
            "restaurant_url": "https://speckledpigbrewing.com/",
            "menu_type": "Pizza",
            "menu_name": "Pizza Menu"
        })
    
    return items


def scrape_speckledpigbrewing() -> List[Dict]:
    """Main scraping function for Speckled Pig Brewing Co."""
    print("Scraping Speckled Pig Brewing Co. menus...")
    
    all_items = []
    
    # Beer menu
    beer_url = "https://www.speckledpigbrewing.com/pages/beer-menu"
    beer_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    beer_cookies = {
        "localization": "US",
        "cart_currency": "USD",
        "_shopify_y": "a05da19d-59b9-43f0-9e83-93d2221f1e95",
        "_shopify_s": "7a938c61-c7fd-4a57-bd62-03ec4c976244",
        "_shopify_analytics": ":AZuO5QQbAAEAgeMtNoRhsYrYIALYcUicWXQQj1upBcHquRfartscQnZfrf8I3X2ulfuMFSc:",
        "shopify_client_id": "a05da19d-59b9-43f0-9e83-93d2221f1e95",
        "__kla_id": "eyJjaWQiOiJPVE5tWkRFNU1XUXRZak5qTlMwMFptWTBMV0l4TkRBdE9EWmxaak5tTXpBeE5USTAifQ==",
        "goodav_block_popup-1263": "",
        "_shopify_essential": ":AZuO5QOFAAEATSzHfMk7it3wXn9Ze761JAcg_QnfD0hV9OQK2rQzDJEcnvr5vIpET2SB6VpU_5G9qP3jSKCsCb0yMozEEu2m7Copo-Y3AB0YI4IXTXSgCqHjrWY721Q1B8L5VbQK5h05VPJkFXy3yLnv8KGyvJpg8ve2EgsMli1-tRPuX9rFkharCLvl6N6RwtVL1dQcnaOiypTgPQg7-6w9YpNDUZUfompIqjD37ueI6oRe0DrE8AWce3sTXVmW0DGlHGcZqv0mHJCzcAkz5iVgTjZYk1Aa1BHKZYxUH-td6tlv0JGofb8KEO-sEAGeg5UCPAyHFmdv9qyeFmNcBIfolx_wV_tSbuLxsGzTeeD_7FMscBZ1YL4QiFnWSUWaBIOcj4yG1QPJOcF9H12CKw:",
        "keep_alive": "eyJ2IjoyLCJ0cyI6MTc2NzYyOTA4MjU4MywiZW52Ijp7IndkIjowLCJ1YSI6MSwiY3YiOjEsImJyIjoxfSwiYmh2Ijp7Im1hIjo1LCJjYSI6MCwia2EiOjAsInNhIjo5LCJrYmEiOjAsInRhIjowLCJ0Ijo2MSwibm0iOjEsIm1zIjowLCJtaiI6MC43OCwibXNwIjowLjk3LCJ2YyI6MCwiY3AiOjAsInJjIjowLCJraiI6MCwia2kiOjAsInNzIjowLjYyLCJzaiI6MC41NCwic3NtIjowLjkzLCJzcCI6MCwidHMiOjAsInRqIjowLCJ0cCI6MCwidHNtIjowfSwic2VzIjp7InAiOjMsInMiOjE3Njc2Mjg5MzMwODIsImQiOjE0MH19"
    }
    
    print("  Downloading beer menu...")
    beer_html = fetch_beer_menu_html(beer_url, beer_headers, beer_cookies)
    beer_items = parse_beer_menu_items(beer_html)
    all_items.extend(beer_items)
    print(f"  Found {len(beer_items)} beer items")
    
    # Pizza menu
    pizza_url = "https://www.speckledpigbrewing.com/pages/pizza-menu"
    pizza_headers = {
        "Referer": "https://www.speckledpigbrewing.com/pages/beer-menu",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    print("  Downloading pizza menu...")
    pizza_html = fetch_pizza_menu_html(pizza_url, pizza_headers)
    pizza_items = parse_pizza_menu_items(pizza_html)
    all_items.extend(pizza_items)
    print(f"  Found {len(pizza_items)} pizza items")
    
    print(f"Total: {len(all_items)} items scraped from Speckled Pig Brewing Co.")
    
    return all_items


if __name__ == "__main__":
    items = scrape_speckledpigbrewing()
    
    # Save to JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "speckledpigbrewing_com.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(items)} items to {output_file}")

