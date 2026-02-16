#!/usr/bin/env python3
"""
PromoBG Data Pipeline - Production Ready

Usage:
  python pipeline.py --full              # Full pipeline (scrape all → sync → match → export)
  python pipeline.py --daily             # Daily run (sync + match + export, no scrape)
  python pipeline.py --scrape lidl       # Scrape single store
  python pipeline.py --sync lidl         # Sync store from latest raw file
  python pipeline.py --match             # Run matching only
  python pipeline.py --export            # Export to frontend only
  python pipeline.py --report            # Generate status report

Pipeline phases:
  1. SCRAPE  → raw_scrapes/{store}_{date}.json
  2. SYNC    → DB (products, prices, price_history)
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
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

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

def scrape_store(store_name, limit=None):
    """Run scraper for a specific store"""
    log.info(f"Scraping {store_name}...")
    
    # Import store-specific scraper
    if store_name == 'lidl':
        from scrapers.lidl import LidlScraper
        scraper = LidlScraper()
    else:
        log.warning(f"No scraper for {store_name}")
        return None
    
    # Scrape
    products = scraper.scrape(limit=limit)
    
    # Save raw
    RAW_SCRAPES_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = RAW_SCRAPES_DIR / f"{store_name}_{date_str}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    log.info(f"Saved {len(products)} raw products to {output_path}")
    return output_path


# =============================================================================
# STEP 2: SYNC (replaces old clean_and_import)
# =============================================================================

def sync_store(store_name, raw_file=None):
    """Sync store using daily_sync module"""
    from daily_sync import DailySync
    
    # Find latest raw file if not specified
    if raw_file is None:
        files = sorted(RAW_SCRAPES_DIR.glob(f"{store_name}_*.json"), reverse=True)
        if not files:
            log.warning(f"No raw files found for {store_name}")
            return None
        raw_file = files[0]
    
    log.info(f"Syncing {store_name} from {raw_file}...")
    
    with open(raw_file) as f:
        products = json.load(f)
    
    sync = DailySync(store_name)
    stats = sync.sync(products)
    sync.detect_delisted(days_threshold=3)
    
    report = sync.generate_report()
    print(report)
    
    sync.close()
    return stats


# =============================================================================
# STEP 3: MATCH
# =============================================================================

def run_matching():
    """Run cross-store matching"""
    log.info("Running cross-store matching...")
    
    config = load_config("matching")
    conn = get_db()
    cur = conn.cursor()
    
    # Load active products with prices
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand,
            s.name as store,
            pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE pr.current_price IS NOT NULL 
        AND pr.current_price > 0
        AND (sp.status = 'active' OR sp.status IS NULL)
    """)
    
    products = [dict(row) for row in cur.fetchall()]
    log.info(f"Loaded {len(products)} active products with prices")
    
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
    
    # Deduplicate
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
    
    for pattern in config['ignore_patterns']:
        name = name.replace(pattern.lower(), '')
    
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
    
    return len(common) / len(tokens1 | tokens2)


def categorize(name, categories):
    """Categorize product by name keywords"""
    name_lower = name.lower()
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in name_lower:
                return cat
    return 'other'


# =============================================================================
# STEP 4: EXPORT
# =============================================================================

