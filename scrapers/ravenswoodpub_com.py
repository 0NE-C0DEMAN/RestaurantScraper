"""
Scraper for Ravenswood Pub (ravenswoodpub.com)
"""
import json
import re
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup

# Try to import Playwright
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Get the project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

def fetch_menu_html() -> str:
    """Fetch the menu HTML page"""
    url = "https://ravenswoodpub.com/clifton-park-ravenswood-food-menu"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Referer": "https://ravenswoodpub.com/",
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
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def parse_menu_items(soup: BeautifulSoup, menu_class: str, menu_name: str, menu_type: str) -> List[Dict]:
    """Parse menu items from a specific menu section"""
    items = []
    
    # Find the menu container
    menu_container = soup.find('div', class_=menu_class)
    if not menu_container:
        return items
    
    # Find all section containers
    sections = menu_container.find_all('div', class_='food-menu-grid-item')
    
    for section_div in sections:
        # Find section name (h2)
        section_h2 = section_div.find('h2')
        if not section_h2:
            continue
        
        section_name = section_h2.get_text(strip=True)
        
        # Find section description (food-menu-description) - this may contain addon info or prices
        section_desc_div = section_div.find('div', class_='food-menu-description')
        section_addons = ""
        section_price = ""  # Price that applies to all items in this section
        if section_desc_div:
            section_text = section_desc_div.get_text(strip=True)
            # Check if section description contains prices (e.g., "Personal (4 Cut Round) $14.99 | Large (8 Cut Round) $23.99")
            price_pattern = r'((?:Personal|Large|Small|Cup|Bowl|Half|Full|Regular|Single|Family)\s*\([^)]+\)\s*\$[\d.]+(?:\s*\|\s*(?:Personal|Large|Small|Cup|Bowl|Half|Full|Regular|Single|Family)\s*\([^)]+\)\s*\$[\d.]+)*)'
            price_match = re.search(price_pattern, section_text, re.IGNORECASE)
            if price_match:
                section_price = price_match.group(1).strip()
                # Remove price from section text, rest is addons
                section_addons = re.sub(price_pattern, '', section_text, flags=re.IGNORECASE).strip()
            else:
                section_addons = section_text
        
        # Find all menu items in this section
        food_content = section_div.find('div', class_='food-menu-content')
        if not food_content:
            continue
        
        item_holders = food_content.find_all('div', class_='food-item-holder')
        
        for item_holder in item_holders:
            # Get item name
            title_div = item_holder.find('div', class_='food-item-title')
            if not title_div:
                continue
            
            h3 = title_div.find('h3')
            if not h3:
                continue
            
            item_name = h3.get_text(strip=True)
            
            # Get price
            price_div = item_holder.find('div', class_='food-price')
            price = ""
            if price_div:
                price = price_div.get_text(strip=True)
            
            # Get description
            desc_div = item_holder.find('div', class_='food-item-description')
            description = ""
            if desc_div:
                description = desc_div.get_text(separator=' ', strip=True)
            
            # Check if price is in description (e.g., "Small $5.99 | Large $11.99" or "1 Lb Boneless $15.99 | 12 Bone in $17.99")
            # Extract prices from description if price div is empty
            if not price and description:
                # Look for price patterns with size labels
                # Pattern 1: "Size Label $X | Size Label $Y"
                price_pattern1 = r'((?:Small|Large|Cup|Bowl|Half|Full|Personal|Regular|Single|Family|8 Cut|12 Cut)\s+\$[\d.]+(?:\s*\|\s*(?:Small|Large|Cup|Bowl|Half|Full|Personal|Regular|Single|Family|8 Cut|12 Cut)\s+\$[\d.]+)*)'
                # Pattern 2: "1 Lb X $X | 12 Bone Y $Y" or similar
                price_pattern2 = r'((?:\d+\s*(?:Lb|Bone|oz|piece|pieces|serving|servings)\s+[^$]*?\$[\d.]+(?:\s*\|\s*\d+\s*(?:Lb|Bone|oz|piece|pieces|serving|servings)\s+[^$]*?\$[\d.]+)*))'
                # Pattern 3: Any pattern with $ followed by numbers, possibly with labels before
                price_pattern3 = r'((?:[A-Za-z0-9\s]+\s+)?\$[\d.]+(?:\s*\|\s*(?:[A-Za-z0-9\s]+\s+)?\$[\d.]+)*)'
                
                price_match = None
                for pattern in [price_pattern1, price_pattern2, price_pattern3]:
                    price_match = re.search(pattern, description, re.IGNORECASE)
                    if price_match:
                        price = price_match.group(1).strip()
                        # Remove price from description
                        description = re.sub(re.escape(price), '', description, flags=re.IGNORECASE).strip()
                        # Clean up any remaining separators
                        description = re.sub(r'^\s*[•|]\s*', '', description).strip()
                        break
            
            # If no price found and section has a price, use section price
            if not price and section_price:
                price = section_price
            
            # Format price - ensure it starts with $ if it's a number
            if price:
                # Handle prices like "$24.99/pp" or "$20.99 / per person"
                price = re.sub(r'\s*/\s*(?:pp|per person)', '/pp', price, flags=re.IGNORECASE)
                # Ensure prices have $ symbol
                if not price.startswith('$') and not price.startswith('Half') and not price.startswith('Full') and not price.startswith('Small') and not price.startswith('Large') and not price.startswith('Cup') and not price.startswith('Bowl') and not price.startswith('Personal') and not price.startswith('Regular') and not price.startswith('Single') and not price.startswith('Family') and not price.startswith('1 Lb') and not price.startswith('12 Bone') and not price.startswith('8 Cut') and not price.startswith('12 Cut'):
                    # Check if it's a number
                    if re.match(r'^[\d.]+', price):
                        price = f"${price}"
            
            # Extract addons from description (before removing price)
            addons = []
            addon_texts_to_remove = []  # Track addon text to remove from description
            
            if description:
                # Check for "Choice of:" patterns first
                if 'Choice of:' in description or 'choice of' in description.lower():
                    choice_match = re.search(r'Choice of:?\s*(.+?)(?:\s*•|$)', description, re.IGNORECASE | re.DOTALL)
                    if choice_match:
                        choice_text = choice_match.group(1)
                        # Extract individual choices with prices
                        choices = re.findall(r'([^|]+?)\s*\+\$?([\d.]+)', choice_text)
                        for choice, addon_price in choices:
                            addon_text = choice.strip()
                            if len(addon_text) > 3:
                                addons.append(f"{addon_text} +${addon_price}")
                                addon_texts_to_remove.append(f"Choice of: {choice_text}")
                        # Remove choice text from description
                        description = re.sub(r'Choice of:?\s*.+?(?:\s*•|$)', '', description, flags=re.IGNORECASE | re.DOTALL).strip()
                
                # Look for standalone addon patterns (e.g., "Add X +$Y" or "X +$Y")
                # Pattern 1: "Add [text] +$X"
                addon_pattern1 = r'Add\s+([^+|•]+?)\s*\+\$?([\d.]+)'
                matches1 = re.finditer(addon_pattern1, description, re.IGNORECASE)
                for match in matches1:
                    addon_text = match.group(1).strip()
                    addon_price = match.group(2)
                    if len(addon_text) > 3:
                        addons.append(f"{addon_text} +${addon_price}")
                        addon_texts_to_remove.append(match.group(0))
                
                # Pattern 2: "[text] +$X" (but not if it's part of a price like "Small $5.99" or already captured by Pattern 1)
                # Only match if it doesn't start with "Add" (to avoid duplicates with Pattern 1)
                addon_pattern2 = r'(?<!Add\s)([^|•$]+?)\s*\+\$?([\d.]+)'
                matches2 = re.finditer(addon_pattern2, description, re.IGNORECASE)
                for match in matches2:
                    addon_text = match.group(1).strip()
                    addon_price = match.group(2)
                    # Skip if it looks like a size label (Small, Large, etc.) or if too short
                    # Also skip if it starts with "Add" (already captured by Pattern 1)
                    if (len(addon_text) > 3 and 
                        not addon_text.strip().startswith('Add') and
                        not re.match(r'^(Small|Large|Cup|Bowl|Half|Full|Personal|Regular|Single|Family|1 Lb|12 Bone|8 Cut|12 Cut)', addon_text, re.IGNORECASE) and
                        'Choice of' not in addon_text):
                        # Check if this addon is already in the list (by text content, not exact match)
                        addon_key = f"{addon_text} +${addon_price}"
                        # Normalize for comparison - remove "Add" prefix if present in existing addons
                        existing_addon_texts = [a.split(' +$')[0].replace('Add ', '').strip() for a in addons if ' +$' in a]
                        if addon_text not in existing_addon_texts:
                            addons.append(addon_key)
                            addon_texts_to_remove.append(match.group(0))
            
            # Remove addon text from description
            for addon_text in addon_texts_to_remove:
                description = description.replace(addon_text, '').strip()
            # Clean up extra separators
            description = re.sub(r'\s*\|\s*\|\s*', ' | ', description)  # Remove double separators
            description = re.sub(r'^\s*[|•]\s*', '', description)  # Remove leading separator
            description = re.sub(r'\s*[|•]\s*$', '', description)  # Remove trailing separator
            description = description.strip()
            
            # Combine description and addons
            final_description = description
            if addons:
                addon_str = ' / '.join(addons)
                # Check if addons are already in description to avoid duplication
                if 'Add-ons:' not in final_description:
                    if final_description:
                        final_description += f" | Add-ons: {addon_str}"
                    else:
                        final_description = f"Add-ons: {addon_str}"
            
            # Add section addons if present (and not already included)
            if section_addons and ('Add' in section_addons or '+' in section_addons):
                # Check if section addons are already in description
                if section_addons not in final_description:
                    if final_description:
                        final_description += f" | {section_addons}"
                    else:
                        final_description = section_addons
            
            # Skip if no price and no description
            if not price and not final_description:
                continue
            
            items.append({
                "name": item_name,
                "description": final_description if final_description else None,
                "price": price if price else "",
                "section": section_name,
                "restaurant_name": "Ravenswood Pub",
                "restaurant_url": "https://ravenswoodpub.com/",
                "menu_type": menu_type,
                "menu_name": menu_name
            })
    
    return items

