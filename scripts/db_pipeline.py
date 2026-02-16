#!/usr/bin/env python3
"""
Database pipeline for PromoBG:
1. Log scan run
2. Append raw data (never delete)
3. Update prices with timestamps
4. Track price changes in history
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
import uuid

DB_PATH = 'data/promobg.db'

class PromoBGDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self
    
    def close(self):
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        return self.connect()
    
    def __exit__(self, *args):
        self.close()
    
    def start_scan_run(self, store: str) -> int:
        """Start a new scan run, return run_id."""
        cursor = self.conn.cursor()
        
        # Get store_id
        cursor.execute("SELECT id FROM stores WHERE name = ?", (store,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO stores (name) VALUES (?)", (store,))
            store_id = cursor.lastrowid
        else:
            store_id = row['id']
        
        cursor.execute("""
            INSERT INTO scan_runs (store_id, started_at, status)
            VALUES (?, datetime('now'), 'running')
        """, (store_id,))
        self.conn.commit()
        return cursor.lastrowid
    
    def complete_scan_run(self, run_id: int, stats: dict):
        """Mark scan run as complete with stats."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE scan_runs SET
                completed_at = datetime('now'),
                status = 'completed',
                products_scraped = ?,
                new_products = ?,
                price_changes = ?,
                errors = ?
            WHERE id = ?
        """, (
            stats.get('products_scraped', 0),
            stats.get('new_products', 0),
            stats.get('price_changes', 0),
            stats.get('errors', 0),
            run_id
        ))
        self.conn.commit()
    
    def append_raw_scrape(self, run_id: int, product: dict):
        """Append raw scrape data (never overwrite)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO raw_scrapes (
                scan_run_id, store, sku, raw_name, raw_subtitle,
                raw_description, price_bgn, old_price_bgn, discount_pct,
                image_url, product_url, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            run_id,
            product.get('store'),
            product.get('sku'),
            product.get('raw_name'),
            product.get('raw_subtitle'),
            product.get('raw_description'),
            product.get('price_bgn'),
            product.get('old_price_bgn'),
            product.get('discount_pct'),
            product.get('image_url'),
            product.get('product_url'),
        ))
        return cursor.lastrowid
    
    def update_price_with_history(self, store_product_id: int, new_price: float, 
                                   old_price: float = None, discount_pct: float = None):
        """Update price and track change in history."""
        cursor = self.conn.cursor()
        
        # Get current price
        cursor.execute("""
            SELECT current_price FROM prices WHERE store_product_id = ?
        """, (store_product_id,))
        row = cursor.fetchone()
        
        if row:
            prev_price = row['current_price']
            if prev_price != new_price:
                # Record price change
                change_pct = ((new_price - prev_price) / prev_price * 100) if prev_price else 0
                cursor.execute("""
                    INSERT INTO price_history (store_product_id, old_price, new_price, change_pct, changed_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (store_product_id, prev_price, new_price, change_pct))
            
            # Update current price
            cursor.execute("""
                UPDATE prices SET 
                    current_price = ?, old_price = ?, discount_pct = ?, scraped_at = datetime('now')
                WHERE store_product_id = ?
            """, (new_price, old_price, discount_pct, store_product_id))
        else:
            # Insert new price
            cursor.execute("""
                INSERT INTO prices (store_product_id, current_price, old_price, discount_pct, scraped_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (store_product_id, new_price, old_price, discount_pct))
        
        self.conn.commit()
        return cursor.rowcount
    
    def get_price_history(self, store: str, sku: str, days: int = 30):
        """Get price history for a product."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT rs.price_bgn, rs.old_price_bgn, rs.scraped_at
            FROM raw_scrapes rs
            WHERE rs.store = ? AND rs.sku = ?
            AND rs.scraped_at >= datetime('now', ?)
            ORDER BY rs.scraped_at DESC
        """, (store, sku, f'-{days} days'))
        return cursor.fetchall()
    
    def import_from_json(self, json_path: str, store: str):
        """Import raw products from JSON file."""
        with open(json_path) as f:
            products = json.load(f)
        
        run_id = self.start_scan_run(store)
        
        for p in products:
            p['store'] = store
            self.append_raw_scrape(run_id, p)
        
        self.complete_scan_run(run_id, {
            'products_scraped': len(products),
            'new_products': len(products),
            'price_changes': 0,
            'errors': 0
        })
        
        self.conn.commit()
        return run_id, len(products)

def main():
    """Import current raw_products.json to database."""
    with PromoBGDatabase() as db:
        print("Importing raw_products.json to database...")
        
        with open('output/raw_products.json') as f:
            products = json.load(f)
        
        # Group by store
        by_store = {}
        for p in products:
            store = p.get('store', 'Unknown')
            if store not in by_store:
                by_store[store] = []
            by_store[store].append(p)
        
        total = 0
        for store, prods in by_store.items():
            run_id = db.start_scan_run(store)
            for p in prods:
                p['store'] = store
                db.append_raw_scrape(run_id, p)
            db.complete_scan_run(run_id, {
                'products_scraped': len(prods),
                'new_products': len(prods),
            })
            print(f"  {store}: {len(prods)} products (run_id={run_id})")
            total += len(prods)
        
        print(f"\n✓ Imported {total} products to raw_scrapes")
        
        # Show stats
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM raw_scrapes")
        print(f"Total raw_scrapes: {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM scan_runs")
        print(f"Total scan_runs: {cursor.fetchone()[0]}")

if __name__ == '__main__':
    main()