def export_frontend():
    """Export DB to frontend JSON"""
    log.info("Exporting to frontend...")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Load active products
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand,
            s.name as store,
            pr.current_price as price,
            sp.image_url
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE pr.current_price IS NOT NULL 
        AND pr.current_price > 0
        AND (sp.status = 'active' OR sp.status IS NULL)
    """)
    
    products = []
    for row in cur.fetchall():
        products.append({
            'id': row['id'],
            'name': row['name'],
            'brand': row['brand'],
            'store': row['store'],
            'price': round(row['price'], 2),
            'image_url': row['image_url'],
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
    
    # Assign group_ids
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
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    conn.close()
    
    log.info(f"Exported {len(products)} products, {len(groups)} groups")
    return len(products), len(groups)


# =============================================================================
# REPORT
# =============================================================================

def generate_report():
    """Generate current status report"""
    conn = get_db()
    cur = conn.cursor()
    
    print("\n" + "="*50)
    print("PROMOBG STATUS REPORT")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # Products by store
    cur.execute("""
        SELECT s.name, 
               COUNT(*) as total,
               SUM(CASE WHEN sp.status = 'active' OR sp.status IS NULL THEN 1 ELSE 0 END) as active
        FROM store_products sp
        JOIN stores s ON sp.store_id = s.id
        GROUP BY s.name
    """)
    
    print("\nPRODUCTS BY STORE:")
    for row in cur.fetchall():
        print(f"  {row['name']}: {row['active']} active / {row['total']} total")
    
    # Matches
    cur.execute("SELECT COUNT(*) FROM cross_store_matches")
    matches = cur.fetchone()[0]
    print(f"\nCROSS-STORE MATCHES: {matches}")
    
    # Recent price changes
    cur.execute("""
        SELECT COUNT(*) FROM price_history 
        WHERE changed_at > datetime('now', '-1 day')
    """)
    recent_changes = cur.fetchone()[0]
    print(f"PRICE CHANGES (24h): {recent_changes}")
    
    # Recent scan runs
    cur.execute("""
        SELECT s.name, sr.completed_at, sr.products_scraped, sr.new_products, sr.price_changes
        FROM scan_runs sr
        JOIN stores s ON sr.store_id = s.id
        ORDER BY sr.completed_at DESC
        LIMIT 5
    """)
    
    runs = cur.fetchall()
    if runs:
        print("\nRECENT SCAN RUNS:")
        for r in runs:
            print(f"  {r['name']} @ {r['completed_at']}: {r['products_scraped']} products, +{r['new_products']} new, {r['price_changes']} price changes")
    
    print("="*50 + "\n")
    conn.close()


# =============================================================================
# MAIN
# =============================================================================

def run_full_pipeline(stores=None):
    """Run complete pipeline"""
    stores = stores or ['lidl']  # Only Lidl has scraper for now
    
    log.info("="*60)
    log.info("PROMOBG PIPELINE - FULL RUN")
    log.info("="*60)
    
    for store in stores:
        # Scrape
        raw_file = scrape_store(store)
        if raw_file:
            # Sync
            sync_store(store, raw_file)
    
    # Match
    run_matching()
    
    # Export
    export_frontend()
    
    # Report
    generate_report()
    
    log.info("="*60)
    log.info("PIPELINE COMPLETE")
    log.info("="*60)


def run_daily():
    """Daily run without scraping"""
    log.info("="*60)
    log.info("PROMOBG PIPELINE - DAILY RUN (no scrape)")
    log.info("="*60)
    
    run_matching()
    export_frontend()
    generate_report()


def main():
    parser = argparse.ArgumentParser(description='PromoBG Data Pipeline')
    parser.add_argument('--full', action='store_true', help='Full pipeline (scrape + sync + match + export)')
    parser.add_argument('--daily', action='store_true', help='Daily run (match + export only)')
    parser.add_argument('--scrape', type=str, help='Scrape specific store')
    parser.add_argument('--sync', type=str, help='Sync specific store')
    parser.add_argument('--match', action='store_true', help='Run matching only')
    parser.add_argument('--export', action='store_true', help='Export to frontend only')
    parser.add_argument('--report', action='store_true', help='Generate status report')
    parser.add_argument('--limit', type=int, help='Limit products to scrape')
    
    args = parser.parse_args()
    
    if args.full:
        run_full_pipeline()
    elif args.daily:
        run_daily()
    elif args.scrape:
        scrape_store(args.scrape, limit=args.limit)
    elif args.sync:
        sync_store(args.sync)
    elif args.match:
        run_matching()
    elif args.export:
        export_frontend()
    elif args.report:
        generate_report()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
