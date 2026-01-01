"""
Scraper for: https://www.30parkcp.com/
HTML-based menu with tabbed sections
"""

import json
import sys
import asyncio
import re
import requests
from pathlib import Path
from bs4 import BeautifulSoup


def extract_menu_items_from_html(soup, tab_name: str) -> list:
    """
    Extract menu items from HTML soup for a specific tab.
    
    Args:
        soup: BeautifulSoup object
        tab_name: Name of the tab to extract from
    
    Returns:
        List of menu items with name, description, and price
    """
    items = []
    
    try:
        # Find the tabpanel for this tab
        # First, find all tabpanels
        tabpanels = soup.find_all('div', {'role': 'tabpanel'})
        
        # Find the one that's not hidden (active tab)
        active_panel = None
        for panel in tabpanels:
            if panel.get('aria-hidden') != 'true':
                # Check if this panel contains content related to our tab
                heading = panel.find(['h2', 'h3'])
                if heading and tab_name.lower() in heading.get_text().lower():
                    active_panel = panel
                    break
        
        # If not found by heading, try to find by tab index or just get visible one
        if not active_panel:
            for panel in tabpanels:
                if panel.get('aria-hidden') != 'true':
                    active_panel = panel
                    break
        
        # If still no panel, search in main/article
        if not active_panel:
            main = soup.find('main') or soup.find('article')
            if main:
                active_panel = main
        
        if not active_panel:
            return items
        
        # Find all list items in the panel
        list_items = active_panel.find_all('li')
        
        for li in list_items:
            try:
                # Get the strong element (item name with price)
                strong_elem = li.find('strong')
                text_content = li.get_text().strip()
                
                # Handle list items without strong tags but with prices in text (like "Razzle Dazzle 11")
                if not strong_elem:
                    # Check if text has a price pattern
                    price_match = re.search(r'^([A-Za-z\s&\']+?)\s+(\d+)(?:\s+\|?\s*\d+)?(?:\s|$)', text_content)
                    if price_match:
                        name = price_match.group(1).strip()
                        price_num = price_match.group(2).strip()
                        
                        if name and len(name) > 2:
                            # Extract description (everything after the price)
                            description = text_content.replace(name, "").replace(price_num, "").strip()
                            description = re.sub(r'^\s*[-–]\s*', '', description).strip()
                            
                            # Check if we already have this item
                            if not any(item['name'].upper() == name.upper() for item in items):
                                items.append({
                                    'name': name.upper(),
                                    'description': description,
                                    'price': f"${price_num}"
                                })
                    continue
                
                name_with_price = strong_elem.get_text().strip()
                
                if not name_with_price:
                    continue
                
                # Extract price from the name
                # Pattern: "ITEM NAME 5" or "ITEM NAME 6 | 10" or "ITEM NAME $5" or "ITEM NAME $6 | $10"
                # Also handle cases like "ITEM NAME – 2 FOR $8" or "ITEM NAME $8"
                price = ""
                name = name_with_price
                
                # Try to find price with dollar sign first (e.g., "– 2 FOR $8")
                dollar_price_match = re.search(r'[\s–-]*(?:\d+\s+)?(?:FOR|for)?\s*\$\s*(\d+(?:\s*\|\s*\d+)?)', name_with_price)
                if dollar_price_match:
                    price = dollar_price_match.group(1).strip()
                    # Remove everything from "–" or "FOR" onwards including the price
                    name = re.sub(r'[\s–-]*(?:\d+\s+)?(?:FOR|for)?\s*\$\s*\d+(?:\s*\|\s*\d+)?.*$', '', name_with_price).strip()
                    name = re.sub(r'[\s–-]+$', '', name).strip()
                else:
                    # Try to find price at the end without dollar sign (most common case)
                    price_match = re.search(r'[\s$]*(\d+(?:\s*\|\s*\d+)?)\s*$', name_with_price)
                    if price_match:
                        price = price_match.group(1).strip()
                        # Remove price and any preceding text like "– 2 FOR" or "FOR"
                        name = re.sub(r'[\s–-]*(?:\d+\s+)?(?:FOR|for)?\s*[\s$]*\d+(?:\s*\|\s*\d+)?\s*$', '', name_with_price).strip()
                        # Clean up any trailing dashes or spaces
                        name = re.sub(r'[\s–-]+$', '', name).strip()
                
                # Get description (text after strong element)
                description = ""
                if not text_content:
                    text_content = li.get_text()
                if text_content:
                    # Remove the name/price part to get description
                    desc_text = text_content.replace(name_with_price, "").strip()
                    # Clean up description
                    desc_text = re.sub(r'^\s*[-–]\s*', '', desc_text)
                    description = desc_text.strip()
                    
                    # Special handling for wine items with multiple options
                    # Pattern: "CABERNET SAUVIGNON" with text "Josh Cellar (CA) – GLS 12 | BTL 38 Hidden Post (WA) – GLS 10 | BTL 46"
                    # Also handle "GLAS" (typo) instead of "GLS"
                    # Also handle wines with only GLS (no BTL) like "Brilla! (Italy) – GLS 11"
                    
                    # Get full text content for wine extraction (includes all text nodes)
                    full_text_for_wine = li.get_text(separator=' ', strip=False)
                    
                    # First, try to find wines with both GLS and BTL
                    # Make dash optional to handle "DAOU (CA) GLAS 9 | BTL 35" (no dash)
                    wine_options_gls_btl = re.findall(r'([A-Za-z\s&!]+?)\s*\([^)]+\)\s*[–-]?\s*(?:GLS|GLAS)\s*(\d+)\s*\|\s*BTL\s*(\d+)', full_text_for_wine, re.IGNORECASE)
                    
                    # Also check for wines with only GLS (no BTL)
                    wine_options_gls_only = re.findall(r'([A-Za-z\s&!]+?)\s*\([^)]+\)\s*[–-]?\s*(?:GLS|GLAS)\s*(\d+)(?!\s*\|\s*BTL)', full_text_for_wine, re.IGNORECASE)
                    
                    if wine_options_gls_btl or wine_options_gls_only:
                        # Extract base wine name
                        base_name = name
                        # Remove any price info from base name (like "– GLS 12 | BTL")
                        base_name = re.sub(r'[\s–-]*(?:GLS|GLAS)\s*\d+.*$', '', base_name, flags=re.IGNORECASE).strip()
                        base_name = re.sub(r'[\s–-]+$', '', base_name).strip()
                        
                        # Create separate items for wines with GLS and BTL
                        for wine_name, gls_price, btl_price in wine_options_gls_btl:
                            wine_name_clean = wine_name.strip()
                            # Remove base_name from wine_name if it's already included (to avoid duplication)
                            if wine_name_clean.upper().startswith(base_name.upper()):
                                wine_name_clean = wine_name_clean[len(base_name):].strip()
                            full_name = f"{base_name} {wine_name_clean}".strip()
                            wine_price = f"${gls_price} (glass) | ${btl_price} (bottle)"
                            
                            # Check if we already have this item
                            if not any(item['name'].upper() == full_name.upper() for item in items):
                                items.append({
                                    'name': full_name.upper(),
                                    'description': "",
                                    'price': wine_price
                                })
                        
                        # Create separate items for wines with only GLS
                        for wine_name, gls_price in wine_options_gls_only:
                            wine_name_clean = wine_name.strip()
                            # Remove base_name from wine_name if it's already included (to avoid duplication)
                            if wine_name_clean.upper().startswith(base_name.upper()):
                                wine_name_clean = wine_name_clean[len(base_name):].strip()
                            full_name = f"{base_name} {wine_name_clean}".strip()
                            wine_price = f"${gls_price}"
                            
                            # Check if we already have this item
                            if not any(item['name'].upper() == full_name.upper() for item in items):
                                items.append({
                                    'name': full_name.upper(),
                                    'description': "",
                                    'price': wine_price
                                })
                        
                        # Don't add the base item if we extracted wine options
                        continue
                    
                    # Also handle single wine items with GLS | BTL format in the name
                    # Like "PINOT NOIR – GLS 12 | BTL 46"
                    if 'GLS' in name_with_price.upper() or 'GLAS' in name_with_price.upper():
                        gls_btl_match = re.search(r'(?:GLS|GLAS)\s*(\d+)\s*\|\s*BTL\s*(\d+)', name_with_price, re.IGNORECASE)
                        if gls_btl_match:
                            gls_price = gls_btl_match.group(1)
                            btl_price = gls_btl_match.group(2)
                            # Clean name
                            name = re.sub(r'[\s–-]*(?:GLS|GLAS)\s*\d+.*$', '', name_with_price, flags=re.IGNORECASE).strip()
                            name = re.sub(r'[\s–-]+$', '', name).strip()
                            price = f"${gls_price} (glass) | ${btl_price} (bottle)"
                
                # Skip if name is empty or too short
                if len(name) < 2:
                    continue
                
                # Format price with dollar sign and small/large labels
                if price:
                    if '|' in price:
                        # Two prices: "6 | 10" -> "$6 (small) | $10 (large)"
                        prices = [p.strip() for p in price.split('|')]
                        if len(prices) == 2:
                            price = f"${prices[0]} (small) | ${prices[1]} (large)"
                        else:
                            price = " | ".join([f"${p}" for p in prices])
                    else:
                        price = f"${price}"
                
                items.append({
                    'name': name,
                    'description': description,
                    'price': price
                })
                
            except Exception as e:
                print(f"    Error extracting item: {e}")
                continue
        
        # Also check for items in paragraphs
        paragraphs = active_panel.find_all('p')
        for p in paragraphs:
            try:
                strong_elem = p.find('strong')
                if strong_elem:
                    text = p.get_text()
                    if text and any(char.isdigit() for char in text):
                        name_with_price = strong_elem.get_text().strip()
                        if name_with_price and len(name_with_price) > 3:
                            price_match = re.search(r'(\d+(?:\s*\|\s*\d+)?)$', name_with_price)
                            price = ""
                            name = name_with_price
                            
                            if price_match:
                                price = price_match.group(1).strip()
                                name = re.sub(r'[\s$]*\d+(?:\s*\|\s*\d+)?\s*$', '', name_with_price).strip()
                                name = re.sub(r'[\s–-]+$', '', name).strip()
                            
                            description = text.replace(name_with_price, "").strip()
                            description = re.sub(r'^\s*[-–]\s*', '', description).strip()
                            
                            if len(name) >= 2:
                                if price:
                                    if '|' in price:
                                        prices = [p.strip() for p in price.split('|')]
                                        if len(prices) == 2:
                                            price = f"${prices[0]} (small) | ${prices[1]} (large)"
                                        else:
                                            price = " | ".join([f"${p}" for p in prices])
                                    else:
                                        price = f"${price}"
                                
                                # Check if we already have this item
                                if not any(item['name'] == name for item in items):
                                    items.append({
                                        'name': name,
                                        'description': description,
                                        'price': price
                                    })
            except:
                continue
        
    except Exception as e:
        print(f"  Error extracting from {tab_name}: {e}")
    
    return items


