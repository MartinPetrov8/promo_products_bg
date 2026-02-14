#!/usr/bin/env python3
"""
Phase 1: Transliteration-based matching
Matches unmatched Bulgarian products using Cyrillic→Latin transliteration
"""
import sqlite3
import json
import re
from pathlib import Path
from transliterate import translit
from collections import defaultdict
from difflib import SequenceMatcher

BASE_DIR = Path(__file__).parent.parent / "data"

# Bulgarian food terms → English
FOOD_TERM_MAP = {
    # Wine varieties
    'пино гриджо': 'pinot grigio',
    'пино гри': 'pinot grigio',
    'шардоне': 'chardonnay',
    'каберне': 'cabernet',
    'совиньон': 'sauvignon',
    'мерло': 'merlot',
    'темпранийо': 'tempranillo',
    'рислинг': 'riesling',
    'мускат': 'muscat',
    'мавруд': 'mavrud',
    'розе': 'rose',
    # Fruits
    'помело': 'pomelo',
    'манго': 'mango',
    'авокадо': 'avocado',
    'киви': 'kiwi',
    'банан': 'banana',
    'портокал': 'orange',
    'лимон': 'lemon',
    'грейпфрут': 'grapefruit',
    # Dairy
    'моцарела': 'mozzarella',
    'пармезан': 'parmesan',
    'бри': 'brie',
    'камамбер': 'camembert',
    'рикота': 'ricotta',
    'маскарпоне': 'mascarpone',
    'горгонзола': 'gorgonzola',
    'кашкавал': 'kashkaval cheese',
    'сирене': 'cheese',
    'мляко': 'milk',
    'кисело мляко': 'yogurt',
    # Meat
    'пилешко': 'chicken',
    'свинско': 'pork',
    'телешко': 'beef',
    'агнешко': 'lamb',
    'шунка': 'ham',
    'салам': 'salami',
    'кренвирш': 'frankfurter',
    'бекон': 'bacon',
    # Alcohol
    'уиски': 'whisky',
    'водка': 'vodka',
    'джин': 'gin',
    'ром': 'rum',
    'текила': 'tequila',
    'бира': 'beer',
    'вино': 'wine',
    # Other
    'паста': 'pasta',
    'спагети': 'spaghetti',
    'пица': 'pizza',
    'хляб': 'bread',
    'масло': 'butter',
    'яйца': 'eggs',
}

def transliterate_bg(text):
    """Transliterate Bulgarian to Latin"""
    try:
        return translit(text, 'bg', reversed=True)
    except:
        return text

def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\sа-яА-Яa-zA-Z0-9]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def apply_food_terms(text):
    """Replace Bulgarian food terms with English equivalents"""
    text_lower = text.lower()
    for bg, en in FOOD_TERM_MAP.items():
        if bg in text_lower:
            text_lower = text_lower.replace(bg, en)
    return text_lower

def tokenize(text):
    return [t for t in normalize(text).split() if len(t) > 1]

