#!/usr/bin/env python3
"""
Validate and clean cross-store product groups - V2.
Stricter rules:
- Must have 2+ DIFFERENT stores
- Brand must match if both have brands
- Product type must match
- Price ratio <= 4x
- No absurd prices (>€100 for groceries)
"""
import json
import re
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).parent.parent
INPUT_FILE = REPO_ROOT / "docs" / "data" / "products.json"
OUTPUT_FILE = REPO_ROOT / "docs" / "data" / "products_clean.json"

MIN_CONFIDENCE = 0.75
MAX_PRICE_RATIO = 4.0
MAX_GROCERY_PRICE = 100.0  # €100 cap for regular groceries

# Meat types - must not mix
MEAT_TYPES = {
    'pork': [r'свин', r'pork'],
    'beef': [r'телеш', r'говежд', r'beef'],
    'lamb': [r'агнеш', r'lamb'],
    'chicken': [r'пиле', r'пилеш', r'chicken'],
    'turkey': [r'пуйка', r'пуйч', r'turkey'],
    'fish': [r'риба', r'fish', r'сьомга', r'скумрия'],
}

# Vegetable types - must not mix
VEG_TYPES = {
    'potato': [r'\bкартоф', r'potato'],
    'sweet_potato': [r'сладък картоф', r'сладки картоф', r'sweet potato', r'батат'],
    'carrot': [r'морков', r'carrot'],
}

# Dairy types - must not mix
DAIRY_TYPES = {
    'milk': [r'\bмляко\b', r'\bmilk\b'],
    'yogurt': [r'кисело мляко', r'йогурт', r'yogurt'],
    'cheese': [r'сирене', r'кашкавал', r'cheese'],
    'butter': [r'масло', r'butter'],
}


def detect_subtype(name: str, type_dict: dict) -> str:
    """Detect subtype from name."""
    name_lower = name.lower()
    for subtype, patterns in type_dict.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                return subtype
    return None


def extract_brand(name: str) -> str:
    """Extract likely brand from product name (first word often)."""
    # Known brands
    brands = ['ferrero', 'rocher', 'raffaello', 'merci', 'pergale', 'roshen', 
              'pepsi', 'coca-cola', 'fanta', 'sprite', 'heinz', 'jacobs', 'tchibo',
              'monini', 'bertolli', 'filippo berio', 'marlenka', 'muhler']
    name_lower = name.lower()
    for brand in brands:
        if brand in name_lower:
            return brand
    return None


def validate_group_strict(group_id: str, products: list) -> dict:
    """Stricter validation."""
    result = {
        'valid': True,
        'reasons': [],
        'clean_products': products.copy(),
    }
    
    # Check 1: Need 2+ DIFFERENT stores
    stores = set(p['store'] for p in products)
    if len(stores) < 2:
        result['valid'] = False
        result['reasons'].append(f'same_store_only: {list(stores)}')
        return result
    
    # Check 2: Confidence threshold
    low_conf = [p for p in products if (p.get('match_confidence') or 0) < MIN_CONFIDENCE]
    if low_conf:
        result['valid'] = False
        result['reasons'].append(f'low_confidence: {len(low_conf)} below {MIN_CONFIDENCE}')
    
    # Check 3: Absurd prices
    absurd = [p for p in products if p.get('price', 0) > MAX_GROCERY_PRICE]
    if absurd:
        result['valid'] = False
        result['reasons'].append(f'absurd_price: {[p["price"] for p in absurd]}')
    
    # Check 4: Price ratio
    prices = [p['price'] for p in products if p.get('price') and p['price'] <= MAX_GROCERY_PRICE]
    if len(prices) >= 2:
        ratio = max(prices) / min(prices)
        if ratio > MAX_PRICE_RATIO:
            result['valid'] = False
            result['reasons'].append(f'price_ratio: {ratio:.1f}x > {MAX_PRICE_RATIO}x')
    
    # Check 5: Product subtype consistency (meat, veg, dairy)
    for type_name, type_dict in [('meat', MEAT_TYPES), ('veg', VEG_TYPES), ('dairy', DAIRY_TYPES)]:
        subtypes = {}
        for p in products:
            st = detect_subtype(p['name'], type_dict)
            if st:
                subtypes[st] = subtypes.get(st, 0) + 1
        if len(subtypes) > 1:
            result['valid'] = False
            result['reasons'].append(f'mixed_{type_name}: {list(subtypes.keys())}')
    
    # Check 6: Brand consistency (if detectable)
    brands = set()
    for p in products:
        b = extract_brand(p['name'])
        if b:
            brands.add(b)
    if len(brands) > 1:
        result['valid'] = False
        result['reasons'].append(f'mixed_brands: {list(brands)}')
    
    return result


def main():
    print("=" * 60)
    print("STRICT CROSS-STORE GROUP VALIDATION (V2)")
    print("=" * 60)
    
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    products = data['products']
    groups = data.get('groups', {})
    
    products_by_group = defaultdict(list)
    for p in products:
        if p.get('group_id'):
            products_by_group[p['group_id']].append(p)
    
    stats = {'total': len(groups), 'valid': 0, 'invalid': 0, 'reasons': defaultdict(int)}
    valid_groups = {}
    
    print(f"\nValidating {len(groups)} groups...\n")
    
    for gid, ginfo in groups.items():
        gprods = products_by_group.get(gid, [])
        result = validate_group_strict(gid, gprods)
        
        if result['valid']:
            stats['valid'] += 1
            valid_groups[gid] = ginfo
            print(f"✓ {gid}: {len(gprods)} products, {len(set(p['store'] for p in gprods))} stores")
        else:
            stats['invalid'] += 1
            for r in result['reasons']:
                stats['reasons'][r.split(':')[0]] += 1
            print(f"✗ {gid}: {result['reasons']}")
            for p in gprods:
                print(f"    - {p['store']}: {p['name'][:40]} €{p['price']}")
    
    print(f"\n{'='*60}")
    print("RESULTS")
    print("="*60)
    print(f"Valid: {stats['valid']} / {stats['total']}")
    print(f"Invalid: {stats['invalid']}")
    print(f"\nFailure breakdown:")
    for r, c in sorted(stats['reasons'].items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")
    
    # Remove group_id from invalid products
    valid_group_ids = set(valid_groups.keys())
    for p in products:
        if p.get('group_id') and p['group_id'] not in valid_group_ids:
            p['group_id'] = None
    
    # Rebuild valid groups
    final_groups = {}
    for gid in valid_group_ids:
        gprods = [p for p in products if p.get('group_id') == gid]
        stores = list(set(p['store'] for p in gprods))
        prices = [p['price'] for p in gprods if p.get('price')]
        final_groups[gid] = {
            'off_barcode': groups[gid].get('off_barcode'),
            'product_ids': [p['id'] for p in gprods],
            'stores': sorted(stores),
            'min_price': min(prices) if prices else None,
            'max_price': max(prices) if prices else None
        }
    
    output = {
        'meta': {
            'updated_at': data['meta']['updated_at'],
            'total_products': len(products),
            'cross_store_groups': len(final_groups),
            'stores': data['meta']['stores']
        },
        'products': products,
        'off': data.get('off', {}),
        'groups': final_groups
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Clean data: {OUTPUT_FILE}")
    print(f"  Groups: {len(groups)} → {len(final_groups)}")


if __name__ == "__main__":
    main()
