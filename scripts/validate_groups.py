#!/usr/bin/env python3
"""
Validate and clean cross-store product groups.
Removes groups that fail quality checks.
"""
import json
import re
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).parent.parent
INPUT_FILE = REPO_ROOT / "docs" / "data" / "products.json"
OUTPUT_FILE = REPO_ROOT / "docs" / "data" / "products_clean.json"

# Minimum confidence for group inclusion
MIN_CONFIDENCE = 0.70

# Maximum price ratio within a group
MAX_PRICE_RATIO = 5.0

# Product type patterns (alcohol focus)
PRODUCT_TYPES = {
    'whisky': [r'уиски', r'уиск[иь]', r'whisky', r'whiskey', r'bourbon', r'бърбън', r'скоч', r'scotch'],
    'rum': [r'\bром\b', r'\brum\b'],
    'vodka': [r'водка', r'vodka'],
    'gin': [r'\bджин\b', r'\bgin\b'],
    'tequila': [r'текила', r'tequila'],
    'liqueur': [r'ликьор', r'liqueur', r'liquor'],
    'wine': [r'\bвино\b', r'\bwine\b', r'шампанско', r'champagne', r'prosecco'],
    'beer': [r'\bбира\b', r'\bbeer\b', r'пиво'],
    'brandy': [r'коняк', r'бренди', r'brandy', r'cognac'],
}


def detect_product_type(name: str) -> str:
    """Detect alcohol product type from name."""
    name_lower = name.lower()
    for ptype, patterns in PRODUCT_TYPES.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                return ptype
    return 'other'


