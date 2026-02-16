#!/usr/bin/env python3
"""
PromoBG - Production Scraping System

Usage:
    python3 main.py scrape --store all
    python3 main.py scrape --store kaufland
    python3 main.py clean
    python3 main.py match
    python3 main.py export
    python3 main.py all
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Import scrapers
from scrapers.base import Store, RawProduct
from scrapers.kaufland.scraper import KauflandScraper
from scrapers.lidl.scraper import LidlScraper
from scrapers.billa.scraper import BillaScraper

# Import database
from scripts.db_pipeline import PromoBGDatabase

# Scraper registry
SCRAPERS = {
    'kaufland': KauflandScraper,
    'lidl': LidlScraper,
    'billa': BillaScraper,
}

# Minimum products threshold (fail-safe)
MIN_PRODUCTS_THRESHOLD = {
    'kaufland': 100,
    'lidl': 50,
    'billa': 50,
}

def validate_scrape(store: str, products: List[RawProduct]) -> bool:
    """Validate scrape results before committing."""
    min_count = MIN_PRODUCTS_THRESHOLD.get(store.lower(), 10)
    
    if len(products) < min_count:
        logger.error(f"{store}: Only {len(products)} products (minimum: {min_count})")
        return False
    
    # Check for empty prices
    with_price = sum(1 for p in products if p.price_bgn)
    if with_price < len(products) * 0.5:
        logger.warning(f"{store}: Only {with_price}/{len(products)} have prices")
    
    return True

def cmd_scrape(store: str = 'all'):
    """Run scrapers and save to database."""
    
    if store == 'all':
        stores = list(SCRAPERS.keys())
    else:
        stores = [store]
    
    logger.info(f"Starting scrape: {', '.join(stores)}")
    
    all_products = []
    results = []
    
    with PromoBGDatabase() as db:
        for store_name in stores:
            scraper_class = SCRAPERS.get(store_name)
            if not scraper_class:
                logger.error(f"Unknown store: {store_name}")
                results.append({'store': store_name, 'success': False, 'error': 'Unknown store'})
                continue
            
            scraper = scraper_class()
            
            # Health check
            if not scraper.health_check():
                logger.error(f"{store_name}: Health check failed")
                results.append({'store': store_name, 'success': False, 'error': 'Health check failed'})
                continue
            
            # Start scan run
            run_id = db.start_scan_run(scraper.store.value)
            logger.info(f"{store_name}: Starting (run_id={run_id})")
            
            try:
                # Scrape
                products = scraper.scrape()
                
                # Validate
                if not validate_scrape(store_name, products):
                    db.fail_scan_run(run_id, f"Validation failed: {len(products)} products")
                    results.append({'store': store_name, 'success': False, 'error': 'Validation failed'})
                    continue
                
                # Batch insert with transaction safety
                product_dicts = [p.to_dict() for p in products]
                db.batch_insert_raw_scrapes(run_id, product_dicts)
                
                # Complete run
                stats = {
                    'products_scraped': len(products),
                    'new_products': len(products),
                    'price_changes': 0,
                    'errors': 0,
                }
                db.complete_scan_run(run_id, stats)
                
                all_products.extend(products)
                logger.info(f"{store_name}: {len(products)} products ✓")
                results.append({'store': store_name, 'success': True, 'products': len(products)})
                
            except Exception as e:
                logger.error(f"{store_name}: Failed - {e}")
                db.fail_scan_run(run_id, str(e))
                results.append({'store': store_name, 'success': False, 'error': str(e)})
    
    # Save to JSON for compatibility
    if all_products:
        output_file = Path("output/raw_products.json")
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in all_products], f, ensure_ascii=False, indent=2)
        
        # Summary
        with_brand = sum(1 for p in all_products if p.brand)
        logger.info(f"Total: {len(all_products)} products, {with_brand} with brand ({with_brand*100/len(all_products):.1f}%)")
        logger.info(f"Saved to {output_file}")
    
    return results

def cmd_clean():
    """Run hybrid cleaning pipeline."""
    logger.info("Running cleaning pipeline...")
    import subprocess
    result = subprocess.run([sys.executable, 'scripts/clean_products_hybrid.py'], 
                          capture_output=True, text=True, timeout=600)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        return False
    return True

def cmd_match():
    """Run cross-store matching."""
    logger.info("Running cross-store matcher...")
    import subprocess
    result = subprocess.run([sys.executable, 'scripts/cross_store_matcher.py'],
                          capture_output=True, text=True, timeout=120)
    print(result.stdout)
    return result.returncode == 0

def cmd_export():
    """Export to frontend."""
    logger.info("Exporting to frontend...")
    import subprocess
    result = subprocess.run([sys.executable, 'scripts/export_frontend.py'],
                          capture_output=True, text=True, timeout=120)
    print(result.stdout)
    return result.returncode == 0

def cmd_all():
    """Run full pipeline."""
    results = cmd_scrape('all')
    
    # Only continue if at least one scrape succeeded
    if not any(r.get('success') for r in results):
        logger.error("All scrapes failed, aborting pipeline")
        return False
    
    cmd_clean()
    cmd_match()
    cmd_export()
    return True

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'scrape':
        store = 'all'
        for arg in sys.argv[2:]:
            if arg.startswith('--store='):
                store = arg.split('=')[1]
            elif arg == '--store' and len(sys.argv) > sys.argv.index(arg) + 1:
                store = sys.argv[sys.argv.index(arg) + 1]
            elif not arg.startswith('-'):
                store = arg
        cmd_scrape(store)
    elif cmd == 'clean':
        cmd_clean()
    elif cmd == 'match':
        cmd_match()
    elif cmd == 'export':
        cmd_export()
    elif cmd == 'all':
        cmd_all()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
