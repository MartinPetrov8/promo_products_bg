#!/usr/bin/env python3
"""
Import scraped products into the database.

Usage:
    python import_products.py              # Import all from default locations
    python import_products.py --file path  # Import from specific file
    python import_products.py --scrape     # Run scrapers then import
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.database.db import Database, get_db

logger = logging.getLogger(__name__)

# Store mappings
STORE_CODES = {
    'kaufland': 1,
    'lidl': 2,
    'billa': 3,
    'metro': 4,
    'fantastico': 5,
}


def import_products_from_file(db: Database, file_path: Path, store_code: str) -> int:
    """
    Import products from a JSON file into the database.
    
    Returns number of products imported.
    """
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        products = json.load(f)
    
    if not products:
        logger.warning(f"No products in {file_path}")
        return 0
    
    store_id = STORE_CODES.get(store_code)
    if not store_id:
        logger.error(f"Unknown store code: {store_code}")
        return 0
    
    imported = 0
    
    for p in products:
        try:
            # Normalize field names (different scrapers use different names)
            name = p.get('name') or p.get('fullTitle') or p.get('title', '')
            if not name:
                continue
            
            # Get prices
            price_eur = p.get('price_eur') or p.get('price', 0)
            price_bgn = p.get('price_bgn') or p.get('priceSecond', price_eur * 1.95583)
            old_price_eur = p.get('old_price_eur') or p.get('oldPrice')
            old_price_bgn = p.get('old_price_bgn') or p.get('oldPriceSecond')
            discount = p.get('discount_pct') or p.get('discount', 0)
            
            # Ensure price is valid
            if not price_eur or price_eur <= 0:
                continue
            
            # Insert/update product
            product_data = {
                'name': name,
                'normalized_name': name.lower().strip(),
                'brand': p.get('brand'),
                'unit': p.get('quantity') or 'бр',
            }
            product_id = db.upsert_product(product_data)
            
            # Create store_product link
            store_product_data = {
                'store_product_code': str(p.get('product_id') or p.get('internal_code') or hash(name) % 10000000),
                'store_product_url': p.get('product_url') or p.get('store_product_url'),
                'store_image_url': p.get('image_url') or p.get('image'),
            }
            store_product_id = db.upsert_store_product(store_id, product_id, store_product_data)
            
            # Insert current price
            price_data = {
                'current_price': price_eur,
                'old_price': old_price_eur,
                'discount_percent': discount,
                'price_per_unit': price_eur,  # TODO: Calculate properly
                'is_promotional': discount > 0 if discount else False,
            }
            db.upsert_price(store_product_id, price_data)
            
            imported += 1
            
        except Exception as e:
            logger.warning(f"Failed to import product: {e}")
            continue
    
    db.conn.commit()
    logger.info(f"Imported {imported} products from {store_code}")
    
    return imported


def import_all_products(db: Database, data_dir: Path) -> dict:
    """Import products from all scraped data files."""
    
    results = {}
    
    # Define file mappings
    files = {
        'kaufland': data_dir / 'kaufland_products.json',
        'lidl': data_dir / 'lidl_products.json',
        'billa': data_dir / 'billa_products.json',
    }
    
    for store_code, file_path in files.items():
        count = import_products_from_file(db, file_path, store_code)
        results[store_code] = count
    
    return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Import products into database')
    parser.add_argument('--file', type=str, help='Specific JSON file to import')
    parser.add_argument('--store', type=str, help='Store code for --file import')
    parser.add_argument('--scrape', action='store_true', help='Run scrapers first')
    parser.add_argument('--db', type=str, help='Database path')
    
    args = parser.parse_args()
    
    # Get database
    db = get_db(args.db) if args.db else get_db()
    db.init_schema()
    
    print("=" * 60)
    print("Product Import Tool")
    print("=" * 60)
    
    if args.scrape:
        print("\n📦 Running scrapers first...")
        # TODO: Run scrapers
        print("   (scraper integration TBD)")
    
    if args.file:
        if not args.store:
            print("❌ --store required with --file")
            return
        
        file_path = Path(args.file)
        count = import_products_from_file(db, file_path, args.store)
        print(f"\n✅ Imported {count} products from {args.store}")
    
    else:
        # Import from default locations
        data_dir = Path(__file__).parent.parent / 'scraper' / 'data'
        
        print(f"\n📁 Looking for data in: {data_dir}")
        
        results = import_all_products(db, data_dir)
        
        print("\n📊 Import Results:")
        print("-" * 40)
        total = 0
        for store, count in results.items():
            status = "✅" if count > 0 else "⚠️"
            print(f"   {status} {store}: {count} products")
            total += count
        
        print("-" * 40)
        print(f"   Total: {total} products")
    
    # Show database stats
    print("\n📈 Database Stats:")
    stats = db.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print(f"\n✅ Database: {db.db_path}")


if __name__ == '__main__':
    main()
