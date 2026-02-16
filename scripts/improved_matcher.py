#!/usr/bin/env python3
"""Improved cross-store matcher with token similarity"""

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime

INPUT_FILE = 'standardized_final.json'
OUTPUT_FILE = 'cross_store_matches_final.json'
DB_PATH = 'data/promobg.db'

def tokenize(name):
    """Extract significant tokens from product name"""
    name = name.lower()
    name = re.sub(r'[®™©\n]', ' ', name)
    name = re.sub(r'\d+\s*(г|гр|мл|л|кг|бр|x|х)\b', '', name)
    name = re.sub(r'различни видове', '', name)
    name = re.sub(r'от свежата витрина', '', name)
    name = re.sub(r'от деликатесната витрина', '', name)
    name = re.sub(r'за 1 кг', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    tokens = set(name.split())
    stopwords = {'или', 'от', 'за', 'в', 'с', 'на', 'и', 'по', 'до', 'the', 'a', 'an', '-', '–'}
    tokens = {t for t in tokens if len(t) > 1} - stopwords
    return tokens

def match_score(tokens1, tokens2):
    if not tokens1 or not tokens2:
        return 0
    common = tokens1 & tokens2
    if len(common) < 2:
        return 0
    return len(common) / len(tokens1 | tokens2)

def find_matches(products, min_score=0.4):
    # Build index by category
    by_category = defaultdict(lambda: defaultdict(list))
    for p in products:
        cat = p.get('category', 'other')
        store = p['store']
        p['tokens'] = tokenize(p['clean_name'])
        by_category[cat][store].append(p)
    
    matches = []
    for cat, by_store in by_category.items():
        stores = list(by_store.keys())
        
        for i, store1 in enumerate(stores):
            for store2 in stores[i+1:]:
                for p1 in by_store[store1]:
                    for p2 in by_store[store2]:
                        score = match_score(p1['tokens'], p2['tokens'])
                        if score >= min_score:
                            matches.append({
                                'score': score,
                                'category': cat,
                                'products': [p1, p2],
                                'common_words': ' '.join(p1['tokens'] & p2['tokens']),
                                'brand': p1.get('brand') or p2.get('brand')
                            })
    
    # Deduplicate
    seen = set()
    unique = []
    for m in sorted(matches, key=lambda x: -x['score']):
        key = tuple(sorted([m['products'][0]['id'], m['products'][1]['id']]))
        if key not in seen:
            seen.add(key)
            unique.append(m)
    
    return unique

def save_to_db(matches):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('DELETE FROM cross_store_matches')
    
    for m in matches:
        p1, p2 = m['products']
        kaufland_id = lidl_id = billa_id = None
        
        for p in m['products']:
            if p['store'] == 'Kaufland':
                kaufland_id = p['id']
            elif p['store'] == 'Lidl':
                lidl_id = p['id']
            elif p['store'] == 'Billa':
                billa_id = p['id']
        
        cur.execute('''
            INSERT INTO cross_store_matches (
                kaufland_product_id, lidl_product_id, billa_product_id,
                canonical_name, canonical_brand,
                match_type, confidence, store_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (kaufland_id, lidl_id, billa_id, m['common_words'], m.get('brand'),
              'token_similarity', round(m['score'], 2), 2))
    
    conn.commit()
    print(f"Saved {len(matches)} matches to database")
    conn.close()

def main():
    with open(INPUT_FILE) as f:
        products = json.load(f)
    
    print(f"Products: {len(products)}")
    matches = find_matches(products, min_score=0.4)
    print(f"Matches found: {len(matches)}")
    
    # Stats
    by_pair = defaultdict(int)
    total_savings = 0
    for m in matches:
        p1, p2 = m['products']
        pair = tuple(sorted([p1['store'], p2['store']]))
        by_pair[pair] += 1
        total_savings += abs(p1['price'] - p2['price'])
    
    print(f"\nBy store pair:")
    for pair, count in by_pair.items():
        print(f"  {pair[0]}-{pair[1]}: {count}")
    print(f"\n💰 Total savings potential: €{total_savings:.2f}")
    
    # Save to JSON
    output = {
        'meta': {
            'total_matches': len(matches),
            'by_category': dict(defaultdict(int)),
            'updated_at': datetime.now().isoformat()
        },
        'matches': matches
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved to {OUTPUT_FILE}")
    
    # Save to DB
    save_to_db(matches)

if __name__ == '__main__':
    main()
