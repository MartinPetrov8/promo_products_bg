#!/usr/bin/env python3
"""
Cross-store product matcher v2.

Matching logic:
1. Brand + name similarity (if both have brand)
2. Name similarity (fallback)

Quantity rules:
- "Други" category: match only if BOTH have no quantity, OR quantities match
- Categorized products: allow one missing quantity (category confirms product type)
- kg products (fruits/veg): comparable (price per kg is standard)
- XXL/size indicators: NOT comparable unless BOTH have same indicator
"""

import json
import re
from difflib import SequenceMatcher
from collections import defaultdict

# Size indicators that make products incomparable
SIZE_INDICATORS = ['xxl', 'xl', 'семейна', 'семеен', 'голям', 'малък', 'мини', 'макси', 'джъмбо', 'jumbo', 'фамилия']

def normalize_name(name):
    """Normalize name for comparison."""
    if not name:
        return ''
    n = name.lower()
    n = re.sub(r'[^\w\sа-яё]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def get_size_indicators(text):
    """Get list of size indicators in text."""
    if not text:
        return []
    text_lower = text.lower()
    return sorted([ind for ind in SIZE_INDICATORS if ind in text_lower])

def normalize_quantity(qty_val, qty_unit):
    """Normalize to base units (ml, g). Returns (value, unit) or None."""
    if not qty_val or not qty_unit:
        return None
    try:
        qty = float(qty_val)
    except:
        return None
    
    unit = qty_unit.lower().strip()
    
    if unit in ('l', 'л', 'литър', 'литра'):
        return qty * 1000, 'ml'
    if unit in ('kg', 'кг', 'килограм'):
        return qty * 1000, 'g'
    if unit in ('ml', 'мл', 'милилитър'):
        return qty, 'ml'
    if unit in ('g', 'г', 'гр', 'грам'):
        return qty, 'g'
    if unit in ('бр', 'бр.', 'броя', 'брой'):
        return qty, 'pcs'
    
    return qty, unit

def is_per_kg_product(product):
    """Check if product is priced per kg (fruits, vegetables, meat)."""
    name = (product.get('clean_name') or product.get('raw_name') or '').lower()
    
    if re.search(r'за\s*1\s*кг|на\s*кг|per\s*kg|\/кг', name):
        return True
    
    unit = (product.get('quantity_unit') or '').lower()
    if unit in ('kg', 'кг'):
        qty = product.get('quantity_value')
        if qty and float(qty) == 1:
            return True
    
    return False

def similarity(a, b):
    """String similarity ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def quantities_compatible(p1, p2):
    """Check if quantities are compatible."""
    q1 = normalize_quantity(p1.get('quantity_value'), p1.get('quantity_unit'))
    q2 = normalize_quantity(p2.get('quantity_value'), p2.get('quantity_unit'))
    
    if q1 is None and q2 is None:
        return True, "both_no_qty"
    
    if q1 is None or q2 is None:
        return None, "one_missing_qty"  # Return None = maybe (depends on context)
    
    if q1[1] != q2[1]:
        return False, "different_units"
    
    ratio = q1[0] / q2[0] if q2[0] else 0
    if 0.8 <= ratio <= 1.2:
        return True, "qty_match"
    
    return False, "qty_mismatch"

def can_compare_products(p1, p2, category):
    """
    Determine if two products are comparable.
    Returns: (comparable: bool, reason: str)
    """
    name1 = p1.get('clean_name') or p1.get('raw_name') or ''
    name2 = p2.get('clean_name') or p2.get('raw_name') or ''
    
    if len(name1) < 3 or len(name2) < 3:
        return False, "empty_name"
    
    # Size indicator check - must have same indicators
    ind1 = get_size_indicators(name1)
    ind2 = get_size_indicators(name2)
    
    if ind1 != ind2:
        return False, "size_indicator_mismatch"
    
    # Per-kg products always comparable
    if is_per_kg_product(p1) and is_per_kg_product(p2):
        return True, "per_kg"
    
    # Quantity compatibility check
    qty_ok, qty_reason = quantities_compatible(p1, p2)
    
    if qty_ok is True:
        return True, qty_reason
    
    if qty_ok is False:
        return False, qty_reason
    
    # qty_ok is None (one_missing_qty)
    # For "Други" category: strict - require both have or neither has quantity
    if category == 'Други':
        return False, "altri_missing_qty"
    
    # For categorized products: allow (category confirms product type)
    return True, "categorized_one_missing_qty"

def match_score(p1, p2, min_name_sim=0.65):
    """Calculate match score."""
    name1 = normalize_name(p1.get('clean_name') or p1.get('raw_name'))
    name2 = normalize_name(p2.get('clean_name') or p2.get('raw_name'))
    
    brand1 = (p1.get('brand') or '').strip()
    brand2 = (p2.get('brand') or '').strip()
    
    if brand1 in ('', 'NO_BRAND'):
        brand1 = None
    if brand2 in ('', 'NO_BRAND'):
        brand2 = None
    
    # Method 1: Brand + name (both have brand)
    if brand1 and brand2:
        brand_sim = similarity(brand1, brand2)
        name_sim = similarity(name1, name2)
        
        if brand_sim >= 0.85 and name_sim >= 0.55:
            combined = brand_sim * 0.3 + name_sim * 0.7
            return combined, "brand+name"
    
    # Method 2: Name only
    name_sim = similarity(name1, name2)
    if name_sim >= min_name_sim:
        return name_sim, "name_only"
    
    return 0, None

def match_products(products, min_similarity=0.65, max_price_diff_pct=150):
    """Find cross-store matches."""
    
    def get_price(p):
        try:
            return float(p.get('price_bgn') or 0)
        except:
            return 0
    
    valid_products = [p for p in products 
                      if get_price(p) > 0 
                      and len(p.get('clean_name') or p.get('raw_name') or '') >= 3]
    print(f"Valid products: {len(valid_products)}")
    
    by_category = defaultdict(list)
    for p in valid_products:
        cat = p.get('category', 'Други')
        by_category[cat].append(p)
    
    matches = []
    stats = {'comparisons': 0, 'by_method': defaultdict(int), 'rejected': defaultdict(int)}
    
    for cat, items in by_category.items():
        if len(items) < 2:
            continue
            
        for i, p1 in enumerate(items):
            for p2 in items[i+1:]:
                if p1['store'] == p2['store']:
                    continue
                
                stats['comparisons'] += 1
                
                comparable, reason = can_compare_products(p1, p2, cat)
                if not comparable:
                    stats['rejected'][reason] += 1
                    continue
                
                score, method = match_score(p1, p2, min_similarity)
                if score == 0:
                    continue
                
                price1, price2 = get_price(p1), get_price(p2)
                price_diff_pct = abs(price1 - price2) / min(price1, price2) * 100
                
                if price_diff_pct > max_price_diff_pct:
                    stats['rejected']['price_too_different'] += 1
                    continue
                
                stats['by_method'][method] += 1
                
                cheaper_store = p1['store'] if price1 < price2 else p2['store']
                savings_pct = (max(price1, price2) - min(price1, price2)) / max(price1, price2) * 100
                
                matches.append({
                    'product': p1.get('clean_name') or p1.get('raw_name'),
                    'product_alt': p2.get('clean_name') or p2.get('raw_name'),
                    'category': cat,
                    'stores': {
                        p1['store']: {
                            'price': price1, 
                            'sku': p1['sku'], 
                            'name': p1.get('clean_name') or p1.get('raw_name'),
                            'quantity': f"{p1.get('quantity_value') or ''} {p1.get('quantity_unit') or ''}".strip()
                        },
                        p2['store']: {
                            'price': price2, 
                            'sku': p2['sku'], 
                            'name': p2.get('clean_name') or p2.get('raw_name'),
                            'quantity': f"{p2.get('quantity_value') or ''} {p2.get('quantity_unit') or ''}".strip()
                        }
                    },
                    'cheaper_store': cheaper_store,
                    'savings_pct': round(savings_pct, 1),
                    'similarity': round(score, 2),
                    'match_method': method
                })
    
    matches.sort(key=lambda x: -x['savings_pct'])
    return matches, stats

def main():
    with open('output/products_clean.json') as f:
        products = json.load(f)
    
    print(f"=== CROSS-STORE MATCHER v2 ===")
    print(f"Total products: {len(products)}\n")
    
    matches, stats = match_products(products)
    
    print(f"\n=== RESULTS ===")
    print(f"Comparisons: {stats['comparisons']:,}")
    print(f"Matches: {len(matches)}")
    
    print(f"\nBy method:")
    for method, count in sorted(stats['by_method'].items(), key=lambda x: -x[1]):
        print(f"  {method}: {count}")
    
    print(f"\nRejections:")
    for reason, count in sorted(stats['rejected'].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")
    
    print(f"\n=== TOP 20 SAVINGS ===\n")
    for m in matches[:20]:
        stores = m['stores']
        store_list = list(stores.keys())
        s1, s2 = stores[store_list[0]], stores[store_list[1]]
        q1 = s1.get('quantity', '')
        q2 = s2.get('quantity', '')
        print(f"{m['product'][:45]}")
        print(f"  {store_list[0]}: {s1['price']:.2f}лв {q1}")
        print(f"  {store_list[1]}: {s2['price']:.2f}лв {q2}")
        print(f"  → {m['cheaper_store']} -{m['savings_pct']:.0f}% [{m['match_method']}]")
        print()
    
    with open('output/cross_store_matches.json', 'w', encoding='utf-8') as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)
    print(f"Saved: output/cross_store_matches.json ({len(matches)} matches)")
    
    print("\n=== STORE WINS ===")
    from collections import Counter
    wins = Counter(m['cheaper_store'] for m in matches)
    for store, count in wins.most_common():
        print(f"  {store}: {count} ({count*100/len(matches):.1f}%)")

if __name__ == '__main__':
    main()
