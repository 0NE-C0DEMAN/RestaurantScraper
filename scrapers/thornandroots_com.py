"""
Scraper for Thorn + Roots (thornandroots.com)
Scrapes menu from ToastTab catering page using Playwright
Handles: multi-price, multi-size, and add-ons
"""

import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


RESTAURANT_NAME = "Thorn + Roots"
RESTAURANT_URL = "https://www.thornandroots.com/"

MENU_URL = "https://www.toasttab.com/catering/thornandroots"


def extract_menu_from_page(page) -> List[Dict]:
    """Extract menu items from the rendered page using proper DOM structure"""
    items = []
    
    # Wait for page to be interactive
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)
        page.wait_for_timeout(10000)  # Wait longer for dynamic content
    except:
        pass
    
    # Extract using JavaScript - find all menu item links
    try:
        items_data = page.evaluate("""
            () => {
                const items = [];
                const seen = new Set();
                
                // Find all links that point to catering items
                const links = document.querySelectorAll('a[href*="catering"], a[href*="thornandroots"]');
                
                links.forEach(link => {
                    // Skip if it's a navigation link
                    const href = link.getAttribute('href') || '';
                    if (href.includes('mode=fulfillment') || !href.includes('catering')) {
                        // This is likely a menu item
                    } else if (!href.includes('catering') && !href.includes('thornandroots')) {
                        return; // Skip non-menu links
                    }
                    
                    // Get the container - could be the link itself or a parent
                    const container = link;
                    const text = container.innerText || '';
                    
                    // Skip if no price
                    const priceMatch = text.match(/\\$[\\d,]+(?:\\.\\d{2})?/);
                    if (!priceMatch) return;
                    
                    const price = priceMatch[0];
                    
                    // Extract name - usually the first line or heading
                    let name = null;
                    const nameElem = container.querySelector('h3, h4, [class*="name"], [class*="title"], div:first-child > div:first-child');
                    if (nameElem) {
                        name = nameElem.innerText.trim();
                    } else {
                        // Try to get first meaningful line
                        const lines = text.split('\\n').filter(l => l.trim().length > 0);
                        for (const line of lines) {
                            const cleanLine = line.trim();
                            if (cleanLine.length > 3 && cleanLine.length < 200 && 
                                !cleanLine.includes('$') && 
                                !cleanLine.toLowerCase().includes('serves') &&
                                !cleanLine.toLowerCase().includes('includes') &&
                                !cleanLine.toLowerCase().includes('choice')) {
                                name = cleanLine;
                                break;
                            }
                        }
                    }
                    
                    if (!name) return;
                    
                    // Clean up name
                    name = name.split('SERVES')[0].split('Choice')[0].split('Includes')[0].trim();
                    if (name.length < 3 || name.length > 200) return;
                    
                    // Extract description
                    let description = null;
                    const descElem = container.querySelector('p, [class*="description"]');
                    if (descElem) {
                        description = descElem.innerText.trim();
                    } else {
                        // Look for text after name, before price
                        const nameIndex = text.indexOf(name);
                        const priceIndex = text.indexOf(price);
                        if (nameIndex >= 0 && priceIndex > nameIndex) {
                            const descText = text.substring(nameIndex + name.length, priceIndex).trim();
                            if (descText.length > 5 && descText.length < 1000) {
                                description = descText;
                            }
                        }
                    }
                    
                    // Skip cookie/consent items
                    if (name.toLowerCase().includes('cookie') || 
                        name.toLowerCase().includes('consent') ||
                        name.toLowerCase().includes('privacy')) {
                        return;
                    }
                    
                    // Find section by looking up the DOM tree
                    let section = 'Menu';
                    let parent = link.parentElement;
                    for (let i = 0; i < 15 && parent; i++) {
                        const heading = parent.querySelector('h2, h3, [class*="heading"], [class*="title"]');
                        if (heading) {
                            const headingText = heading.innerText.trim();
                            if (headingText && headingText.length < 150 && 
                                !headingText.toLowerCase().includes('cookie') && 
                                !headingText.toLowerCase().includes('consent') &&
                                !headingText.toLowerCase().includes('thorn + roots') &&
                                headingText !== name) {
                                section = headingText;
                                break;
                            }
                        }
                        parent = parent.parentElement;
                    }
                    
                    // Create unique key
                    const key = (name + price).toLowerCase().replace(/\\s+/g, '');
                    if (seen.has(key)) return;
                    seen.add(key);
                    
                    items.push({
                        name: name,
                        description: description || null,
                        price: price,
                        section: section
                    });
                });
                
                return items;
            }
        """)
        
        if items_data:
            items.extend(items_data)
            print(f"  [DEBUG] Extracted {len(items_data)} items")
    except Exception as e:
        print(f"  [WARNING] Error in JavaScript extraction: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def scrape_thornandroots() -> List[Dict]:
    """Main scraping function"""
    print("=" * 60)
    print(f"Scraping {RESTAURANT_NAME} from ToastTab")
    print("=" * 60)
    
    all_items = []
    
    with sync_playwright() as p:
        print("\n[1] Launching browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        print(f"[2] Navigating to {MENU_URL}...")
        try:
            page.goto(MENU_URL, wait_until='load', timeout=60000)
            print("[OK] Page loaded")
        except Exception as e:
            print(f"[ERROR] Failed to load page: {e}")
            browser.close()
            return []
        
        # Wait for content to load
        print("\n[3] Waiting for menu content...")
        page.wait_for_timeout(10000)  # Wait for API calls and dynamic content
        
        print("\n[4] Extracting menu items from page...")
        page_items = extract_menu_from_page(page)
        print(f"[OK] Found {len(page_items)} items from page")
        
        # Filter out invalid items
        valid_items = []
        for item in page_items:
            name = item.get('name', '').strip()
            price = item.get('price', '')
            if name and len(name) >= 3 and len(name) <= 200 and price:
                if not any(word in name.lower() for word in ['cookie', 'consent', 'privacy', 'manage', 'preference']):
                    valid_items.append(item)
        
        all_items.extend(valid_items)
        
        # Format items
        for item in all_items:
            item['restaurant_name'] = RESTAURANT_NAME
            item['restaurant_url'] = RESTAURANT_URL
            item['menu_type'] = "Menu"
            item['menu_name'] = item.get('section', 'Menu')
        
        browser.close()
    
    print(f"\n[OK] Extracted {len(all_items)} items total")
    
    return all_items


if __name__ == "__main__":
    items = scrape_thornandroots()
    
    # Save to JSON
    output_dir = "output"
    output_dir_path = Path(__file__).parent.parent / output_dir
    output_dir_path.mkdir(exist_ok=True)
    output_file = output_dir_path / "thornandroots_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")
