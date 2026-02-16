#!/usr/bin/env python3
"""
PromoBG Data Pipeline - Production Ready

Single entry point for all data operations:
  python pipeline.py --full          # Run complete pipeline
  python pipeline.py --scrape lidl   # Scrape single store
  python pipeline.py --match         # Run matching only
  python pipeline.py --export        # Export to frontend only

Pipeline steps:
  1. SCRAPE  → raw_scrapes/{store}_{date}.json
  2. CLEAN   → DB (products, store_products, prices)
  3. MATCH   → DB (cross_store_matches)
  4. EXPORT  → docs/data/products.json
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Setup paths
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

DB_PATH = REPO_ROOT / "data" / "promobg.db"
CONFIG_DIR = REPO_ROOT / "config"
RAW_SCRAPES_DIR = REPO_ROOT / "raw_scrapes"
OUTPUT_PATH = REPO_ROOT / "docs" / "data" / "products.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)


def load_config(name):
    """Load config from JSON file"""
    path = CONFIG_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# STEP 1: SCRAPE
# =============================================================================

def scrape_store(store_name):
    """Run scraper for a specific store"""
    log.info(f"Scraping {store_name}...")
    
    # Import store-specific scraper
    if store_name == 'lidl':
        from scrapers.lidl import LidlScraper
        scraper = LidlScraper()
    elif store_name == 'kaufland':
        from scrapers.kaufland import KauflandScraper
        scraper = KauflandScraper()
    elif store_name == 'billa':
        from scrapers.billa import BillaScraper
        scraper = BillaScraper()
    else:
        raise ValueError(f"Unknown store: {store_name}")
    
    # Scrape and save raw
    products = scraper.scrape()
    
    RAW_SCRAPES_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = RAW_SCRAPES_DIR / f"{store_name}_{date_str}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    log.info(f"Saved {len(products)} raw products to {output_path}")
    return output_path


# =============================================================================
# STEP 2: CLEAN & IMPORT
# =============================================================================

def clean_and_import(store_name, raw_file=None):
    """Clean raw scrape data and import to DB"""
    log.info(f"Cleaning and importing {store_name}...")
    
    config = load_config("cleaning")
    
    # Find latest raw file if not specified
    if raw_file is None:
        files = sorted(RAW_SCRAPES_DIR.glob(f"{store_name}_*.json"), reverse=True)
        if not files:
            log.warning(f"No raw files found for {store_name}")
            return 0
        raw_file = files[0]
    
    with open(raw_file) as f:
        raw_products = json.load(f)
    
    log.info(f"Loaded {len(raw_products)} raw products from {raw_file}")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get store ID
    cur.execute("SELECT id FROM stores WHERE name = ?", (store_name.title(),))
    row = cur.fetchone()
    if not row:
        log.error(f"Store {store_name} not found in DB")
        return 0
    store_id = row['id']
    
    # Get existing product names to avoid duplicates
    cur.execute("""
        SELECT p.name FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = ?
    """, (store_id,))
    existing = {row['name'].lower() for row in cur.fetchall()}
    
    # Process products
    imported = 0
    for raw in raw_products:
        name = clean_name(raw.get('name', ''), config)
        if not name:
            continue
        
        # Skip duplicates
        if name.lower() in existing:
            continue
        
        # Get price (convert BGN to EUR if needed)
        price = raw.get('price')
        if price is None:
            continue
        
        currency = raw.get('currency', 'EUR')
        if currency == 'BGN':
            price = round(price / config['currency']['bgn_to_eur'], 2)
        
        # Skip invalid prices
        if price <= 0 or price > 10000:
            continue
        
        # Get brand
        brand = raw.get('brand') or extract_brand(name)
        
        # Get category
        category = categorize(name, config['categories'])
        
        # Insert to DB
        try:
            cur.execute("INSERT INTO products (name, brand) VALUES (?, ?)", (name, brand))
            product_id = cur.lastrowid
            
            cur.execute("INSERT INTO store_products (store_id, product_id) VALUES (?, ?)",
                       (store_id, product_id))
            store_product_id = cur.lastrowid
            
            cur.execute("INSERT INTO prices (store_product_id, current_price) VALUES (?, ?)",
                       (store_product_id, price))
            
            existing.add(name.lower())
            imported += 1
        except Exception as e:
            log.debug(f"Error importing {name}: {e}")
    
    conn.commit()
    conn.close()
    
    log.info(f"Imported {imported} new products for {store_name}")
    return imported


def clean_name(name, config):
    """Clean product name"""
    if not name:
        return ""
    
    # Remove patterns
    for pattern in config['name_cleanup']['remove_patterns']:
        name = name.replace(pattern, ' ')
    
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


def extract_brand(name):
    """Extract brand from product name (first word if capitalized)"""
    words = name.split()
    if words and words[0][0].isupper():
        return words[0]
    return None


def categorize(name, categories):
    """Categorize product by name keywords"""
    name_lower = name.lower()
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in name_lower:
                return cat
    return 'other'


# =============================================================================
# STEP 3: MATCH
# =============================================================================

def run_matching():
    """Run cross-store matching"""
    log.info("Running cross-store matching...")
    
    config = load_config("matching")
    conn = get_db()
    cur = conn.cursor()
    
    # Load all products with prices
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand,
            s.name as store,
            pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE pr.current_price IS NOT NULL AND pr.current_price > 0
    """)
    
    products = [dict(row) for row in cur.fetchall()]
    log.info(f"Loaded {len(products)} products with prices")
    
    # Tokenize and categorize
    cleaning_config = load_config("cleaning")
    for p in products:
        p['tokens'] = tokenize(p['name'], config)
        p['category'] = categorize(p['name'], cleaning_config['categories'])
    
    # Group by category and store
    by_category = defaultdict(lambda: defaultdict(list))
    for p in products:
        by_category[p['category']][p['store']].append(p)
    
    # Find matches
    matches = []
    min_threshold = config['token_similarity']['min_threshold']
    
    for cat, by_store in by_category.items():
        stores = list(by_store.keys())
        
        for i, store1 in enumerate(stores):
            for store2 in stores[i+1:]:
                for p1 in by_store[store1]:
                    for p2 in by_store[store2]:
                        score = token_similarity(p1['tokens'], p2['tokens'], config)
                        if score >= min_threshold:
                            matches.append({
                                'score': score,
                                'category': cat,
                                'p1': p1,
                                'p2': p2,
                                'common': p1['tokens'] & p2['tokens']
                            })
    
    # Deduplicate (keep highest score per pair)
    seen = set()
    unique_matches = []
    for m in sorted(matches, key=lambda x: -x['score']):
        key = tuple(sorted([m['p1']['id'], m['p2']['id']]))
        if key not in seen:
            seen.add(key)
            unique_matches.append(m)
    
    log.info(f"Found {len(unique_matches)} unique matches")
    
    # Save to DB
    cur.execute('DELETE FROM cross_store_matches')
    
    for m in unique_matches:
        p1, p2 = m['p1'], m['p2']
        kaufland_id = lidl_id = billa_id = None
        
        if p1['store'] == 'Kaufland': kaufland_id = p1['id']
        elif p1['store'] == 'Lidl': lidl_id = p1['id']
        elif p1['store'] == 'Billa': billa_id = p1['id']
        
        if p2['store'] == 'Kaufland': kaufland_id = p2['id']
        elif p2['store'] == 'Lidl': lidl_id = p2['id']
        elif p2['store'] == 'Billa': billa_id = p2['id']
        
        cur.execute('''
            INSERT INTO cross_store_matches (
                kaufland_product_id, lidl_product_id, billa_product_id,
                canonical_name, canonical_brand, match_type, confidence, store_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            kaufland_id, lidl_id, billa_id,
            ' '.join(m['common']),
            m['p1'].get('brand') or m['p2'].get('brand'),
            'token_similarity',
            round(m['score'], 2),
            2
        ))
    
    conn.commit()
    conn.close()
    
    log.info(f"Saved {len(unique_matches)} matches to database")
    return len(unique_matches)


def tokenize(name, config):
    """Tokenize product name for matching"""
    name = name.lower()
    
    # Remove ignore patterns
    for pattern in config['ignore_patterns']:
        name = name.replace(pattern.lower(), '')
    
    # Remove quantities
    name = re.sub(r'\d+\s*(г|гр|мл|л|кг|бр|x|х)\b', '', name)
    name = re.sub(r'[®™©\n]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    tokens = set(name.split())
    stopwords = set(config['stopwords'])
    
    return {t for t in tokens if len(t) > 1 and t not in stopwords}


def token_similarity(tokens1, tokens2, config):
    """Calculate token similarity score"""
    if not tokens1 or not tokens2:
        return 0
    
    common = tokens1 & tokens2
    min_common = config['token_similarity']['min_common_tokens']
    
    if len(common) < min_common:
        return 0
    
    # Jaccard similarity
    return len(common) / len(tokens1 | tokens2)


# =============================================================================
# STEP 4: EXPORT
# =============================================================================

def export_frontend():
    """Export DB to frontend JSON"""
    log.info("Exporting to frontend...")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Load products
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand,
            s.name as store,
            pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE pr.current_price IS NOT NULL AND pr.current_price > 0
    """)
    
    products = []
    for row in cur.fetchall():
        products.append({
            'id': row['id'],
            'name': row['name'],
            'brand': row['brand'],
            'store': row['store'],
            'price': round(row['price'], 2),
            'group_id': None
        })
    
    # Load matches and build groups
    cur.execute("SELECT * FROM cross_store_matches")
    matches = cur.fetchall()
    
    groups = {}
    product_to_group = {}
    
    for i, m in enumerate(matches):
        group_id = f"g{i+1}"
        
        stores = []
        for store, col in [('Kaufland', 'kaufland_product_id'), 
                          ('Lidl', 'lidl_product_id'), 
                          ('Billa', 'billa_product_id')]:
            if m[col]:
                stores.append(store)
                product_to_group[m[col]] = group_id
        
        groups[group_id] = {
            'canonical_name': m['canonical_name'],
            'canonical_brand': m['canonical_brand'],
            'stores': stores,
            'confidence': m['confidence']
        }
    
    # Assign group_ids to products
    for p in products:
        p['group_id'] = product_to_group.get(p['id'])
    
    # Build output
    output = {
        'meta': {
            'total_products': len(products),
            'cross_store_groups': len(groups),
            'updated_at': datetime.now().isoformat()
        },
        'products': products,
        'groups': groups,
        'off': {}
    }
    
    # Write
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    conn.close()
    
    log.info(f"Exported {len(products)} products, {len(groups)} groups to {OUTPUT_PATH}")
    return len(products), len(groups)


# =============================================================================
# MAIN
# =============================================================================

def run_full_pipeline(stores=None):
    """Run complete pipeline for all or specified stores"""
    stores = stores or ['lidl', 'kaufland', 'billa']
    
    log.info("="*60)
    log.info("PROMOBG PIPELINE - FULL RUN")
    log.info("="*60)
    
    # Step 1: Scrape (only if scraper exists)
    for store in stores:
        try:
            scrape_store(store)
        except ImportError:
            log.warning(f"No scraper for {store}, skipping scrape step")
    
    # Step 2: Clean & Import
    for store in stores:
        clean_and_import(store)
    
    # Step 3: Match
    run_matching()
    
    # Step 4: Export
    export_frontend()
    
    log.info("="*60)
    log.info("PIPELINE COMPLETE")
    log.info("="*60)


def main():
    parser = argparse.ArgumentParser(description='PromoBG Data Pipeline')
    parser.add_argument('--full', action='store_true', help='Run full pipeline')
    parser.add_argument('--scrape', type=str, help='Scrape specific store')
    parser.add_argument('--import', dest='import_store', type=str, help='Import specific store')
    parser.add_argument('--match', action='store_true', help='Run matching only')
    parser.add_argument('--export', action='store_true', help='Export to frontend only')
    
    args = parser.parse_args()
    
    if args.full:
        run_full_pipeline()
    elif args.scrape:
        scrape_store(args.scrape)
    elif args.import_store:
        clean_and_import(args.import_store)
    elif args.match:
        run_matching()
    elif args.export:
        export_frontend()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
