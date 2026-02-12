#!/usr/bin/env python3
"""
Offline Product Matcher - Match our products against local OFF database.

Fast matching: ~10 seconds for 2500 products against 15K OFF products.
"""

import re
import sqlite3
import sys
import time
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"
OFF_DB = PROJECT_ROOT / "data" / "off_bulgaria.db"


def normalize(text):
    """Normalize text for matching."""
    if not text:
        return ""
    text = text.lower().strip()
    # Remove promotional text
    text = re.sub(r'king\s+оферта\s*-?\s*', '', text)
    text = re.sub(r'супер\s+цена\s*-?\s*', '', text)
    text = re.sub(r'само\s+с\s+billa\s+card\s*-?\s*', '', text)
    text = re.sub(r'продукт[,\s]+маркиран.*', '', text)
    # Remove special chars but keep Cyrillic
    text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_brand(name):
    """Extract brand from product name."""
    brands = [
        'coca-cola', 'coca cola', 'кока-кола', 'pepsi', 'пепси', 'fanta', 'фанта',
        'sprite', 'спрайт', 'nestle', 'нестле', 'nescafe', 'нескафе',
        'danone', 'данон', 'activia', 'активиа', 'milka', 'милка',
        'oreo', 'орео', 'ferrero', 'фереро', 'raffaello', 'рафаело',
        'lindt', 'линдт', 'toblerone', 'тоблерон', 'haribo', 'харибо',
        'snickers', 'сникърс', 'mars', 'марс', 'twix', 'твикс', 'bounty', 'баунти',
        'kitkat', 'kit kat', 'lion', 'лион',
        'jacobs', 'якобс', 'lavazza', 'лаваца', 'davidoff', 'давидоф',
        'верея', 'vereia', 'olympus', 'олимпус', 'president', 'президент',
        'devin', 'девин', 'bankya', 'банкя', 'gorna banya', 'горна баня',
        'zagorka', 'загорка', 'kamenitza', 'каменица', 'heineken', 'хайнекен',
        'ariel', 'ариел', 'persil', 'персил', 'lenor', 'ленор', 'finish', 'финиш',
        'nivea', 'нивеа', 'garnier', 'гарние', 'colgate', 'колгейт', 'dove', 'дав',
        'head & shoulders', 'palmolive', 'палмолив',
    ]
    name_lower = name.lower()
    for brand in sorted(brands, key=len, reverse=True):
        if brand in name_lower:
            return brand
    return None


def calculate_similarity(our_name, off_name, our_brand, off_brand):
    """Calculate match confidence."""
    score = 0.0
    
    # Brand match: +0.5
    if our_brand and off_brand:
        our_b = our_brand.lower().replace('-', ' ')
        off_b = off_brand.lower().replace('-', ' ')
        if our_b in off_b or off_b in our_b:
            score += 0.5
        elif SequenceMatcher(None, our_b, off_b).ratio() > 0.8:
            score += 0.4
    
    # Name similarity: +0.5
    our_norm = normalize(our_name)
    off_norm = normalize(off_name)
    
    # Check word overlap
    our_words = set(our_norm.split())
    off_words = set(off_norm.split())
    
    if our_words and off_words:
        overlap = len(our_words & off_words) / max(len(our_words), len(off_words))
        score += overlap * 0.3
    
    # Sequence similarity
    seq_sim = SequenceMatcher(None, our_norm, off_norm).ratio()
    score += seq_sim * 0.2
    
    return min(score, 1.0)