def main():
    print("=" * 60)
    print("PHASE 1: TRANSLITERATION MATCHING")
    print("=" * 60)
    
    prom_conn = sqlite3.connect(BASE_DIR / "promobg.db")
    off_conn = sqlite3.connect(BASE_DIR / "off_bulgaria.db")
    
    # Load unmatched products
    cur = prom_conn.cursor()
    cur.execute('''
        SELECT p.id, p.name, p.brand
        FROM products p
        WHERE p.id NOT IN (SELECT product_id FROM product_off_matches)
    ''')
    unmatched = [{'id': r[0], 'name': r[1], 'brand': r[2]} for r in cur.fetchall()]
    print(f"Unmatched products: {len(unmatched)}")
    
    # Load OFF products
    off_cur = off_conn.cursor()
    off_cur.execute('SELECT id, barcode, product_name, product_name_bg, brands FROM off_products')
    off_products = {}
    off_name_index = defaultdict(list)  # normalized name -> [off_ids]
    
    for row in off_cur.fetchall():
        off_id = row[0]
        off_products[off_id] = {
            'id': off_id, 'barcode': row[1], 
            'name': row[2] or '', 'name_bg': row[3], 'brands': row[4]
        }
        # Index by normalized name tokens
        for name in [row[2], row[3]]:
            if name:
                for token in tokenize(name):
                    if len(token) > 2:
                        off_name_index[token].append(off_id)
    
    print(f"OFF products: {len(off_products)}")
    print(f"Name index tokens: {len(off_name_index)}")
    
    # Match using transliteration
    matches = []
    
    for i, prod in enumerate(unmatched):
        if (i + 1) % 100 == 0:
            print(f"Processing {i+1}/{len(unmatched)}...")
        
        name = prod['name']
        
        # Create variants
        variants = [
            normalize(name),
            normalize(transliterate_bg(name)),
            normalize(apply_food_terms(name)),
            normalize(transliterate_bg(apply_food_terms(name))),
        ]
        
        # Find candidates
        candidates = set()
        for variant in variants:
            tokens = tokenize(variant)
            for token in tokens:
                if token in off_name_index:
                    candidates.update(off_name_index[token][:50])
        
        if not candidates:
            continue
        
        # Score candidates
        best_match = None
        best_score = 0
        
        for off_id in candidates:
            off_prod = off_products[off_id]
            
            # Compare against OFF names
            for off_name in [off_prod['name'], off_prod['name_bg']]:
                if not off_name:
                    continue
                
                off_norm = normalize(off_name)
                
                for variant in variants:
                    ratio = SequenceMatcher(None, variant, off_norm).ratio()
                    
                    # Token overlap bonus
                    v_tokens = set(tokenize(variant))
                    o_tokens = set(tokenize(off_norm))
                    if v_tokens and o_tokens:
                        overlap = len(v_tokens & o_tokens) / len(v_tokens | o_tokens)
                        ratio = ratio * 0.6 + overlap * 0.4
                    
                    if ratio > best_score:
                        best_score = ratio
                        best_match = {
                            'product_id': prod['id'],
                            'off_id': off_id,
                            'confidence': ratio,
                            'variant_used': variant,
                            'off_name': off_name
                        }
        
        if best_match and best_match['confidence'] >= 0.45:
            matches.append(best_match)
    
    # Results
    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"New matches found: {len(matches)}")
    
    confident = [m for m in matches if m['confidence'] >= 0.85]
    likely = [m for m in matches if 0.75 <= m['confidence'] < 0.85]
    low = [m for m in matches if m['confidence'] < 0.75]
    
    print(f"  Confident (≥0.85): {len(confident)}")
    print(f"  Likely (0.75-0.84): {len(likely)}")
    print(f"  Low (<0.75): {len(low)}")
    
    # Sample matches
    print("\nSample matches:")
    for m in sorted(matches, key=lambda x: -x['confidence'])[:10]:
        cur.execute('SELECT name FROM products WHERE id = ?', (m['product_id'],))
        prod_name = cur.fetchone()[0]
        print(f"  [{m['confidence']:.2f}] '{prod_name[:30]}' → '{m['off_name'][:30]}'")
    
    # Save matches
    print("\nSaving matches...")
    for m in matches:
        match_type = 'translit_confident' if m['confidence'] >= 0.85 else \
                     'translit_likely' if m['confidence'] >= 0.75 else 'translit_low'
        try:
            cur.execute('''
                INSERT INTO product_off_matches 
                (product_id, off_product_id, match_type, match_confidence, is_verified, created_at)
                VALUES (?, ?, ?, ?, 0, datetime('now'))
            ''', (m['product_id'], m['off_id'], match_type, m['confidence']))
        except sqlite3.IntegrityError:
            pass  # Already exists
    
    prom_conn.commit()
    
    # Export results
    with open(BASE_DIR / "phase1_results.json", 'w') as f:
        json.dump({
            'total_unmatched': len(unmatched),
            'new_matches': len(matches),
            'confident': len(confident),
            'likely': len(likely),
            'low': len(low),
            'matches': matches[:100]
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Phase 1 complete. Added {len(matches)} matches.")
    return len(matches)

if __name__ == '__main__':
    main()
