#!/usr/bin/env python3
"""Quick export to products.json for frontend"""

import sqlite3
import json
from datetime import datetime
from collections import defaultdict

DB_PATH = 'data/promobg.db'
OUTPUT_PATH = 'docs/data/products.json'

def export_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get all products with prices
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand,
            s.name as store,
            pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE pr.current_price IS NOT NULL AND pr.current_price > 0
    """)
    
    products = []
    product_ids = {}  # Map product name to list of IDs
    
    for row in cur.fetchall():
        prod = {
            'id': row['id'],
            'name': row['name'],
            'brand': row['brand'],
            'store': row['store'],
            'price': round(row['price'], 2),
            'group_id': None
        }
        products.append(prod)
        
        # Track by normalized name for grouping
        key = row['name'].lower().strip()
        if key not in product_ids:
            product_ids[key] = []
        product_ids[key].append(row['id'])
    
    print(f"Loaded {len(products)} products")
    
    # Get cross-store matches
    cur.execute("""
        SELECT * FROM cross_store_matches
    """)
    
    groups = {}
    group_counter = 1
    
    for row in cur.fetchall():
        group_id = f"g{group_counter}"
        group_counter += 1
        
        stores = []
        product_ids_in_group = []
        
        if row['kaufland_product_id']:
            stores.append('Kaufland')
            product_ids_in_group.append(row['kaufland_product_id'])
        if row['lidl_product_id']:
            stores.append('Lidl')
            product_ids_in_group.append(row['lidl_product_id'])
        if row['billa_product_id']:
            stores.append('Billa')
            product_ids_in_group.append(row['billa_product_id'])
        
        if len(stores) >= 2:
            groups[group_id] = {
                'canonical_name': row['canonical_name'],
                'canonical_brand': row['canonical_brand'],
                'stores': stores,
                'confidence': row['confidence']
            }
            
            # Assign group_id to products
            for prod in products:
                if prod['id'] in product_ids_in_group:
                    prod['group_id'] = group_id
    
    print(f"Found {len(groups)} cross-store groups")
    
    # Calculate stats
    cross_store_count = len([p for p in products if p['group_id']])
    
    # Build output
    output = {
        'meta': {
            'total_products': len(products),
            'cross_store_groups': len(groups),
            'updated_at': datetime.now().isoformat()
        },
        'products': products,
        'groups': groups,
        'off': {}  # Empty for now
    }
    
    # Write output
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"Exported to {OUTPUT_PATH}")
    print(f"  Products: {len(products)}")
    print(f"  Groups: {len(groups)}")

if __name__ == "__main__":
    export_data()
