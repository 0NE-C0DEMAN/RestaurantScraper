"""
Playwright-based scraper for King Brothers Dairy
Visits all sections and uses "View ALL" functionality when available
"""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict
from pathlib import Path


# All sections from the website
SECTIONS = [
    {"name": "Featured Products", "url": "https://kingbrothersdairy.com/summary.php?go=products", "menu_type": "Featured Products"},
    {"name": "Pasta", "url": "https://kingbrothersdairy.com/pasta_frozen", "menu_type": "Pasta"},
    {"name": "Holiday Gift Ideas", "url": "https://kingbrothersdairy.com/holiday-gift-ideas", "menu_type": "Holiday Gift Ideas"},
    {"name": "Dairy/Eggs", "url": "https://kingbrothersdairy.com/c-331-dairy-eggs.html", "menu_type": "Dairy/Eggs"},
    {"name": "Meat", "url": "https://kingbrothersdairy.com/c-386-meat.html", "menu_type": "Meat"},
    {"name": "Pantry Staples", "url": "https://kingbrothersdairy.com/c-404-pantry-staples.html", "menu_type": "Pantry Staples"},
    {"name": "Taste of the Farm Bundles", "url": "https://kingbrothersdairy.com/taste-of-the-farm-bundles", "menu_type": "Taste of the Farm Bundles"},
    {"name": "Beverages", "url": "https://kingbrothersdairy.com/c-395-beverages.html", "menu_type": "Beverages"},
    {"name": "Fresh Produce", "url": "https://kingbrothersdairy.com/c-373-fresh-produce.html", "menu_type": "Fresh Produce"},
    {"name": "Snacks", "url": "https://kingbrothersdairy.com/c-394-snacks.html", "menu_type": "Snacks"},
    {"name": "Frozen Pizza/ Frozen Chicken Pot Pie", "url": "https://kingbrothersdairy.com/frozen-pizza", "menu_type": "Frozen Pizza"},
    {"name": "Soup", "url": "https://kingbrothersdairy.com/pasta-sauces-soups", "menu_type": "Soup"},
    {"name": "Desserts", "url": "https://kingbrothersdairy.com/desserts", "menu_type": "Desserts"},
    {"name": "Helpful Delivery Items", "url": "https://kingbrothersdairy.com/c-335-helpful-delivery-items.html", "menu_type": "Helpful Delivery Items"},
]


