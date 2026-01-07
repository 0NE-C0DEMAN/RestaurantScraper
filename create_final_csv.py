"""
Create final unified CSV file from all JSON files
- Includes sr_no, restaurant_name, restaurant_url, menu_type, section, name, description, price
- Removes location field
- Saves outside csv_output folder
"""

import json
import csv
from pathlib import Path

def normalize_field(item, field_name, alternatives=None):
    """Get field value, trying alternatives if main field doesn't exist"""
    if alternatives is None:
        alternatives = []
    
    # Try main field first
    if field_name in item and item[field_name]:
        return item[field_name]
    
    # Try alternatives
    for alt in alternatives:
        if alt in item and item[alt]:
            return item[alt]
    
    return ''


def create_final_csv():
    """Create final unified CSV with standardized columns"""
    output_dir = Path(__file__).parent / "output"
    
    # Find all JSON files
    json_files = list(output_dir.glob("*.json"))
    json_files.sort()
    
    if not json_files:
        print("[ERROR] No JSON files found in output directory")
        return
    
    print(f"[INFO] Found {len(json_files)} JSON files")
    
    # Define standardized columns
    columns = [
        'sr_no',
        'restaurant_name',
        'restaurant_url',
        'menu_type',  # Lunch, Dinner, Breakfast, etc. (from menu_type or menu_name)
        'section',    # Appetizers, Entrees, etc.
        'name',
        'description',
        'price'
    ]
    
    # Create unified CSV file (save outside csv_output)
    csv_file = Path(__file__).parent / "all_restaurant_menus.csv"
    
    total_records = 0
    records_by_restaurant = {}
    sr_no = 1
    
    # Statistics for sanity check
    stats = {
        'with_menu_type': 0,
        'with_section': 0,
        'with_both': 0,
        'with_price': 0,
        'empty_price': 0,
        'empty_description': 0,
        'empty_name': 0
    }
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        # Process each JSON file
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as jf:
                    data = json.load(jf)
                    
                if not isinstance(data, list):
                    print(f"[WARNING] {json_file.name} is not a list, skipping")
                    continue
                
                record_count = 0
                restaurant_name = None
                
                for item in data:
                    if isinstance(item, dict):
                        # Get menu_type (from menu_type or menu_name)
                        menu_type = normalize_field(item, 'menu_type', ['menu_name'])
                        
                        # Get section (from section only)
                        section = normalize_field(item, 'section', [])
                        
                        # Create standardized row
                        row = {
                            'sr_no': sr_no,
                            'restaurant_name': normalize_field(item, 'restaurant_name', ['restaurant']),
                            'restaurant_url': normalize_field(item, 'restaurant_url', ['url', 'website']),
                            'menu_type': menu_type,
                            'section': section,
                            'name': normalize_field(item, 'name', ['item_name', 'item', 'title']),
                            'description': normalize_field(item, 'description', ['desc', 'details']),
                            'price': normalize_field(item, 'price', ['pricing', 'cost'])
                        }
                        
                        # Update statistics
                        if row['menu_type']:
                            stats['with_menu_type'] += 1
                        if row['section']:
                            stats['with_section'] += 1
                        if row['menu_type'] and row['section']:
                            stats['with_both'] += 1
                        if row['price']:
                            stats['with_price'] += 1
                        else:
                            stats['empty_price'] += 1
                        if not row['description']:
                            stats['empty_description'] += 1
                        if not row['name']:
                            stats['empty_name'] += 1
                        
                        writer.writerow(row)
                        sr_no += 1
                        record_count += 1
                        
                        # Track restaurant name for summary
                        if not restaurant_name and row['restaurant_name']:
                            restaurant_name = row['restaurant_name']
                
                total_records += record_count
                if restaurant_name:
                    records_by_restaurant[restaurant_name] = record_count
                else:
                    records_by_restaurant[json_file.stem] = record_count
                
                print(f"[INFO] Processed {json_file.name}: {record_count} records")
                
            except json.JSONDecodeError as e:
                print(f"[ERROR] Invalid JSON in {json_file.name}: {e}")
            except Exception as e:
                print(f"[ERROR] Error processing {json_file.name}: {e}")
    
    print(f"\n[SUCCESS] Created unified CSV file: {csv_file}")
    print(f"[INFO] Total records: {total_records}")
    print(f"[INFO] Total restaurants: {len(records_by_restaurant)}")
    print(f"[INFO] Serial numbers: 1 to {sr_no - 1}")
    
    # Sanity check
    print("\n" + "=" * 80)
    print("SANITY CHECK")
    print("=" * 80)
    print(f"Records with menu_type: {stats['with_menu_type']} ({stats['with_menu_type']/total_records*100:.1f}%)")
    print(f"Records with section: {stats['with_section']} ({stats['with_section']/total_records*100:.1f}%)")
    print(f"Records with both menu_type and section: {stats['with_both']} ({stats['with_both']/total_records*100:.1f}%)")
    print(f"Records with price: {stats['with_price']} ({stats['with_price']/total_records*100:.1f}%)")
    print(f"Records without price: {stats['empty_price']} ({stats['empty_price']/total_records*100:.1f}%)")
    print(f"Records without description: {stats['empty_description']} ({stats['empty_description']/total_records*100:.1f}%)")
    print(f"Records without name: {stats['empty_name']} ({stats['empty_name']/total_records*100:.1f}%)")
    
    # Create summary file
    summary_file = Path(__file__).parent / "csv_summary.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("UNIFIED CSV SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total Records: {total_records}\n")
        f.write(f"Total Restaurants: {len(records_by_restaurant)}\n")
        f.write(f"CSV File: {csv_file}\n")
        f.write(f"Serial Numbers: 1 to {sr_no - 1}\n\n")
        f.write("Columns:\n")
        f.write("  - sr_no: Serial number (1, 2, 3, ...)\n")
        f.write("  - restaurant_name: Name of the restaurant\n")
        f.write("  - restaurant_url: Website URL\n")
        f.write("  - menu_type: Menu type (Lunch, Dinner, Breakfast, etc.) from 'menu_type' or 'menu_name'\n")
        f.write("  - section: Menu section (Appetizers, Entrees, etc.) from 'section'\n")
        f.write("  - name: Menu item name\n")
        f.write("  - description: Item description\n")
        f.write("  - price: Item price\n\n")
        f.write("Sanity Check:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Records with menu_type: {stats['with_menu_type']} ({stats['with_menu_type']/total_records*100:.1f}%)\n")
        f.write(f"Records with section: {stats['with_section']} ({stats['with_section']/total_records*100:.1f}%)\n")
        f.write(f"Records with both: {stats['with_both']} ({stats['with_both']/total_records*100:.1f}%)\n")
        f.write(f"Records with price: {stats['with_price']} ({stats['with_price']/total_records*100:.1f}%)\n")
        f.write(f"Records without price: {stats['empty_price']} ({stats['empty_price']/total_records*100:.1f}%)\n")
        f.write(f"Records without description: {stats['empty_description']} ({stats['empty_description']/total_records*100:.1f}%)\n")
        f.write(f"Records without name: {stats['empty_name']} ({stats['empty_name']/total_records*100:.1f}%)\n\n")
        f.write("Records by Restaurant:\n")
        f.write("-" * 80 + "\n")
        
        # Sort by record count (descending)
        sorted_restaurants = sorted(records_by_restaurant.items(), key=lambda x: x[1], reverse=True)
        for restaurant, count in sorted_restaurants:
            f.write(f"{restaurant:50} {count:>6} records\n")
    
    print(f"[INFO] Created summary file: {summary_file}")
    print(f"\n[SUCCESS] Final CSV conversion complete!")
    print(f"[INFO] CSV saved to: {csv_file}")


if __name__ == "__main__":
    create_final_csv()

