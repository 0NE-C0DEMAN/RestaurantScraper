"""
Scraper for saratogacasino.com - Morton's The Steakhouse menu
Scrapes menu from a single page with multiple sections
"""

import json
import re
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup


def download_html_with_requests(url: str) -> str:
    """Download HTML from URL"""
    try:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://saratogacasino.com/dining/mortons/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        cookies = {
            "_gcl_au": "1.1.813927681.1767455837",
            "_ga": "GA1.1.628080045.1767455837",
            "_fbp": "fb.1.1767455838185.848107700203249067",
            "pys_first_visit": "true",
            "pysTrafficSource": "direct",
            "pys_landing_page": "https://saratogacasino.com/dining/lucky-joes/",
            "last_pysTrafficSource": "direct",
            "last_pys_landing_page": "https://saratogacasino.com/dining/lucky-joes/",
            "pbid": "1656f97fd936912f527f19b380b08a4691dad3219c55fb988fc28a232241da35",
            "nmstat": "d7a67008-000b-5065-aeb0-8124d6c0d216",
            "_ga_TY2EVVN9HL": "GS2.1.s1767531337$o2$g1$t1767531946$j56$l0$h0",
            "_ga_4CD380528X": "GS2.1.s1767531337$o2$g1$t1767531946$j56$l0$h0"
        }
        response = requests.get(url, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_menu_page(html: str) -> List[Dict]:
    """Parse menu from the menu page"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    restaurant_name = "Morton's The Steakhouse"
    restaurant_url = "https://www.mortons.com/location/mortons-the-steakhouse-saratoga-springs-ny/"
    
    # Find the entry-content section
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        print("[WARNING] Entry content not found")
        return items
    
    current_section = ""  # Track current section
    
    # Find all elements in order
    for element in entry_content.find_all(['h3', 'p'], recursive=True):  # pyright: ignore[reportAttributeAccessIssue]
        # Check if this is a section heading
        if element.name == 'h3':
            section_text = element.get_text(strip=True)
            # Skip if it's just formatting or empty
            if section_text and not section_text.startswith('<'):
                current_section = section_text
            continue
        
        # Check if this is a menu item paragraph
        if element.name == 'p':
            # Skip if it doesn't contain strong tags (likely not a menu item)
            strong_tags = element.find_all('strong')
            if not strong_tags:
                continue
            
            # Skip disclaimer/note paragraphs
            text_content = element.get_text(strip=True)
            if any(keyword in text_content.lower() for keyword in ['calories a day', 'nutrition information', 'food allergy', 'gratuity', 'saratoga casino hotel', 'saratoga springs']):
                continue
            
            # Get the full HTML content to parse more accurately
            html_content = str(element)
            
            # Special handling for OCEAN PLATTER section
            if current_section == "OCEAN PLATTER":
                # This section has description first, then prices with size labels
                full_text = element.get_text(separator=' ', strip=True)
                # Extract prices with size labels: "Grand* 1760 cal $85 | Epic* 2860 cal $160"
                # Pattern: (SizeLabel*) (calories) ($price) | (SizeLabel*) (calories) ($price)
                price_pattern = r'(\w+\*?)\s+\d+\s*cal\s*\$(\d+)'
                matches = re.findall(price_pattern, full_text)
                if matches:
                    # Format: "Grand $85 | Epic $160"
                    price_parts = [f"{size.replace('*', '')} ${price}" for size, price in matches]
                    price = ' | '.join(price_parts)
                    # Extract description (everything before the first size label)
                    first_size_pos = full_text.find(matches[0][0])
                    description = full_text[:first_size_pos].strip()
                    # Remove calorie info
                    description = re.sub(r'\d+\s*cal', '', description, flags=re.I)
                    description = re.sub(r'\s+', ' ', description).strip()
                    # Create item
                    item = {
                        'name': 'Ocean Platter',
                        'description': description,
                        'price': price,
                        'restaurant_name': restaurant_name,
                        'restaurant_url': restaurant_url,
                        'menu_type': 'Menu',
                        'menu_name': current_section
                    }
                    items.append(item)
                continue
            
            # Split by <br /> tags to get individual lines
            lines = re.split(r'<br\s*/?>', html_content, flags=re.IGNORECASE)
            
            current_item = None
            
            for line in lines:
                line_soup = BeautifulSoup(line, 'html.parser')
                strong_tags_in_line = line_soup.find_all('strong')
                
                if not strong_tags_in_line:
                    # This might be a description line
                    text = line_soup.get_text(strip=True)
                    # Skip calorie info
                    if re.match(r'^\d+\s*cal', text, re.I):
                        continue
                    # Skip empty or very short lines
                    if len(text) < 3:
                        continue
                    
                    # Check if this line contains size labels with prices (e.g., "8 oz. Single $54 | Petite Twin Tails $52")
                    # Pattern: (Size Label) ($price) | (Size Label) ($price)
                    size_price_pattern = r'([^$|]+?)\s*\$(\d+)'
                    size_price_matches = re.findall(size_price_pattern, text)
                    
                    if size_price_matches and len(size_price_matches) > 1 and current_item:
                        # This line has size labels with prices - update the price field
                        price_parts = [f"{size.strip()} ${price}" for size, price in size_price_matches]
                        current_item['price'] = ' | '.join(price_parts)
                        # Don't add this to description since it's price info
                        continue
                    elif size_price_matches and len(size_price_matches) == 1 and current_item:
                        # Single size/price - might be part of description or price
                        # Check if current item already has a price
                        if not current_item.get('price'):
                            current_item['price'] = f"${size_price_matches[0][1]}"
                            # Add size to description if it's meaningful
                            size_label = size_price_matches[0][0].strip()
                            if size_label and not re.match(r'^\d+\s*cal', size_label, re.I):
                                if current_item['description']:
                                    current_item['description'] += ' ' + size_label
                                else:
                                    current_item['description'] = size_label
                        continue
                    
                    # Regular description line
                    if current_item:
                        if current_item['description']:
                            current_item['description'] += ' ' + text
                        else:
                            current_item['description'] = text
                    continue
                
                # Check if all strong tags contain only prices (no item name)
                all_are_prices = all('$' in tag.get_text() for tag in strong_tags_in_line)
                line_text = line_soup.get_text()
                
                if all_are_prices and current_item:
                    # This line has only prices with size labels - update current item's price
                    # Pattern: (Size Label) ($price) | (Size Label) ($price)
                    size_price_pattern = r'([^$|]+?)\s*\$(\d+)'
                    size_price_matches = re.findall(size_price_pattern, line_text)
                    if size_price_matches:
                        price_parts = [f"{size.strip()} ${price}" for size, price in size_price_matches]
                        current_item['price'] = ' | '.join(price_parts)
                    continue
                
                # This line has strong tags - likely a new item
                # Save previous item if exists
                if current_item:
                    # Clean up description
                    current_item['description'] = re.sub(r'\s+', ' ', current_item['description']).strip()
                    # Skip if no price and no description
                    if current_item['price'] or current_item['description']:
                        items.append(current_item)
                    current_item = None
                
                # Extract item name (first strong tag)
                name = strong_tags_in_line[0].get_text(strip=True)
                if not name:
                    continue
                
                # Skip if name is just a price (like "$85") - this is a special format
                if re.match(r'^\$\s*\d+', name):
                    # This might be a special format where description comes first
                    # Check if there are multiple strong tags with prices
                    price_tags = [s for s in strong_tags_in_line if '$' in s.get_text()]
                    if len(price_tags) >= 2:
                        # This is OCEAN PLATTER format - description first, then prices
                        # Get all text before the first price
                        line_text = line_soup.get_text()
                        first_price_pos = line_text.find(price_tags[0].get_text())
                        name = line_text[:first_price_pos].strip()
                        # Remove calorie info from name
                        name = re.sub(r'\d+\s*cal', '', name, flags=re.I).strip()
                        # Extract prices from all price tags
                        prices = [s.get_text(strip=True) for s in price_tags]
                        price = ' / '.join(prices)
                        # Description is empty for this format
                        description = ""
                    else:
                        continue
                
                # Extract price - look for $ followed by numbers, might be in strong tag or just before it
                price = ""
                if 'price' not in locals() or not price:  # Only extract if not already set
                    line_text = line_soup.get_text()
                    
                    # Check for multiple prices with potential size indicators
                    # Pattern like: "590/870 cal $25 / $47" or "$25 / $47"
                    multi_price_match = re.findall(r'\$\s*(\d+)', line_text)
                    
                    if len(multi_price_match) > 1:
                        # Check if there are size indicators before prices (like "590/870 cal")
                        # Look for calorie patterns that might indicate sizes
                        cal_pattern = r'(\d+/\d+)\s*cal'
                        cal_match = re.search(cal_pattern, line_text)
                        if cal_match:
                            # Has calorie info that might indicate sizes
                            # Format as "$25 / $47" (sizes not explicitly labeled, so just show prices)
                            price = ' / '.join(['$' + p for p in multi_price_match])
                        else:
                            # Multiple prices without explicit size labels
                            price = ' / '.join(['$' + p for p in multi_price_match])
                    elif len(multi_price_match) == 1:
                        price = '$' + multi_price_match[0]
                    else:
                        # Look for single price pattern: $ followed by numbers, possibly split across tags
                        price_match = re.search(r'\$\s*(\d+)', line_text)
                        if price_match:
                            price = '$' + price_match.group(1)
                
                # Extract description from the line (text after name and price)
                description = ""
                # Remove name and price from line text to get description
                desc_text = line_text
                # Remove name (case-insensitive, handle special chars)
                desc_text = re.sub(re.escape(name), '', desc_text, count=1, flags=re.I)
                # Remove price (handle $ escaping)
                if price:
                    # Remove all price variations
                    price_clean = price.replace('$', r'\$')
                    desc_text = re.sub(re.escape(price_clean), '', desc_text, flags=re.I)
                    # Also remove individual price parts if multiple prices
                    for price_part in price.split(' / '):
                        desc_text = re.sub(re.escape(price_part.replace('$', r'\$')), '', desc_text, flags=re.I)
                # Remove calorie info (including patterns like "590/870 cal")
                desc_text = re.sub(r'\d+/\d+\s*cal', '', desc_text, flags=re.I)
                desc_text = re.sub(r'\d+\s*cal', '', desc_text, flags=re.I)
                # Remove any remaining price patterns
                desc_text = re.sub(r'\$\s*\d+', '', desc_text)
                desc_text = desc_text.strip()
                # Clean up extra spaces, slashes, and punctuation
                desc_text = re.sub(r'[/\s]+', ' ', desc_text).strip()
                desc_text = re.sub(r'^\s*[/|]\s*', '', desc_text)  # Remove leading | or /
                desc_text = re.sub(r'\s*[/|]\s*$', '', desc_text)  # Remove trailing | or /
                if desc_text and len(desc_text) > 2:
                    description = desc_text
                
                # Create new item
                current_item = {
                    'name': name,
                    'description': description,
                    'price': price,
                    'restaurant_name': restaurant_name,
                    'restaurant_url': restaurant_url,
                    'menu_type': 'Menu',
                    'menu_name': current_section
                }
            
            # Save last item if exists
            if current_item:
                # Clean up description
                current_item['description'] = re.sub(r'\s+', ' ', current_item['description']).strip()
                # Skip if no price and no description
                if current_item['price'] or current_item['description']:
                    items.append(current_item)
    
    return items


def scrape_mortons_menu() -> List[Dict]:
    """Scrape menu from Morton's The Steakhouse"""
    print("=" * 60)
    print("Scraping Morton's The Steakhouse (saratogacasino.com)")
    print("=" * 60)
    
    url = "https://saratogacasino.com/mortons-steakhouse-menu/"
    
    # Download HTML
    print(f"\n[1] Downloading menu HTML...")
    html = download_html_with_requests(url)
    if not html:
        print("[ERROR] Failed to download HTML")
        return []
    
    print(f"[OK] Downloaded {len(html)} characters")
    
    # Parse menu
    print(f"\n[2] Parsing menu items...")
    items = parse_menu_page(html)
    
    print(f"[OK] Total items extracted: {len(items)}")
    
    # Display sample
    if items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(items[:5], 1):
            try:
                price_str = item.get('price', '') if item.get('price') else "No price"
                print(f"  {i}. {item.get('name', 'Unknown')} - {price_str} ({item.get('menu_name', 'Unknown')})")
            except Exception as e:
                print(f"  {i}. [Error displaying item: {e}]")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
    
    return items


if __name__ == "__main__":
    items = scrape_mortons_menu()
    
    # Save to JSON
    if items:
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "saratogacasino_com_mortons.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        
        print(f"\n[OK] Saved {len(items)} items to {output_file}")

