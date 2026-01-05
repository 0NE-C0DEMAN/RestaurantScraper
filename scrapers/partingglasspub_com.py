"""
Scraper for partingglasspub.com (Parting Glass Pub)
Scrapes menu from GraphQL API
"""

import json
import re
from pathlib import Path
from typing import List, Dict
from playwright.sync_api import sync_playwright


def format_price(price) -> str:
    """Format price to include $ symbol."""
    if price is None:
        return ""
    if isinstance(price, str):
        price = price.strip()
        if not price:
            return ""
        # Remove any existing $ symbols and add one
        price = re.sub(r'\$+', '', price)
        if price:
            return f"${price}"
        return ""
    elif isinstance(price, (int, float)):
        return f"${price:.2f}".rstrip('0').rstrip('.')
    return ""


def get_menu_sections(page) -> List[Dict]:
    """Get all menu section IDs from the menu page by intercepting GraphQL requests"""
    sections = []
    section_ids = set()
    section_names = {}
    
    try:
        # Intercept network requests to find section IDs
        def handle_response(response):
            url = response.url
            if 'graphql' in url and 'menuSection' in url:
                try:
                    # Extract from URL first
                    if 'sectionId' in url or 'variables' in url:
                        import urllib.parse
                        parsed = urllib.parse.urlparse(url)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'variables' in params:
                            try:
                                variables = json.loads(urllib.parse.unquote(params['variables'][0]))
                                section_id = variables.get('sectionId')
                                if section_id:
                                    section_ids.add(section_id)
                            except:
                                pass
                    
                    # Try to get response body for section name
                    if response.status == 200:
                        try:
                            data = response.json()
                            if 'data' in data and 'menuSection' in data['data']:
                                menu_section = data['data']['menuSection']
                                section_id = menu_section.get('id')
                                section_name = menu_section.get('name') or menu_section.get('title')
                                if section_id:
                                    section_ids.add(section_id)
                                    if section_name:
                                        section_names[section_id] = section_name
                        except:
                            pass
                except:
                    pass
        
        page.on('response', handle_response)
        
        # Navigate to menu page
        page.goto("https://www.partingglasspub.com/menu", wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(3000)
        
        # Try to find and click menu section buttons/tabs to trigger more requests
        # Look for common menu section selectors
        selectors = [
            'button[class*="menu"]',
            'a[class*="menu"]',
            '[data-section-id]',
            '[data-menu-section]',
            'button[role="tab"]',
            '.menu-tab',
            '.menu-section-button',
            '[class*="tab"]',
            '[class*="section"]'
        ]
        
        clicked_elements = set()
        for selector in selectors:
            try:
                buttons = page.query_selector_all(selector)
                for button in buttons[:15]:  # Limit clicks
                    try:
                        element_id = button.get_attribute('id') or button.get_attribute('data-id') or str(button)
                        if element_id not in clicked_elements:
                            button.click()
                            clicked_elements.add(element_id)
                            page.wait_for_timeout(1500)
                    except:
                        pass
            except:
                pass
        
        # Wait for all requests to complete
        page.wait_for_timeout(3000)
        
        # Also try scrolling to trigger lazy loading
        for i in range(3):
            page.evaluate(f"window.scrollTo(0, {i * 500})")
            page.wait_for_timeout(500)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
        
    except Exception as e:
        print(f"[WARNING] Could not extract sections from page: {e}")
    
    # Convert found section IDs to section dicts
    if section_ids:
        for section_id in section_ids:
            name = section_names.get(section_id, f"Section {section_id}")
            sections.append({"id": section_id, "name": name})
    
    # Add known sections that might not be discovered
    known_sections = [
        {"id": 901935, "name": "Starters"},
        {"id": 901947, "name": "Soups & Salads"},
        {"id": 901961, "name": "Irish Fare"},
        {"id": 901975, "name": "Kids Pics"},
        {"id": 901985, "name": "Pub Grub"},
        {"id": 901993, "name": "Specialty Burgers with fries"},
        {"id": 902001, "name": "Bar Menu"},  # Bar menu section (Beers on Tap)
        {"id": 902047, "name": "Domestic, Imported & Craft Brews"},  # Additional bar menu section
        {"id": 902105, "name": "Non-Alcoholic"},  # Non-alcoholic drinks section
        {"id": 902123, "name": "Wines by The Glass"},  # Wine menu section
        {"id": 902129, "name": "Wines by The Bottles"},  # Wine bottles section
        {"id": 902139, "name": "Dessert Menu"}  # Dessert menu section
    ]
    
    # Add known sections that aren't already in the list
    existing_ids = {s["id"] for s in sections}
    for known in known_sections:
        if known["id"] not in existing_ids:
            sections.append(known)
    
    # If no sections found at all, use fallback
    if not sections:
        sections = [{"id": 901935, "name": "Menu"}]
    
    return sections


def fetch_menu_section(section_id: int, page) -> Dict:
    """Fetch menu section data from GraphQL API"""
    try:
        # Build GraphQL URL with proper encoding (matching the curl command format)
        import urllib.parse
        variables = urllib.parse.quote(json.dumps({
            "orderingEventId": -1,
            "orderingEventAvailable": False,
            "sectionId": section_id
        }))
        extensions = urllib.parse.quote(json.dumps({
            "operationId": "PopmenuClient/238fca77b51509238a53cdae6d14140c"
        }))
        
        url = f"https://www.partingglasspub.com/graphql?operationName=menuSection&variables={variables}&extensions={extensions}"
        
        # Make request using Playwright
        response = page.request.get(
            url,
            headers={
                'accept': '*/*',
                'referer': 'https://www.partingglasspub.com/menu',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
            }
        )
        
        if response.status == 200:
            return response.json()
        else:
            print(f"[ERROR] Failed to fetch section {section_id}: Status {response.status}")
            return None
    except Exception as e:
        print(f"[ERROR] Failed to fetch section {section_id}: {e}")
        return None


def parse_menu_items(graphql_data: Dict, section_name: str = "Menu") -> List[Dict]:
    """Parse menu items from GraphQL response"""
    items = []
    
    if not graphql_data or 'data' not in graphql_data:
        return items
    
    menu_section = graphql_data.get('data', {}).get('menuSection')
    if not menu_section:
        return items
    
    subsections = menu_section.get('subsections', [])
    
    for subsection in subsections:
        # Try to get subsection name from various fields
        subsection_name = (subsection.get('name') or 
                          subsection.get('title') or 
                          subsection.get('displayName') or 
                          section_name)
        menu_items = subsection.get('items', [])
        
        for item in menu_items:
            # Skip disabled or out of stock items if needed
            if not item.get('isEnabled', True):
                continue
            
            item_name = item.get('name', '').strip()
            if not item_name:
                continue
            
            # Get description
            description = item.get('description', '') or item.get('htmlContent', '') or ''
            if description:
                # Clean HTML if present
                description = re.sub(r'<[^>]+>', '', description).strip()
                # Replace newlines with spaces
                description = re.sub(r'\s+', ' ', description).strip()
            
            # Get price FIRST (before extracting addons from description)
            price = item.get('price')
            price_custom_text = item.get('priceCustomText')
            
            # Use custom text if available, otherwise format the price
            if price_custom_text:
                price_str = price_custom_text
            elif price is not None:
                price_str = format_price(price)
            else:
                price_str = ""
            
            # Handle extras/addons from GraphQL
            extras = item.get('extras', [])
            extra_groups = item.get('extraGroups', [])
            
            addons = []
            
            # Process extras
            for extra in extras:
                extra_name = extra.get('name', '').strip()
                extra_price = extra.get('price')
                if extra_name and extra_price is not None:
                    addon_price = format_price(extra_price)
                    addons.append(f"{extra_name} {addon_price}")
            
            # Process extra groups
            for group in extra_groups:
                group_name = group.get('name', '').strip()
                group_extras = group.get('extras', [])
                for extra in group_extras:
                    extra_name = extra.get('name', '').strip()
                    extra_price = extra.get('price')
                    if extra_name and extra_price is not None:
                        addon_price = format_price(extra_price)
                        addons.append(f"{extra_name} {addon_price}")
            
            # Also extract addons from description text (e.g., "Additional items .50: mush, onion, bacon")
            # Do this AFTER we've already extracted the main price
            if description:
                # Look for patterns like "Additional items .50:" or "Add .50:" or "+.50:"
                # Pattern: "Additional items .50:" or "Additional items $0.50:" or similar
                # Handle both ".50" and "0.50" formats
                addon_pattern = re.search(r'(?:Additional items?|Add|Add-ons?|Extras?)\s+(?:\$?)?(\.?\d+\.?\d*)\s*[:\-]?\s*(.+?)(?:\n|$|\.|$)', description, re.IGNORECASE)
                if addon_pattern:
                    addon_price_str = addon_pattern.group(1)
                    # If price starts with dot, add leading zero
                    if addon_price_str.startswith('.'):
                        addon_price_str = '0' + addon_price_str
                    addon_price = format_price(addon_price_str)
                    addon_items = addon_pattern.group(2).strip()
                    # Remove trailing period if present
                    addon_items = addon_items.rstrip('.')
                    # Split by comma and format
                    addon_list = [item.strip() for item in addon_items.split(',')]
                    for addon_item in addon_list:
                        if addon_item:
                            # Handle "or" in the list (e.g., "mush, onion, bacon, peppers, or cheese")
                            if addon_item.lower().startswith('or '):
                                addon_item = addon_item[3:].strip()
                            addons.append(f"{addon_item} {addon_price}")
                    # Remove the addon text from description
                    description = description[:addon_pattern.start()].strip()
            
            # Add addons to description
            if addons:
                if description:
                    description += f" | Add-ons: {' / '.join(addons)}"
                else:
                    description = f"Add-ons: {' / '.join(addons)}"
            
            # Skip if no price and no description (but allow items with description even if no price)
            # For drink menus (beer, wine, cocktails), items might not have prices in the GraphQL response
            # but they're still valid menu items. Only skip if there's no name, price, or description
            if not item_name:
                continue
            # Keep items that have at least a name (drinks might not have prices in the API)
            
            # Handle multiple sizes/prices if present
            # Check if there are variant prices or size options
            # This might be in dish variants or price options
            
            items.append({
                "name": item_name,
                "description": description,
                "price": price_str,
                "restaurant_name": "Parting Glass Pub",
                "restaurant_url": "https://www.partingglasspub.com/",
                "menu_type": "Menu",
                "menu_name": subsection_name
            })
    
    return items


def scrape_partingglasspub():
    """Main scraping function"""
    print("=" * 60)
    print("Scraping Parting Glass Pub (partingglasspub.com)")
    print("=" * 60)
    
    all_items = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            # Get menu sections
            print("\n[1] Fetching menu sections...")
            sections = get_menu_sections(page)
            print(f"  [OK] Found {len(sections)} section(s)")
            
            # Fetch each section
            for section in sections:
                section_id = section.get('id')
                section_name = section.get('name', 'Menu')
                
                print(f"\n[2] Fetching section: {section_name} (ID: {section_id})...")
                
                graphql_data = fetch_menu_section(section_id, page)
                if graphql_data:
                    items = parse_menu_items(graphql_data, section_name)
                    all_items.extend(items)
                    print(f"  [OK] Found {len(items)} items")
                else:
                    print(f"  [ERROR] Failed to fetch section {section_id}")
        
        finally:
            browser.close()
    
    print(f"\n[OK] Total items extracted: {len(all_items)}")
    
    # Save to JSON
    output_path = Path(__file__).parent.parent / "output" / "partingglasspub_com.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(all_items)} items to {output_path}")
    
    # Print sample items
    if all_items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(all_items[:5], 1):
            print(f"  {i}. {item['name']} - {item.get('price', 'N/A')} ({item['menu_type']} / {item['menu_name']})")
        if len(all_items) > 5:
            print(f"  ... and {len(all_items) - 5} more")
    
    return all_items


if __name__ == "__main__":
    scrape_partingglasspub()

