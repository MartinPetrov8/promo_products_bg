#!/usr/bin/env python3
"""
Multi-Pass Product Matcher - Match store products against OFF database.
Uses pre-built indices for fast matching.

Usage:
    python3 multi_pass_matcher.py [--dry-run] [--store STORE]
"""

import re
import json
import sqlite3
import sys
import argparse
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"
INDEX_DIR = PROJECT_ROOT / "data" / "indices"

# Confidence thresholds
THRESHOLD_HIGH = 0.85
THRESHOLD_MEDIUM = 0.70
THRESHOLD_LOW = 0.55

# Stopwords
STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'а', 'до', 'по', 'при', 'към', 'под', 'над'}

# Brand transliterations
BRAND_TRANSLITERATIONS = {
    'кока-кола': 'coca-cola', 'кока кола': 'coca-cola',
    'пепси': 'pepsi', 'фанта': 'fanta', 'спрайт': 'sprite',
    'нестле': 'nestle', 'нескафе': 'nescafe', 'данон': 'danone',
    'активиа': 'activia', 'милка': 'milka', 'орео': 'oreo',
    'фереро': 'ferrero', 'рафаело': 'raffaello', 'линдт': 'lindt',
    'тоблерон': 'toblerone', 'харибо': 'haribo', 'сникърс': 'snickers',
    'марс': 'mars', 'твикс': 'twix', 'баунти': 'bounty', 'лион': 'lion',
    'якобс': 'jacobs', 'лаваца': 'lavazza', 'давидоф': 'davidoff',
    'верея': 'vereia', 'олимпус': 'olympus', 'президент': 'president',
    'девин': 'devin', 'банкя': 'bankya', 'загорка': 'zagorka',
    'каменица': 'kamenitza', 'хайнекен': 'heineken', 'ариел': 'ariel',
    'персил': 'persil', 'ленор': 'lenor', 'нивеа': 'nivea',
    'гарние': 'garnier', 'колгейт': 'colgate', 'дав': 'dove',
    'палмолив': 'palmolive', 'бондюел': 'bonduelle',
}


def load_indices():
    """Load pre-built indices."""
    print("📂 Loading indices...")
    
    with open(INDEX_DIR / "off_brand_index.json", 'r', encoding='utf-8') as f:
        brand_index = json.load(f)
    
    with open(INDEX_DIR / "off_quantity_index.json", 'r', encoding='utf-8') as f:
        quantity_index = json.load(f)
    
    with open(INDEX_DIR / "off_token_index.json", 'r', encoding='utf-8') as f:
        token_index = json.load(f)
    
    with open(INDEX_DIR / "off_product_data.json", 'r', encoding='utf-8') as f:
        product_data = json.load(f)
    
    print(f"  Brands: {len(brand_index)}, Quantities: {len(quantity_index)}, Tokens: {len(token_index)}, Products: {len(product_data)}")
    return brand_index, quantity_index, token_index, product_data


def normalize_brand(brand):
    """Normalize brand for matching."""
    if not brand:
        return None
    brand = brand.lower().strip()
    brand = re.sub(r'[^\w\s\u0400-\u04FF-]', '', brand)
    brand = re.sub(r'\s+', ' ', brand).strip()
    if brand in BRAND_TRANSLITERATIONS:
        return BRAND_TRANSLITERATIONS[brand]
    return brand if brand else None


def normalize_quantity(qty):
    """Normalize quantity for matching."""
    if not qty:
        return None
    qty = qty.lower().strip()
    qty = re.sub(r'\s+', '', qty)
    qty = qty.replace('кг', 'kg').replace('г', 'g')
    qty = qty.replace('мл', 'ml').replace('л', 'l')
    match = re.match(r'(\d+(?:[.,]\d+)?)(g|kg|l|ml)', qty)
    if match:
        value = match.group(1).replace(',', '.')
        return f"{value}{match.group(2)}"
    return qty if qty else None


def tokenize(name):
    """Tokenize name into significant words."""
    if not name:
        return []
    name = name.lower()
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    words = name.split()
    return [w for w in words if w not in STOPWORDS and len(w) >= 3]


