"""
Check if prices are correct in both scrapers
"""

import json
from pathlib import Path
from collections import defaultdict

def load_json(filepath):
    """Load JSON file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def check_prices():
    """Compare prices from both scrapers"""
    
    base_path = Path(__file__).parent / 'output'
    bs_file = base_path / 'www_30parkcp_com_.json'
    gemini_file = base_path / 'www_30parkcp_com__gemini.json'
    
    print("="*70)
    print("PRICE VERIFICATION")
    print("="*70)
    print()
    
    # Load both files
    try:
        bs_data = load_json(bs_file)
        gemini_data = load_json(gemini_file)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return
    
    # Create lookup by name (normalized)
    bs_by_name = {}
    for item in bs_data:
        name = item.get('name', '').upper().strip()
        if name:
            bs_by_name[name] = item
    
    gemini_by_name = {}
    for item in gemini_data:
        name = item.get('name', '').upper().strip()
        if name:
            gemini_by_name[name] = item
    
    # Find common items
    common_names = set(bs_by_name.keys()) & set(gemini_by_name.keys())
    
    print(f"Common items found in both scrapers: {len(common_names)}")
    print()
    
    # Check price differences
    price_differences = []
    missing_prices_bs = []
    missing_prices_gemini = []
    
    for name in sorted(common_names):
        bs_item = bs_by_name[name]
        gemini_item = gemini_by_name[name]
        
        bs_price = bs_item.get('price', '').strip()
        gemini_price = gemini_item.get('price', '').strip()
        
        if bs_price != gemini_price:
            if not bs_price:
                missing_prices_bs.append((name, gemini_price))
            elif not gemini_price:
                missing_prices_gemini.append((name, bs_price))
            else:
                price_differences.append((name, bs_price, gemini_price))
    
    # Report results
    if price_differences:
        print("="*70)
        print(f"PRICE DIFFERENCES ({len(price_differences)} items)")
        print("="*70)
        for name, bs_price, gemini_price in price_differences[:20]:
            print(f"\n{name[:50]}")
            print(f"  BeautifulSoup: {bs_price}")
            print(f"  Gemini:        {gemini_price}")
        if len(price_differences) > 20:
            print(f"\n... and {len(price_differences) - 20} more differences")
    
    if missing_prices_bs:
        print("\n" + "="*70)
        print(f"ITEMS WITH PRICE IN GEMINI BUT NOT IN BS ({len(missing_prices_bs)} items)")
        print("="*70)
        for name, price in missing_prices_bs[:10]:
            print(f"  {name[:50]:50} | {price}")
        if len(missing_prices_bs) > 10:
            print(f"  ... and {len(missing_prices_bs) - 10} more")
    
    if missing_prices_gemini:
        print("\n" + "="*70)
        print(f"ITEMS WITH PRICE IN BS BUT NOT IN GEMINI ({len(missing_prices_gemini)} items)")
        print("="*70)
        for name, price in missing_prices_gemini[:10]:
            print(f"  {name[:50]:50} | {price}")
        if len(missing_prices_gemini) > 10:
            print(f"  ... and {len(missing_prices_gemini) - 10} more")
    
    # Check items with dual prices
    print("\n" + "="*70)
    print("DUAL PRICE ITEMS (small | large)")
    print("="*70)
    print()
    
    dual_price_items = []
    for name in sorted(common_names):
        bs_item = bs_by_name[name]
        gemini_item = gemini_by_name[name]
        
        bs_price = bs_item.get('price', '')
        gemini_price = gemini_item.get('price', '')
        
        if '|' in bs_price or '|' in gemini_price:
            dual_price_items.append((name, bs_price, gemini_price))
    
    for name, bs_price, gemini_price in dual_price_items[:10]:
        print(f"{name[:50]}")
        print(f"  BS:     {bs_price}")
        print(f"  Gemini: {gemini_price}")
        print()
    
    # Summary
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total common items: {len(common_names)}")
    print(f"Price differences: {len(price_differences)}")
    print(f"Missing prices in BS: {len(missing_prices_bs)}")
    print(f"Missing prices in Gemini: {len(missing_prices_gemini)}")
    print(f"Dual price items: {len(dual_price_items)}")
    
    if not price_differences and not missing_prices_bs and not missing_prices_gemini:
        print("\n✓ All prices match perfectly!")

if __name__ == '__main__':
    check_prices()

