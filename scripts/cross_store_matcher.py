#!/usr/bin/env python3
"""
Cross-store product matcher.
Finds same/similar products across stores and compares prices.
"""

import json
import re
from difflib import SequenceMatcher
from collections import defaultdict

def normalize_quantity(qty, unit):
    """Normalize to base units (ml, g)."""
    if not qty or not unit:
        return None
    try:
        qty = float(qty)
    except:
        return None
    
    unit = unit.lower().strip()
    # Convert to base units
    if unit in ('l', 'л'):
        return qty * 1000, 'ml'
    if unit in ('kg', 'кг'):
        return qty * 1000, 'g'
    if unit in ('ml', 'мл'):
        return qty, 'ml'
    if unit in ('g', 'г', 'гр'):
        return qty, 'g'
    return qty, unit

def match_products(products, min_similarity=0.7, max_price_diff_pct=200):
    """Find cross-store matches."""
    
    def get_price(p):
        try:
            return float(p.get('price_bgn') or 0)
        except:
            return 0
    
    # Group by category (reduces O(n²) comparisons)
    by_category = defaultdict(list)
    for p in products:
        if get_price(p) > 0:
            by_category[p['category']].append(p)
    
    def similarity(a, b):
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    def qty_compatible(p1, p2):
        """Check if quantities are compatible (same or None)."""
        q1 = normalize_quantity(p1.get('quantity'), p1.get('quantity_unit'))
        q2 = normalize_quantity(p2.get('quantity'), p2.get('quantity_unit'))
        
        if q1 is None or q2 is None:
            return True  # Can't compare, allow match
        
        if q1[1] != q2[1]:
            return False  # Different unit types
        
        # Allow 20% quantity tolerance
        ratio = q1[0] / q2[0] if q2[0] else 0
        return 0.8 <= ratio <= 1.2
    
    matches = []
    for cat, items in by_category.items():
        if cat == 'Други':
            continue
            
        for i, p1 in enumerate(items):
            for p2 in items[i+1:]:
                if p1['store'] == p2['store']:
                    continue
                
                name_sim = similarity(p1['clean_name'] or '', p2['clean_name'] or '')
                if name_sim < min_similarity:
                    continue
                
                if not qty_compatible(p1, p2):
                    continue
                
                price1, price2 = get_price(p1), get_price(p2)
                price_diff_pct = abs(price1 - price2) / min(price1, price2) * 100
                
                if price_diff_pct > max_price_diff_pct:
                    continue  # Too different, probably not same product
                
                cheaper_store = p1['store'] if price1 < price2 else p2['store']
                savings_pct = (max(price1, price2) - min(price1, price2)) / max(price1, price2) * 100
                
                matches.append({
                    'product': p1['clean_name'],
                    'category': cat,
                    'stores': {
                        p1['store']: {'price': price1, 'sku': p1['sku']},
                        p2['store']: {'price': price2, 'sku': p2['sku']}
                    },
                    'cheaper_store': cheaper_store,
                    'savings_pct': round(savings_pct, 1),
                    'similarity': round(name_sim, 2)
                })
    
    # Sort by savings
    matches.sort(key=lambda x: -x['savings_pct'])
    return matches

def main():
    with open('output/products_clean.json') as f:
        products = json.load(f)
    
    print(f"Analyzing {len(products)} products...")
    matches = match_products(products)
    
    print(f"\n=== CROSS-STORE MATCHES: {len(matches)} ===\n")
    
    # Top savings
    print("TOP 20 SAVINGS:")
    for m in matches[:20]:
        stores = m['stores']
        store_list = list(stores.keys())
        print(f"{m['product'][:40]}")
        print(f"  {store_list[0]}: {stores[store_list[0]]['price']:.2f}лв | {store_list[1]}: {stores[store_list[1]]['price']:.2f}лв")
        print(f"  → {m['cheaper_store']} -{m['savings_pct']:.0f}%")
        print()
    
    # Save all matches
    with open('output/cross_store_matches.json', 'w', encoding='utf-8') as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: output/cross_store_matches.json")
    
    # Summary by store
    print("\n=== CHEAPEST STORE BY CATEGORY ===")
    from collections import Counter
    wins = Counter()
    for m in matches:
        wins[m['cheaper_store']] += 1
    
    for store, count in wins.most_common():
        print(f"  {store}: {count} wins ({count*100/len(matches):.1f}%)")

if __name__ == '__main__':
    main()