def scrape_30park_menu():
    """Scrape menu from 30 Park website"""
    
    url = "https://www.30parkcp.com/"
    menu_url = "https://www.30parkcp.com/restaurant/"
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    # Remove 'www_' prefix and 'menu' if present
    if url_safe.startswith('www_'):
        url_safe = url_safe[4:]
    url_safe = url_safe.replace('_menu', '')
    output_json = Path(__file__).parent.parent / 'output' / f'{url_safe}.json'
    
    print(f"Scraping: {url}")
    print(f"Menu page: {menu_url}")
    print(f"Output file: {output_json}")
    print()
    
    restaurant_name = "30 Park"
    all_items = []
    
    try:
        # Fetch HTML using requests
        print(f"Fetching menu page HTML...")
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://www.30parkcp.com/',
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
        
        response = requests.get(menu_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all tabs
        tabs = soup.find_all(['button', 'a'], {'role': 'tab'})
        tab_names = []
        for tab in tabs:
            text = tab.get_text().strip()
            if text and text in ['Happy Hour', 'Snacks', 'Soup & Salad', 'Appetizers', 'Handful', 'Knife & Fork', 'Drinks', 'Sweet Treats']:
                tab_names.append(text)
        
        # If no tabs found, use hardcoded list
        if not tab_names:
            tab_names = ['Happy Hour', 'Snacks', 'Soup & Salad', 'Appetizers', 'Handful', 'Knife & Fork', 'Drinks', 'Sweet Treats']
            print("Using hardcoded tab list")
        
        print(f"Found {len(tab_names)} menu sections: {', '.join(tab_names)}")
        print()
        
        # Process each tab by clicking it and extracting
        # Since we have the full HTML, we need to simulate tab clicks or extract all tabpanels
        # Let's extract all tabpanels and match them to tabs
        tabpanels = soup.find_all('div', {'role': 'tabpanel'})
        
        # Process each tab
        for i, tab_name in enumerate(tab_names, 1):
            print(f"[{i}/{len(tab_names)}] Processing: {tab_name}")
            
            try:
                # Find the corresponding tabpanel
                # Try to match by index or by heading
                panel = None
                if i <= len(tabpanels):
                    # Try by index first
                    panel = tabpanels[i-1]
                else:
                    # Try to find by heading
                    for p in tabpanels:
                        heading = p.find(['h2', 'h3'])
                        if heading and tab_name.lower() in heading.get_text().lower():
                            panel = p
                            break
                
                if panel:
                    # Create a temporary soup with just this panel active
                    temp_soup = BeautifulSoup(str(panel), 'html.parser')
                    items = extract_menu_items_from_html(temp_soup, tab_name)
                else:
                    # Fallback: search in main content
                    items = extract_menu_items_from_html(soup, tab_name)
                
                if items:
                    # Add restaurant info and menu type to each item
                    for item in items:
                        item['restaurant_name'] = restaurant_name
                        item['restaurant_url'] = url
                        item['menu_type'] = tab_name
                    
                    all_items.extend(items)
                    print(f"  [OK] Extracted {len(items)} items from {tab_name}")
                else:
                    print(f"  [WARNING] No items extracted from {tab_name}")
                
            except Exception as e:
                print(f"  [ERROR] Failed to process {tab_name}: {e}")
                import traceback
                traceback.print_exc()
            
            print()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Save JSON file with menu items
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Restaurant: {restaurant_name}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_json}")


if __name__ == '__main__':
    scrape_30park_menu()

