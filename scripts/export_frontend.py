#!/usr/bin/env python3
"""
Export cleaned products + cross-store matches to frontend data format.
"""

import json
from datetime import datetime, timezone

def main():
    # Load cleaned products
    with open('output/products_clean.json') as f:
        products = json.load(f)
    
    # Load cross-store matches
    with open('output/cross_store_matches.json') as f:
        matches = json.load(f)
    
    # Build groups from matches
    groups = {}
    product_groups = {}  # sku -> group_id
    
    for i, match in enumerate(matches):
        group_id = f"g{i+1}"
        stores = match['stores']
        store_list = list(stores.keys())
        
        # Find min/max prices
        prices = [s['price'] for s in stores.values()]
        min_price = min(prices)
        max_price = max(prices)
        savings = round((max_price - min_price) / max_price * 100, 1)
        
        groups[group_id] = {
            'name': match['product'],
            'category': match['category'],
            'stores': {
                store: {'price': info['price'], 'sku': info['sku']}
                for store, info in stores.items()
            },
            'min_price': min_price,
            'max_price': max_price,
            'savings': savings,
            'cheaper_store': match['cheaper_store']
        }
        
        # Map SKUs to group
        for store, info in stores.items():
            product_groups[info['sku']] = group_id
    
    # Build frontend products
    frontend_products = []
    for i, p in enumerate(products):
        price = p.get('price_bgn')
        if not price:
            continue
            
        frontend_products.append({
            'id': i + 1,
            'sku': p['sku'],
            'name': p['clean_name'] or p['raw_name'],
            'brand': p.get('brand') or '',
            'category': p.get('category', 'Други'),
            'store': p['store'],
            'price': price,
            'old_price': p.get('old_price_bgn'),
            'discount': p.get('discount_pct'),
            'image_url': p.get('image_url'),
            'url': p.get('url'),
            'group_id': product_groups.get(p['sku'])
        })
    
    # Sort by: has group first, then by discount
    frontend_products.sort(key=lambda x: (
        0 if x['group_id'] else 1,
        -(x.get('discount') or 0)
    ))
    
    # Build output
    output = {
        'meta': {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'total_products': len(frontend_products),
            'cross_store_groups': len(groups),
            'stores': ['Kaufland', 'Lidl', 'Billa']
        },
        'products': frontend_products,
        'groups': groups
    }
    
    with open('docs/data/products.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"=== EXPORTED ===")
    print(f"Products: {len(frontend_products)}")
    print(f"Groups: {len(groups)}")
    print(f"With group_id: {sum(1 for p in frontend_products if p['group_id'])}")
    print(f"\nSaved: docs/data/products.json")

if __name__ == '__main__':
    main()
