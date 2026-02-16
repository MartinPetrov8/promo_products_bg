#!/usr/bin/env python3
"""
Cross-Store Product Matcher v5

Key improvements:
- STRICT brand matching (both must have same brand, or both no brand)
- Better product type differentiation (fresh milk ≠ yogurt)
- Quantity-aware matching
"""
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).parent.parent
INPUT_FILE = REPO / "standardized_final.json"
OUTPUT_FILE = REPO / "cross_store_matches_final.json"

# Thresholds
MIN_SIMILARITY = 0.55
MAX_PRICE_RATIO = 2.5

# Stopwords
STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'до', 'кг', 'г', 'л', 'мл', 
             'бр', 'различни', 'видове', 'избрани', 'vol', 'ml', 'kg', 'l', 'g', 'pcs',
             'промо', 'класик', 'нов', 'клас', 'до', 'покупка', 'при', 'само'}

# Product type keywords that should NOT match together
INCOMPATIBLE_TYPES = [
    ({'прясно мляко', 'прясно'}, {'кисело мляко', 'кисело', 'йогурт'}),  # Fresh milk ≠ yogurt
    ({'топено сирене', 'топено'}, {'крема сирене', 'крема'}),  # Melted cheese ≠ cream cheese
    ({'шоколад'}, {'бисквити'}),  # Chocolate ≠ biscuits
    ({'локум'}, {'халва'}),  # Lokum ≠ halva
]

def normalize_name(name):
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r'\d+[.,]?\d*\s*(кг|г|л|мл|бр|ml|kg|l|g|pcs|%|vol)\b', '', name)
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    words = [w for w in name.split() if w not in STOPWORDS and len(w) >= 2]
    return ' '.join(words)

def get_keywords(name):
    """Get significant keywords."""
    return set(normalize_name(name).split())

def types_compatible(name1, name2):
    """Check if product types are compatible."""
    n1 = name1.lower()
    n2 = name2.lower()
    
    for type1_keywords, type2_keywords in INCOMPATIBLE_TYPES:
        has_type1_in_n1 = any(kw in n1 for kw in type1_keywords)
        has_type2_in_n1 = any(kw in n1 for kw in type2_keywords)
        has_type1_in_n2 = any(kw in n2 for kw in type1_keywords)
        has_type2_in_n2 = any(kw in n2 for kw in type2_keywords)
        
        # One is type1, other is type2 = incompatible
        if (has_type1_in_n1 and has_type2_in_n2) or (has_type2_in_n1 and has_type1_in_n2):
            return False
    
    return True

