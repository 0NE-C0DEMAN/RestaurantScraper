"""
Scraper for: https://www.mixedbreedbrewingvp.com/
Extracts menu items from the menu page using Wix restaurant menu component
Uses Playwright to click "Show More" buttons and load all add-ons
"""

import json
import re
import asyncio
from pathlib import Path
from typing import List, Dict
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed. Install with: pip install playwright")


def extract_addons(item_container):
    """
    Extract add-ons from an item container.
    Returns a list of tuples: [(addon_name, addon_price), ...]
    Add-ons use modifier group structure:
    - data-hook="item.modifierGroups" contains all modifiers
    - data-hook="item.modifier.*" are individual modifier items
    - data-hook="modifier.name" is the modifier name
    - data-hook="modifier.price" is the modifier price
    """
    addons = []
    
    # Find the modifier groups container
    modifier_groups = item_container.find(attrs={'data-hook': 'item.modifierGroups'})
    if not modifier_groups:
        return addons
    
    # Find all modifier items (data-hook="item.modifier.*")
    modifier_items = modifier_groups.find_all(attrs={'data-hook': re.compile(r'item\.modifier\.', re.I)})
    
    for modifier_item in modifier_items:
        # Extract modifier name
        name_elem = modifier_item.find(attrs={'data-hook': 'modifier.name'})
        if not name_elem:
            continue
        
        addon_name = name_elem.get_text(strip=True)
        if not addon_name:
            continue
        
        # Extract modifier price
        price_elem = modifier_item.find(attrs={'data-hook': 'modifier.price'})
        if not price_elem:
            continue
        
        price_text = price_elem.get_text(strip=True)
        if not price_text:
            continue
        
        # Format price
        if not price_text.startswith('$'):
            price_match = re.search(r'(\d+\.?\d*)', price_text)
            if price_match:
                addon_price = f"${price_match.group(1)}"
            else:
                addon_price = price_text
        else:
            addon_price = price_text
        
        addons.append((addon_name, addon_price))
    
    return addons


