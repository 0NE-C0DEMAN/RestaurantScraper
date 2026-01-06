def parse_beverages_html(html: str) -> List[Dict]:
    """Parse beverages menu from HTML (structured Untappd data)"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Structure based on actual HTML:
    # - Section: h3.section-name (e.g., "THE BASICS")
    # - Menu item: div.menu-item
    #   - Beer name: h4.item-name > a > span (e.g., "Bud Light")
    #   - Beer type: span.item-category (e.g., "Light Lager")
    #   - ABV: span.item-abv (e.g., "4.2% ABV")
    #   - Brewery: span.brewery > a (e.g., "Anheuser-Busch")
    #   - Size: span.type (e.g., "12oz")
    #   - Price: span.price (contains "4.00")
    
    # Find all menu items
    menu_items = soup.find_all('div', class_='menu-item')
    
    if menu_items:
        print(f"    Found {len(menu_items)} menu items - parsing structured data...")
        
        current_section = "Beverages"  # Default section
        
        for menu_item in menu_items:
            # Find section - look for nearest h3.section-name before this item
            section_header = menu_item.find_previous('h3', class_='section-name')
            if section_header:
                current_section = section_header.get_text(strip=True)
            
            # Find item-details div
            item_details = menu_item.find('div', class_='item-details')
            if not item_details:
                continue
            
            # Extract beer name from h4.item-name > a > span
            h4_name = item_details.find('h4', class_='item-name')
            if not h4_name:
                continue
            
            # Get the span inside the link
            name_link = h4_name.find('a')
            if not name_link:
                continue
            
            name_span = name_link.find('span')
            if not name_span:
                continue
            
            beer_name = name_span.get_text(strip=True)
            if not beer_name:
                continue
            
            # Extract beer type from span.item-category
            category_span = h4_name.find('span', class_='item-category')
            beer_type = category_span.get_text(strip=True) if category_span else None
            
            # Extract ABV from span.item-abv
            abv_span = item_details.find('span', class_='item-abv')
            abv_text = abv_span.get_text(strip=True) if abv_span else None
            
            # Extract brewery from span.brewery > a
            brewery_span = item_details.find('span', class_='brewery')
            brewery_name = None
            if brewery_span:
                brewery_link = brewery_span.find('a')
                if brewery_link:
                    brewery_name = brewery_link.get_text(strip=True)
            
            # Build description
            description_parts = []
            if beer_type:
                description_parts.append(beer_type)
            if abv_text:
                description_parts.append(abv_text)
            if brewery_name:
                description_parts.append(f"Brewery: {brewery_name}")
            description = " | ".join(description_parts) if description_parts else None
            
            # Extract size and price from div.container-list
            container_list = item_details.find('div', class_='container-list')
            size = None
            price_value = None
            
            if container_list:
                # Find size from span.type
                type_span = container_list.find('span', class_='type')
                if type_span:
                    size = type_span.get_text(strip=True)
                
                # Find price from span.price
                price_span = container_list.find('span', class_='price')
                if price_span:
                    # Get all text from price span (e.g., "4.00" or "$4.00")
                    price_text = price_span.get_text(strip=True)
                    # Extract number (might have $ or other text)
                    price_match = re.search(r'(\d+\.?\d*)', price_text)
                    if price_match:
                        price_value = price_match.group(1)
            
            # Format price
            if price_value:
                if size:
                    price = f"{size} ${price_value}"
                else:
                    price = f"${price_value}"
            else:
                price = "Price not listed"
            
            item = {
                "name": beer_name,
                "description": description,
                "price": price,
                "section": current_section,
                "restaurant_name": "The Hideaway",
                "restaurant_url": "https://www.hideawaysaratoga.com/",
                "menu_type": "Beverages",
                "menu_name": "Beverages Menu"
            }
            
            items.append(item)
    
    print(f"      [OK] Extracted {len(items)} items from structured HTML")
    
    # If no structured items found, check for images as fallback
    if not items:
        img_tags = soup.find_all('img')
        beverage_images = []
        for img in img_tags:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                src_lower = src.lower()
                if any(keyword in src_lower for keyword in ['beverage', 'beer', 'wine', 'cocktail', 'drink', 'menu']):
                    if 'logo' not in src_lower:
                        if src.startswith('http'):
                            beverage_images.append(src)
                        elif src.startswith('//'):
                            beverage_images.append(f"https:{src}")
                        elif src.startswith('/'):
                            beverage_images.append(f"https://www.hideawaysaratoga.com{src}")
        
        # If we found beverage images, process them with Gemini
        if beverage_images and GEMINI_AVAILABLE and GEMINI_API_KEY:
            print(f"    Found {len(beverage_images)} beverage menu image(s) - using Gemini as fallback")
            for i, image_url in enumerate(beverage_images, 1):
                print(f"    Processing beverage image {i}/{len(beverage_images)}...")
                
                # Download image
                image_filename = f"hideaway_beverages_{i}.jpg"
                image_path = Path(f"temp/hideaway_images/{image_filename}")
                
                if download_image(image_url, image_path):
                    print(f"      [OK] Downloaded image")
                    
                    # Extract menu items using Gemini
                    beverage_items = extract_menu_from_image_with_gemini(
                        image_path,
                        "Beverages Menu",
                        "Beverages",
                        "Beverages"
                    )
                    items.extend(beverage_items)
                    print(f"      [OK] Extracted {len(beverage_items)} items from image")
                else:
                    print(f"      [ERROR] Failed to download image")
    
    return items