def name_similarity(name1, name2):
    """Calculate similarity."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    if not norm1 or not norm2:
        return 0.0, 0
    
    kw1 = set(norm1.split())
    kw2 = set(norm2.split())
    
    common = kw1 & kw2
    union = kw1 | kw2
    
    if not union:
        return 0.0, 0
    
    jaccard = len(common) / len(union)
    seq = SequenceMatcher(None, norm1, norm2).ratio()
    
    return jaccard * 0.5 + seq * 0.5, len(common)

def brands_match_strict(brand1, brand2):
    """STRICT brand matching."""
    b1 = (brand1 or '').lower().strip()
    b2 = (brand2 or '').lower().strip()
    
    # If both have no brand, compatible (generic products)
    if not b1 and not b2:
        return True
    
    # If one has brand and other doesn't, NOT compatible
    if (b1 and not b2) or (b2 and not b1):
        return False
    
    # Both have brands - must match
    if b1 == b2:
        return True
    if b1 in b2 or b2 in b1:
        return True
    
    return False

def find_matches(products):
    """Find matches with strict criteria."""
    by_store_cat = defaultdict(list)
    for p in products:
        by_store_cat[(p['store'], p['category'])].append(p)
    
    stores = ['Kaufland', 'Lidl', 'Billa']
    categories = list(set(p['category'] for p in products))
    
    matches = []
    used_ids = set()
    
    for category in categories:
        if category == 'other':
            continue
        
        store_prods = {s: by_store_cat.get((s, category), []) for s in stores}
        
        for i, s1 in enumerate(stores):
            for s2 in stores[i+1:]:
                prods1 = [p for p in store_prods[s1] if p['id'] not in used_ids]
                prods2 = [p for p in store_prods[s2] if p['id'] not in used_ids]
                
                if not prods1 or not prods2:
                    continue
                
                for p1 in prods1:
                    if p1['id'] in used_ids:
                        continue
                    
                    best_match = None
                    best_score = 0
                    best_common = 0
                    
                    for p2 in prods2:
                        if p2['id'] in used_ids:
                            continue
                        
                        # STRICT brand matching
                        if not brands_match_strict(p1.get('brand'), p2.get('brand')):
                            continue
                        
                        # Product type compatibility
                        if not types_compatible(p1['clean_name'], p2['clean_name']):
                            continue
                        
                        # Price ratio
                        price1, price2 = p1.get('price', 0), p2.get('price', 0)
                        if price1 > 0 and price2 > 0:
                            ratio = max(price1, price2) / min(price1, price2)
                            if ratio > MAX_PRICE_RATIO:
                                continue
                        
                        # Name similarity
                        sim, common = name_similarity(p1['clean_name'], p2['clean_name'])
                        
                        if common < 1:  # Must share at least 1 word
                            continue
                        
                        if sim >= MIN_SIMILARITY and sim > best_score:
                            best_score = sim
                            best_match = p2
                            best_common = common
                    
                    if best_match:
                        # Bidirectional check
                        reverse_best = None
                        reverse_score = 0
                        
                        for p2 in prods1:
                            if p2['id'] in used_ids or p2['id'] == p1['id']:
                                continue
                            if not brands_match_strict(best_match.get('brand'), p2.get('brand')):
                                continue
                            if not types_compatible(best_match['clean_name'], p2['clean_name']):
                                continue
                            
                            sim, _ = name_similarity(best_match['clean_name'], p2['clean_name'])
                            if sim > reverse_score:
                                reverse_score = sim
                                reverse_best = p2
                        
                        # p1 should be the best match for best_match
                        sim_p1, _ = name_similarity(best_match['clean_name'], p1['clean_name'])
                        if reverse_best and reverse_score > sim_p1:
                            continue  # Not mutual best match
                        
                        matches.append({
                            'products': [p1, best_match],
                            'category': category,
                            'similarity': round(best_score, 3),
                            'common_words': best_common,
                            'brand': p1.get('brand') or best_match.get('brand'),
                            'stores': sorted([s1, s2])
                        })
                        used_ids.add(p1['id'])
                        used_ids.add(best_match['id'])
    
    return matches

def main():
    print("Loading data...")
    with open(INPUT_FILE) as f:
        products = json.load(f)
    
    print(f"Products: {len(products)}")
    
    print("\nFinding matches with strict criteria...")
    matches = find_matches(products)
    
    # Stats
    by_cat = defaultdict(int)
    by_stores = defaultdict(int)
    for m in matches:
        by_cat[m['category']] += 1
        by_stores[tuple(m['stores'])] += 1
    
    print(f"\n=== RESULTS ===")
    print(f"Total validated matches: {len(matches)}")
    
    print(f"\nBy category:")
    for cat, cnt in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")
    
    print(f"\nBy store pair:")
    for stores, cnt in sorted(by_stores.items(), key=lambda x: -x[1]):
        print(f"  {stores[0]} ↔ {stores[1]}: {cnt}")
    
    print(f"\n=== ALL MATCHES ===")
    for m in matches:
        p1, p2 = m['products']
        price_diff = abs(p1['price'] - p2['price'])
        savings = f"Save €{price_diff:.2f}" if price_diff > 0.05 else "Same price"
        print(f"\n[{m['category']}] {m['brand'] or 'Generic'} ({savings})")
        print(f"  {p1['store']:10} €{p1['price']:6.2f} | {p1['clean_name'][:45]}")
        print(f"  {p2['store']:10} €{p2['price']:6.2f} | {p2['clean_name'][:45]}")
    
    # Save
    output = {
        'meta': {
            'total_matches': len(matches),
            'by_category': dict(by_cat),
            'by_store_pair': {f"{k[0]}-{k[1]}": v for k, v in by_stores.items()}
        },
        'matches': matches
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
