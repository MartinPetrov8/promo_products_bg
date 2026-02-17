#!/usr/bin/env python3
"""
PromoBG Data Pipeline - Production Ready (FIXED)

Changes from original:
- export_frontend: Best-confidence-wins deduplication
- export_frontend: Recalculate stores from actual products
- export_frontend: Filter invalid groups (< 2 products or < 2 stores)
- Added clean_product_name function for display names
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


# Store-specific suffixes to strip
STORE_SUFFIXES = [
    r'\s*от свежата витрина\s*',
    r'\s*от нашата пекарна\s*',
    r'\s*от деликатесната витрина\s*',
    r'\s*За 1 кг\s*',
    r'\s*\d+\s*бр\.?\s*$',
    r'\s*\d+-\d+\*?\s*',
]


def clean_product_name(name):
    """Clean product name for display"""
    if not name:
        return ''
    cleaned = name.replace('\n', ' ')
    for pattern in STORE_SUFFIXES:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
    return ' '.join(cleaned.split())  # Normalize whitespace


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
    
    if store_name == 'lidl':
        from scrapers.lidl import LidlScraper
        scraper = LidlScraper()
    else:
        log.warning(f"No scraper for {store_name}")
        return None
    
    products = scraper.scrape(limit=limit)
    
    RAW_SCRAPES_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = RAW_SCRAPES_DIR / f"{store_name}_{date_str}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    log.info(f"Saved {len(products)} raw products to {output_path}")
    return output_path


# =============================================================================
# STEP 2: SYNC
# =============================================================================

def sync_store(store_name, raw_file=None):
    """Sync store using daily_sync module"""
    from daily_sync import DailySync
    
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
# STEP 3: MATCH (v2 - brand-aware, quantity-aware, price-validated)
# =============================================================================

def run_matching():
    """Run cross-store matching with brand, quantity, and price validation"""
    log.info("Running cross-store matching (v2)...")
    
    config = load_config("matching")
    match_config = config.get('token_similarity', {})
    rules = config.get('rules', {})
    min_threshold = match_config.get('min_threshold', 0.5)
    min_common = match_config.get('min_common_tokens', 2)
    brand_same_boost = rules.get('brand_same_boost', 0.15)
    brand_unknown_penalty = rules.get('brand_unknown_penalty', 0.85)
    qty_incompatible_penalty = rules.get('quantity_incompatible_penalty', 0.4)
    qty_compatible_boost = rules.get('quantity_compatible_boost', 0.05)
    price_warning_threshold = rules.get('price_ratio_warning_threshold', 3.0)
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand, p.quantity, p.quantity_unit,
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
    
    # Enrich: extract quantities from names if not in DB
    from quantity_extractor import extract_quantity_from_name
    
    qty_from_db = 0
    qty_from_name = 0
    for p in products:
        if p.get('quantity') and p['quantity'] > 0:
            qty_from_db += 1
        else:
            qty = extract_quantity_from_name(p['name'])
            if qty:
                p['quantity'] = qty['value']
                p['quantity_unit'] = qty['unit']
                qty_from_name += 1
    
    log.info(f"Quantities: {qty_from_db} from DB, {qty_from_name} from name parsing, "
             f"{len(products) - qty_from_db - qty_from_name} unknown")
    
    # Tokenize and categorize
    cleaning_config = load_config("cleaning")
    for p in products:
        p['tokens'] = tokenize(p['name'], config)
        p['category'] = categorize(p['name'], cleaning_config['categories'])
        p['brand_normalized'] = normalize_brand(p.get('brand'))
    
    # Group by category then store
    by_category = defaultdict(lambda: defaultdict(list))
    for p in products:
        by_category[p['category']][p['store']].append(p)
    
    matches = []
    stats = {'total_comparisons': 0, 'brand_rejected': 0, 'qty_penalized': 0, 
             'price_flagged': 0, 'below_threshold': 0, 'accepted': 0}
    
    for cat, by_store in by_category.items():
        stores = list(by_store.keys())
        
        for i, store1 in enumerate(stores):
            for store2 in stores[i+1:]:
                for p1 in by_store[store1]:
                    for p2 in by_store[store2]:
                        stats['total_comparisons'] += 1
                        
                        # Step 1: Token similarity (base score)
                        base_score = token_similarity(p1['tokens'], p2['tokens'], config)
                        if base_score < min_threshold * 0.8:  # Allow slightly lower for brand boost
                            stats['below_threshold'] += 1
                            continue
                        
                        # Step 2: Brand check
                        brand_result = check_brand_compatibility(p1, p2)
                        if brand_result == 'reject':
                            stats['brand_rejected'] += 1
                            continue
                        
                        # Apply brand modifier
                        score = base_score
                        if brand_result == 'match':
                            score = min(1.0, score + brand_same_boost)  # Same brand boost
                        elif brand_result == 'mismatch_one_unknown':
                            score = score * brand_unknown_penalty  # Slight penalty
                        # 'both_unknown' = no change
                        
                        # Step 3: Quantity check
                        qty_result = check_quantity_compatibility(p1, p2)
                        if qty_result == 'same_size':
                            score = min(1.0, score + qty_compatible_boost)  # Boost for same size
                        elif qty_result == 'different_size':
                            pass  # Neutral — different packaging is fine, we'll show unit prices
                        elif qty_result == 'incompatible':
                            if brand_result == 'match':
                                score = score * 0.7  # Mild penalty: same brand, wildly different size
                            else:
                                score = score * qty_incompatible_penalty  # Heavy penalty: different brand + wildly different size
                            stats['qty_penalized'] += 1
                        # 'unknown' = no change
                        
                        # Step 4: Price ratio flag (informational, doesn't reject)
                        price_ratio = max(p1['price'], p2['price']) / min(p1['price'], p2['price']) if min(p1['price'], p2['price']) > 0 else 999
                        price_flag = price_ratio > price_warning_threshold
                        if price_flag:
                            stats['price_flagged'] += 1
                        
                        # Final threshold check
                        if score < min_threshold:
                            stats['below_threshold'] += 1
                            continue
                        
                        stats['accepted'] += 1
                        matches.append({
                            'score': round(score, 3),
                            'base_score': round(base_score, 3),
                            'category': cat,
                            'p1': p1,
                            'p2': p2,
                            'common': p1['tokens'] & p2['tokens'],
                            'brand_result': brand_result,
                            'qty_result': qty_result,
                            'price_ratio': round(price_ratio, 2),
                            'price_flag': price_flag
                        })
    
    # Deduplicate: keep highest score per product pair
    seen = set()
    unique_matches = []
    for m in sorted(matches, key=lambda x: -x['score']):
        key = tuple(sorted([m['p1']['id'], m['p2']['id']]))
        if key not in seen:
            seen.add(key)
            unique_matches.append(m)
    
    log.info(f"Matching stats: {stats}")
    log.info(f"Found {len(unique_matches)} unique matches (was {len(matches)} before dedup)")
    
    # Save to DB
    cur.execute('DELETE FROM cross_store_matches')
    
    for m in unique_matches:
        p1, p2 = m['p1'], m['p2']
        kaufland_id = lidl_id = billa_id = None
        
        for p in [p1, p2]:
            if p['store'] == 'Kaufland': kaufland_id = p['id']
            elif p['store'] == 'Lidl': lidl_id = p['id']
            elif p['store'] == 'Billa': billa_id = p['id']
        
        cur.execute('''
            INSERT INTO cross_store_matches (
                kaufland_product_id, lidl_product_id, billa_product_id,
                canonical_name, canonical_brand, match_type, confidence, store_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            kaufland_id, lidl_id, billa_id,
            ' '.join(m['common']),
            m['p1'].get('brand') or m['p2'].get('brand'),
            f"token_v2|brand:{m['brand_result']}|qty:{m['qty_result']}|pr:{m['price_ratio']}",
            m['score'],
            2
        ))
    
    conn.commit()
    conn.close()
    
    log.info(f"Saved {len(unique_matches)} matches to database")
    return len(unique_matches)


def normalize_brand(brand):
    """Normalize brand name for comparison"""
    IGNORE_BRANDS = {'no_brand', 'unknown', 'n/a', 'generic', 'none', ''}
    if not brand or brand.strip().lower() in IGNORE_BRANDS:
        return None
    brand = brand.strip().lower()
    brand = re.sub(r'[®™©]', '', brand)
    brand = brand.strip()
    # Handle common variants
    brand = brand.replace('parkside®', 'parkside')
    brand = brand.replace('extra zytnia', 'extra')
    return brand if brand else None


def check_brand_compatibility(p1, p2):
    """
    Check if two products have compatible brands.
    
    Returns:
        'match' - Same brand (boost score)
        'reject' - Different known brands (skip match)
        'mismatch_one_unknown' - One has brand, other doesn't (slight penalty)
        'both_unknown' - Neither has brand (neutral)
    """
    b1 = p1.get('brand_normalized')
    b2 = p2.get('brand_normalized')
    
    if b1 and b2:
        if b1 == b2:
            return 'match'
        # Check if one contains the other (e.g., "extra" in "extra zytnia")
        # Only allow substring matching for brands >= 4 chars to avoid false positives
        if (len(b1) >= 4 and b1 in b2) or (len(b2) >= 4 and b2 in b1):
            return 'match'
        return 'reject'
    
    if b1 or b2:
        return 'mismatch_one_unknown'
    
    return 'both_unknown'


def check_quantity_compatibility(p1, p2):
    """
    Check if two products have compatible quantities.
    
    Philosophy: Different sizes of the same product ARE valid comparisons.
    Users want to compare unit prices across stores. A 500ml milk at Store A
    vs 1L milk at Store B is useful — we show price/L for both.
    
    We only penalize when quantities suggest fundamentally different products
    (e.g., a 10g spice sachet vs 500g jar — likely different products entirely).
    
    Returns:
        'same_size' - Same or near-identical quantity (<1.3x ratio) → boost
        'different_size' - Different packaging but likely same product (1.3-5x) → neutral, flag for unit price display
        'incompatible' - Wildly different (>5x ratio) → likely different products, penalize
        'unknown' - Can't determine (one or both missing qty)
    """
    q1 = p1.get('quantity')
    q2 = p2.get('quantity')
    u1 = p1.get('quantity_unit')
    u2 = p2.get('quantity_unit')
    
    if not q1 or not q2 or q1 <= 0 or q2 <= 0:
        return 'unknown'
    
    # Only compare same unit types (weight vs weight, volume vs volume)
    if u1 != u2:
        return 'unknown'
    
    ratio = max(q1, q2) / min(q1, q2)
    
    if ratio <= 1.3:
        return 'same_size'       # Essentially same product
    elif ratio <= 5.0:
        return 'different_size'  # Different packaging, same product — show unit price
    else:
        return 'incompatible'    # 10g sachet vs 1kg bag — probably different products


def tokenize(name, config):
    """Tokenize product name for matching — strips store-specific noise"""
    name = name.lower()
    
    # Config-driven ignore patterns
    for pattern in config.get('ignore_patterns', []):
        name = name.replace(pattern.lower(), '')
    
    # Store-specific noise removal (Billa's "blue star" labels, etc.)
    billa_noise = [
        r'продукт,?\s*маркиран\s*със\s*синя\s*звезда',
        r'произход\s*[-–]\s*българия',
        r'само\s*с\s*billa\s*app\s*[-–]?\s*',
        r'супер\s*цена\s*[-–]?\s*',
        r'\d+[.,]?\d*\s*(?:€|лв\.?)/\s*\d+[.,]?\d*\s*(?:€|лв\.?)?\s*(?:изпиране)?',
    ]
    for pattern in billa_noise:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
    
    # Strip quantities (they're handled separately now)
    name = re.sub(r'\d+(?:[.,]\d+)?\s*[xх×]\s*\d+(?:[.,]\d+)?\s*(?:г|гр|мл|л|кг|kg|g|ml|l)\b', '', name)
    name = re.sub(r'\d+(?:[.,]\d+)?\s*(?:г|гр|мл|л|кг|бр|kg|g|ml|l|cl|см)\b', '', name)
    name = re.sub(r'[®™©\n]', ' ', name)
    
    # Strip percentage patterns (alcohol %, discount %)
    name = re.sub(r'\d+[.,]?\d*\s*%\s*(?:vol)?', '', name)
    
    # Strip size ranges (S - XXL, M-XL)
    name = re.sub(r'\b[SMLX]{1,3}\s*[-–]\s*[SMLX]{1,4}\b', '', name)
    
    # Strip model numbers that are just letters+digits (BCH400, PSG85)
    name = re.sub(r'\b[a-z]{1,4}\d{2,}[a-z]?\d*\b', '', name)
    
    name = re.sub(r'\s+', ' ', name).strip()
    
    tokens = set(name.split())
    stopwords = set(config.get('stopwords', []))
    
    return {t for t in tokens if len(t) > 1 and t not in stopwords}


def token_similarity(tokens1, tokens2, config):
    """Calculate Jaccard similarity between token sets"""
    if not tokens1 or not tokens2:
        return 0
    
    common = tokens1 & tokens2
    min_common = config.get('token_similarity', {}).get('min_common_tokens', 2)
    
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
# STEP 4: EXPORT (FIXED)
# =============================================================================

def export_frontend():
    """Export DB to frontend JSON - FIXED VERSION"""
    log.info("Exporting to frontend...")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Load active products
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand, p.quantity, p.quantity_unit,
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
    
    # Enrich quantities from name if not in DB
    from quantity_extractor import extract_quantity_from_name
    
    products = []
    exported_ids = set()
    for row in cur.fetchall():
        qty = row['quantity']
        qty_unit = row['quantity_unit']
        
        # Try to extract from name if missing
        if not qty or qty <= 0:
            parsed = extract_quantity_from_name(row['name'])
            if parsed:
                qty = parsed['value']
                qty_unit = parsed['unit']
        
        product = {
            'id': row['id'],
            'name': row['name'],
            'brand': row['brand'],
            'store': row['store'],
            'price': round(row['price'], 2),
            'image_url': row['image_url'],
            'group_id': None
        }
        
        # Add quantity if available
        if qty and qty > 0:
            product['quantity'] = qty
            product['quantity_unit'] = qty_unit
            # Calculate unit price
            if qty_unit == 'g' and qty >= 100:
                product['price_per_kg'] = round(row['price'] / qty * 1000, 2)
            elif qty_unit == 'ml' and qty >= 100:
                product['price_per_l'] = round(row['price'] / qty * 1000, 2)
        
        products.append(product)
        exported_ids.add(row['id'])
    
    log.info(f"Loaded {len(products)} exportable products")
    
    # Load matches
    cur.execute("SELECT * FROM cross_store_matches ORDER BY confidence DESC")
    matches = cur.fetchall()
    
    # FIX 1: Best-confidence-wins deduplication
    # Track which products are already assigned
    product_to_group = {}
    product_to_confidence = {}
    groups = {}
    
    for i, m in enumerate(matches):
        group_id = f"g{i+1}"
        
        # Check which products from this match are available and not yet assigned
        available_pids = []
        for store, col in [('Kaufland', 'kaufland_product_id'), 
                           ('Lidl', 'lidl_product_id'), 
                           ('Billa', 'billa_product_id')]:
            pid = m[col]
            if pid and pid in exported_ids:
                # Only assign if not yet assigned OR this match has higher confidence
                current_conf = product_to_confidence.get(pid, -1)
                if m['confidence'] > current_conf:
                    available_pids.append((pid, store, m['confidence']))
        
        # Only create group if we have 2+ products
        if len(available_pids) >= 2:
            # Assign all available products to this group
            for pid, store, conf in available_pids:
                # Unassign from previous group if needed
                old_group = product_to_group.get(pid)
                if old_group and old_group in groups:
                    groups[old_group]['_pids'].discard(pid)
                
                product_to_group[pid] = group_id
                product_to_confidence[pid] = conf
            
            groups[group_id] = {
                'canonical_name': m['canonical_name'],
                'canonical_brand': m['canonical_brand'],
                'confidence': m['confidence'],
                '_pids': set(pid for pid, _, _ in available_pids)  # Track for later
            }
    
    # Assign group_ids to products
    for p in products:
        p['group_id'] = product_to_group.get(p['id'])
    
    # FIX 2: Recalculate stores from actual assigned products
    for gid in list(groups.keys()):
        group_products = [p for p in products if p['group_id'] == gid]
        actual_stores = list(set(p['store'] for p in group_products))
        
        if len(group_products) < 2 or len(actual_stores) < 2:
            # Invalid group - remove it
            del groups[gid]
            for p in group_products:
                p['group_id'] = None
        else:
            groups[gid]['stores'] = actual_stores
            groups[gid]['product_count'] = len(group_products)
            del groups[gid]['_pids']  # Remove internal tracking
            
            # Calculate savings and flag suspicious price ratios
            prices = [p['price'] for p in group_products if p.get('price')]
            if len(prices) >= 2:
                groups[gid]['savings'] = round(max(prices) - min(prices), 2)
                price_ratio = max(prices) / min(prices)
                if price_ratio > 3.0:
                    groups[gid]['price_warning'] = True
                    groups[gid]['price_ratio'] = round(price_ratio, 1)
    
    # Count valid groups
    valid_groups = len(groups)
    log.info(f"Created {valid_groups} valid cross-store groups")
    
    # Build output
    output = {
        'meta': {
            'total_products': len(products),
            'cross_store_groups': valid_groups,
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
    
    log.info(f"Exported {len(products)} products, {valid_groups} groups to {OUTPUT_PATH}")
    return len(products), valid_groups


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
    
    cur.execute("SELECT COUNT(*) FROM cross_store_matches")
    matches = cur.fetchone()[0]
    print(f"\nCROSS-STORE MATCHES IN DB: {matches}")
    
    # Check exported data
    try:
        with open(OUTPUT_PATH) as f:
            exported = json.load(f)
        print(f"EXPORTED PRODUCTS: {len(exported['products'])}")
        print(f"VALID GROUPS: {len(exported['groups'])}")
    except:
        pass
    
    cur.execute("""
        SELECT COUNT(*) FROM price_history 
        WHERE changed_at > datetime('now', '-1 day')
    """)
    recent_changes = cur.fetchone()[0]
    print(f"PRICE CHANGES (24h): {recent_changes}")
    
    print("="*50 + "\n")
    conn.close()


# =============================================================================
# MAIN
# =============================================================================

def run_full_pipeline(stores=None):
    """Run complete pipeline"""
    stores = stores or ['lidl']
    
    log.info("="*60)
    log.info("PROMOBG PIPELINE - FULL RUN")
    log.info("="*60)
    
    for store in stores:
        raw_file = scrape_store(store)
        if raw_file:
            sync_store(store, raw_file)
    
    run_matching()
    export_frontend()
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
    parser.add_argument('--full', action='store_true', help='Full pipeline')
    parser.add_argument('--daily', action='store_true', help='Daily run')
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
