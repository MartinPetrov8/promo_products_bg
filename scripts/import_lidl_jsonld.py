#!/usr/bin/env python3
"""
Import Lidl products from JSON-LD scraper output into the database.

Converts JSON-LD format to database schema and handles:
- Duplicate detection (by product name)
- Price normalization (BGN -> EUR at 1.95583 fixed rate)
- Brand/name standardization
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "promobg.db"
BGN_TO_EUR = 1.95583  # Fixed exchange rate


def import_lidl_products(json_path: str, dry_run: bool = False):
    """Import products from JSON file into database"""
    
    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        products = json.load(f)
    
    print(f"Loaded {len(products)} products from {json_path}")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get Lidl store ID
    cur.execute("SELECT id FROM stores WHERE name = 'Lidl'")
    row = cur.fetchone()
    if not row:
        print("ERROR: Lidl store not found in database")
        return
    lidl_store_id = row['id']
    
    # Get existing Lidl product names (to avoid duplicates)
    cur.execute("""
        SELECT p.name FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = ?
    """, (lidl_store_id,))
    existing_names = {row['name'].lower() for row in cur.fetchall()}
    print(f"Found {len(existing_names)} existing Lidl products")
    
    # Track stats
    stats = {
        'new_products': 0,
        'skipped_existing': 0,
        'skipped_no_price': 0,
        'skipped_no_name': 0,
    }
    
    for prod in products:
        name = prod.get('name', '').strip()
        brand = prod.get('brand', '').strip() if prod.get('brand') else None
        price_bgn = prod.get('price')
        
        # Skip if no name
        if not name:
            stats['skipped_no_name'] += 1
            continue
        
        # Skip if no price (out of stock)
        if price_bgn is None:
            stats['skipped_no_price'] += 1
            continue
        
        # Prepend brand to name if brand exists
        full_name = f"{brand} {name}" if brand else name
        
        # Skip if already exists (case-insensitive)
        if full_name.lower() in existing_names:
            stats['skipped_existing'] += 1
            continue
        
        # Convert BGN to EUR
        price_eur = round(price_bgn / BGN_TO_EUR, 2)
        
        if dry_run:
            print(f"  Would add: {full_name} @ {price_eur:.2f}€ (was {price_bgn:.2f} BGN)")
            stats['new_products'] += 1
            existing_names.add(full_name.lower())  # Track for this run
            continue
        
        try:
            # Insert into products table
            cur.execute("""
                INSERT INTO products (name, brand)
                VALUES (?, ?)
            """, (full_name, brand))
            product_db_id = cur.lastrowid
            
            # Insert into store_products
            cur.execute("""
                INSERT INTO store_products (store_id, product_id)
                VALUES (?, ?)
            """, (lidl_store_id, product_db_id))
            store_product_id = cur.lastrowid
            
            # Insert price
            cur.execute("""
                INSERT INTO prices (store_product_id, current_price)
                VALUES (?, ?)
            """, (store_product_id, price_eur))
            
            stats['new_products'] += 1
            existing_names.add(full_name.lower())  # Track as added
            
        except Exception as e:
            print(f"  Error adding {full_name}: {e}")
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    
    print(f"\nImport complete:")
    print(f"  New products added: {stats['new_products']}")
    print(f"  Skipped (existing): {stats['skipped_existing']}")
    print(f"  Skipped (no price): {stats['skipped_no_price']}")
    print(f"  Skipped (no name):  {stats['skipped_no_name']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Import Lidl JSON-LD products')
    parser.add_argument('json_file', help='Path to JSON file from scraper')
    parser.add_argument('--dry-run', action='store_true', help='Preview without importing')
    args = parser.parse_args()
    
    import_lidl_products(args.json_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