def validate_group(group_id: str, products: list, group_info: dict) -> dict:
    """
    Validate a group. Returns dict with:
    - valid: bool
    - reasons: list of failure reasons
    - clean_products: list of valid products
    """
    result = {
        'valid': True,
        'reasons': [],
        'clean_products': products.copy(),
        'removed': []
    }
    
    if len(products) < 2:
        result['valid'] = False
        result['reasons'].append('less_than_2_products')
        return result
    
    # Check 1: Confidence threshold
    low_conf_products = []
    for p in products:
        conf = p.get('match_confidence') or 0
        if conf < MIN_CONFIDENCE:
            low_conf_products.append(p)
    
    if low_conf_products:
        result['reasons'].append(f'low_confidence: {len(low_conf_products)} products below {MIN_CONFIDENCE}')
        # Remove low confidence products
        result['clean_products'] = [p for p in result['clean_products'] if p not in low_conf_products]
        result['removed'].extend(low_conf_products)
    
    # Check 2: Product type consistency
    types = defaultdict(list)
    for p in result['clean_products']:
        ptype = detect_product_type(p['name'])
        types[ptype].append(p)
    
    # Remove 'other' from consideration if we have specific types
    specific_types = {k: v for k, v in types.items() if k != 'other'}
    if len(specific_types) > 1:
        # Multiple product types - keep only the majority type
        result['reasons'].append(f'mixed_types: {list(specific_types.keys())}')
        majority_type = max(specific_types.items(), key=lambda x: len(x[1]))[0]
        # Keep majority + 'other', remove rest
        keep_types = {majority_type, 'other'}
        removed = [p for p in result['clean_products'] if detect_product_type(p['name']) not in keep_types]
        result['clean_products'] = [p for p in result['clean_products'] if detect_product_type(p['name']) in keep_types]
        result['removed'].extend(removed)
    
    # Check 3: Price sanity
    if len(result['clean_products']) >= 2:
        prices = [p['price'] for p in result['clean_products'] if p.get('price')]
        if prices and len(prices) >= 2:
            price_ratio = max(prices) / min(prices)
            if price_ratio > MAX_PRICE_RATIO:
                result['reasons'].append(f'price_ratio: {price_ratio:.1f}x (max {MAX_PRICE_RATIO}x)')
                # Remove outliers (keep median-ish products)
                median_price = sorted(prices)[len(prices) // 2]
                removed = []
                kept = []
                for p in result['clean_products']:
                    if p.get('price'):
                        ratio = max(p['price'], median_price) / min(p['price'], median_price)
                        if ratio > MAX_PRICE_RATIO:
                            removed.append(p)
                        else:
                            kept.append(p)
                    else:
                        kept.append(p)
                result['clean_products'] = kept
                result['removed'].extend(removed)
    
    # Final check: still have 2+ products?
    if len(result['clean_products']) < 2:
        result['valid'] = False
        result['reasons'].append('insufficient_products_after_cleanup')
    elif result['reasons']:
        result['valid'] = False  # Had issues, mark invalid but provide cleanup
    
    return result


def main():
    print("=" * 60)
    print("CROSS-STORE GROUP VALIDATION")
    print("=" * 60)
    
    # Load data
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    products = data['products']
    groups = data.get('groups', {})
    
    print(f"Loaded {len(products)} products, {len(groups)} groups")
    
    # Index products by group_id
    products_by_group = defaultdict(list)
    for p in products:
        if p.get('group_id'):
            products_by_group[p['group_id']].append(p)
    
    # Validate each group
    stats = {
        'total': len(groups),
        'valid': 0,
        'invalid': 0,
        'reasons': defaultdict(int),
        'products_removed': 0,
        'groups_dissolved': 0,
    }
    
    invalid_groups = []
    clean_groups = {}
    
    for group_id, group_info in groups.items():
        group_products = products_by_group.get(group_id, [])
        result = validate_group(group_id, group_products, group_info)
        
        if result['valid']:
            stats['valid'] += 1
            clean_groups[group_id] = group_info
        else:
            stats['invalid'] += 1
            for reason in result['reasons']:
                reason_key = reason.split(':')[0]
                stats['reasons'][reason_key] += 1
            
            if len(result['clean_products']) >= 2:
                # Can salvage with cleanup
                clean_groups[group_id] = group_info
            else:
                stats['groups_dissolved'] += 1
            
            stats['products_removed'] += len(result['removed'])
            
            invalid_groups.append({
                'group_id': group_id,
                'off_barcode': group_info.get('off_barcode'),
                'reasons': result['reasons'],
                'products': [{'store': p['store'], 'name': p['name'], 'price': p['price'], 
                              'conf': p.get('match_confidence')} for p in group_products],
                'removed': [{'store': p['store'], 'name': p['name']} for p in result['removed']]
            })
    
    # Print results
    print(f"\n{'='*60}")
    print("VALIDATION RESULTS")
    print("="*60)
    print(f"Total groups: {stats['total']}")
    print(f"Valid groups: {stats['valid']}")
    print(f"Invalid groups: {stats['invalid']}")
    print(f"Groups dissolved: {stats['groups_dissolved']}")
    print(f"Products removed from groups: {stats['products_removed']}")
    
    print(f"\nFailure reasons:")
    for reason, count in sorted(stats['reasons'].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")
    
    # Show sample of invalid groups
    print(f"\n{'='*60}")
    print("SAMPLE INVALID GROUPS (first 10)")
    print("="*60)
    for ig in invalid_groups[:10]:
        print(f"\n[{ig['group_id']}] OFF: {ig['off_barcode']}")
        print(f"  Reasons: {ig['reasons']}")
        for p in ig['products']:
            status = "❌" if any(p['name'] == r['name'] for r in ig['removed']) else "✓"
            print(f"  {status} {p['store']}: {p['name'][:50]} - €{p['price']} (conf: {p['conf']})")
    
    # Update products - remove group_id from removed products
    removed_products = set()
    for ig in invalid_groups:
        for r in ig['removed']:
            removed_products.add((r['store'], r['name']))
    
    for p in products:
        key = (p['store'], p['name'])
        if key in removed_products:
            p['group_id'] = None  # Remove from group
    
    # Rebuild groups dict
    new_groups = {}
    for group_id in clean_groups:
        group_products = [p for p in products if p.get('group_id') == group_id]
        if len(group_products) >= 2:
            stores = list(set(p['store'] for p in group_products))
            prices = [p['price'] for p in group_products if p.get('price')]
            new_groups[group_id] = {
                'off_barcode': groups[group_id].get('off_barcode'),
                'product_ids': [p['id'] for p in group_products],
                'stores': sorted(stores),
                'min_price': min(prices) if prices else None,
                'max_price': max(prices) if prices else None
            }
    
    # Output
    output = {
        'meta': {
            'updated_at': data['meta']['updated_at'],
            'total_products': len(products),
            'cross_store_groups': len(new_groups),
            'stores': data['meta']['stores'],
            'validation': {
                'groups_before': len(groups),
                'groups_after': len(new_groups),
                'products_removed': stats['products_removed']
            }
        },
        'products': products,
        'off': data.get('off', {}),
        'groups': new_groups
    }
    
    # Write clean output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Clean data written to {OUTPUT_FILE}")
    print(f"  Groups: {len(groups)} → {len(new_groups)}")
    
    # Also write validation report
    report_file = REPO_ROOT / "docs" / "data" / "validation_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'stats': dict(stats),
            'invalid_groups': invalid_groups
        }, f, ensure_ascii=False, indent=2)
    print(f"  Report: {report_file}")
    
    return stats


if __name__ == "__main__":
    main()
