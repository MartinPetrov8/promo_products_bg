#!/usr/bin/env python3
"""
Product Enrichment Script
Extracts brand, quantity, and description from raw_scrapes 
and updates the products table.

Sources:
- Kaufland: raw_name (brand), raw_subtitle (description + quantity)
- Lidl: brand field, raw_description (HTML with details)  
- Billa: Already rich names, brand field
"""

import re
import sqlite3
import sys
import logging
from pathlib import Path
from html import unescape

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
DB_PATH = REPO_ROOT / "data" / "promobg.db"

from quantity_extractor import extract_quantity_from_name

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger(__name__)


def strip_html(text):
    """Remove HTML tags and decode entities"""
    if not text:
        return ''
    text = unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_brand_from_name(name):
    """Try to extract brand from product name (first word if UPPERCASE or known pattern)"""
    if not name:
        return None
    
    # Common pattern: Brand name is the first word(s) in CAPS or Title Case
    words = name.strip().split()
    if not words:
        return None
    
    # If first word is all caps and > 2 chars, it's likely a brand
    first = words[0]
    if first.isupper() and len(first) > 2 and first not in ('LED', 'USB', 'XXL', 'LCD'):
        return first
    
    # If first 2 words form a brand pattern (Title Case + Title Case)
    if len(words) >= 2:
        if words[0][0].isupper() and words[1][0].isupper() and not words[1][0].isdigit():
            # Check it's not a Bulgarian product description
            bg_starters = {'от', 'за', 'на', 'до', 'без', 'със', 'или', 'при', 'към', 'около',
                          'пресен', 'прясно', 'домашно', 'пилешко', 'свинско', 'телешко', 'червен'}
            if words[1].lower() not in bg_starters:
                return f"{words[0]} {words[1]}"
    
    return None


def enrich_kaufland(conn):
    """Enrich Kaufland products from raw_scrapes subtitles.
    
    Product names are constructed as: raw_name + "\n" + raw_subtitle
    So we can match by reconstructing this pattern.
    """
    cur = conn.cursor()
    
    # Build lookup: (raw_name + "\n" + subtitle) → raw data
    # Also index by raw_name alone for products without subtitle
    cur.execute("""SELECT raw_name, raw_subtitle, raw_description, brand, price_bgn
        FROM raw_scrapes WHERE store='Kaufland'""")
    
    raw_by_fullname = {}
    raw_by_rawname = {}
    for r in cur.fetchall():
        raw_name = (r[0] or '').strip()
        subtitle = (r[1] or '').strip()
        desc = r[2]
        brand = r[3]
        
        entry = {
            'raw_name': raw_name,
            'subtitle': subtitle,
            'description': desc,
            'brand': brand,
            'price': r[4]
        }
        
        # Product names may have newlines collapsed to spaces or preserved
        # Index both with-newline and without-newline versions
        if subtitle:
            full_key = f"{raw_name}\n{subtitle}".lower()
        else:
            full_key = raw_name.lower()
        
        # Also index with newlines replaced by spaces (how products table stores them)
        normalized_key = full_key.replace('\n', ' ')
        
        raw_by_fullname[full_key] = entry
        raw_by_fullname[normalized_key] = entry
        raw_by_rawname[raw_name.lower()] = entry
    
    log.info(f"Kaufland: {len(raw_by_fullname)} raw scrapes indexed")
    
    # Get current products
    cur.execute("""SELECT p.id, p.name, p.brand, p.quantity, p.quantity_unit
        FROM products p
        JOIN store_products sp ON sp.product_id = p.id
        JOIN stores s ON sp.store_id = s.id
        WHERE s.name = 'Kaufland'""")
    
    updated_brand = 0
    updated_qty = 0
    updated_name = 0
    matched = 0
    
    for pid, name, brand, qty, qty_unit in cur.fetchall():
        # Try exact full name match (normalize newlines to spaces)
        key = name.strip().lower().replace('\n', ' ') if name else ''
        raw = raw_by_fullname.get(key)
        
        if not raw:
            # Try with newlines preserved
            key_nl = name.strip().lower() if name else ''
            raw = raw_by_fullname.get(key_nl)
        
        if not raw:
            # Try first line only
            first_line = name.split('\n')[0].strip().lower() if name else ''
            raw = raw_by_rawname.get(first_line)
        
        if not raw:
            continue
        
        matched += 1
        updates = {}
        
        # Update brand if missing
        if (not brand or brand in ('NO_BRAND', '', 'Unknown')) and raw.get('brand'):
            updates['brand'] = raw['brand']
            updated_brand += 1
        
        # Update quantity from subtitle or description
        if not qty or qty <= 0:
            # Try subtitle
            q = extract_quantity_from_name(raw.get('subtitle', ''))
            # Try description
            if not q and raw.get('description'):
                q = extract_quantity_from_name(strip_html(raw['description']))
            # Try the full product name (might have qty in second line)
            if not q:
                q = extract_quantity_from_name(name)
            if q:
                updates['quantity'] = q['value']
                updates['quantity_unit'] = q['unit']
                updated_qty += 1
        
        # Store normalized_name (name + subtitle combined for matching)
        subtitle = raw.get('subtitle', '').strip()
        if subtitle and subtitle.lower() not in name.lower():
            full_name = f"{name} {subtitle}"
            updates['normalized_name'] = full_name[:200]
            updated_name += 1
        
        if updates:
            set_clause = ', '.join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [pid]
            cur.execute(f"UPDATE products SET {set_clause} WHERE id=?", values)
    
    conn.commit()
    log.info(f"Kaufland: matched {matched}/{matched + (890 - matched)} products to raw_scrapes")
    log.info(f"Kaufland enrichment: {updated_brand} brands, {updated_qty} quantities, {updated_name} names updated")


