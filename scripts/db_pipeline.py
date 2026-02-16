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
                image_url, product_url, brand, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
            product.get('brand'),
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_price_history(self, store: str, sku: str, days: int = 30):
        """Get price history for a product."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT price_bgn, old_price_bgn, scraped_at
            FROM raw_scrapes
            WHERE store = ? AND sku = ?
            AND scraped_at >= datetime('now', ?)
            ORDER BY scraped_at DESC
        """, (store, sku, f'-{days} days'))
        return cursor.fetchall()
