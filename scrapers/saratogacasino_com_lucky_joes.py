"""
Scraper for saratogacasino.com - Lucky Joe's menu
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
            "referer": "https://saratogacasino.com/dining/lucky-joes/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download HTML from {url}: {e}")
        return ""


def parse_menu_page(html: str) -> List[Dict]:
    """Parse menu from the menu page"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    restaurant_name = "Lucky Joe's"
    restaurant_url = "https://saratogacasino.com/dining/lucky-joes/"
    
    # Find the entry-content section
    entry_content = soup.find('div', class_='entry-content')
    if not entry_content:
        print("[WARNING] Entry content not found")
        return items
    
    current_section = ""  # Track current section
    
    # Find all elements in order
    for element in entry_content.find_all(['h3', 'p']):  # pyright: ignore[reportAttributeAccessIssue]
        # Check if this is a section heading
        if element.name == 'h3':
            strong = element.find('strong')
            if strong:
                current_section = strong.get_text(strip=True)
            else:
                current_section = element.get_text(strip=True)
            continue
        
        # Check if this is a menu item paragraph
        if element.name == 'p':
            # Get all text from the paragraph
            text = element.get_text(separator='\n', strip=True)
            if not text or len(text) < 3:
                continue
            
            # Skip if it's just a note/instruction (no price)
            if not re.search(r'\$\s*[\d,]+\.?\d*', text):
                # Check if it contains price info in a different format
                if '|' in text and '$' in text:
                    # This might be a price variant (e.g., "Cup $7 | Bowl $10")
                    pass
                else:
                    continue
            
            # Extract item name and price
            # Format is usually: <strong>Item Name $Price</strong> or <strong>Item Name</strong> followed by description and price
            strong_tags = element.find_all('strong')
            
            name = ""
            price = ""
            description = ""
            
            if strong_tags:
                # First strong tag usually contains name
                first_strong = strong_tags[0].get_text(strip=True)
                
                # Check if price is in the first strong tag (name and price together)
                price_match = re.search(r'\$\s*([\d,]+\.?\d*)', first_strong)
                if price_match:
                    # Price is in the strong tag, extract name
                    name = re.sub(r'\$\s*[\d,]+\.?\d*.*$', '', first_strong).strip()
                    price = f"${price_match.group(1).replace(',', '')}"
                else:
                    # Name is in first strong tag, check for prices in other strong tags or text
                    name = first_strong
                    
                    # Check if there are multiple strong tags with prices (e.g., "10 wings $17" and "20 wings $25")
                    price_parts = []
                    element_html = str(element)
                    
                    # Track previous strong tag position
                    prev_strong_end_pos = 0
                    if len(strong_tags) > 0:
                        # Get position after the first strong tag (name)
                        first_strong_html = str(strong_tags[0])
                        first_strong_pos = element_html.find(first_strong_html)
                        if first_strong_pos >= 0:
                            prev_strong_end_pos = first_strong_pos + len(first_strong_html)
                    
                    for i, strong_tag in enumerate(strong_tags[1:], 1):  # Skip first (name)
                        strong_text = strong_tag.get_text(strip=True)
                        price_match = re.search(r'\$\s*([\d,]+\.?\d*)', strong_text)
                        if price_match:
                            # Get label before price in the strong tag
                            label_text = re.sub(r'\$\s*[\d,]+\.?\d*.*$', '', strong_text).strip()
                            
                            # If no label in strong tag, try to get it from text before the strong tag
                            if not label_text or label_text == name:
                                strong_html = str(strong_tag)
                                
                                # Find position of this strong tag
                                strong_pos = element_html.find(strong_html, prev_strong_end_pos)
                                if strong_pos > 0:
                                    # Get HTML between previous strong tag end and current one
                                    between_html = element_html[prev_strong_end_pos:strong_pos]
                                    
                                    # Parse it to get text
                                    between_soup = BeautifulSoup(between_html, 'html.parser')
                                    between_text = between_soup.get_text(separator=' ', strip=True)
                                    
                                    # Remove any prices that might be in this text
                                    between_text = re.sub(r'\$\s*[\d,]+\.?\d*', '', between_text).strip()
                                    
                                    # Get the last few words as potential label
                                    # Labels are usually short (1-3 words) and come right before the price
                                    words = between_text.split()
                                    if len(words) >= 1:
                                        # Try to get label from last 1-3 words
                                        for word_count in [3, 2, 1]:
                                            if len(words) >= word_count:
                                                potential_label = ' '.join(words[-word_count:]).strip()
                                                # Check if it looks like a label (not description text)
                                                if (potential_label and 
                                                    len(potential_label) < 25 and 
                                                    potential_label != name and
                                                    not potential_label.lower().startswith(('served', 'with', 'choice', 'and', 'or', 'buffalo', 'garlic')) and
                                                    not any(word.lower() in potential_label.lower() for word in ['cheese', 'celery', 'ranch', 'sauce', 'dressing', 'honey', 'bbq'])):
                                                    label_text = potential_label
                                                    break
                                
                                # Update previous strong tag end position for next iteration
                                if strong_pos >= 0:
                                    prev_strong_end_pos = strong_pos + len(strong_html)
                            
                            if label_text and len(label_text) < 30 and label_text != name:
                                price_parts.append(f"{label_text} ${price_match.group(1).replace(',', '')}")
                            else:
                                price_parts.append(f"${price_match.group(1).replace(',', '')}")
                    
                    if price_parts:
                        price = " | ".join(price_parts)
                    else:
                        # No prices in strong tags, check in text
                        # Remove name from text to get the rest (description + prices)
                        text_after_name = text.replace(name, '', 1).strip()
                        
                        # Check for multiple prices with labels (e.g., "Cup $7 | Bowl $10" or "Single $18.5 | Double $25")
                        # Pattern: Label $Price | Label $Price
                        multi_price_pattern = r'([A-Za-z\s]+)\s*\$\s*([\d,]+\.?\d*)\s*\|\s*([A-Za-z\s]+)\s*\$\s*([\d,]+\.?\d*)'
                        multi_match = re.search(multi_price_pattern, text_after_name)
                        if multi_match:
                            label1 = multi_match.group(1).strip()
                            price1 = multi_match.group(2).replace(',', '')
                            label2 = multi_match.group(3).strip()
                            price2 = multi_match.group(4).replace(',', '')
                            price = f"{label1} ${price1} | {label2} ${price2}"
                        else:
                            # Single price or multiple without clear labels
                            prices = re.findall(r'\$\s*([\d,]+\.?\d*)', text_after_name)
                            if len(prices) > 1:
                                # Try to extract labels before each price
                                price_parts = []
                                # Split by | to get individual price segments
                                segments = text_after_name.split('|')
                                for segment in segments:
                                    price_match = re.search(r'\$\s*([\d,]+\.?\d*)', segment)
                                    if price_match:
                                        # Get text before the price as label
                                        label_text = re.sub(r'\$\s*[\d,]+\.?\d*.*$', '', segment).strip()
                                        if label_text and len(label_text) < 20:  # Reasonable label length
                                            price_parts.append(f"{label_text} ${price_match.group(1).replace(',', '')}")
                                        else:
                                            price_parts.append(f"${price_match.group(1).replace(',', '')}")
                                if price_parts:
                                    price = " | ".join(price_parts)
                                else:
                                    price = " | ".join([f"${p.replace(',', '')}" for p in prices])
                            elif len(prices) == 1:
                                price = f"${prices[0].replace(',', '')}"
            
            # Get description (everything after the name/price, excluding price labels)
            if name:
                # Remove name from text
                desc_text = text
                desc_text = re.sub(re.escape(name), '', desc_text, count=1)
                
                # Remove price patterns (with or without labels)
                # Remove patterns like "Cup $7 | Bowl $10" or "Single $18.5 | Double $25"
                desc_text = re.sub(r'[A-Za-z\s]+\s*\$\s*[\d,]+\.?\d*\s*\|?\s*[A-Za-z\s]*\s*\$\s*[\d,]+\.?\d*', '', desc_text)
                desc_text = re.sub(r'[A-Za-z\s]+\s*\$\s*[\d,]+\.?\d*\s*\|?\s*', '', desc_text)
                desc_text = re.sub(r'\$\s*[\d,]+\.?\d*\s*\|?\s*', '', desc_text)
                desc_text = desc_text.replace('|', '').strip()
                
                # Clean up extra whitespace and newlines
                description = ' '.join(desc_text.split())
                
                # Remove common price-related words that might be left
                description = re.sub(r'\b(Cup|Bowl|Single|Double|10 wings|20 wings)\b', '', description, flags=re.IGNORECASE).strip()
                description = ' '.join(description.split())
            
            # Skip if no name or price
            if not name or not price:
                continue
            
            # Use section name or default
            menu_section = current_section if current_section else "Menu"
            
            items.append({
                'name': name,
                'description': description,
                'price': price,
                'menu_type': 'Menu',
                'restaurant_name': restaurant_name,
                'restaurant_url': restaurant_url,
                'menu_name': menu_section
            })
    
    return items


