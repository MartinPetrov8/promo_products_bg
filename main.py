#!/usr/bin/env python3
"""
PromoBG - Production Scraping System
Usage:
    python main.py scrape --store all
    python main.py scrape --store kaufland
    python main.py clean
    python main.py match
    python main.py export
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

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

def cmd_scrape(store: str = 'all'):
    """Run scrapers and save to database"""
    
    if store == 'all':
        stores = list(SCRAPERS.keys())
    else:
        stores = [store]
    
    logger.info(f"Starting scrape: {', '.join(stores)}")
    
    all_products = []
    
    with PromoBGDatabase() as db:
        for store_name in stores:
            scraper_class = SCRAPERS.get(store_name)
            if not scraper_class:
                logger.error(f"Unknown store: {store_name}")
                continue
            
            scraper = scraper_class()
            
            # Health check
            if not scraper.health_check():
                logger.error(f"{store_name}: Health check failed")
                continue
            
            # Start scan run
            run_id = db.start_scan_run(scraper.store.value)
            logger.info(f"{store_name}: Starting (run_id={run_id})")
            
            try:
                # Scrape
                products = scraper.scrape()
                
                # Save to DB
                for p in products:
                    db.append_raw_scrape(run_id, p.to_dict())
                
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
                
            except Exception as e:
                logger.error(f"{store_name}: Failed - {e}")
                db.conn.execute(
                    "UPDATE scan_runs SET status='failed', error_log=? WHERE id=?",
                    (str(e), run_id)
                )
                db.conn.commit()
    
    # Also save to JSON for compatibility
    output_file = Path("output/raw_products.json")
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([p.to_dict() for p in all_products], f, ensure_ascii=False, indent=2)
    
    # Summary
    with_brand = sum(1 for p in all_products if p.brand)
    logger.info(f"Total: {len(all_products)} products, {with_brand} with brand ({with_brand*100/len(all_products):.1f}%)")
    logger.info(f"Saved to {output_file}")

def cmd_clean():
    """Run hybrid cleaning pipeline"""
    logger.info("Running cleaning pipeline...")
    import subprocess
    result = subprocess.run([sys.executable, 'scripts/clean_products_hybrid.py'], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)

def cmd_match():
    """Run cross-store matching"""
    logger.info("Running cross-store matcher...")
    import subprocess
    result = subprocess.run([sys.executable, 'scripts/cross_store_matcher.py'],
                          capture_output=True, text=True)
    print(result.stdout)

def cmd_export():
    """Export to frontend"""
    logger.info("Exporting to frontend...")
    import subprocess
    result = subprocess.run([sys.executable, 'scripts/export_frontend.py'],
                          capture_output=True, text=True)
    print(result.stdout)

def cmd_all():
    """Run full pipeline"""
    cmd_scrape('all')
    cmd_clean()
    cmd_match()
    cmd_export()

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'scrape':
        store = sys.argv[2] if len(sys.argv) > 2 else 'all'
        if store.startswith('--store='):
            store = store.split('=')[1]
        elif store == '--store' and len(sys.argv) > 3:
            store = sys.argv[3]
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
