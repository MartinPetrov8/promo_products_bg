#!/usr/bin/env python3
"""
Kaufland Data Cleaner

Updates Kaufland products in the database with enhanced data from the scraper:
1. Adds brand extraction
2. Adds size from subtitle, description, or title
3. Cleans product names
"""

import re
import sqlite3
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"
KAUFLAND_DATA = PROJECT_ROOT / "services" / "scraper" / "data" / "kaufland_enhanced.json"


def normalize_name(name: str) -> str:
    """Normalize name for matching."""
    if not name:
        return ""
    # Lowercase, remove special chars, collapse whitespace
    name = name.lower()
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def load_enhanced_data() -> dict:
    """Load enhanced data from scraper, indexed by normalized title."""
    if not KAUFLAND_DATA.exists():
        print(f"ERROR: {KAUFLAND_DATA} not found!")
        print("Run the kaufland_enhanced_scraper.py first.")
        return {}
    
    with open(KAUFLAND_DATA) as f:
        products = json.load(f)
    
    # Index by normalized title for name-based matching
    result = {}
    for p in products:
        key = normalize_name(p.get('title', ''))
        if key:
            result[key] = p
        # Also index by detail_title if different
        detail_key = normalize_name(p.get('detail_title', ''))
        if detail_key and detail_key != key:
            result[detail_key] = p
    
    return result


def run_analysis():
    """Analyze what would be updated."""
    print("=" * 70)
    print("KAUFLAND DATA CLEANING ANALYSIS")
    print("=" * 70)
    
    enhanced = load_enhanced_data()
    if not enhanced:
        return []
    
    print(f"Loaded {len(enhanced)} products from enhanced scraper")
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    # Get Kaufland products from DB
    cursor.execute('''
        SELECT p.id, p.name, p.brand, p.quantity, p.unit, sp.store_product_code
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = 1
    ''')
    db_products = cursor.fetchall()
    print(f"Total Kaufland products in DB: {len(db_products)}")
    
    to_update = []
    matched = 0
    will_add_size = 0
    will_add_brand = 0
    
    for pid, name, db_brand, db_quantity, db_unit, store_code in db_products:
        update = {
            'id': pid,
            'original_name': name,
            'original_brand': db_brand,
            'original_quantity': db_quantity,
            'original_unit': db_unit,
        }
        
        # Try to match by normalized name
        norm_name = normalize_name(name)
        enh = enhanced.get(norm_name)
        if enh:
            matched += 1
            
            # Copy enhanced data
            if enh.get('size_value') and not db_quantity:
                update['size_value'] = enh['size_value']
                update['size_unit'] = enh['size_unit']
                will_add_size += 1
            
            if enh.get('brand') and not db_brand:
                update['new_brand'] = enh['brand']
                will_add_brand += 1
            
            if enh.get('detail_title'):
                update['cleaned_name'] = enh['detail_title']
            else:
                update['cleaned_name'] = name
            
            update['description'] = enh.get('description')
        else:
            update['cleaned_name'] = name
        
        to_update.append(update)
    
    print(f"\nAnalysis:")
    print(f"  Matched to enhanced data: {matched}")
    print(f"  Will add size: {will_add_size}")
    print(f"  Will add brand: {will_add_brand}")
    
    # Sample
    print("\n" + "=" * 70)
    print("SAMPLE UPDATES")
    print("=" * 70)
    
    samples = [u for u in to_update if u.get('size_value') or u.get('new_brand')][:15]
    for item in samples:
        print(f"\nOriginal: {item['original_name'][:50]}")
        print(f"  Cleaned: {item.get('cleaned_name', '')[:50]}")
        print(f"  Brand: {item.get('original_brand')} → {item.get('new_brand')}")
        print(f"  Size: {item.get('original_quantity')} → {item.get('size_value')} {item.get('size_unit')}")
    
    conn.close()
    return to_update


def update_database(updates: list):
    """Apply updates to database."""
    print("\n" + "=" * 70)
    print("UPDATING DATABASE")
    print("=" * 70)
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    updated_sizes = 0
    updated_brands = 0
    
    for item in updates:
        # Update normalized name
        if item.get('cleaned_name'):
            cursor.execute('''
                UPDATE products 
                SET normalized_name = ?
                WHERE id = ?
            ''', (item['cleaned_name'].lower(), item['id']))
        
        # Update size
        if item.get('size_value'):
            cursor.execute('''
                UPDATE products 
                SET quantity = ?, unit = ?
                WHERE id = ?
            ''', (item['size_value'], item['size_unit'], item['id']))
            updated_sizes += 1
        
        # Update brand
        if item.get('new_brand'):
            cursor.execute('''
                UPDATE products 
                SET brand = ?
                WHERE id = ?
            ''', (item['new_brand'], item['id']))
            updated_brands += 1
    
    conn.commit()
    
    # Verify
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN brand IS NOT NULL AND brand != '' THEN 1 ELSE 0 END) as with_brand,
            SUM(CASE WHEN quantity IS NOT NULL THEN 1 ELSE 0 END) as with_size
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = 1
    ''')
    total, brands, sizes = cursor.fetchone()
    
    print(f"Updated {updated_sizes} sizes, {updated_brands} brands")
    print(f"\nVerification:")
    print(f"  Total Kaufland products: {total}")
    print(f"  With brand: {brands}")
    print(f"  With size: {sizes}")
    
    conn.close()


if __name__ == '__main__':
    data = run_analysis()
    
    if '--update' in sys.argv:
        update_database(data)
    else:
        print("\n⚠️  Run with --update to apply changes to database")
