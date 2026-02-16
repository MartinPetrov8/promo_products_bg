#!/usr/bin/env python3
"""
QA Cleanup v2 - More aggressive filtering.
"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).parent.parent
INPUT_FILE = REPO / "docs" / "data" / "products.json"  # Use original
OUTPUT_FILE = REPO / "docs" / "data" / "products_clean.json"

# Thresholds
MIN_CONFIDENCE = 0.90  # Higher threshold
MIN_PRICE = 0.05
MAX_PRICE_RATIO = 2.5  # Products in same group shouldn't differ more than 2.5x

# Stopwords for name comparison
STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'различни', 'видове', 
             'избрани', 'нашата', 'пекарна', 'витрина', 'свежата', 'промопакет',
             'ml', 'г', 'л', 'кг', 'мл', 'бр'}

# Food keywords for Lidl fix
FOOD_KEYWORDS = [
    'хляб', 'донат', 'мъфин', 'кифла', 'баничка', 'кроасан', 'земел', 
    'брецел', 'бейгъл', 'брускета', 'енсаимада', 'пура', 'кит кат',
    'орео', 'milka', 'лаваш', 'питка', 'франзела', 'козунак', 'руло',
    'торта', 'кекс', 'бисквита', 'вафла', 'шоколад', 'бонбон',
    'джинджифил', 'сладкиш', 'десерт', 'футболен'
]

NONFOOD_KEYWORDS = [
    'бормашина', 'прахосмукачка', 'фурна', 'фрайър', 'миксер', 'блендер',
    'уред', 'машина', 'станция', 'инструмент', 'акумулаторн', 'електрическ'
]

def is_food_item(name):
    name_lower = name.lower()
    for kw in NONFOOD_KEYWORDS:
        if kw in name_lower:
            return False
    for kw in FOOD_KEYWORDS:
        if kw in name_lower:
            return True
    return False

def fix_lidl_price(product):
    if product['store'] != 'Lidl':
        return product
    
    price = product.get('price', 0)
    if price and price > 50 and is_food_item(product['name']):
        product['price'] = round(price / 100, 2)
        if product.get('old_price'):
            product['old_price'] = round(product['old_price'] / 100, 2)
    return product

def extract_keywords(name):
    """Extract meaningful keywords from product name."""
    name = name.lower()
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    words = name.split()
    # Filter stopwords and short words
    return set(w for w in words if w not in STOPWORDS and len(w) >= 3)

def extract_brand(name):
    """Extract likely brand from product name (usually first 1-2 words)."""
    name = name.lower()
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    words = name.split()[:2]
    # Filter stopwords
    brand_words = [w for w in words if w not in STOPWORDS and len(w) >= 2]
    return ' '.join(brand_words) if brand_words else ''

def products_match(p1, p2):
    """Check if two products are actually the same item."""
    name1 = p1['name']
    name2 = p2['name']
    
    kw1 = extract_keywords(name1)
    kw2 = extract_keywords(name2)
    
    if not kw1 or not kw2:
        return False
    
    # Calculate Jaccard similarity
    common = len(kw1 & kw2)
    total = len(kw1 | kw2)
    jaccard = common / total if total > 0 else 0
    
    # Also check brand similarity
    brand1 = extract_brand(name1)
    brand2 = extract_brand(name2)
    
    # If brands are present and different, likely not same product
    if brand1 and brand2 and brand1 != brand2:
        # Check if one contains the other
        if brand1 not in brand2 and brand2 not in brand1:
            return False
    
    # Require decent keyword overlap
    return jaccard >= 0.3 and common >= 1

def validate_group(products_in_group):
    """Validate all products in group are actually the same item."""
    if len(products_in_group) < 2:
        return False
    
    # Price check
    prices = [p['price'] for p in products_in_group if p.get('price')]
    if not prices:
        return False
    
    min_price = min(prices)
    max_price = max(prices)
    
    if min_price > 0 and max_price / min_price > MAX_PRICE_RATIO:
        return False
    
    # Check all pairs match
    for i, p1 in enumerate(products_in_group):
        for p2 in products_in_group[i+1:]:
            if not products_match(p1, p2):
                return False
    
    return True

def main():
    print("Loading original data...")
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    products = data['products']
    print(f"Input: {len(products)} products")
    
    # Step 1: Fix Lidl prices
    print("\n=== Fix Lidl prices ===")
    fixed = 0
    for p in products:
        old = p.get('price')
        fix_lidl_price(p)
        if p.get('price') != old:
            fixed += 1
    print(f"Fixed {fixed} prices")
    
    # Step 2: Remove low confidence matches
    print("\n=== Filter low confidence ===")
    removed = 0
    for p in products:
        conf = p.get('match_confidence', 0)
        if conf and conf < MIN_CONFIDENCE:
            p['group_id'] = None
            p['off_barcode'] = None
            p['match_type'] = None
            p['match_confidence'] = None
            removed += 1
    print(f"Removed {removed} low-confidence matches")
    
    # Step 3: Rebuild and validate groups
    print("\n=== Validate groups ===")
    group_products = {}
    for p in products:
        gid = p.get('group_id')
        if gid:
            if gid not in group_products:
                group_products[gid] = []
            group_products[gid].append(p)
    
    valid_groups = {}
    invalid = 0
    for gid, prods in group_products.items():
        if validate_group(prods):
            # Additional check: require 2+ different stores for cross-store comparison
            stores = set(p['store'] for p in prods)
            if len(stores) >= 2:
                valid_groups[gid] = {
                    'off_barcode': prods[0].get('off_barcode'),
                    'product_ids': [p['id'] for p in prods],
                    'stores': sorted(stores),
                    'min_price': min(p['price'] for p in prods if p.get('price')),
                    'max_price': max(p['price'] for p in prods if p.get('price'))
                }
            else:
                # Single store group - remove group_id
                for p in prods:
                    p['group_id'] = None
                invalid += 1
        else:
            for p in prods:
                p['group_id'] = None
            invalid += 1
    
    print(f"Valid cross-store groups: {len(valid_groups)}")
    print(f"Invalid/single-store groups removed: {invalid}")
    
    # Step 4: Filter bad prices
    print("\n=== Filter bad prices ===")
    filtered = [p for p in products if p.get('price', 0) >= MIN_PRICE]
    removed = len(products) - len(filtered)
    print(f"Filtered {removed} products")
    products = filtered
    
    # Build output
    output = {
        'meta': {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'total_products': len(products),
            'cross_store_groups': len(valid_groups),
            'stores': ['Kaufland', 'Lidl', 'Billa'],
            'qa_version': 2
        },
        'products': products,
        'off': data.get('off', {}),
        'groups': valid_groups
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n=== RESULTS ===")
    print(f"Products: {len(products)}")
    print(f"Cross-store groups: {len(valid_groups)}")
    print(f"Saved to: {OUTPUT_FILE}")
    
    # Show remaining groups
    print(f"\n=== REMAINING GROUPS ===")
    for gid, group in valid_groups.items():
        prods = [p for p in products if p.get('group_id') == gid]
        print(f"\n{gid}:")
        for p in prods:
            print(f"  {p['store']}: {p['name'][:45]} | €{p['price']}")

if __name__ == '__main__':
    main()