def run_matching():
    """Run offline matching."""
    print("=" * 60)
    print("🔍 Offline Product Matching")
    print("=" * 60)
    
    start_time = time.time()
    
    # Load our products
    print("\n📦 Loading our products...")
    our_conn = sqlite3.connect(str(OUR_DB))
    our_cursor = our_conn.cursor()
    our_cursor.execute('''
        SELECT DISTINCT p.id, p.name, p.brand, s.name as store
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        WHERE p.deleted_at IS NULL
    ''')
    our_products = our_cursor.fetchall()
    print(f"   Loaded {len(our_products):,} products")
    
    # Load OFF products
    print("\n📦 Loading OFF products...")
    off_conn = sqlite3.connect(str(OFF_DB))
    off_cursor = off_conn.cursor()
    off_cursor.execute('''
        SELECT barcode, product_name, brands, normalized_name, normalized_brand
        FROM off_products
        WHERE barcode IS NOT NULL AND barcode != ''
    ''')
    off_products = off_cursor.fetchall()
    print(f"   Loaded {len(off_products):,} OFF products")
    
    # Build OFF index by brand for faster matching
    print("\n🔧 Building search index...")
    off_by_brand = defaultdict(list)
    off_all = []
    for barcode, name, brands, norm_name, norm_brand in off_products:
        entry = {
            'barcode': barcode,
            'name': name or '',
            'brands': brands or '',
            'norm_name': norm_name or '',
            'norm_brand': norm_brand or '',
        }
        off_all.append(entry)
        
        # Index by brand words
        if brands:
            for word in brands.lower().split():
                if len(word) > 2:
                    off_by_brand[word].append(entry)
    
    print(f"   Index built: {len(off_by_brand)} brand keys")
    
    # Match products
    print("\n🎯 Matching products...")
    
    matches = []
    high_confidence = 0
    medium_confidence = 0
    low_confidence = 0
    no_match = 0
    
    for i, (pid, name, brand_db, store) in enumerate(our_products):
        if i % 500 == 0:
            print(f"   Processing {i:,}/{len(our_products):,}...")
        
        our_brand = brand_db or extract_brand(name)
        our_norm = normalize(name)
        
        best_match = None
        best_score = 0
        
        # Get candidates from brand index
        candidates = []
        if our_brand:
            for word in our_brand.lower().split():
                if word in off_by_brand:
                    candidates.extend(off_by_brand[word])
        
        # If no brand candidates, sample from all (limit for speed)
        if not candidates:
            # Check first 1000 products for non-branded items
            candidates = off_all[:1000]
        
        # Score candidates
        for off in candidates:
            score = calculate_similarity(name, off['name'], our_brand, off['brands'])
            if score > best_score:
                best_score = score
                best_match = off
        
        if best_score >= 0.6:
            matches.append({
                'our_id': pid,
                'our_name': name,
                'our_brand': our_brand,
                'store': store,
                'barcode': best_match['barcode'],
                'off_name': best_match['name'],
                'off_brand': best_match['brands'],
                'confidence': best_score,
            })
            
            if best_score >= 0.8:
                high_confidence += 1
            elif best_score >= 0.7:
                medium_confidence += 1
            else:
                low_confidence += 1
        else:
            no_match += 1
    
    elapsed = time.time() - start_time
    
    # Save matches to our database
    print("\n💾 Saving matches to database...")
    saved = 0
    for match in matches:
        if match['confidence'] >= 0.7:  # Only save medium+ confidence
            our_cursor.execute('''
                UPDATE products 
                SET barcode_ean = ?, match_confidence = ?
                WHERE id = ?
            ''', (match['barcode'], match['confidence'], match['our_id']))
            saved += 1
    our_conn.commit()
    
    # Print results
    print("\n" + "=" * 60)
    print("📊 MATCHING RESULTS")
    print("=" * 60)
    print(f"Our products:         {len(our_products):,}")
    print(f"OFF products:         {len(off_products):,}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Total matches:        {len(matches):,}")
    print(f"  High (≥80%):        {high_confidence:,}")
    print(f"  Medium (70-79%):    {medium_confidence:,}")
    print(f"  Low (60-69%):       {low_confidence:,}")
    print(f"No match:             {no_match:,}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Barcodes saved:       {saved:,} (≥70% confidence)")
    print(f"Match rate:           {len(matches)/len(our_products)*100:.1f}%")
    print(f"Time elapsed:         {elapsed:.1f} seconds")
    
    # Show sample matches
    print("\n" + "=" * 60)
    print("📋 SAMPLE HIGH-CONFIDENCE MATCHES")
    print("=" * 60)
    
    high_matches = [m for m in matches if m['confidence'] >= 0.8]
    for m in high_matches[:20]:
        print(f"\n✅ {m['confidence']:.0%} | Barcode: {m['barcode']}")
        print(f"   Our:  [{m['store'][:8]:8}] {m['our_name'][:45]}")
        print(f"   OFF:  {m['off_name'][:45]} ({m['off_brand'][:20]})")
    
    # Show products with barcodes by store
    print("\n" + "=" * 60)
    print("📊 BARCODES BY STORE")
    print("=" * 60)
    
    store_counts = defaultdict(int)
    for m in matches:
        if m['confidence'] >= 0.7:
            store_counts[m['store']] += 1
    
    for store, count in sorted(store_counts.items()):
        print(f"  {store}: {count:,} products with barcodes")
    
    our_conn.close()
    off_conn.close()
    
    return matches


if __name__ == '__main__':
    run_matching()
