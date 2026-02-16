#!/usr/bin/env python3
"""
QA Cleanup Script - Fix matching and price issues.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).parent.parent
INPUT_FILE = REPO / "docs" / "data" / "products.json"
OUTPUT_FILE = REPO / "docs" / "data" / "products_clean.json"

# Price thresholds
MAX_FOOD_PRICE = 50  # No food item should cost more than €50
MIN_PRICE = 0.05     # Nothing should cost less than 5 cents

# Matching thresholds
MIN_CONFIDENCE = 0.85  # Reject matches below this

# Food keywords for Lidl price fix
FOOD_KEYWORDS = [
    'хляб', 'донат', 'мъфин', 'кифла', 'баничка', 'кроасан', 'земел', 
    'брецел', 'бейгъл', 'брускета', 'енсаимада', 'пура', 'кит кат',
    'орео', 'milka', 'лаваш', 'питка', 'франзела', 'козунак', 'руло',
    'торта', 'кекс', 'бисквита', 'вафла', 'шоколад', 'бонбон',
    'джинджифил', 'сладкиш', 'десерт'
]

# Non-food keywords (these can legitimately be expensive)
NONFOOD_KEYWORDS = [
    'бормашина', 'прахосмукачка', 'фурна', 'фрайър', 'миксер', 'блендер',
    'уред', 'машина', 'станция', 'инструмент', 'акумулаторн', 'електрическ',
    'телевизор', 'монитор', 'компютър', 'таблет', 'телефон'
]

def is_food_item(name):
    """Check if product name suggests food/bakery item."""
    name_lower = name.lower()
    
    # Check for non-food first
    for kw in NONFOOD_KEYWORDS:
        if kw in name_lower:
            return False
    
    # Check for food
    for kw in FOOD_KEYWORDS:
        if kw in name_lower:
            return True
    
    return False

def fix_lidl_price(product):
    """Fix Lidl prices that are 100x too high."""
    if product['store'] != 'Lidl':
        return product
    
    price = product.get('price', 0)
    if not price:
        return product
    
    # If price > €50 and it's a food item, it's probably 100x too high
    if price > 50 and is_food_item(product['name']):
        product['price'] = round(price / 100, 2)
        product['price_fixed'] = True
        
        # Fix old_price too if present
        if product.get('old_price'):
            product['old_price'] = round(product['old_price'] / 100, 2)
    
    return product

def validate_match(product):
    """Check if match is valid."""
    confidence = product.get('match_confidence')
    match_type = product.get('match_type')
    
    # No match is fine
    if not match_type:
        return True
    
    # Reject low confidence matches
    if confidence and confidence < MIN_CONFIDENCE:
        return False
    
    # Reject "embedding_low" type matches
    if match_type and 'low' in match_type.lower():
        return False
    
    return True

def validate_group(products_in_group):
    """Check if all products in a group are actually the same item."""
    if len(products_in_group) < 2:
        return False
    
    prices = [p['price'] for p in products_in_group if p.get('price')]
    if not prices:
        return False
    
    # Price ratio check - max should be < 3x min for same product
    min_price = min(prices)
    max_price = max(prices)
    
    if min_price > 0 and max_price / min_price > 3:
        return False
    
    return True

def main():
    print("Loading data...")
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    products = data['products']
    print(f"Input: {len(products)} products")
    
    # Step 1: Fix Lidl prices
    print("\n=== STEP 1: Fix Lidl prices ===")
    fixed_count = 0
    for p in products:
        old_price = p.get('price')
        p = fix_lidl_price(p)
        if p.get('price_fixed'):
            fixed_count += 1
    print(f"Fixed {fixed_count} Lidl prices")
    
    # Step 2: Validate matches and remove group_id for bad matches
    print("\n=== STEP 2: Validate matches ===")
    invalid_matches = 0
    for p in products:
        if not validate_match(p):
            p['group_id'] = None
            p['off_barcode'] = None
            p['match_type'] = None
            p['match_confidence'] = None
            invalid_matches += 1
    print(f"Invalidated {invalid_matches} low-confidence matches")
    
    # Step 3: Rebuild groups
    print("\n=== STEP 3: Rebuild groups ===")
    group_products = {}
    for p in products:
        gid = p.get('group_id')
        if gid:
            if gid not in group_products:
                group_products[gid] = []
            group_products[gid].append(p)
    
    # Validate each group
    valid_groups = {}
    invalid_group_count = 0
    for gid, prods in group_products.items():
        if validate_group(prods):
            valid_groups[gid] = {
                'off_barcode': prods[0].get('off_barcode'),
                'product_ids': [p['id'] for p in prods],
                'stores': list(set(p['store'] for p in prods)),
                'min_price': min(p['price'] for p in prods if p.get('price')),
                'max_price': max(p['price'] for p in prods if p.get('price'))
            }
        else:
            # Remove group_id from products in invalid groups
            invalid_group_count += 1
            for p in prods:
                p['group_id'] = None
    
    print(f"Valid groups: {len(valid_groups)}")
    print(f"Invalid groups removed: {invalid_group_count}")
    
    # Step 4: Filter unrealistic prices
    print("\n=== STEP 4: Filter unrealistic prices ===")
    filtered = []
    price_filtered = 0
    for p in products:
        price = p.get('price', 0)
        if price < MIN_PRICE:
            price_filtered += 1
            continue
        filtered.append(p)
    
    print(f"Filtered {price_filtered} products with unrealistic prices")
    products = filtered
    
    # Build output
    output = {
        'meta': {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'total_products': len(products),
            'cross_store_groups': len(valid_groups),
            'stores': ['Kaufland', 'Lidl', 'Billa'],
            'qa_cleaned': True
        },
        'products': products,
        'off': data.get('off', {}),
        'groups': valid_groups
    }
    
    # Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n=== RESULTS ===")
    print(f"Output: {len(products)} products")
    print(f"Groups: {len(valid_groups)}")
    print(f"Saved to: {OUTPUT_FILE}")
    
    # Verify no more suspicious groups
    print(f"\n=== VERIFICATION ===")
    suspicious = 0
    for gid, group in valid_groups.items():
        if group['min_price'] > 0:
            ratio = group['max_price'] / group['min_price']
            if ratio > 3:
                suspicious += 1
                print(f"WARNING: Group {gid} still has {ratio:.1f}x price variance")
    
    if suspicious == 0:
        print("✓ All groups pass price variance check")
    else:
        print(f"✗ {suspicious} groups still have issues")

if __name__ == '__main__':
    main()
