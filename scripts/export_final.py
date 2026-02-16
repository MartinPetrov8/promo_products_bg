#!/usr/bin/env python3
"""Export products and matches to frontend JSON"""

import json
from datetime import datetime

PRODUCTS_FILE = 'standardized_final.json'
MATCHES_FILE = 'cross_store_matches_final.json'
OUTPUT_FILE = 'docs/data/products.json'

def export():
    # Load products
    with open(PRODUCTS_FILE) as f:
        products = json.load(f)
    
    # Load matches
    with open(MATCHES_FILE) as f:
        matches_data = json.load(f)
    
    # Build product ID to group mapping
    product_to_group = {}
    groups = {}
    
    for i, match in enumerate(matches_data['matches']):
        group_id = f"g{i+1}"
        p1, p2 = match['products'][0], match['products'][1]
        
        product_to_group[p1['id']] = group_id
        product_to_group[p2['id']] = group_id
        
        stores = sorted(set([p1['store'], p2['store']]))
        groups[group_id] = {
            'canonical_name': match.get('common_words', p1['clean_name']),
            'canonical_brand': match.get('brand'),
            'stores': stores,
            'confidence': 0.9,
            'off_barcode': None
        }
    
    # Build output products
    output_products = []
    for p in products:
        output_products.append({
            'id': p['id'],
            'name': p['raw_name'],
            'brand': p.get('brand'),
            'store': p['store'],
            'price': p['price'],
            'old_price': p.get('old_price'),
            'discount_pct': p.get('discount_pct'),
            'price_per_kg': p.get('unit_price') if p.get('unit_price_base') == 'kg' else None,
            'price_per_l': p.get('unit_price') if p.get('unit_price_base') == 'l' else None,
            'image_url': p.get('image_url'),
            'off_barcode': None,
            'group_id': product_to_group.get(p['id'])
        })
    
    # Build output
    output = {
        'meta': {
            'total_products': len(output_products),
            'cross_store_groups': len(groups),
            'updated_at': datetime.now().isoformat()
        },
        'products': output_products,
        'groups': groups,
        'off': {}
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # Stats
    with_group = sum(1 for p in output_products if p['group_id'])
    by_store = {}
    for p in output_products:
        by_store[p['store']] = by_store.get(p['store'], 0) + 1
    
    print(f"Exported to {OUTPUT_FILE}")
    print(f"  Products: {len(output_products)}")
    print(f"  Groups: {len(groups)}")
    print(f"  Products with matches: {with_group}")
    print(f"  By store: {by_store}")

if __name__ == '__main__':
    export()
