"""
Scraper for: http://harusaratoga.com/
Restaurant: Haru
Uses Playwright to render the Vue.js application and extract menu items
Menu URL: https://order.5189788888.honormenus.com/
"""

import json
import re
from pathlib import Path
from typing import Dict, List
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup


def extract_menu_items_from_rendered_html(html: str) -> List[Dict]:
    """
    Extract menu items from the rendered HTML.
    The page structure has categories and items with prices.
    """
    items = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main menu container
    # Based on the browser snapshot, items are in a structure with categories
    # Categories are in elements with class containing "category" or similar
    # Items have prices in $ format
    
    # Try to find menu items by looking for price patterns
    # Items seem to be in divs with specific structure
    
    # Find all elements that contain prices (look for $X.XX pattern)
    all_elements = soup.find_all(text=re.compile(r'\$\d+\.\d{2}'))
    
    # Group items by finding their parent containers
    processed_items = set()
    
    # Look for the menu content area - based on browser snapshot structure
    # The items appear to be in a container with category groups
    menu_container = soup.find('div', class_=lambda x: x and ('menu' in x.lower() or 'category' in x.lower() or 'wrap' in x.lower()))
    
    if not menu_container:
        # Try to find by looking for the structure we saw in browser
        # Items are in a structure like: <div>Item Name</div><div>$Price</div>
        menu_container = soup.find('body')
    
    if menu_container:
        # Find all price elements and work backwards to find item names
        price_elements = menu_container.find_all(text=re.compile(r'\$\d+\.\d{2}'))
        
        for price_text in price_elements:
            price_match = re.search(r'\$(\d+\.\d{2})', price_text)
            if not price_match:
                continue
            
            price = f"${price_match.group(1)}"
            price_elem = price_text.parent if hasattr(price_text, 'parent') else None
            
            if not price_elem:
                continue
            
            # Find the item name - it should be nearby
            # Look for sibling or parent elements
            item_name = ""
            description = ""
            category = ""
            
            # Try to find name in previous siblings or parent
            current = price_elem
            for _ in range(5):  # Check up to 5 levels up
                if not current:
                    break
                
                # Look for text that might be the item name
                # Item names are usually before the price
                prev_sibling = current.find_previous_sibling()
                if prev_sibling:
                    name_text = prev_sibling.get_text(strip=True)
                    if name_text and len(name_text) > 2 and name_text != price:
                        # Check if it's not a category name (categories are usually shorter and in caps)
                        if not (name_text.isupper() and len(name_text.split()) <= 3):
                            item_name = name_text
                            break
                
                # Also check parent for name
                parent = current.parent
                if parent:
                    # Look for text nodes or child elements with the name
                    for child in parent.children:
                        if hasattr(child, 'get_text'):
                            child_text = child.get_text(strip=True)
                            if child_text and child_text != price and len(child_text) > 2:
                                if '$' not in child_text and not child_text.isdigit():
                                    if not item_name:
                                        item_name = child_text
                                    elif len(child_text) > len(item_name):
                                        # Longer text might be description
                                        description = child_text
                
                current = current.parent
            
            # If we found a name, create an item
            if item_name and item_name not in processed_items:
                processed_items.add(item_name)
                
                # Try to find category by looking at section headers
                # Categories are usually in the left sidebar or as section headers
                category_elem = price_elem
                for _ in range(10):
                    if not category_elem:
                        break
                    # Look for class names that might indicate category
                    if hasattr(category_elem, 'get'):
                        class_name = category_elem.get('class', [])
                        if class_name:
                            class_str = ' '.join(class_name)
                            if 'category' in class_str.lower() or 'section' in class_str.lower():
                                cat_text = category_elem.get_text(strip=True)
                                if cat_text and len(cat_text) > 2:
                                    category = cat_text
                                    break
                    
                    # Check parent
                    category_elem = category_elem.parent if hasattr(category_elem, 'parent') else None
                
                items.append({
                    'name': item_name,
                    'description': description,
                    'price': price,
                    'category': category or 'Menu'
                })
    
    # Alternative approach: Look for specific structure patterns
    # Based on browser snapshot, items might be in a more structured format
    # Let's try a different approach - look for divs that contain both name and price
    
    if len(items) < 10:  # If we didn't find many items, try alternative method
        # Look for patterns like: <div>Name</div><div>$Price</div> or similar
        # Find all divs and look for price patterns nearby
        all_divs = soup.find_all('div')
        
        for div in all_divs:
            div_text = div.get_text(strip=True)
            
            # Check if this div contains a price
            price_match = re.search(r'\$(\d+\.\d{2})', div_text)
            if price_match:
                price = f"${price_match.group(1)}"
                
                # Extract name (everything before the price)
                name_part = div_text.split('$')[0].strip()
                
                # Look for description in siblings or children
                description = ""
                
                # Check if there's a description in a sibling or child
                for sibling in div.find_next_siblings():
                    sib_text = sibling.get_text(strip=True)
                    if sib_text and '$' not in sib_text and len(sib_text) > 10:
                        description = sib_text
                        break
                
                # Also check children
                for child in div.children:
                    if hasattr(child, 'get_text'):
                        child_text = child.get_text(strip=True)
                        if child_text and '$' not in child_text and len(child_text) > 10:
                            if not description or len(child_text) > len(description):
                                description = child_text
                
                # Clean up name (remove price if it's there)
                name = name_part.replace(price, '').strip()
                
                if name and len(name) > 2 and name not in processed_items:
                    processed_items.add(name)
                    items.append({
                        'name': name,
                        'description': description,
                        'price': price,
                        'category': 'Menu'
                    })
    
    return items


