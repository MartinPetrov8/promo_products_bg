#!/usr/bin/env python3
"""
Daily Sync - Handle new products, price changes, and delisted products

Usage:
    python daily_sync.py --store lidl --file raw_scrapes/lidl_20260216.json
    python daily_sync.py --store lidl --scrape  # Scrape first, then sync
"""

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "promobg.db"
CONFIG_PATH = REPO_ROOT / "config" / "cleaning.json"
BRAND_CACHE_PATH = REPO_ROOT / "data" / "brand_cache.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

# Load config
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

BGN_TO_EUR = CONFIG['currency']['bgn_to_eur']
PRICE_SPIKE_THRESHOLD = 2.0  # Flag if price changes by more than 100%


class DailySync:
    """Handle daily sync of scraped products to database"""
    
    def __init__(self, store_name):
        self.store_name = store_name.title()
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        
        # Get store ID
        self.cur.execute("SELECT id FROM stores WHERE name = ?", (self.store_name,))
        row = self.cur.fetchone()
        if not row:
            raise ValueError(f"Store not found: {self.store_name}")
        self.store_id = row['id']
        
        # Stats
        self.stats = {
            'processed': 0,
            'new_products': 0,
            'price_increases': 0,
            'price_decreases': 0,
            'unchanged': 0,
            'errors': 0,
            'price_spikes': [],
        }
        
        # Track what we've seen this run
        self.seen_external_ids = set()
        
        # Load brand cache for OCR-extracted brands
        self.brand_cache = {}
        if BRAND_CACHE_PATH.exists():
            try:
                with open(BRAND_CACHE_PATH) as f:
                    self.brand_cache = json.load(f)
                log.info(f"Loaded brand cache: {len(self.brand_cache)} entries")
            except Exception as e:
                log.warning(f"Failed to load brand cache: {e}")
    
    def sync(self, products):
        """Sync a list of scraped products"""
        log.info(f"Syncing {len(products)} products for {self.store_name}...")
        
        # Create scan run record
        self.cur.execute("""
            INSERT INTO scan_runs (store_id, urls_found) VALUES (?, ?)
        """, (self.store_id, len(products)))
        self.scan_run_id = self.cur.lastrowid
        
        # Build lookup of existing products by external_id
        self.cur.execute("""
            SELECT sp.id, sp.external_id, sp.product_id, p.name, pr.current_price
            FROM store_products sp
            JOIN products p ON sp.product_id = p.id
            LEFT JOIN prices pr ON pr.store_product_id = sp.id
            WHERE sp.store_id = ? AND sp.external_id IS NOT NULL
        """, (self.store_id,))
        
        self.existing = {}
        for row in self.cur.fetchall():
            self.existing[row['external_id']] = {
                'store_product_id': row['id'],
                'product_id': row['product_id'],
                'name': row['name'],
                'current_price': row['current_price']
            }
        
        log.info(f"Found {len(self.existing)} existing products with external_id")
        
        # Process each product
        for prod in products:
            try:
                self._process_product(prod)
            except Exception as e:
                log.error(f"Error processing product: {e}")
                self.stats['errors'] += 1
        
        # Update scan run
        self.cur.execute("""
            UPDATE scan_runs SET
                completed_at = CURRENT_TIMESTAMP,
                status = 'completed',
                products_scraped = ?,
                new_products = ?,
                price_changes = ?,
                errors = ?
            WHERE id = ?
        """, (
            self.stats['processed'],
            self.stats['new_products'],
            self.stats['price_increases'] + self.stats['price_decreases'],
            self.stats['errors'],
            self.scan_run_id
        ))
        
        self.conn.commit()
        return self.stats
    
    def _process_product(self, prod):
        """Process a single product - detect new/changed/same"""
        self.stats['processed'] += 1
        
        external_id = prod.get('sku') or prod.get('external_id')
        name = prod.get('name', '').strip()
        brand = prod.get('brand')
        
        # Check brand cache if no brand from scraper (OCR-extracted brands)
        if not brand and external_id and external_id in self.brand_cache:
            cached = self.brand_cache[external_id]
            if cached.get('brand'):
                brand = cached['brand']
                log.debug(f"Brand from OCR cache: {brand}")
        price = prod.get('price')
        currency = prod.get('currency', 'EUR')
        product_url = prod.get('product_url')
        image_url = prod.get('image_url')
        
        # Skip if no name or price
        if not name or price is None:
            return
        
        # Convert currency
        if currency == 'BGN':
            price = round(price / BGN_TO_EUR, 2)
        
        # Skip invalid prices
        if price <= 0 or price > 10000:
            return
        
        # Track this external_id
        if external_id:
            self.seen_external_ids.add(external_id)
        
        # Check if exists
        existing = self.existing.get(external_id) if external_id else None
        
        if existing:
            # EXISTING PRODUCT
            store_product_id = existing['store_product_id']
            old_price = existing['current_price']
            
            # Update last_seen_at
            self.cur.execute("""
                UPDATE store_products SET last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (store_product_id,))
            
            if old_price and abs(price - old_price) > 0.01:
                # PRICE CHANGED
                change_pct = ((price - old_price) / old_price) * 100
                
                # Check for spike
                if abs(change_pct) > (PRICE_SPIKE_THRESHOLD - 1) * 100:
                    self.stats['price_spikes'].append({
                        'name': name,
                        'old': old_price,
                        'new': price,
                        'change_pct': change_pct
                    })
                    log.warning(f"⚠️ Price spike: {name} €{old_price} → €{price} ({change_pct:+.1f}%)")
                
                # Log price history
                self.cur.execute("""
                    INSERT INTO price_history (store_product_id, old_price, new_price, change_pct)
                    VALUES (?, ?, ?, ?)
                """, (store_product_id, old_price, price, round(change_pct, 2)))
                
                # Update current price
                self.cur.execute("""
                    UPDATE prices SET current_price = ? WHERE store_product_id = ?
                """, (price, store_product_id))
                
                if price > old_price:
                    self.stats['price_increases'] += 1
                    log.debug(f"📈 Price up: {name} €{old_price} → €{price}")
                else:
                    self.stats['price_decreases'] += 1
                    log.debug(f"📉 Price down: {name} €{old_price} → €{price}")
            else:
                self.stats['unchanged'] += 1
        else:
            # NEW PRODUCT
            self._insert_new_product(name, brand, price, external_id, product_url, image_url)
            self.stats['new_products'] += 1
            log.debug(f"🆕 New: {name} @ €{price}")
    
    def _insert_new_product(self, name, brand, price, external_id, product_url, image_url):
        """Insert a new product"""
        # Insert into products
        self.cur.execute("""
            INSERT INTO products (name, brand) VALUES (?, ?)
        """, (name, brand))
        product_id = self.cur.lastrowid
        
        # Insert into store_products
        self.cur.execute("""
            INSERT INTO store_products (store_id, product_id, external_id, status, last_seen_at, product_url, image_url)
            VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP, ?, ?)
        """, (self.store_id, product_id, external_id, product_url, image_url))
        store_product_id = self.cur.lastrowid
        
        # Insert price
        self.cur.execute("""
            INSERT INTO prices (store_product_id, current_price) VALUES (?, ?)
        """, (store_product_id, price))
        
        # Update existing lookup
        if external_id:
            self.existing[external_id] = {
                'store_product_id': store_product_id,
                'product_id': product_id,
                'name': name,
                'current_price': price
            }
    
    def detect_delisted(self, days_threshold=3):
        """Mark products not seen recently as inactive"""
        threshold = datetime.now() - timedelta(days=days_threshold)
        
        self.cur.execute("""
            UPDATE store_products 
            SET status = 'inactive'
            WHERE store_id = ? 
            AND status = 'active'
            AND last_seen_at < ?
        """, (self.store_id, threshold.isoformat()))
        
        delisted_count = self.cur.rowcount
        self.conn.commit()
        
        if delisted_count > 0:
            log.info(f"Marked {delisted_count} products as inactive (not seen in {days_threshold}+ days)")
        
        return delisted_count
    
    def generate_report(self):
        """Generate daily sync report"""
        report = f"""