def enrich_lidl(conn):
    """Enrich Lidl products from raw_scrapes descriptions and brand_cache"""
    cur = conn.cursor()
    
    # Load brand cache
    import json
    brand_cache_path = REPO_ROOT / "data" / "brand_cache.json"
    brand_cache = {}
    if brand_cache_path.exists():
        with open(brand_cache_path) as f:
            brand_cache = json.load(f)
        log.info(f"Loaded {len(brand_cache)} entries from brand_cache.json")
    
    # Get Lidl raw scrapes with descriptions
    cur.execute("""SELECT raw_name, raw_description, brand, sku
        FROM raw_scrapes WHERE store='Lidl'""")
    raw_by_name = {}
    for r in cur.fetchall():
        key = r[0].strip().lower()[:30] if r[0] else ''
        if key:
            raw_by_name[key] = {
                'description': strip_html(r[1] or ''),
                'brand': r[2],
                'sku': r[3]
            }
    
    log.info(f"Lidl: {len(raw_by_name)} raw scrapes")
    
    cur.execute("""SELECT p.id, p.name, p.brand, p.quantity, p.quantity_unit, sp.external_id
        FROM products p
        JOIN store_products sp ON sp.product_id = p.id
        JOIN stores s ON sp.store_id = s.id
        WHERE s.name = 'Lidl'""")
    
    updated_brand = 0
    updated_qty = 0
    
    for pid, name, brand, qty, qty_unit, ext_id in cur.fetchall():
        updates = {}
        
        # Try brand from brand_cache (keyed by SKU/external_id)
        if (not brand or brand in ('NO_BRAND', '', 'Unknown')):
            # Try brand cache
            if ext_id and ext_id in brand_cache:
                cache_entry = brand_cache[ext_id]
                if cache_entry.get('brand') and cache_entry['brand'] not in ('NO_BRAND', 'ocr_failed'):
                    updates['brand'] = cache_entry['brand']
                    updated_brand += 1
            
            # Try raw scrapes brand
            if 'brand' not in updates:
                key = name.strip().lower()[:30] if name else ''
                raw = raw_by_name.get(key)
                if raw and raw.get('brand'):
                    updates['brand'] = raw['brand'].replace('®', '').strip()
                    updated_brand += 1
        
        # Try quantity from description
        if not qty or qty <= 0:
            key = name.strip().lower().replace('\n', ' ')[:30] if name else ''
            raw = raw_by_name.get(key)
            if raw and raw.get('description'):
                q = extract_quantity_from_name(raw['description'])
                if q:
                    updates['quantity'] = q['value']
                    updates['quantity_unit'] = q['unit']
                    updated_qty += 1
            
            # Try brand cache quantity
            if 'quantity' not in updates and ext_id and ext_id in brand_cache:
                cache_entry = brand_cache[ext_id]
                if cache_entry.get('quantity'):
                    updates['quantity'] = cache_entry['quantity']['value']
                    updates['quantity_unit'] = cache_entry['quantity']['unit']
                    updated_qty += 1
        
        if updates:
            set_clause = ', '.join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [pid]
            cur.execute(f"UPDATE products SET {set_clause} WHERE id=?", values)
    
    conn.commit()
    log.info(f"Lidl enrichment: {updated_brand} brands, {updated_qty} quantities updated")