def scrape_haru_menu() -> List[Dict]:
    """
    Main function to scrape Haru menu using Playwright.
    """
    menu_url = "https://order.5189788888.honormenus.com/"
    restaurant_url = "http://harusaratoga.com/"
    restaurant_name = "Haru"
    
    print("=" * 60)
    print(f"Scraping: {restaurant_url}")
    print(f"Menu URL: {menu_url}")
    print("=" * 60)
    
    all_items = []
    
    try:
        with sync_playwright() as p:
            print("\n[1/1] Loading page with Playwright...")
            
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # Navigate to the page
            print(f"  Navigating to {menu_url}...")
            page.goto(menu_url, wait_until='networkidle', timeout=60000)
            
            # Wait for menu to load (Vue.js app needs time to render)
            print("  Waiting for menu to render...")
            try:
                # Wait for menu items to appear (look for price elements)
                page.wait_for_selector('text=/$', timeout=30000)
            except PlaywrightTimeoutError:
                print("  [WARNING] Timeout waiting for menu, proceeding anyway...")
            
            # Wait a bit more for Vue to finish rendering
            page.wait_for_timeout(3000)
            
            # Get the rendered HTML
            html = page.content()
            print(f"  [OK] Page loaded, HTML length: {len(html)}")
            
            # Extract menu items
            print("  Extracting menu items...")
            items = extract_menu_items_from_rendered_html(html)
            
            # Use Playwright's JavaScript evaluation to properly extract structured data
            print("  [INFO] Using JavaScript extraction to parse DOM structure...")
            try:
                menu_data = page.evaluate("""
                    () => {
                        const items = [];
                        const categoryNames = [
                            'Soup & Salad', 'Cold Appetizer', 'Hot Appetizer', 'A La Carte',
                            'Roll', 'Signature Rolls', 'Tempura', 'Teriyaki', 'Udon',
                            'Japanese Fried Rice', 'Bento Special', "Chef's Suggestions",
                            'Hibachi Entree', 'Side Order', "Kid's Menu", 'Sushi Entrees',
                            'Haru Love Boat Special', 'Non Alcoholic Drinks', 'Bubble Milk Tea'
                        ];
                        
                        // Find all price elements using the menuPrice class
                        const priceElements = Array.from(document.querySelectorAll('.menuPrice'));
                        
                        // Track current category as we iterate
                        let currentCategory = '';
                        
                        // Also find category headers to track sections
                        const categoryHeaders = Array.from(document.querySelectorAll('*')).filter(el => {
                            const text = (el.textContent || '').trim();
                            return categoryNames.includes(text);
                        });
                        
                        priceElements.forEach(priceEl => {
                            // Get the price
                            const priceText = (priceEl.textContent || '').match(/\\$\\d+\\.\\d{2}/);
                            if (!priceText) return;
                            
                            const price = priceText[0];
                            
                            // Find the item container - usually a parent div
                            let container = priceEl.parentElement;
                            let name = '';
                            let description = '';
                            let category = '';
                            
                            // Look for name and description in siblings or parent
                            // Structure: name element, description element (optional), price element
                            const siblings = container ? Array.from(container.children) : [];
                            
                            for (let sibling of siblings) {
                                const text = (sibling.textContent || '').trim();
                                
                                // Skip if it's the price element or empty
                                if (sibling === priceEl || !text || text === price) continue;
                                
                                // Skip category names and navigation text
                                if (categoryNames.includes(text) || 
                                    text.includes('Haru') || 
                                    text.includes('518-978') ||
                                    text.includes('Old Gick') ||
                                    text.includes('Start Order') ||
                                    text.includes('Sign In') ||
                                    text.length < 3) continue;
                                
                                // If it looks like a price, skip
                                if (/^\\$/.test(text)) continue;
                                
                                // Check if this is likely the name (shorter, more specific)
                                if (!name && text.length > 3 && text.length < 100) {
                                    // Check if it's not a description (descriptions are usually longer)
                                    if (text.length < 50 && !text.includes(',')) {
                                        name = text;
                                    } else if (text.length >= 20) {
                                        description = text;
                                    }
                                } else if (text.length > description.length && text.length > 20) {
                                    // Longer text is likely description
                                    description = text;
                                }
                            }
                            
                            // If we didn't find name in siblings, look in parent's text
                            if (!name && container) {
                                const containerText = container.textContent || '';
                                const parts = containerText.split(price);
                                if (parts[0]) {
                                    const namePart = parts[0].trim();
                                    // Clean up - remove category names and other noise
                                    const cleaned = namePart.split('\\n')
                                        .map(p => p.trim())
                                        .filter(p => p && 
                                               !categoryNames.includes(p) &&
                                               !p.includes('Haru') &&
                                               !p.includes('518') &&
                                               p.length > 2 &&
                                               p.length < 100)
                                        .pop();
                                    
                                    if (cleaned && cleaned.length > 2) {
                                        name = cleaned;
                                    }
                                }
                                if (parts[1]) {
                                    const descPart = parts[1].trim();
                                    if (descPart.length > 10) {
                                        description = descPart;
                                    }
                                }
                            }
                            
                            // Find category by looking for section headers above this item
                            let current = priceEl;
                            for (let i = 0; i < 10; i++) {
                                if (!current) break;
                                
                                // Check if current element or sibling contains a category name
                                const checkCategory = (el) => {
                                    if (!el) return '';
                                    const text = (el.textContent || '').trim();
                                    for (let cat of categoryNames) {
                                        if (text === cat || text.includes(cat)) {
                                            return cat;
                                        }
                                    }
                                    return '';
                                };
                                
                                category = checkCategory(current) || 
                                          checkCategory(current.previousElementSibling) ||
                                          checkCategory(current.parentElement);
                                
                                if (category) break;
                                
                                current = current.parentElement;
                            }
                            
                            // Only add if we have a valid name
                            if (name && name.length > 2 && name.length < 200) {
                                // Clean up name - remove any remaining category text
                                name = name.replace(new RegExp(categoryNames.join('|'), 'g'), '').trim();
                                if (name.length > 2) {
                                    items.push({
                                        name: name,
                                        description: description || '',
                                        price: price,
                                        category: category || 'Menu'
                                    });
                                }
                            }
                        });
                        
                        // Remove duplicates based on name and price
                        const seen = new Set();
                        return items.filter(item => {
                            const key = `${item.name}|${item.price}`;
                            if (seen.has(key)) return false;
                            seen.add(key);
                            return true;
                        });
                    }
                """)
                
                if menu_data and len(menu_data) > 0:
                    print(f"  [OK] Found {len(menu_data)} items via JavaScript extraction")
                    items = menu_data
                else:
                    print(f"  [WARNING] JavaScript extraction returned {len(menu_data) if menu_data else 0} items")
            except Exception as e:
                print(f"  [WARNING] JavaScript extraction failed: {e}")
                import traceback
                traceback.print_exc()
            
            browser.close()
            
            print(f"[OK] Extracted {len(items)} items")
            
            # Add metadata to all items
            for item in items:
                item['menu_type'] = item.get('category', 'MENU').upper()
                item['restaurant_name'] = restaurant_name
                item['restaurant_url'] = restaurant_url
                item['menu_name'] = 'Menu'
                # Remove category field if it exists (we use menu_type instead)
                if 'category' in item:
                    del item['category']
            
            all_items.extend(items)
    
    except Exception as e:
        print(f"[ERROR] Error during scraping: {e}")
        import traceback
        traceback.print_exc()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Use harusaratoga_com.json as the output filename
    output_file = output_dir / "harusaratoga_com.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total items found: {len(all_items)}")
    print(f"Saved to: {output_file}")
    print(f"{'='*60}")
    
    return all_items


if __name__ == "__main__":
    scrape_haru_menu()