def format_price_with_addons(base_price, addons):
    """
    Format price string with add-ons.
    Example: "$10.35 / Add Bacon $3.11 / Add Grilled Chicken $4.14 / Add Short Rib $8.28"
    """
    if not addons:
        return base_price
    
    addon_strs = [f"Add {name} {price}" for name, price in addons]
    return f"{base_price} / {' / '.join(addon_strs)}"


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
        
        print(f"  Processing section: {section_name}")
        
        # Find all items in this section using data-hook="item.container"
        item_containers = section.find_all(attrs={'data-hook': 'item.container'})
        
        if len(item_containers) == 0:
            print(f"    [WARNING] No items found in section: {section_name}")
            continue
        
        print(f"    Found {len(item_containers)} items in section: {section_name}")
        
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
                
                # Check for price variants first (data-hook="item.priceVariants")
                price_variants_elem = item_container.find(attrs={'data-hook': 'item.priceVariants'})
                
                if price_variants_elem:
                    # Extract all variants
                    variants = price_variants_elem.find_all(attrs={'data-hook': 'item.variant'})
                    
                    if variants:
                        # Create an item for each variant
                        for variant in variants:
                            variant_name_elem = variant.find(attrs={'data-hook': 'variant.name'})
                            variant_price_elem = variant.find(attrs={'data-hook': 'variant.price'})
                            
                            if variant_name_elem and variant_price_elem:
                                variant_name = variant_name_elem.get_text(strip=True)
                                variant_price_text = variant_price_elem.get_text(strip=True)
                                
                                # Format price
                                price = ""
                                if variant_price_text:
                                    if not variant_price_text.startswith('$'):
                                        price_match = re.search(r'(\d+\.?\d*)', variant_price_text)
                                        if price_match:
                                            price = f"${price_match.group(1)}"
                                        else:
                                            price = variant_price_text
                                    else:
                                        price = variant_price_text
                                
                                # Combine item name with variant name
                                full_item_name = f"{item_name} - {variant_name}" if variant_name else item_name
                                
                                # Extract add-ons and include them in the price
                                addons = extract_addons(item_container)
                                formatted_price = format_price_with_addons(price, addons)
                                
                                items.append({
                                    'name': full_item_name,
                                    'description': description,
                                    'price': formatted_price,
                                    'menu_type': section_name,
                                })
                    else:
                        # No variants found, try regular price
                        price_elem = item_container.find(attrs={'data-hook': 'item.price'})
                        price = ""
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            if price_text:
                                if not price_text.startswith('$'):
                                    price_match = re.search(r'(\d+\.?\d*)', price_text)
                                    if price_match:
                                        price = f"${price_match.group(1)}"
                                    else:
                                        price = price_text
                                else:
                                    price = price_text
                        
                        if price:
                            # Extract add-ons and include them in the price
                            addons = extract_addons(item_container)
                            formatted_price = format_price_with_addons(price, addons)
                            
                            items.append({
                                'name': item_name,
                                'description': description,
                                'price': formatted_price,
                                'menu_type': section_name,
                            })
                else:
                    # No price variants, use regular price
                    price_elem = item_container.find(attrs={'data-hook': 'item.price'})
                    if not price_elem:
                        price_elem = item_container.find(attrs={'data-hook': 'item.price'})
                    
                    price = ""
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        if price_text:
                            if not price_text.startswith('$'):
                                price_match = re.search(r'(\d+\.?\d*)', price_text)
                                if price_match:
                                    price = f"${price_match.group(1)}"
                                else:
                                    price = price_text
                            else:
                                price = price_text
                    
                    # Extract add-ons and include them in the price
                    addons = extract_addons(item_container)
                    formatted_price = format_price_with_addons(price, addons)
                    
                    # Include items even without prices (some menu items might not have prices)
                    items.append({
                        'name': item_name,
                        'description': description,
                        'price': formatted_price,
                        'menu_type': section_name,
                    })
                
            except Exception as e:
                print(f"    [ERROR] Error processing item: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    return items


async def load_page_with_playwright(url: str) -> str:
    """
    Load the page using Playwright, click all "Show More" buttons to reveal hidden add-ons,
    and return the HTML content.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError("Playwright is required for this scraper. Install with: pip install playwright")
    
    async with async_playwright() as p:
        # Launch browser in headless mode
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        try:
            # Set cookies and headers
            await context.add_cookies([
                {
                    'name': 'server-session-bind',
                    'value': '2d90633c-4e26-4e70-a3de-c628722cbae0',
                    'domain': '.mixedbreedbrewingvp.com',
                    'path': '/'
                },
                {
                    'name': 'XSRF-TOKEN',
                    'value': '1767254239|6XZQ4htcAU3A',
                    'domain': '.mixedbreedbrewingvp.com',
                    'path': '/'
                }
            ])
            
            print("  Loading page with Playwright...")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Wait for page to be interactive (use a more lenient approach)
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
            except:
                # If networkidle times out, just wait a bit and continue
                await asyncio.sleep(3)
            
            await asyncio.sleep(2)  # Additional wait for dynamic content
            
            # Find and click all "Show More" buttons
            print("  Clicking 'Show More' buttons to reveal all add-ons...")
            show_more_buttons = await page.query_selector_all('[data-hook="modifierGroup.showButton"]')
            
            clicked_count = 0
            for button in show_more_buttons:
                try:
                    # Scroll button into view
                    await button.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    
                    # Click the button
                    await button.click()
                    clicked_count += 1
                    await asyncio.sleep(0.5)  # Wait for content to load
                except Exception as e:
                    print(f"    [WARNING] Could not click button: {e}")
                    continue
            
            if clicked_count > 0:
                print(f"  [OK] Clicked {clicked_count} 'Show More' button(s)")
                # Wait a bit more for all content to load
                await asyncio.sleep(2)
            
            # Scroll to bottom to trigger any lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            
            # Get the final HTML
            html_content = await page.content()
            
            await browser.close()
            return html_content
            
        except Exception as e:
            await browser.close()
            raise e


def scrape_mixedbreedbrewingvp_menu(base_url: str = None) -> List[Dict]:
    """
    Main function to scrape all menus from mixedbreedbrewingvp.com
    Scrapes Food Menu, Beer Menu, and Entrées
    
    Args:
        base_url: Base URL (optional, defaults to menu page)
    
    Returns:
        List of dictionaries containing all menu items from all menus
    """
    all_items = []
    restaurant_name = "Mixed Breed Brewing"
    
    # Define all menus to scrape
    menus = [
        ("https://www.mixedbreedbrewingvp.com/menu?location=Location+1", "Food Menu"),
        ("https://www.mixedbreedbrewingvp.com/menu?location=Location+1&menu=beer-menu", "Beer Menu"),
        ("https://www.mixedbreedbrewingvp.com/menu?location=Location+1&menu=entrees", "Entrées")
    ]
    
    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use a consistent output filename
    output_json = output_dir / 'www_mixedbreedbrewingvp_com_menu.json'
    print(f"Output file: {output_json}\n")
    
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5',
        'cache-control': 'no-cache',
        'cookie': 'server-session-bind=2d90633c-4e26-4e70-a3de-c628722cbae0; XSRF-TOKEN=1767254239|6XZQ4htcAU3A; hs=377252671; svSession=6534cf70618b6149ab69a5e2f2ccfe4c07d3c250c8d8b09b90b98d8984a475ed802476b827abebd1effdde9dd5549e711e60994d53964e647acf431e4f798bcde7d7f63ae3b34f03a7aeb3ade4ff71a4501dede30c1713cc6d24535957040b343aff52e721ef6bfb4c013c68e8363b16b36f3324044ad1d4cad3936c102b0c3e7b6633b59518d985eeb07b40ff2ec2b3; bSession=60db09b1-9de5-47af-8f35-a07de134d880|1; client-session-bind=2d90633c-4e26-4e70-a3de-c628722cbae0; ssr-caching=cache#desc=hit#varnish=hit_miss_prefetch#dc#desc=fastly_sea1_g',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.mixedbreedbrewingvp.com/menu?location=Location+1',
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
    
    try:
        # Scrape each menu
        for menu_url, menu_name in menus:
            print(f"\n{'='*60}")
            print(f"Scraping {menu_name}")
            print(f"{'='*60}\n")
            
            # Load page with Playwright to click "Show More" buttons and get all add-ons
            print(f"Loading {menu_name} with Playwright...")
            html_content = asyncio.run(load_page_with_playwright(menu_url))
            
            print(f"[OK] Received HTML content with all add-ons loaded\n")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract items
            print(f"Extracting items from {menu_name}...")
            items = extract_menu_items_from_html(soup)
            
            if items:
                for item in items:
                    item['restaurant_name'] = restaurant_name
                    item['restaurant_url'] = "https://www.vanpattengolf.com/mixed-breed-brewing"
                    item['menu_name'] = menu_name
                all_items.extend(items)
                print(f"[OK] Extracted {len(items)} items from {menu_name}\n")
            else:
                print(f"[WARNING] No items found in {menu_name}\n")
        
        print(f"\n{'='*60}")
        print(f"[OK] Extracted {len(all_items)} total items from all menus")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Save to JSON
    print(f"Saved {len(all_items)} items to: {output_json}\n")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    return all_items


if __name__ == "__main__":
    scrape_mixedbreedbrewingvp_menu()

