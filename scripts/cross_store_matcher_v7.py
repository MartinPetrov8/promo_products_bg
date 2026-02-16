#!/usr/bin/env python3
"""
Cross-Store Product Matcher v7

Fixed: More incompatible types, stricter meat/fish matching
"""
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).parent.parent
INPUT_FILE = REPO / "standardized_final.json"
OUTPUT_FILE = REPO / "cross_store_matches_final.json"

GENERIC_CATEGORIES = {'produce', 'bakery'}  # Removed meat - too error prone
BRANDED_CATEGORIES = {'snacks', 'beverages', 'alcohol', 'dairy', 'coffee', 'personal_care', 'household', 'meat', 'fish', 'frozen'}

MIN_SIMILARITY_BRANDED = 0.55
MIN_SIMILARITY_GENERIC = 0.50
MAX_PRICE_RATIO = 2.5

STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'до', 'кг', 'г', 'л', 'мл', 
             'бр', 'различни', 'видове', 'избрани', 'vol', 'ml', 'kg', 'l', 'g', 'pcs',
             'промо', 'класик', 'нов', 'клас', 'до', 'покупка', 'при', 'само', 'около',
             'деликатесната', 'витрина', 'клиент', 'охладена', 'охладено', 'прясна', 'пресен'}

# Extended incompatible types
INCOMPATIBLE_TYPES = [
    # Dairy
    ({'прясно мляко', 'прясно'}, {'кисело мляко', 'кисело', 'йогурт'}),
    ({'топено сирене', 'топено'}, {'крема сирене', 'крема'}),
    # Meat types - CRITICAL
    ({'пилешко', 'пилешки', 'пиле'}, {'свинско', 'свински', 'свиня'}),
    ({'пилешко', 'пилешки', 'пиле'}, {'телешко', 'телешки', 'теле', 'говеждо', 'говежди'}),
    ({'пилешко', 'пилешки', 'пиле'}, {'пуешко', 'пуешки', 'пуйка', 'патица', 'патешко'}),
    ({'свинско', 'свински'}, {'телешко', 'телешки', 'говеждо', 'говежди'}),
    ({'свинско', 'свински'}, {'пуешко', 'пуешки', 'пуйка', 'патица'}),
    ({'телешко', 'телешки', 'говеждо'}, {'пуешко', 'пуешки', 'пуйка', 'патица'}),
    # Meat products
    ({'шунка'}, {'кренвирш', 'колбас', 'шпек', 'салам'}),
    ({'шницел'}, {'кайма', 'кюфте'}),
    ({'колбас'}, {'салам', 'шпек'}),
    ({'кренвирш'}, {'салам', 'шпек'}),
    # Wine
    ({'червено вино', 'червено'}, {'бяло вино', 'бяло', 'розе'}),
    # Frozen
    ({'пица'}, {'риба', 'цаца', 'сьомга', 'скумрия'}),
    ({'сладолед'}, {'пица', 'риба'}),
    # Produce
    ({'кокос'}, {'авокадо'}),  # "Кокос или авокадо" shouldn't match plain "Авокадо"
]

def normalize_name(name):
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r'\d+[.,]?\d*\s*(кг|г|л|мл|бр|ml|kg|l|g|pcs|%|vol)\b', '', name)
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    words = [w for w in name.split() if w not in STOPWORDS and len(w) >= 2]
    return ' '.join(words)

def types_compatible(name1, name2):
    n1, n2 = name1.lower(), name2.lower()
    for type1_kw, type2_kw in INCOMPATIBLE_TYPES:
        has1_in_n1 = any(kw in n1 for kw in type1_kw)
        has2_in_n1 = any(kw in n1 for kw in type2_kw)
        has1_in_n2 = any(kw in n2 for kw in type1_kw)
        has2_in_n2 = any(kw in n2 for kw in type2_kw)
        if (has1_in_n1 and has2_in_n2) or (has2_in_n1 and has1_in_n2):
            return False
    return True

def name_similarity(name1, name2):
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    if not norm1 or not norm2:
        return 0.0, 0
    kw1, kw2 = set(norm1.split()), set(norm2.split())
    common = kw1 & kw2
    union = kw1 | kw2
    if not union:
        return 0.0, 0
    jaccard = len(common) / len(union)
    seq = SequenceMatcher(None, norm1, norm2).ratio()
    return jaccard * 0.5 + seq * 0.5, len(common)

def brands_match_strict(brand1, brand2):
    """Strict brand matching."""
    b1 = (brand1 or '').lower().strip()
    b2 = (brand2 or '').lower().strip()
    
    if not b1 and not b2:
        return True
    if not b1 or not b2:
        return False
    if b1 == b2 or b1 in b2 or b2 in b1:
        return True
    return False

def brands_match_relaxed(brand1, brand2):
    """Relaxed - allows one missing."""
    b1 = (brand1 or '').lower().strip()
    b2 = (brand2 or '').lower().strip()
    
    if not b1 or not b2:
        return True
    if b1 == b2 or b1 in b2 or b2 in b1:
        return True
    return False

def find_matches(products):
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
        
        is_generic = category in GENERIC_CATEGORIES
        min_sim = MIN_SIMILARITY_GENERIC if is_generic else MIN_SIMILARITY_BRANDED
        brand_check = brands_match_relaxed if is_generic else brands_match_strict
        
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
                        
                        if not brand_check(p1.get('brand'), p2.get('brand')):
                            continue
                        
                        if not types_compatible(p1['clean_name'], p2['clean_name']):
                            continue
                        
                        price1, price2 = p1.get('price', 0), p2.get('price', 0)
                        if price1 > 0 and price2 > 0:
                            ratio = max(price1, price2) / min(price1, price2)
                            if ratio > MAX_PRICE_RATIO:
                                continue
                        
                        sim, common = name_similarity(p1['clean_name'], p2['clean_name'])
                        
                        if common < 1:
                            continue
                        
                        if sim >= min_sim and sim > best_score:
                            best_score = sim
                            best_match = p2
                            best_common = common
                    
                    if best_match:
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
    with open(INPUT_FILE) as f:
        products = json.load(f)
    
    print(f"Products: {len(products)}")
    print("Finding matches (v7)...")
    
    matches = find_matches(products)
    
    by_cat = defaultdict(int)
    by_stores = defaultdict(int)
    for m in matches:
        by_cat[m['category']] += 1
        by_stores[tuple(m['stores'])] += 1
    
    print(f"\n=== RESULTS: {len(matches)} matches ===")
    print(f"By category: {dict(sorted(by_cat.items(), key=lambda x: -x[1]))}")
    print(f"By store pair: {dict((f'{k[0]}-{k[1]}', v) for k, v in by_stores.items())}")
    
    # Show matches
    total_savings = 0
    print(f"\n=== MATCHES ===")
    for m in matches:
        p1, p2 = m['products']
        savings = abs(p1['price'] - p2['price'])
        total_savings += savings
        cheaper = p1['store'] if p1['price'] < p2['price'] else p2['store']
        print(f"[{m['category']}] {m.get('brand') or 'Generic'} - €{savings:.2f} ({cheaper} cheaper)")
        print(f"  {p1['store']:8} €{p1['price']:5.2f} {p1['clean_name'][:42]}")
        print(f"  {p2['store']:8} €{p2['price']:5.2f} {p2['clean_name'][:42]}")
    
    print(f"\n💰 Total savings potential: €{total_savings:.2f}")
    
    # Save
    output = {'meta': {'total_matches': len(matches), 'by_category': dict(by_cat)}, 'matches': matches}
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved")

if __name__ == '__main__':
    main()
