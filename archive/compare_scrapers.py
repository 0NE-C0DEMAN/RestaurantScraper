"""
Compare results from BeautifulSoup scraper vs Gemini HTML scraper
"""

import json
from pathlib import Path

def load_json(filepath):
    """Load JSON file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def compare_scrapers():
    """Compare results from both scrapers"""
    
    base_path = Path(__file__).parent / 'output'
    bs_file = base_path / 'www_30parkcp_com_.json'
    gemini_file = base_path / 'www_30parkcp_com__gemini.json'
    
    print("="*70)
    print("COMPARING SCRAPER RESULTS")
    print("="*70)
    print()
    
    # Load both files
    try:
        bs_data = load_json(bs_file)
        gemini_data = load_json(gemini_file)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return
    
    print(f"BeautifulSoup scraper: {len(bs_data)} items")
    print(f"Gemini HTML scraper: {len(gemini_data)} items")
    print()
    
    # Group by menu type
    bs_by_type = {}
    gemini_by_type = {}
    
    for item in bs_data:
        menu_type = item.get('menu_type', 'Unknown')
        if menu_type not in bs_by_type:
            bs_by_type[menu_type] = []
        bs_by_type[menu_type].append(item)
    
    for item in gemini_data:
        menu_type = item.get('menu_type', 'Unknown')
        if menu_type not in gemini_by_type:
            gemini_by_type[menu_type] = []
        gemini_by_type[menu_type].append(item)
    
    # Compare by section
    print("="*70)
    print("COMPARISON BY MENU SECTION")
    print("="*70)
    print()
    
    all_types = set(list(bs_by_type.keys()) + list(gemini_by_type.keys()))
    
    for menu_type in sorted(all_types):
        bs_count = len(bs_by_type.get(menu_type, []))
        gemini_count = len(gemini_by_type.get(menu_type, []))
        
        diff = gemini_count - bs_count
        diff_str = f"(+{diff})" if diff > 0 else f"({diff})" if diff < 0 else "(same)"
        
        print(f"{menu_type:20} | BS: {bs_count:3} | Gemini: {gemini_count:3} {diff_str}")
    
    print()
    print("="*70)
    print("SAMPLE COMPARISONS")
    print("="*70)
    print()
    
    # Compare first few items from each section
    for menu_type in sorted(all_types)[:3]:  # First 3 sections
        print(f"\n--- {menu_type} ---")
        bs_items = bs_by_type.get(menu_type, [])[:3]
        gemini_items = gemini_by_type.get(menu_type, [])[:3]
        
        print("\nBeautifulSoup:")
        for item in bs_items:
            print(f"  - {item.get('name', 'N/A')[:40]:40} | {item.get('price', 'N/A'):20}")
        
        print("\nGemini:")
        for item in gemini_items:
            print(f"  - {item.get('name', 'N/A')[:40]:40} | {item.get('price', 'N/A'):20}")
    
    # Find items unique to each scraper
    print()
    print("="*70)
    print("UNIQUE ITEMS")
    print("="*70)
    print()
    
    bs_names = {item.get('name', '').upper() for item in bs_data}
    gemini_names = {item.get('name', '').upper() for item in gemini_data}
    
    only_bs = bs_names - gemini_names
    only_gemini = gemini_names - bs_names
    
    if only_bs:
        print(f"Only in BeautifulSoup ({len(only_bs)} items):")
        for name in sorted(list(only_bs)[:10]):
            print(f"  - {name}")
        if len(only_bs) > 10:
            print(f"  ... and {len(only_bs) - 10} more")
    
    if only_gemini:
        print(f"\nOnly in Gemini ({len(only_gemini)} items):")
        for name in sorted(list(only_gemini)[:10]):
            print(f"  - {name}")
        if len(only_gemini) > 10:
            print(f"  ... and {len(only_gemini) - 10} more")
    
    if not only_bs and not only_gemini:
        print("All items found by both scrapers!")

if __name__ == '__main__':
    compare_scrapers()

