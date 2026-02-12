#!/usr/bin/env python3
"""
Improved OFF Matcher - Uses cleaned names + size matching.

Key improvements over offline_matcher.py:
1. Uses cleaned/normalized names
2. Matches on brand + size, not just brand
3. Better confidence scoring
"""

import re
import sqlite3
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"
OFF_DB = PROJECT_ROOT / "data" / "off_bulgaria.db"


def normalize(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.lower().strip())


def extract_size(name):
    """Extract size in normalized format (value, unit)."""
    name_lower = name.lower()
    
    # Pack: "2 x 1.5 л"
    pack = re.search(r'(\d+)\s*[хx]\s*(\d+[.,]?\d*)\s*(г|гр|кг|мл|л|g|kg|ml|l)\b', name_lower)
    if pack:
        count = int(pack.group(1))
        val = float(pack.group(2).replace(',', '.'))
        unit = pack.group(3)
        if unit in ['л', 'l']:
            return (count * val * 1000, 'ml')
        elif unit in ['кг', 'kg']:
            return (count * val * 1000, 'g')
        elif unit in ['мл', 'ml']:
            return (count * val, 'ml')
        else:
            return (count * val, 'g')
    
    # Single: "500 г"
    single = re.search(r'(\d+[.,]?\d*)\s*(г|гр|кг|мл|л|g|kg|ml|l)\b', name_lower)
    if single:
        val = float(single.group(1).replace(',', '.'))
        unit = single.group(2)
        if unit in ['л', 'l']:
            return (val * 1000, 'ml')
        elif unit in ['кг', 'kg']:
            return (val * 1000, 'g')
        elif unit in ['мл', 'ml']:
            return (val, 'ml')
        else:
            return (val, 'g')
    
    return (None, None)


def parse_off_quantity(qty_str):
    """Parse OFF quantity field like '500 g', '1.5 l', '6 x 330 ml'."""
    if not qty_str:
        return (None, None)
    
    qty_lower = qty_str.lower()
    
    # Pack format
    pack = re.search(r'(\d+)\s*x\s*(\d+[.,]?\d*)\s*(g|kg|ml|l)\b', qty_lower)
    if pack:
        count = int(pack.group(1))
        val = float(pack.group(2).replace(',', '.'))
        unit = pack.group(3)
        if unit == 'l':
            return (count * val * 1000, 'ml')
        elif unit == 'kg':
            return (count * val * 1000, 'g')
        elif unit == 'ml':
            return (count * val, 'ml')
        else:
            return (count * val, 'g')
    
    # Single
    single = re.search(r'(\d+[.,]?\d*)\s*(g|kg|ml|l)\b', qty_lower)
    if single:
        val = float(single.group(1).replace(',', '.'))
        unit = single.group(2)
        if unit == 'l':
            return (val * 1000, 'ml')
        elif unit == 'kg':
            return (val * 1000, 'g')
        elif unit == 'ml':
            return (val, 'ml')
        else:
            return (val, 'g')
    
    return (None, None)


def sizes_match(s1, s2, tolerance=0.15):
    """Check if two sizes match within tolerance."""
    val1, unit1 = s1
    val2, unit2 = s2
    
    if not val1 or not val2:
        return False
    if unit1 != unit2:
        return False
    
    diff = abs(val1 - val2) / max(val1, val2)
    return diff <= tolerance


def extract_brand(name):
    """Extract brand from product name."""
    brands = {
        'coca-cola': 'coca-cola', 'coca cola': 'coca-cola', 'кока-кола': 'coca-cola',
        'pepsi': 'pepsi', 'пепси': 'pepsi',
        'fanta': 'fanta', 'фанта': 'fanta',
        'nescafe': 'nescafe', 'нескафе': 'nescafe',
        'nestle': 'nestle', 'нестле': 'nestle',
        'jacobs': 'jacobs', 'якобс': 'jacobs',
        'lavazza': 'lavazza', 'лаваца': 'lavazza',
        'milka': 'milka', 'милка': 'milka',
        'oreo': 'oreo', 'орео': 'oreo',
        'ferrero': 'ferrero', 'фереро': 'ferrero',
        'lindt': 'lindt', 'линдт': 'lindt',
        'snickers': 'snickers', 'сникърс': 'snickers',
        'mars': 'mars', 'марс': 'mars',
        'twix': 'twix', 'твикс': 'twix',
        'kitkat': 'kitkat', 'kit kat': 'kitkat',
        'lion': 'lion', 'лион': 'lion',
        'haribo': 'haribo', 'харибо': 'haribo',
        'верея': 'vereia', 'vereia': 'vereia',
        'olympus': 'olympus', 'олимпус': 'olympus',
        'danone': 'danone', 'данон': 'danone',
        'activia': 'activia', 'активиа': 'activia',
        'president': 'president', 'президент': 'president',
        'devin': 'devin', 'девин': 'devin',
        'bankya': 'bankya', 'банкя': 'bankya',
        'zagorka': 'zagorka', 'загорка': 'zagorka',
        'kamenitza': 'kamenitza', 'каменица': 'kamenitza',
        'heineken': 'heineken', 'хайнекен': 'heineken',
        'ariel': 'ariel', 'ариел': 'ariel',
        'persil': 'persil', 'персил': 'persil',
        'finish': 'finish', 'финиш': 'finish',
        'nivea': 'nivea', 'нивеа': 'nivea',
        'colgate': 'colgate', 'колгейт': 'colgate',
        'hochland': 'hochland', 'хохланд': 'hochland',
    }
    
    name_lower = name.lower()
    for pattern, brand in sorted(brands.items(), key=lambda x: -len(x[0])):
        if pattern in name_lower:
            return brand
    return None