def parse_products_from_html(html: str, menu_name: str) -> List[Dict]:
    """Parse products from HTML using BeautifulSoup"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    restaurant_name = "King Brothers Dairy"
    restaurant_url = "https://www.kingbrothersdairy.com/"
    
    product_blocks = soup.find_all('div', class_='product-block')
    
    for product_block in product_blocks:
        # Get product name
        name_elem = product_block.find('h2', itemprop='name')
        if not name_elem:
            continue
        
        name_link = name_elem.find('a')
        item_name = name_link.get_text(strip=True) if name_link else name_elem.get_text(strip=True)
        
        # Get description
        desc_elem = product_block.find('p', class_='product-summary', itemprop='description')
        description = ""
        if desc_elem:
            description = desc_elem.get_text(separator=' ', strip=True)
        
        # Get price - check for sale price first, then regular price
        price_elem = product_block.find('span', class_='product-sale-price', itemprop='price')
        if not price_elem:
            price_elem = product_block.find('span', class_='product-price', itemprop='price')
        
        price = ""
        if price_elem:
            price_content = price_elem.get('content', '')
            if price_content:
                price = f"${price_content}"
            else:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'\$?(\d+(?:\.\d{2})?)', price_text)
                if price_match:
                    price = f"${price_match.group(1)}"
        
        items.append({
            'name': item_name,
            'description': description,
            'price': price,
            'menu_type': menu_name,
            'restaurant_name': restaurant_name,
            'restaurant_url': restaurant_url,
            'menu_name': menu_name
        })
    
    return items


async def scrape_section(page, section: Dict) -> List[Dict]:
    """Scrape a single section, using View ALL if available"""
    print(f"\n{'='*60}")
    print(f"Scraping: {section['name']}")
    print(f"URL: {section['url']}")
    print(f"{'='*60}")
    
    try:
        # Navigate to the section
        print(f"\n[1] Navigating to section...")
        await page.goto(section['url'], wait_until='networkidle', timeout=60000)
        await page.wait_for_load_state('domcontentloaded')
        await asyncio.sleep(2)
        print("[OK] Page loaded")
        
        # Try to find and use "View ALL" if available
        print(f"\n[2] Checking for 'View ALL' option...")
        view_all_available = False
        
        # Check for select2 dropdown
        select2_container = page.locator('.select2-selection__rendered').filter(has_text='View').first
        if await select2_container.count() > 0:
            print("[OK] Found select2 dropdown with View options")
            view_all_available = True
            
            # Scroll into view
            await select2_container.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            
            # Click to open dropdown
            print("[3] Opening dropdown...")
            await select2_container.click()
            await asyncio.sleep(1)
            
            # Look for "View ALL" option
            view_all_option = page.locator('.select2-results__option').filter(has_text='View ALL').first
            if await view_all_option.count() > 0:
                print("[4] Selecting 'View ALL'...")
                await view_all_option.wait_for(state='visible', timeout=10000)
                await view_all_option.click()
                print("[OK] Selected View ALL")
                
                # Wait for products to load
                print("[5] Waiting for all products to load...")
                await page.wait_for_load_state('networkidle', timeout=30000)
                await asyncio.sleep(3)
                print("[OK] Products loaded")
            else:
                print("[INFO] 'View ALL' option not found in dropdown, using current view")
                # Close dropdown if it's open
                await page.keyboard.press('Escape')
                await asyncio.sleep(1)
        else:
            # Check for regular select element
            select_elem = page.locator('select.show_product_quantity').first
            if await select_elem.count() > 0:
                print("[OK] Found regular select dropdown")
                view_all_available = True
                await select_elem.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                
                # Try to select "View ALL" (value="0")
                try:
                    await select_elem.select_option(value="0")
                    print("[OK] Selected View ALL")
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    await asyncio.sleep(3)
                except:
                    print("[INFO] Could not select View ALL, using current view")
            else:
                print("[INFO] No pagination dropdown found, using current view")
        
        # Extract products
        print(f"\n[6] Extracting products...")
        html = await page.content()
        items = parse_products_from_html(html, section['menu_type'])
        print(f"[OK] Extracted {len(items)} products")
        
        # Display sample
        if items:
            print(f"\n[7] Sample products:")
            for i, item in enumerate(items[:3], 1):
                print(f"  {i}. {item['name']} - {item['price']}")
            if len(items) > 3:
                print(f"  ... and {len(items) - 3} more")
        
        return items
        
    except Exception as e:
        print(f"[ERROR] Error scraping {section['name']}: {e}")
        import traceback
        traceback.print_exc()
        return []


async def scrape_kingbrothersdairy_all_sections():
    """Scrape all sections from King Brothers Dairy using Playwright"""
    all_items = []
    
    async with async_playwright() as p:
        print("\n" + "="*60)
        print("King Brothers Dairy - Full Scraper (Playwright)")
        print("="*60)
        print(f"Total sections to scrape: {len(SECTIONS)}")
        print("="*60)
        
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            # Scrape each section
            for i, section in enumerate(SECTIONS, 1):
                print(f"\n\n[{i}/{len(SECTIONS)}] Processing: {section['name']}")
                items = await scrape_section(page, section)
                all_items.extend(items)
                print(f"[OK] Section complete: {len(items)} items")
                
                # Small delay between sections
                await asyncio.sleep(1)
            
        finally:
            await browser.close()
    
    return all_items


def save_results(items: List[Dict]):
    """Save results to JSON file"""
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / 'kingbrothersdairy_com.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Results saved to: {output_file}")
    return output_file


if __name__ == '__main__':
    print("\n" + "="*60)
    print("King Brothers Dairy - Playwright Scraper")
    print("="*60)
    
    results = asyncio.run(scrape_kingbrothersdairy_all_sections())
    
    print("\n" + "="*60)
    print("SCRAPING COMPLETE")
    print("="*60)
    print(f"Total items found: {len(results)}")
    
    # Group by menu type
    from collections import Counter
    menu_counts = Counter(item['menu_type'] for item in results)
    print(f"\nItems by section:")
    for menu_type, count in sorted(menu_counts.items()):
        print(f"  {menu_type}: {count} items")
    
    # Save results
    output_file = save_results(results)
    print(f"\n[OK] All done! Results saved to: {output_file}")
    print("="*60)