def calculate_name_similarity(name1, name2):
    """Calculate name similarity using token overlap + sequence matching."""
    if not name1 or not name2:
        return 0.0
    
    name1 = name1.lower()
    name2 = name2.lower()
    
    # Token overlap
    tokens1 = set(tokenize(name1))
    tokens2 = set(tokenize(name2))
    
    if not tokens1 or not tokens2:
        return SequenceMatcher(None, name1, name2).ratio()
    
    overlap = len(tokens1 & tokens2) / max(len(tokens1), len(tokens2))
    seq_ratio = SequenceMatcher(None, name1, name2).ratio()
    
    return overlap * 0.6 + seq_ratio * 0.4


def calculate_match_score(our_product, off_barcode, product_data):
    """Calculate match score between our product and OFF product."""
    off = product_data.get(off_barcode)
    if not off:
        return 0.0
    
    our_name = our_product['normalized_name'] or our_product['name']
    our_brand = normalize_brand(our_product.get('brand'))
    our_qty = normalize_quantity(our_product.get('size'))
    
    off_name = off.get('name', '')
    off_brand = normalize_brand(off.get('brand'))
    off_qty = normalize_quantity(off.get('quantity'))
    
    # Brand score (0.40 weight)
    brand_score = 0.0
    if our_brand and off_brand:
        if our_brand == off_brand:
            brand_score = 1.0
        elif our_brand in off_brand or off_brand in our_brand:
            brand_score = 0.8
        else:
            brand_score = SequenceMatcher(None, our_brand, off_brand).ratio() * 0.5
    
    # Name score (0.35 weight)
    name_score = calculate_name_similarity(our_name, off_name)
    
    # Quantity score (0.25 weight)
    qty_score = 0.0
    if our_qty and off_qty:
        if our_qty == off_qty:
            qty_score = 1.0
        else:
            # Try to compare numerically
            our_match = re.match(r'(\d+(?:\.\d+)?)(g|kg|l|ml)', our_qty)
            off_match = re.match(r'(\d+(?:\.\d+)?)(g|kg|l|ml)', off_qty)
            if our_match and off_match:
                our_val = float(our_match.group(1))
                off_val = float(off_match.group(1))
                our_unit = our_match.group(2)
                off_unit = off_match.group(2)
                if our_unit == off_unit:
                    # Same unit - check if within 10%
                    diff = abs(our_val - off_val) / max(our_val, off_val)
                    if diff < 0.1:
                        qty_score = 0.9
                    elif diff < 0.3:
                        qty_score = 0.5
    
    # Weighted total
    total = (brand_score * 0.40) + (name_score * 0.35) + (qty_score * 0.25)
    return total