def scrape_lucky_joes_menu() -> List[Dict]:
    """Scrape menu from Lucky Joe's"""
    print("=" * 60)
    print("Scraping Lucky Joe's (saratogacasino.com)")
    print("=" * 60)
    
    url = "https://saratogacasino.com/lucky-joes-menu/"
    print(f"\n[1] Downloading menu page...")
    print(f"    URL: {url}")
    
    html = download_html_with_requests(url)
    if not html:
        print(f"[ERROR] Failed to download HTML")
        return []
    
    # Save HTML for debugging
    temp_dir = Path(__file__).parent.parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    html_file = temp_dir / "saratogacasino_com_lucky_joes_menu.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] Saved HTML to {html_file.name}")
    
    # Parse menu
    print(f"\n[2] Parsing menu...")
    items = parse_menu_page(html)
    print(f"[OK] Total items extracted: {len(items)}")
    
    # Display sample
    if items:
        print(f"\n[3] Sample items:")
        for i, item in enumerate(items[:5], 1):
            try:
                price_str = item['price'] if item['price'] else "No price"
                print(f"  {i}. {item['name']} - {price_str} ({item['menu_name']})")
            except UnicodeEncodeError:
                name = item['name'].encode('ascii', 'ignore').decode('ascii')
                price_str = item['price'] if item['price'] else "No price"
                print(f"  {i}. {name} - {price_str} ({item['menu_name']})")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
    
    return items


if __name__ == '__main__':
    items = scrape_lucky_joes_menu()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "saratogacasino_com_lucky_joes.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Saved {len(items)} items to {output_file}")