def run_matching():
    print("=" * 70)
    print("IMPROVED OFF MATCHING (with size matching)")
    print("=" * 70)
    
    start = time.time()
    
    # Load our products
    print("\n📦 Loading products...")
    our_conn = sqlite3.connect(str(OUR_DB))
    our_cursor = our_conn.cursor()
    our_cursor.execute('''
        SELECT DISTINCT p.id, p.name, p.normalized_name, s.name as store
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        WHERE p.deleted_at IS NULL
    ''')
    our_products = our_cursor.fetchall()
    print(f"   Our products: {len(our_products)}")
    
    # Load OFF products
    off_conn = sqlite3.connect(str(OFF_DB))
    off_cursor = off_conn.cursor()
    off_cursor.execute('''
        SELECT barcode, product_name, brands, quantity
        FROM off_products
        WHERE barcode IS NOT NULL AND barcode != ''
    ''')
    off_products = off_cursor.fetchall()
    print(f"   OFF products: {len(off_products)}")
    
    # Build OFF index by brand
    print("\n🔧 Building index...")
    off_by_brand = defaultdict(list)
    
    for barcode, name, brands, quantity in off_products:
        off_size = parse_off_quantity(quantity)
        off_brand = extract_brand(f"{name or ''} {brands or ''}")
        
        entry = {
            'barcode': barcode,
            'name': name or '',
            'brands': brands or '',
            'quantity': quantity or '',
            'size': off_size,
            'brand_key': off_brand,
        }
        
        if off_brand:
            off_by_brand[off_brand].append(entry)
    
    print(f"   Brands indexed: {len(off_by_brand)}")
    
    # Match
    print("\n🎯 Matching...")
    
    matches = {
        'brand_and_size': [],
        'brand_only': [],
        'size_only': [],
    }
    no_match = 0
    
    for i, (pid, name, norm_name, store) in enumerate(our_products):
        if i % 500 == 0:
            print(f"   {i}/{len(our_products)}...")
        
        # Use normalized name if available (cleaned Billa names)
        search_name = norm_name if norm_name else name
        our_brand = extract_brand(search_name)
        our_size = extract_size(search_name)
        
        best_match = None
        match_type = None
        
        # Strategy 1: Brand + Size match (best)
        if our_brand and our_brand in off_by_brand:
            for off in off_by_brand[our_brand]:
                if our_size[0] and off['size'][0]:
                    if sizes_match(our_size, off['size']):
                        best_match = off
                        match_type = 'brand_and_size'
                        break
        
        # Strategy 2: Brand only match
        if not best_match and our_brand and our_brand in off_by_brand:
            candidates = off_by_brand[our_brand]
            if candidates:
                best_match = candidates[0]  # Take first
                match_type = 'brand_only'
        
        if best_match:
            matches[match_type].append({
                'our_id': pid,
                'our_name': name,
                'our_brand': our_brand,
                'our_size': our_size,
                'store': store,
                'barcode': best_match['barcode'],
                'off_name': best_match['name'],
                'off_brand': best_match['brands'],
                'off_size': best_match['quantity'],
                'match_type': match_type,
            })
        else:
            no_match += 1
    
    elapsed = time.time() - start
    
    # Results
    print("\n" + "=" * 70)
    print("📊 MATCHING RESULTS")
    print("=" * 70)
    print(f"Brand + Size matches: {len(matches['brand_and_size'])} (BEST)")
    print(f"Brand only matches:   {len(matches['brand_only'])}")
    print(f"No match:             {no_match}")
    print(f"Time:                 {elapsed:.1f}s")
    
    total_good = len(matches['brand_and_size'])
    
    # Show brand+size matches
    print("\n" + "=" * 70)
    print("✅ BRAND + SIZE MATCHES (highest confidence)")
    print("=" * 70)
    
    for m in matches['brand_and_size'][:20]:
        print(f"\nBarcode: {m['barcode']}")
        print(f"  Our:  [{m['store'][:8]:8}] {m['our_name'][:50]}")
        print(f"  OFF:  {m['off_name'][:40]} | {m['off_size']}")
        print(f"  Size: {m['our_size'][0]}{m['our_size'][1]} → {m['off_size']}")
    
    # Save brand+size matches
    print("\n💾 Saving brand+size matches to database...")
    saved = 0
    for m in matches['brand_and_size']:
        our_cursor.execute('''
            UPDATE products 
            SET barcode_ean = ?, match_confidence = 0.95
            WHERE id = ?
        ''', (m['barcode'], m['our_id']))
        saved += 1
    our_conn.commit()
    print(f"   Saved {saved} high-confidence matches")
    
    # Stats by store
    print("\n📊 BY STORE:")
    store_counts = defaultdict(int)
    for m in matches['brand_and_size']:
        store_counts[m['store']] += 1
    for store, count in sorted(store_counts.items()):
        print(f"   {store}: {count} brand+size matches")
    
    our_conn.close()
    off_conn.close()


if __name__ == '__main__':
    run_matching()
