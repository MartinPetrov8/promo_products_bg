"""
Database Connection and Management

SQLite for MVP, designed for easy PostgreSQL migration.
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "promobg.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """
    SQLite database wrapper with connection pooling and utilities.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None
    
    def connect(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,  # Allow multi-threaded access
                timeout=30.0
            )
            self._connection.row_factory = sqlite3.Row  # Dict-like rows
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
        return self._connection
    
    def close(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    @contextmanager
    def transaction(self):
        """Context manager for transactions."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query."""
        return self.connect().execute(query, params)
    
    def executemany(self, query: str, params_list: List[tuple]) -> sqlite3.Cursor:
        """Execute a query with multiple parameter sets."""
        return self.connect().executemany(query, params_list)
    
    def fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Execute query and fetch one result."""
        return self.execute(query, params).fetchone()
    
    def fetchall(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute query and fetch all results."""
        return self.execute(query, params).fetchall()
    
    def init_schema(self):
        """Initialize database schema from SQL file."""
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")
        
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        conn = self.connect()
        conn.executescript(schema_sql)
        conn.commit()
        logger.info(f"Database schema initialized: {self.db_path}")
    
    def get_size_bytes(self) -> int:
        """Get database file size in bytes."""
        if self.db_path.exists():
            return self.db_path.stat().st_size
        return 0
    
    def get_size_mb(self) -> float:
        """Get database file size in MB."""
        return self.get_size_bytes() / (1024 * 1024)
    
    def get_table_counts(self) -> Dict[str, int]:
        """Get row counts for all tables."""
        tables = ['products', 'store_products', 'prices', 'price_history', 
                  'scrape_runs', 'categories', 'stores', 'product_matches']
        counts = {}
        for table in tables:
            try:
                result = self.fetchone(f"SELECT COUNT(*) as cnt FROM {table}")
                counts[table] = result['cnt'] if result else 0
            except sqlite3.OperationalError:
                counts[table] = 0
        return counts
    
    def vacuum(self):
        """Reclaim unused space."""
        self.execute("VACUUM")
        logger.info("Database vacuumed")
    
    def record_metrics(self):
        """Record current DB metrics for monitoring."""
        size = self.get_size_bytes()
        counts = self.get_table_counts()
        
        self.execute("""
            INSERT INTO db_metrics (
                db_size_bytes, products_count, store_products_count,
                prices_count, price_history_count, scrape_runs_count
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            size,
            counts.get('products', 0),
            counts.get('store_products', 0),
            counts.get('prices', 0),
            counts.get('price_history', 0),
            counts.get('scrape_runs', 0)
        ))
        self.connect().commit()
    
    # ========================================
    # Product Operations
    # ========================================
    
    def upsert_product(self, product_data: Dict[str, Any]) -> int:
        """Insert or update a product, return product ID."""
        now = datetime.utcnow().isoformat()
        
        # Check if exists by barcode or normalized name
        existing = None
        if product_data.get('barcode_ean'):
            existing = self.fetchone(
                "SELECT id FROM products WHERE barcode_ean = ?",
                (product_data['barcode_ean'],)
            )
        
        if not existing and product_data.get('normalized_name'):
            existing = self.fetchone(
                "SELECT id FROM products WHERE normalized_name = ? AND brand = ?",
                (product_data['normalized_name'], product_data.get('brand', ''))
            )
        
        if existing:
            # Update existing
            self.execute("""
                UPDATE products SET
                    name = COALESCE(?, name),
                    brand = COALESCE(?, brand),
                    image_url = COALESCE(?, image_url),
                    updated_at = ?
                WHERE id = ?
            """, (
                product_data.get('name'),
                product_data.get('brand'),
                product_data.get('image_url'),
                now,
                existing['id']
            ))
            return existing['id']
        else:
            # Insert new
            cursor = self.execute("""
                INSERT INTO products (name, normalized_name, brand, category_id, 
                    unit, quantity, barcode_ean, image_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_data.get('name', ''),
                product_data.get('normalized_name', ''),
                product_data.get('brand'),
                product_data.get('category_id'),
                product_data.get('unit', 'бр'),
                product_data.get('quantity'),
                product_data.get('barcode_ean'),
                product_data.get('image_url'),
                now, now
            ))
            return cursor.lastrowid
    
    def upsert_store_product(self, store_id: int, product_id: int, 
                             store_data: Dict[str, Any]) -> int:
        """Insert or update store-product link, return store_product ID."""
        now = datetime.utcnow().isoformat()
        store_code = store_data.get('store_product_code', str(product_id))
        
        existing = self.fetchone(
            "SELECT id FROM store_products WHERE store_id = ? AND store_product_code = ?",
            (store_id, store_code)
        )
        
        if existing:
            self.execute("""
                UPDATE store_products SET
                    store_product_url = COALESCE(?, store_product_url),
                    store_image_url = COALESCE(?, store_image_url),
                    is_available = 1,
                    last_seen_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                store_data.get('store_product_url'),
                store_data.get('store_image_url'),
                now, now,
                existing['id']
            ))
            return existing['id']
        else:
            cursor = self.execute("""
                INSERT INTO store_products (product_id, store_id, store_product_code,
                    store_product_url, store_image_url, is_available,
                    first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (
                product_id, store_id, store_code,
                store_data.get('store_product_url'),
                store_data.get('store_image_url'),
                now, now, now, now
            ))
            return cursor.lastrowid
    
    def upsert_price(self, store_product_id: int, price_data: Dict[str, Any]) -> int:
        """Insert or update current price, archive old price to history."""
        now = datetime.utcnow().isoformat()
        
        # Get current active price
        current = self.fetchone(
            "SELECT * FROM prices WHERE store_product_id = ? AND valid_to IS NULL",
            (store_product_id,)
        )
        
        new_price = price_data.get('current_price', 0)
        
        if current:
            # Check if price changed
            if abs(current['current_price'] - new_price) < 0.01:
                # Price unchanged, just update timestamp
                self.execute(
                    "UPDATE prices SET updated_at = ? WHERE id = ?",
                    (now, current['id'])
                )
                return current['id']
            
            # Price changed - archive old price
            self.execute(
                "UPDATE prices SET valid_to = ? WHERE id = ?",
                (now, current['id'])
            )
            
            # Record in history
            self.execute("""
                INSERT INTO price_history (store_product_id, price, old_price,
                    discount_percent, price_per_unit, is_promotional, promotion_label, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                store_product_id,
                current['current_price'],
                current['old_price'],
                current['discount_percent'],
                current['price_per_unit'],
                current['is_promotional'],
                current['promotion_label'],
                now
            ))
        
        # Insert new current price
        cursor = self.execute("""
            INSERT INTO prices (store_product_id, current_price, old_price,
                discount_percent, price_per_unit, price_per_unit_base,
                is_promotional, promotion_label, valid_from, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            store_product_id,
            new_price,
            price_data.get('old_price'),
            price_data.get('discount_percent'),
            price_data.get('price_per_unit'),
            price_data.get('price_per_unit_base'),
            1 if price_data.get('discount_percent') else 0,
            price_data.get('promotion_label'),
            now, now, now
        ))
        
        return cursor.lastrowid
    
    def get_store_id(self, store_code: str) -> Optional[int]:
        """Get store ID by code."""
        result = self.fetchone(
            "SELECT id FROM stores WHERE code = ?",
            (store_code,)
        )
        return result['id'] if result else None
    
    # ========================================
    # Query Operations
    # ========================================
    
    def find_cheapest(self, search_term: str, limit: int = 10) -> List[Dict]:
        """Find cheapest products matching search term across all stores."""
        normalized = search_term.lower().strip()
        
        rows = self.fetchall("""
            SELECT 
                p.name,
                p.brand,
                s.display_name as store,
                s.code as store_code,
                pr.current_price,
                pr.old_price,
                pr.discount_percent,
                pr.promotion_label,
                sp.store_product_url,
                sp.store_image_url
            FROM products p
            JOIN store_products sp ON sp.product_id = p.id
            JOIN stores s ON s.id = sp.store_id
            JOIN prices pr ON pr.store_product_id = sp.id AND pr.valid_to IS NULL
            WHERE p.normalized_name LIKE ?
                AND sp.is_available = 1
                AND s.is_active = 1
            ORDER BY pr.current_price ASC
            LIMIT ?
        """, (f'%{normalized}%', limit))
        
        return [dict(row) for row in rows]
    
    def get_best_deals(self, min_discount: float = 20, limit: int = 50) -> List[Dict]:
        """Get products with best discounts."""
        rows = self.fetchall("""
            SELECT 
                p.name,
                p.brand,
                s.display_name as store,
                s.code as store_code,
                pr.current_price,
                pr.old_price,
                pr.discount_percent,
                pr.promotion_label,
                sp.store_product_url,
                sp.store_image_url
            FROM products p
            JOIN store_products sp ON sp.product_id = p.id
            JOIN stores s ON s.id = sp.store_id
            JOIN prices pr ON pr.store_product_id = sp.id AND pr.valid_to IS NULL
            WHERE pr.discount_percent >= ?
                AND sp.is_available = 1
                AND s.is_active = 1
            ORDER BY pr.discount_percent DESC
            LIMIT ?
        """, (min_discount, limit))
        
        return [dict(row) for row in rows]


# Singleton instance
_db_instance: Optional[Database] = None


def get_db(db_path: Optional[str] = None) -> Database:
    """Get database singleton instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