def run_matching(dry_run=False, store_filter=None):
    print("=" * 60)
    print("🔍 Multi-Pass Product Matching")
    print("=" * 60)
    
    # Load indices
    brand_index, quantity_index, token_index, product_data = load_indices()
    
    # Load our products
    conn = sqlite3.connect(str(OUR_DB))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    
    query = """
        SELECT p.id, p.name, p.normalized_name, p.brand, p.barcode_ean,
               sp.package_size, s.name as store_name
        FROM products p
        JOIN store_products sp ON sp.product_id = p.id
        JOIN stores s ON sp.store_id = s.id
        WHERE p.deleted_at IS NULL AND sp.deleted_at IS NULL
    """
    if store_filter:
        query += f" AND s.name = '{store_filter}'"
    
    cur.execute(query)
    our_products = []
    for row in cur.fetchall():
        our_products.append({
            'id': row[0],
            'name': row[1],
            'normalized_name': row[2],
            'brand': row[3],
            'existing_barcode': row[4],
            'size': row[5],
            'store': row[6]
        })
    
    print(f"Loaded {len(our_products)} store products")
    
    # Track stats
    stats = {
        'total': len(our_products),
        'already_matched': 0,
        'pass1_matches': 0,
        'pass2_matches': 0,
        'pass3_matches': 0,
        'no_match': 0,
    }
    
    matches = []
    matched_ids = set()
    
    # Skip products that already have barcodes
    for p in our_products:
        if p['existing_barcode']:
            stats['already_matched'] += 1
            matched_ids.add(p['id'])
    
    print(f"Already have barcodes: {stats['already_matched']}")
    
    # ========== PASS 1: Brand + Quantity Exact Match ==========
    print(f"\n🔹 Pass 1: Brand + Quantity exact match...")
    for p in our_products:
        if p['id'] in matched_ids:
            continue
        
        our_brand = normalize_brand(p.get('brand'))
        our_qty = normalize_quantity(p.get('size'))
        
        if not our_brand or not our_qty:
            continue
        
        # Find candidates with same brand AND quantity
        brand_candidates = set(brand_index.get(our_brand, []))
        qty_candidates = set(quantity_index.get(our_qty, []))
        candidates = brand_candidates & qty_candidates
        
        if not candidates:
            continue
        
        # Score candidates
        best_barcode = None
        best_score = 0
        
        for barcode in candidates:
            score = calculate_match_score(p, barcode, product_data)
            if score > best_score:
                best_score = score
                best_barcode = barcode
        
        if best_barcode and best_score >= 0.70:
            confidence = min(0.95, best_score + 0.1)  # Boost for exact brand+qty
            matches.append({
                'product_id': p['id'],
                'name': p['name'],
                'brand': p.get('brand'),
                'size': p.get('size'),
                'store': p['store'],
                'barcode': best_barcode,
                'off_name': product_data[best_barcode]['name'],
                'off_brand': product_data[best_barcode]['brand'],
                'confidence': confidence,
                'pass': 1
            })
            matched_ids.add(p['id'])
            stats['pass1_matches'] += 1
    
    print(f"  Found {stats['pass1_matches']} matches")
    
    # ========== PASS 2: Brand + Name Similarity ==========
    print(f"\n🔹 Pass 2: Brand + Name similarity...")
    for p in our_products:
        if p['id'] in matched_ids:
            continue
        
        our_brand = normalize_brand(p.get('brand'))
        if not our_brand:
            continue
        
        # Find candidates with same brand
        candidates = brand_index.get(our_brand, [])
        if not candidates:
            continue
        
        # Score candidates
        best_barcode = None
        best_score = 0
        
        for barcode in candidates[:100]:  # Limit to avoid slowness
            score = calculate_match_score(p, barcode, product_data)
            if score > best_score:
                best_score = score
                best_barcode = barcode
        
        if best_barcode and best_score >= THRESHOLD_MEDIUM:
            matches.append({
                'product_id': p['id'],
                'name': p['name'],
                'brand': p.get('brand'),
                'size': p.get('size'),
                'store': p['store'],
                'barcode': best_barcode,
                'off_name': product_data[best_barcode]['name'],
                'off_brand': product_data[best_barcode]['brand'],
                'confidence': best_score,
                'pass': 2
            })
            matched_ids.add(p['id'])
            stats['pass2_matches'] += 1
    
    print(f"  Found {stats['pass2_matches']} matches")
    
    # ========== PASS 3: Name Token Overlap (2+ tokens) ==========
    print(f"\n🔹 Pass 3: Name token overlap (2+ shared tokens)...")
    for p in our_products:
        if p['id'] in matched_ids:
            continue
        
        our_name = p.get('normalized_name') or p.get('name')
        tokens = tokenize(our_name)
        
        if len(tokens) < 2:
            continue
        
        # Find candidates sharing tokens
        candidate_counts = defaultdict(int)
        for token in tokens:
            for barcode in token_index.get(token, [])[:100]:  # Limit per token
                candidate_counts[barcode] += 1
        
        # Filter to candidates with 2+ shared tokens
        candidates = [bc for bc, cnt in candidate_counts.items() if cnt >= 2]
        
        if not candidates:
            continue
        
        # Score top candidates
        best_barcode = None
        best_score = 0
        
        for barcode in candidates[:50]:
            score = calculate_match_score(p, barcode, product_data)
            if score > best_score:
                best_score = score
                best_barcode = barcode
        
        if best_barcode and best_score >= THRESHOLD_MEDIUM:
            matches.append({
                'product_id': p['id'],
                'name': p['name'],
                'brand': p.get('brand'),
                'size': p.get('size'),
                'store': p['store'],
                'barcode': best_barcode,
                'off_name': product_data[best_barcode]['name'],
                'off_brand': product_data[best_barcode]['brand'],
                'confidence': best_score,
                'pass': 3
            })
            matched_ids.add(p['id'])
            stats['pass3_matches'] += 1
    
    print(f"  Found {stats['pass3_matches']} matches")
    
    # Skip Pass 4 (fuzzy) - too slow and low quality
    
    stats['no_match'] = stats['total'] - stats['already_matched'] - len(matches)
    
    # ========== Results Summary ==========
    print("\n" + "=" * 60)
    print("📊 MATCHING RESULTS")
    print("=" * 60)
    print(f"Total products:         {stats['total']:,}")
    print(f"Already had barcode:    {stats['already_matched']:,}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Pass 1 (brand+qty):     {stats['pass1_matches']:,}")
    print(f"Pass 2 (brand+name):    {stats['pass2_matches']:,}")
    print(f"Pass 3 (token overlap): {stats['pass3_matches']:,}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Total new matches:      {len(matches):,}")
    print(f"No match:               {stats['no_match']:,}")
    
    # Confidence breakdown
    high_conf = [m for m in matches if m['confidence'] >= THRESHOLD_HIGH]
    med_conf = [m for m in matches if THRESHOLD_MEDIUM <= m['confidence'] < THRESHOLD_HIGH]
    low_conf = [m for m in matches if m['confidence'] < THRESHOLD_MEDIUM]
    
    print(f"\n📊 Confidence breakdown:")
    print(f"  High (≥{THRESHOLD_HIGH:.0%}):   {len(high_conf):,}")
    print(f"  Medium ({THRESHOLD_MEDIUM:.0%}-{THRESHOLD_HIGH:.0%}): {len(med_conf):,}")
    print(f"  Low (<{THRESHOLD_MEDIUM:.0%}):    {len(low_conf):,}")
    
    # Store breakdown
    print(f"\n📊 Matches by store:")
    store_counts = defaultdict(int)
    for m in matches:
        store_counts[m['store']] += 1
    for store, count in sorted(store_counts.items()):
        print(f"  {store}: {count:,}")
    
    # Sample matches
    print("\n📋 Sample HIGH confidence matches:")
    for m in sorted(matches, key=lambda x: -x['confidence'])[:10]:
        print(f"\n  ✅ {m['confidence']:.0%} [Pass {m['pass']}] | Barcode: {m['barcode']}")
        print(f"     Our:  [{m['store'][:8]:8}] {m['name'][:45]}")
        print(f"     OFF:  {m['off_name'][:45] if m['off_name'] else 'N/A'}")
    
    # ========== Save to Database ==========
    if dry_run:
        print(f"\n🔸 DRY RUN - not saving to database")
    else:
        print(f"\n💾 Saving {len(matches)} matches to database...")
        saved = 0
        for m in matches:
            if m['confidence'] >= THRESHOLD_LOW:
                cur.execute("""
                    UPDATE products 
                    SET barcode_ean = ?, match_confidence = ?
                    WHERE id = ?
                """, (m['barcode'], m['confidence'], m['product_id']))
                saved += 1
        
        conn.commit()
        print(f"  Saved {saved} barcodes (≥{THRESHOLD_LOW:.0%} confidence)")
    
    conn.close()
    
    # Save matches to JSON for review
    matches_file = PROJECT_ROOT / "data" / "matches_results.json"
    with open(matches_file, 'w', encoding='utf-8') as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)
    print(f"\n📁 Matches saved to: {matches_file}")
    
    print(f"\n✅ Done!")
    return matches


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Multi-pass product matcher')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--store', type=str, help='Filter by store name')
    args = parser.parse_args()
    
    run_matching(dry_run=args.dry_run, store_filter=args.store)
