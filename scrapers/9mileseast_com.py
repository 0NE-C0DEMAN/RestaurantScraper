"""
Scraper for: https://www.9mileseast.com/
Uses ChowNow API to fetch menu data
All code consolidated in a single file
"""

import json
import sys
import requests
from pathlib import Path
from typing import Dict, List
from datetime import datetime

def scrape_9mileseast_menu(url: str) -> List[Dict]:
    """Scrape menu items from 9mileseast.com using ChowNow API"""
    all_items = []
    restaurant_name = "9 Miles East Farm"
    
    # Generate current timestamp for menu version (format: YYYYMMDDHHMM)
    # Using current date/time to ensure we get the latest menu
    # Note: API appears to accept any recent timestamp and returns current menu
    current_timestamp = datetime.now().strftime("%Y%m%d%H%M")
    api_url = f"https://api.chownow.com/api/restaurant/2027/menu/{current_timestamp}"
    
    print(f"Scraping: {url}")
    print(f"API endpoint: {api_url}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output filename based on URL
    url_safe = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
    # Remove 'www_' prefix and 'menu' if present
    if url_safe.startswith('www_'):
        url_safe = url_safe[4:]
    url_safe = url_safe.replace('_menu', '')
    output_json = output_dir / f'{url_safe}.json'
    print(f"Output file: {output_json}\n")
    
    try:
        # Headers from curl command
        headers = {
            'accept': 'application/json version=5.0;',
            'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
            'cache-control': 'no-cache',
            'content-type': 'application/json; charset=UTF-8',
            'cookie': '__cf_bm=V.DnR.pBnkT2Ie1b.h9QPa8gaGX.pq9lVLwRbEQrN9I-1767186959-1.0.1.1-eojLWQKB.m1prKC4MEna0q082Uf_L3Z0QZDk7H42tDVoQNw_XKWYZUJN94PAw9ZD9nbQxYoCLiZ4utOcUXQZxp.E22BSgxRFFffB_q1paoKIb3YC5R0hJQo6bgMsD1bd; __cfruid=390bcb43d0e98400758001b58c91aeda245820e5-1767186959; _cfuvid=htHE8lJX1jhILDmpT40lc0sXx7wRrgeRmK1PD4VMhL8-1767186959804-0.0.1.1-604800000; _ga=GA1.1.1477715558.1767186963; cn_experiment_cookie_v2=diner-c6fab368-4123-489a-9671-eb352c3c4859; cf_clearance=HomDdMWzUlNZnhiuGkzE7ayNvklVc1Tqq2bamPXfjmI-1767186968-1.2.1.1-_dxcfTOUMcbIMT.jKE2G06ih.ZNAFYddMd5U7JZABnL3_Ats15JDiyyC3flcNvf5jpynItO_nwVhE41HX4P2WB9m8uw28pLcilPdBatjlSMgTHxbUoASH28QOyQpMl1rmfiGbZiykIIFRkBXaKQA.aC28uKlJIRzP_9OZr7D3o__tjY8dxq9JLlcumhxjAXoF1OazCTXOG1AYblHV5XfZ9garcTOpZtXtEWkhSWUYlo; session=d341bb32-36d5-dece-179c-80779de3c823; __ssid=78ebdaf583a179528193eb6bd1a5201; OptanonAlertBoxClosed=2025-12-31T13:19:43.138Z; _ga_VK22JG6NRW=GS2.1.s1767186962$o1$g1$t1767187183$j26$l0$h1929271938; OptanonConsent=isGpcEnabled=0&datestamp=Wed+Dec+31+2025+18%3A49%3A44+GMT%2B0530+(India+Standard+Time)&version=202306.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CSSPD_BG%3A1%2CC0004%3A1%2CC0005%3A1%2CC0002%3A1&AwaitingReconsent=false&geolocation=IN%3BRJ',
            'origin': 'https://direct.chownow.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://direct.chownow.com/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'x-cn-app-info': 'Direct-Web/5.170.0'
        }
        
        print("Fetching menu data from API...")
        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        menu_data = response.json()
        print(f"[OK] Received menu data\n")
        
        # Extract items from all categories
        print("Parsing menu items...")
        menu_categories = menu_data.get('menu_categories', [])
        
        for category in menu_categories:
            category_name = category.get('name', 'Menu')
            items = category.get('items', [])
            
            print(f"  Processing category: {category_name} ({len(items)} items)")
            
            for item in items:
                # Extract item data
                name = item.get('name', '') or ''
                name = name.strip() if name else ''
                
                description = item.get('description') or ''
                description = description.strip() if description else ''
                
                price = item.get('price')
                
                # Format price with $ symbol
                if price is not None:
                    # Price is a number, format it with $ and 2 decimal places
                    if isinstance(price, (int, float)):
                        price_str = f"${price:.2f}"
                    else:
                        price_str = str(price)
                        if price_str and not price_str.startswith('$'):
                            price_str = f"${price_str}"
                else:
                    price_str = ""
                
                # Skip if name is empty
                if not name:
                    continue
                
                # Create menu item
                menu_item = {
                    'name': name,
                    'description': description,
                    'price': price_str,
                    'restaurant_name': restaurant_name,
                    'restaurant_url': url,
                    'menu_type': category_name
                }
                
                all_items.append(menu_item)
        
        print(f"\n[OK] Extracted {len(all_items)} items from menu\n")
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching menu data: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error during scraping: {e}")
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
    
    return all_items


def main():
    url = "https://www.9mileseast.com/"
    scrape_9mileseast_menu(url)


if __name__ == "__main__":
    main()