def enrich_billa(conn):
    """Enrich Billa products — extract brand from name if missing"""
    cur = conn.cursor()
    
    cur.execute("""SELECT p.id, p.name, p.brand, p.quantity, p.quantity_unit
        FROM products p
        JOIN store_products sp ON sp.product_id = p.id
        JOIN stores s ON sp.store_id = s.id
        WHERE s.name = 'Billa'""")
    
    updated_brand = 0
    updated_qty = 0
    
    for pid, name, brand, qty, qty_unit in cur.fetchall():
        updates = {}
        
        if not brand or brand in ('NO_BRAND', '', 'Unknown'):
            extracted = extract_brand_from_name(name)
            if extracted:
                updates['brand'] = extracted
                updated_brand += 1
        
        if not qty or qty <= 0:
            q = extract_quantity_from_name(name)
            if q:
                updates['quantity'] = q['value']
                updates['quantity_unit'] = q['unit']
                updated_qty += 1
        
        if updates:
            set_clause = ', '.join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [pid]
            cur.execute(f"UPDATE products SET {set_clause} WHERE id=?", values)
    
    conn.commit()
    log.info(f"Billa enrichment: {updated_brand} brands, {updated_qty} quantities updated")


def report(conn):
    """Print coverage report"""
    cur = conn.cursor()
    
    print("\n" + "=" * 60)
    print("ENRICHMENT COVERAGE REPORT")
    print("=" * 60)
    
    for store in ['Kaufland', 'Lidl', 'Billa']:
        cur.execute("""SELECT COUNT(*) FROM products p
            JOIN store_products sp ON sp.product_id = p.id
            JOIN stores s ON sp.store_id = s.id
            LEFT JOIN prices pr ON pr.store_product_id = sp.id
            WHERE s.name=? AND pr.current_price > 0""", (store,))
        total = cur.fetchone()[0]
        
        cur.execute("""SELECT COUNT(*) FROM products p
            JOIN store_products sp ON sp.product_id = p.id
            JOIN stores s ON sp.store_id = s.id
            LEFT JOIN prices pr ON pr.store_product_id = sp.id
            WHERE s.name=? AND pr.current_price > 0
            AND p.brand IS NOT NULL AND p.brand != '' AND p.brand != 'NO_BRAND'""", (store,))
        with_brand = cur.fetchone()[0]
        
        cur.execute("""SELECT COUNT(*) FROM products p
            JOIN store_products sp ON sp.product_id = p.id
            JOIN stores s ON sp.store_id = s.id
            LEFT JOIN prices pr ON pr.store_product_id = sp.id
            WHERE s.name=? AND pr.current_price > 0
            AND p.quantity IS NOT NULL AND p.quantity > 0""", (store,))
        with_qty = cur.fetchone()[0]
        
        print(f"\n{store}: {total} products")
        print(f"  Brand: {with_brand}/{total} ({with_brand/total*100:.1f}%)")
        print(f"  Qty:   {with_qty}/{total} ({with_qty/total*100:.1f}%)")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    log.info("Starting product enrichment...")
    
    enrich_kaufland(conn)
    enrich_lidl(conn)
    enrich_billa(conn)
    
    report(conn)
    conn.close()


if __name__ == '__main__':
    main()
