#!/usr/bin/env python3
"""
Final validation - manual cleanup of remaining issues.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INPUT = REPO_ROOT / "docs" / "data" / "products_clean.json"
OUTPUT = REPO_ROOT / "docs" / "data" / "products_final.json"

# Manual rejection list
INVALID_GROUPS = {
    'g_e9e0d568',  # Pepsi vs generic soda
    'g_d0a68d78',  # Chocolate bar vs donut
}

def main():
    with open(INPUT) as f:
        data = json.load(f)
    
    # Remove invalid groups
    products = data['products']
    for p in products:
        if p.get('group_id') in INVALID_GROUPS:
            p['group_id'] = None
    
    final_groups = {k: v for k, v in data['groups'].items() if k not in INVALID_GROUPS}
    
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
    
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Final clean data: {OUTPUT}")
    print(f"  Groups: {len(data['groups'])} → {len(final_groups)}")
    
    print("\n=== FINAL VALID GROUPS ===")
    for gid, ginfo in final_groups.items():
        prods = [p for p in products if p.get('group_id') == gid]
        print(f"\n{gid}:")
        for p in prods:
            print(f"  {p['store']}: {p['name'][:40]} - €{p['price']}")


if __name__ == "__main__":
    main()
