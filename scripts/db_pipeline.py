#!/usr/bin/env python3
"""
Database pipeline for PromoBG with transaction safety and batch inserts.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)
DB_PATH = 'data/promobg.db'

class PromoBGDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
    
    def connect(self) -> 'PromoBGDatabase':
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self) -> 'PromoBGDatabase':
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def start_scan_run(self, store: str) -> int:
        """Start a new scan run, return run_id."""
        cursor = self.conn.cursor()
        
        # Use INSERT OR IGNORE to handle concurrent runs
        cursor.execute("INSERT OR IGNORE INTO stores (name) VALUES (?)", (store,))
        cursor.execute("SELECT id FROM stores WHERE name = ?", (store,))
        store_id = cursor.fetchone()['id']
        
        cursor.execute("""
            INSERT INTO scan_runs (store_id, started_at, status)
            VALUES (?, ?, 'running')
        """, (store_id, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        
        return cursor.lastrowid
    
    def complete_scan_run(self, run_id: int, stats: Dict):
        """Mark scan run as complete with stats."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE scan_runs SET
                completed_at = ?,
                status = 'completed',
                products_scraped = ?,
                new_products = ?,
                price_changes = ?,
                errors = ?
            WHERE id = ?
        """, (
            datetime.now(timezone.utc).isoformat(),
            stats.get('products_scraped', 0),
            stats.get('new_products', 0),
            stats.get('price_changes', 0),
            stats.get('errors', 0),
            run_id
        ))
        self.conn.commit()
    
    def fail_scan_run(self, run_id: int, error: str):
        """Mark scan run as failed."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE scan_runs SET
                completed_at = ?,
                status = 'failed',
                error_log = ?
            WHERE id = ?
        """, (datetime.now(timezone.utc).isoformat(), error, run_id))
        self.conn.commit()
    
    def batch_insert_raw_scrapes(self, run_id: int, products: List[Dict]) -> int:
        """
        Batch insert with transaction safety.
        Either all products are inserted or none (rollback on failure).
        """
        if not products:
            return 0
        
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # Prepare batch data
            batch_data = [
                (
                    run_id,
                    p.get('store'),
                    p.get('sku'),
                    p.get('raw_name'),
                    p.get('raw_subtitle'),
                    p.get('raw_description'),
                    p.get('price_bgn'),
                    p.get('old_price_bgn'),
                    p.get('discount_pct'),
                    p.get('image_url'),
                    p.get('product_url'),
                    p.get('brand'),
                    now
                )
                for p in products
            ]
            
            # Batch insert
            cursor.executemany("""
                INSERT INTO raw_scrapes (
                    scan_run_id, store, sku, raw_name, raw_subtitle,
                    raw_description, price_bgn, old_price_bgn, discount_pct,
                    image_url, product_url, brand, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch_data)
            
            # Commit transaction
            self.conn.commit()
            logger.info(f"Batch inserted {len(products)} products for run_id={run_id}")
            return len(products)
            
        except Exception as e:
            # Rollback on any failure
            self.conn.rollback()
            logger.error(f"Batch insert failed, rolled back: {e}")
            raise
    
    def get_latest_run(self, store: str) -> Optional[Dict]:
        """Get the latest completed scan run for a store."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT sr.*, s.name as store_name
            FROM scan_runs sr
            JOIN stores s ON sr.store_id = s.id
            WHERE s.name = ? AND sr.status = 'completed'
            ORDER BY sr.completed_at DESC
            LIMIT 1
        """, (store,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_current_inventory(self, store: str) -> List[Dict]:
        """Get current inventory (latest completed scrape) for a store."""
        latest_run = self.get_latest_run(store)
        if not latest_run:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM raw_scrapes
            WHERE scan_run_id = ?
        """, (latest_run['id'],))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_price_history(self, store: str, sku: str, days: int = 30) -> List[Dict]:
        """Get price history for a product."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT price_bgn, old_price_bgn, scraped_at
            FROM raw_scrapes
            WHERE store = ? AND sku = ?
            AND scraped_at >= datetime('now', ?)
            ORDER BY scraped_at DESC
        """, (store, sku, f'-{days} days'))
        return [dict(row) for row in cursor.fetchall()]