========================================
DAILY SYNC REPORT - {self.store_name}
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
========================================

SUMMARY:
  Products processed: {self.stats['processed']}
  New products:       +{self.stats['new_products']}
  Price increases:    {self.stats['price_increases']}
  Price decreases:    {self.stats['price_decreases']}
  Unchanged:          {self.stats['unchanged']}
  Errors:             {self.stats['errors']}
"""
        
        if self.stats['price_spikes']:
            report += "\n⚠️ PRICE SPIKES (flagged for review):\n"
            for spike in self.stats['price_spikes']:
                report += f"  {spike['name']}: €{spike['old']} → €{spike['new']} ({spike['change_pct']:+.1f}%)\n"
        
        report += "========================================"
        return report
    
    def close(self):
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description='Daily Sync')
    parser.add_argument('--store', required=True, help='Store name (lidl, kaufland, billa)')
    parser.add_argument('--file', help='Path to scraped JSON file')
    parser.add_argument('--scrape', action='store_true', help='Scrape first, then sync')
    parser.add_argument('--delisted-days', type=int, default=3, help='Days before marking as delisted')
    args = parser.parse_args()
    
    # Get products
    if args.scrape:
        # Run scraper first
        from scrapers.lidl import LidlScraper
        scraper = LidlScraper()
        products = scraper.scrape()
    elif args.file:
        with open(args.file) as f:
            products = json.load(f)
    else:
        print("Either --file or --scrape required")
        return
    
    # Sync
    sync = DailySync(args.store)
    sync.sync(products)
    
    # Detect delisted
    sync.detect_delisted(args.delisted_days)
    
    # Report
    print(sync.generate_report())
    
    sync.close()


if __name__ == '__main__':
    main()