def scrape_ravenswoodpub() -> List[Dict]:
    """Scrape menu from Ravenswood Pub website"""
    print("=" * 60)
    print("Scraping Ravenswood Pub (ravenswoodpub.com)")
    print("=" * 60)
    
    all_items = []
    
    # Fetch HTML
    print("\n[1] Fetching menu HTML...")
    try:
        html_content = fetch_menu_html()
        print(f"  [OK] Fetched {len(html_content)} characters")
    except Exception as e:
        print(f"  [ERROR] Failed to fetch HTML: {e}")
        return []
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Parse each menu
    menus = [
        {"class": "menu_701567", "name": "Menu", "type": "Menu"},
        {"class": "menu_701801", "name": "Buffet Packages", "type": "Buffet Packages"},
        {"class": "menu_702020", "name": "Banquet Menu", "type": "Banquet Menu"}
    ]
    
    for menu_info in menus:
        print(f"\n[2] Parsing {menu_info['name']}...")
        items = parse_menu_items(soup, menu_info['class'], menu_info['name'], menu_info['type'])
        all_items.extend(items)
        print(f"  [OK] Found {len(items)} items")
    
    # Filter out items with no price and no description
    filtered_items = []
    for item in all_items:
        if item.get('price') or item.get('description'):
            filtered_items.append(item)
    
    print(f"\n[3] Filtered {len(all_items) - len(filtered_items)} items with no price and no description")
    all_items = filtered_items
    
    # Save to JSON
    output_file = OUTPUT_DIR / "ravenswoodpub_com.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved {len(all_items)} items to {output_file}")
    
    # Show sample items
    if all_items:
        print(f"\n[4] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            price_str = item.get('price', 'N/A')
            section = item.get('section', 'Menu')
            print(f"  {i}. {item.get('name', 'N/A')} - {price_str} ({section})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items

def scrape_drinks_menu_with_playwright() -> List[Dict]:
    """Scrape drinks menu using Playwright to wait for dynamic content"""
    if not PLAYWRIGHT_AVAILABLE:
        print("[ERROR] Playwright not available. Install with: pip install playwright")
        return []
    
    items = []
    
    print("\n[1] Loading drinks menu page with Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            
            # Navigate to drinks menu
            url = "https://ravenswoodpub.com/clifton-park-ravenswood-drink-menu"
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Wait for the Untappd menu to load
            print("  Waiting for Untappd menu content to load...")
            try:
                # Wait for beer items to appear (h4 headings or specific Untappd structure)
                page.wait_for_selector('h3, h4', timeout=30000)
            except:
                pass
            
            # Wait additional time for all content to render
            page.wait_for_timeout(8000)
            
            # Click all "More Info" links to expand descriptions
            print("  Expanding 'More Info' sections...")
            try:
                # Use JavaScript to click all More Info links (they're <a> tags, not buttons)
                page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a.ut-more, a[aria-label*="More Info"]'));
                        links.forEach((link, index) => {
                            try {
                                link.click();
                            } catch(e) {
                                console.log('Error clicking link:', e);
                            }
                        });
                    }
                """)
                page.wait_for_timeout(3000)  # Wait for all to expand
            except Exception as e:
                print(f"  [WARNING] Error expanding More Info: {e}")
            
            # Save HTML for debugging
            html_after_expand = page.content()
            with open('temp_drinks_expanded.html', 'w', encoding='utf-8') as f:
                f.write(html_after_expand)
            print(f"  [DEBUG] Saved expanded HTML to temp_drinks_expanded.html")
            
            # Use JavaScript to extract items directly from DOM
            print("  Extracting items using JavaScript...")
            items_data = page.evaluate("""
                () => {
                    // First, collect all description paragraphs with their IDs
                    const descriptionsMap = {};
                    const allDescParas = document.querySelectorAll('p[id$="_description"]');
                    allDescParas.forEach(para => {
                        const id = para.getAttribute('id');
                        const text = para.textContent.trim();
                        if (id && text && text.length > 20) {
                            // Extract beer ID from description ID (e.g., "allagash_white_description" -> "allagash_white")
                            const beerId = id.replace('_description', '');
                            descriptionsMap[beerId] = text;
                        }
                    });
                    
                    const items = [];
                    const sections = document.querySelectorAll('h3');
                    
                    sections.forEach((h3) => {
                        const sectionName = h3.textContent.trim();
                        if (!sectionName || sectionName.length < 2) return;
                        
                        // Find all items after this h3, before next h3
                        let current = h3.nextElementSibling;
                        while (current && current.tagName !== 'H3') {
                            // Look for h4 (beer name) - it might be inside a link
                            const h4 = current.querySelector('h4');
                            if (h4) {
                                // Get beer name - it's in a link inside h4, or just the h4 text
                                let itemName = '';
                                const link = h4.querySelector('a');
                                if (link) {
                                    itemName = link.textContent.trim();
                                } else {
                                    itemName = h4.textContent.trim();
                                }
                                
                                // Clean up name - remove beer type if included
                                itemName = itemName.split('\\n')[0].trim();
                                
                                if (itemName && itemName.length > 2) {
                                    // Get beer ID - it's in a span with id inside h4, or we can derive it from the item name
                                    let beerId = '';
                                    const nameSpan = h4.querySelector('span[id]');
                                    if (nameSpan) {
                                        beerId = nameSpan.getAttribute('id');
                                    } else {
                                        // Try to derive ID from item name (convert to lowercase, replace spaces with underscores)
                                        beerId = itemName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
                                    }
                                    
                                    // Get description from map using beer ID
                                    let description = '';
                                    if (beerId && descriptionsMap[beerId]) {
                                        description = descriptionsMap[beerId];
                                    } else {
                                        // Try alternative ID formats
                                        const altIds = [
                                            beerId.replace(/_/g, ''),
                                            beerId.replace(/_/g, '-'),
                                            itemName.toLowerCase().replace(/[^a-z0-9]+/g, '')
                                        ];
                                        for (const altId of altIds) {
                                            if (descriptionsMap[altId]) {
                                                description = descriptionsMap[altId];
                                                break;
                                            }
                                        }
                                    }
                                    
                                    // Get beer type/style
                                    let beerType = '';
                                    const typeSpan = h4.querySelector('span.item-category, span.item-style');
                                    if (typeSpan) {
                                        beerType = typeSpan.textContent.trim();
                                    }
                                    
                                    // Get size (e.g., "16oz Draft", "12oz Can")
                                    let size = '';
                                    const allText = current.textContent;
                                    const sizeMatch = allText.match(/(\\d+oz\\s+(?:Draft|Can|Bottle))/i);
                                    if (sizeMatch) {
                                        size = sizeMatch[1];
                                    }
                                    
                                    // Get price
                                    let price = '';
                                    const priceMatch = allText.match(/\\$[\\d.]+/);
                                    if (priceMatch) {
                                        price = priceMatch[0];
                                    }
                                    
                                    // Build description
                                    const descParts = [];
                                    if (beerType) descParts.push(beerType);
                                    if (size) descParts.push('Size: ' + size);
                                    if (description) descParts.push(description);
                                    
                                    items.push({
                                        name: itemName,
                                        description: descParts.join(' | ') || description || null,
                                        price: price || '',
                                        section: sectionName
                                    });
                                }
                            }
                            current = current.nextElementSibling;
                        }
                    });
                    
                    return items;
                }
            """)
            
            browser.close()
            
            print(f"  [OK] Extracted {len(items_data)} items from DOM")
    except Exception as e:
        print(f"  [ERROR] Failed to extract drinks menu: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Convert to our format
    print("\n[2] Formatting items...")
    for item_data in items_data:
        items.append({
            "name": item_data.get('name', ''),
            "description": item_data.get('description'),
            "price": item_data.get('price', ''),
            "section": item_data.get('section', 'Beer'),
            "restaurant_name": "Ravenswood Pub",
            "restaurant_url": "https://ravenswoodpub.com/",
            "menu_type": "Drinks",
            "menu_name": "Beer Menu"
        })
    
    # Filter out items with no price and no description
    filtered_items = []
    for item in items:
        if item.get('price') or item.get('description'):
            filtered_items.append(item)
    
    print(f"[3] Extracted {len(filtered_items)} drink items (filtered {len(items) - len(filtered_items)} items)")
    
    return filtered_items

def extract_beer_item_details(container, h4, section_name: str) -> Dict:
    """Extract details from a beer item container"""
    item_name = h4.get_text(strip=True)
    
    # Get beer type/style (usually in a span or div after the h4 link)
    beer_type = ""
    type_elem = h4.find_next_sibling()
    if type_elem:
        type_text = type_elem.get_text(strip=True)
        if type_text and not type_text.startswith('$'):
            beer_type = type_text
    
    # Get all text content to find ABV, IBU, brewery, location
    all_text = container.get_text(separator=' | ', strip=True)
    
    # Get "More Info" description - look for button with "More Info" text
    description = ""
    more_info_btn = container.find('button', string=re.compile('More Info', re.I))
    if more_info_btn:
        # Find the paragraph that follows the button
        desc_para = more_info_btn.find_next_sibling('p')
        if desc_para:
            description = desc_para.get_text(strip=True)
    
    # Get size (e.g., "16oz Draft", "12oz Can", "16oz Bottle")
    size = ""
    size_elem = container.find(string=re.compile(r'\d+oz\s+(?:Draft|Can|Bottle)', re.I))
    if size_elem:
        size = size_elem.strip()
    else:
        # Try to find in div/span elements
        size_divs = container.find_all(['div', 'span'], string=re.compile(r'\d+oz', re.I))
        if size_divs:
            size = size_divs[0].get_text(strip=True)
    
    # Get price
    price = ""
    price_elem = container.find(string=re.compile(r'\$[\d.]+'))
    if price_elem:
        price = price_elem.strip()
    
    # Build full description
    description_parts = []
    if beer_type:
        description_parts.append(beer_type)
    if size:
        description_parts.append(f"Size: {size}")
    if description:  # "More Info" description
        description_parts.append(description)
    
    full_description = " | ".join(description_parts) if description_parts else (description if description else None)
    
    return {
        "name": item_name,
        "description": full_description,
        "price": price if price else "",
        "section": section_name,
        "restaurant_name": "Ravenswood Pub",
        "restaurant_url": "https://ravenswoodpub.com/",
        "menu_type": "Drinks",
        "menu_name": "Beer Menu"
    }

def scrape_online_order_menu() -> List[Dict]:
    """Scrape online order menu from order.ravenswoodpub.com"""
    items = []
    
    print("\n[ONLINE ORDER MENU]")
    print("  Downloading online order menu HTML...")
    
    url = "https://order.ravenswoodpub.com/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=0, i",
        "referer": "https://ravenswoodpub.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-site",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    cookies = {
        "_ga": "GA1.1.1969313654.1767623658",
        "_ga_VG24VK2VKT": "GS2.1.s1767623658$o1$g1$t1767624275$j58$l0$h0",
        "_ga_G1LNMCS8KE": "GS2.1.s1767623666$o1$g1$t1767624275$j58$l0$h0",
        "RavenswoodpubProd": "1e00lkqaapv3hl5jdgb42dspv0"
    }
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        html_content = response.text
        print(f"  [OK] Downloaded {len(html_content)} characters")
    except Exception as e:
        print(f"  [ERROR] Failed to download online order menu: {e}")
        return []
    
    # Parse HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    print("  Extracting menu items...")
    
    # Find all menu sections
    sections = soup.find_all('div', class_='menu-section')
    
    for section in sections:
        # Get section name
        section_header = section.find('div', class_='menu-section-header')
        if not section_header:
            continue
        
        h2 = section_header.find('h2')
        if not h2:
            continue
        
        section_name = h2.get_text(strip=True)
        # Remove count and arrow symbols if present (e.g., "Popular 33 ×" -> "Popular")
        # The count is in a span, so we need to get just the text from h2 without child elements
        section_name = h2.find(text=True, recursive=False)
        if section_name:
            section_name = section_name.strip()
        else:
            # Fallback: get all text and clean it
            section_name = h2.get_text(strip=True)
            # Remove count numbers and special characters at the end
            section_name = re.sub(r'\s+\d+.*$', '', section_name).strip()
            section_name = re.sub(r'[×\u00d7].*$', '', section_name).strip()
        
        # Find all menu items in this section
        menu_items = section.find_all('a', class_='menu-item')
        
        for item_link in menu_items:
            # Get item name
            menu_desc = item_link.find('div', class_='menu-desc')
            if not menu_desc:
                continue
            
            h4 = menu_desc.find('h4')
            if not h4:
                continue
            
            item_name = h4.get_text(strip=True)
            
            # Get price
            price_elem = menu_desc.find('h5', class_='item-price')
            price = ""
            if price_elem:
                price_span = price_elem.find('span', class_='price')
                if price_span:
                    price = price_span.get_text(strip=True)
            
            # Get description (if available in data attributes or elsewhere)
            description = ""
            # Check if there's a description in the item
            desc_elem = item_link.find('p', class_=lambda x: x and 'description' in str(x).lower())
            if desc_elem:
                description = desc_elem.get_text(strip=True)
            
            # Skip if no price and no description
            if not price and not description:
                continue
            
            items.append({
                "name": item_name,
                "description": description if description else None,
                "price": price if price else "",
                "section": section_name,
                "restaurant_name": "Ravenswood Pub",
                "restaurant_url": "https://ravenswoodpub.com/",
                "menu_type": "Online Order",
                "menu_name": "Online Order Menu"
            })
    
    print(f"  [OK] Extracted {len(items)} items from online order menu")
    
    return items

def scrape_ravenswoodpub_with_drinks() -> List[Dict]:
    """Scrape both food and drinks menus"""
    print("=" * 60)
    print("Scraping Ravenswood Pub (ravenswoodpub.com)")
    print("=" * 60)
    
    all_items = []
    
    # Scrape food menu
    print("\n[FOOD MENU]")
    try:
        html_content = fetch_menu_html()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        menus = [
            {"class": "menu_701567", "name": "Menu", "type": "Menu"},
            {"class": "menu_701801", "name": "Buffet Packages", "type": "Buffet Packages"},
            {"class": "menu_702020", "name": "Banquet Menu", "type": "Banquet Menu"}
        ]
        
        for menu_info in menus:
            print(f"  Parsing {menu_info['name']}...")
            items = parse_menu_items(soup, menu_info['class'], menu_info['name'], menu_info['type'])
            all_items.extend(items)
            print(f"    [OK] Found {len(items)} items")
    except Exception as e:
        print(f"  [ERROR] Failed to scrape food menu: {e}")
    
    # Scrape drinks menu
    print("\n[DRINKS MENU]")
    drinks_items = scrape_drinks_menu_with_playwright()
    all_items.extend(drinks_items)
    
    # Scrape online order menu
    online_order_items = scrape_online_order_menu()
    all_items.extend(online_order_items)
    
    # Filter out items with no price and no description
    filtered_items = []
    for item in all_items:
        if item.get('price') or item.get('description'):
            filtered_items.append(item)
    
    print(f"\n[SUMMARY] Total items: {len(filtered_items)} (filtered {len(all_items) - len(filtered_items)} items)")
    all_items = filtered_items
    
    # Save to JSON
    output_file = OUTPUT_DIR / "ravenswoodpub_com.json"
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved {len(all_items)} items to {output_file}")
    
    # Show sample items
    if all_items:
        print(f"\n[4] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            price_str = item.get('price', 'N/A')
            section = item.get('section', 'Menu')
            print(f"  {i}. {item.get('name', 'N/A')} - {price_str} ({section})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items

if __name__ == "__main__":
    scrape_ravenswoodpub_with_drinks()

