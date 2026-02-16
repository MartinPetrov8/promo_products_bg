#!/usr/bin/env python3
"""
Build cross-store product matches v3.0
- Quantity validation
- Strict product word matching (not just brand)
- Price ratio sanity check
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Tuple, Set

REPO = Path(__file__).parent.parent
INPUT_FILE = REPO / "docs" / "data" / "products.json"
OUTPUT_FILE = REPO / "docs" / "data" / "products_matched.json"

# Thresholds
MIN_SIMILARITY = 0.60
MIN_COMMON_WORDS = 2  # Require at least 2 common meaningful words
MAX_PRICE_RATIO = 2.5

# Stopwords - words that don't help identify the actual product
STOPWORDS = {
    # Generic
    'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'различни', 'видове', 
    'избрани', 'нашата', 'пекарна', 'витрина', 'свежата', 'промопакет',
    'lidl', 'kaufland', 'billa', 'k-classic', 'w5',
    # Units (handled separately)
    'г', 'гр', 'кг', 'мл', 'л', 'бр', 'см',
    # Descriptors that don't identify product
    'нов', 'нова', 'ново', 'специален', 'специална',
}

# Product type words - these MUST match for products to be considered same
PRODUCT_TYPES = {
    # Tools
    'бормашина', 'полираща', 'ъглошлайф', 'шлайф', 'циркуляр', 'зарядно',
    'ударна', 'прободен', 'трион', 'лобзик',
    # Food
    'мляко', 'сирене', 'кашкавал', 'масло', 'йогурт', 'кисело',
    'хляб', 'питка', 'земел', 'баничка', 'кроасан',
    'месо', 'пилешко', 'свинско', 'говеждо', 'кайма', 'филе',
    'риба', 'сьомга', 'скумрия', 'пъстърва',
    # Drinks
    'бира', 'вино', 'уиски', 'водка', 'ром', 'ликьор',
    'сок', 'вода', 'газирана', 'напитка',
    # Cleaning
    'препарат', 'почистващ', 'моп', 'кърпи', 'салфетки',
    # Personal care
    'шампоан', 'сапун', 'крем', 'дезодорант',
}


@dataclass
class QuantityInfo:
    value: float
    unit: str
    original: str
    
    def to_base(self) -> Tuple[float, str]:
        if self.unit == 'l':
            return self.value * 1000, 'ml'
        if self.unit == 'kg':
            return self.value * 1000, 'g'
        return self.value, self.unit
    
    def is_compatible(self, other: 'QuantityInfo', tolerance: float = 0.25) -> bool:
        b1, b2 = self.to_base(), other.to_base()
        if b1[1] != b2[1]:
            return False
        if b1[0] == 0 or b2[0] == 0:
            return False
        ratio = b1[0] / b2[0]
        return (1 - tolerance) <= ratio <= (1 + tolerance)


QUANTITY_PATTERNS = [
    (r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(?:мл|ml)', 'ml', True),
    (r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(?:гр?|g)', 'g', True),
    (r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)', 'ml', False),
    (r'(\d+(?:[.,]\d+)?)\s*(?:л|l|L)(?:\s|$|[^a-zA-Zа-яА-Я])', 'l', False),
    (r'(\d+(?:[.,]\d+)?)\s*(?:гр?|g)(?:\s|$|[^a-zA-Zа-яА-Я])', 'g', False),
    (r'(\d+(?:[.,]\d+)?)\s*(?:кг|kg)', 'kg', False),
]


def extract_quantity(name: str) -> Optional[QuantityInfo]:
    if not name:
        return None
    name_lower = name.lower()
    for pattern, unit, is_pack in QUANTITY_PATTERNS:
        match = re.search(pattern, name_lower)
        if match:
            groups = match.groups()
            if is_pack and len(groups) == 2:
                value = float(groups[0]) * float(groups[1].replace(',', '.'))
            else:
                value = float(groups[0].replace(',', '.'))
            return QuantityInfo(value=value, unit=unit, original=match.group(0))
    return None


def normalize_name(name):
    name = name.lower()
    name = re.sub(r'\|\s*lidl\s*$', '', name)
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def extract_tokens(name):
    """Extract meaningful tokens, keeping product type words"""
    name = normalize_name(name)
    words = name.split()
    return set(w for w in words if w not in STOPWORDS and len(w) >= 2)


def extract_product_types(tokens: Set[str]) -> Set[str]:
    """Extract product type words from tokens"""
    return tokens & PRODUCT_TYPES


def similarity(name1, name2):
    tokens1 = extract_tokens(name1)
    tokens2 = extract_tokens(name2)
    
    if not tokens1 or not tokens2:
        return 0, set()
    
    common = tokens1 & tokens2
    total = tokens1 | tokens2
    jaccard = len(common) / len(total) if total else 0
    
    seq = SequenceMatcher(None, normalize_name(name1), normalize_name(name2)).ratio()
    
    return jaccard * 0.6 + seq * 0.4, common


def products_compatible(p1, p2):
    """Check if products can be matched"""
    name1, name2 = p1['name'], p2['name']
    price1, price2 = p1.get('price', 0), p2.get('price', 0)
    
    # Get tokens and product types
    tokens1 = extract_tokens(name1)
    tokens2 = extract_tokens(name2)
    types1 = extract_product_types(tokens1)
    types2 = extract_product_types(tokens2)
    
    # If both have product types, they must have at least one in common
    if types1 and types2:
        if not (types1 & types2):
            return False, "Different product types"
    
    # Quantity check
    qty1 = extract_quantity(name1)
    qty2 = extract_quantity(name2)
    
    if qty1 and qty2:
        if not qty1.is_compatible(qty2):
            return False, f"Quantity mismatch ({qty1.original} vs {qty2.original})"
    
    # Price ratio check
    if price1 and price2 and min(price1, price2) > 0:
        ratio = max(price1, price2) / min(price1, price2)
        if ratio > MAX_PRICE_RATIO:
            # Allow higher ratio only if quantities match perfectly
            if not (qty1 and qty2 and qty1.is_compatible(qty2, tolerance=0.1)):
                return False, f"Price ratio {ratio:.1f}x"
    
    return True, "OK"


def find_matches(products):
    by_store = defaultdict(list)
    for p in products:
        by_store[p['store']].append(p)
    
    stores = list(by_store.keys())
    matches = []
    used = set()
    
    rejected = defaultdict(int)
    
    print(f"\nProducts by store:")
    for store, prods in by_store.items():
        print(f"  {store}: {len(prods)}")
    
    for i, store1 in enumerate(stores):
        for store2 in stores[i+1:]:
            print(f"\nMatching {store1} vs {store2}...")
            
            prods1 = [p for p in by_store[store1] if p['id'] not in used]
            prods2 = [p for p in by_store[store2] if p['id'] not in used]
            
            match_count = 0
            for p1 in prods1:
                if p1['id'] in used:
                    continue
                
                best_match = None
                best_sim = 0
                
                for p2 in prods2:
                    if p2['id'] in used:
                        continue
                    
                    # Check compatibility first
                    compatible, reason = products_compatible(p1, p2)
                    if not compatible:
                        rejected[reason] += 1
                        continue
                    
                    sim, common = similarity(p1['name'], p2['name'])
                    
                    # Require minimum common words
                    if len(common) < MIN_COMMON_WORDS:
                        continue
                    
                    if sim < MIN_SIMILARITY:
                        continue
                    
                    if sim > best_sim:
                        best_sim = sim
                        best_match = p2
                
                if best_match:
                    matches.append({
                        'products': [p1, best_match],
                        'similarity': best_sim,
                    })
                    used.add(p1['id'])
                    used.add(best_match['id'])
                    match_count += 1
            
            print(f"  Found {match_count} matches")
    
    print(f"\n⚠️  Rejections by reason:")
    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count}")
    
    return matches


def main():
    print("=" * 60)
    print("CROSS-STORE MATCHER v3.0 (strict product type matching)")
    print("=" * 60)
    
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    products = data['products']
    print(f"\nTotal products: {len(products)}")
    
    # Filter prices
    products = [p for p in products if p.get('price', 0) >= 0.05]
    print(f"After price filter: {len(products)}")
    
    # Clear group_ids
    for p in products:
        p['group_id'] = None
    
    matches = find_matches(products)
    print(f"\nTotal matches found: {len(matches)}")
    
    # Build groups
    groups = {}
    for i, match in enumerate(matches):
        gid = f"g_{hashlib.md5(str(i).encode()).hexdigest()[:8]}"
        
        for p in match['products']:
            for prod in products:
                if prod['id'] == p['id']:
                    prod['group_id'] = gid
        
        prices = [p['price'] for p in match['products'] if p.get('price')]
        groups[gid] = {
            'product_ids': [p['id'] for p in match['products']],
            'stores': list(set(p['store'] for p in match['products'])),
            'min_price': min(prices) if prices else None,
            'max_price': max(prices) if prices else None,
        }
    
    output = {
        'meta': {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'total_products': len(products),
            'cross_store_groups': len(groups),
            'stores': list(set(p['store'] for p in products)),
            'matcher_version': '3.0.0'
        },
        'products': products,
        'groups': groups
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {len(products)} products, {len(groups)} groups")
    print(f"{'=' * 60}")
    
    # Show sample matches
    print("\nSAMPLE MATCHES:")
    for gid in list(groups.keys())[:10]:
        group = groups[gid]
        print(f"\n{gid}:")
        for pid in group['product_ids']:
            p = next((x for x in products if x['id'] == pid), None)
            if p:
                print(f"  {p['store']}: {p['name'][:50]} | €{p['price']}")


if __name__ == '__main__':
    main()
