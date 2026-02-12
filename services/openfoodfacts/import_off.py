#!/usr/bin/env python3
"""
Import Open Food Facts products and match to our database.

Matching strategies:
1. Exact barcode match (highest confidence)
2. Brand + product name fuzzy match
3. Product name only fuzzy match (lowest confidence)

Usage:
    python import_off.py                    # Import Bulgarian products
    python import_off.py --limit 100        # Limit import count
    python import_off.py --match-only       # Just run matching on existing OFF data
"""

import argparse
import logging
import re
import sqlite3
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.openfoodfacts.off_client import OpenFoodFactsClient, OFFProduct

logger = logging.getLogger(__name__)

# Paths
DB_PATH = Path(__file__).parent.parent.parent / "data" / "promobg.db"


def normalize_name(name: str) -> str:
    """Normalize product name for matching"""
    if not name:
        return ""
    
    result = name.lower()
    
    # Remove common suffixes/prefixes
    result = re.sub(r'\|\s*lidl\s*$', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\b(био|organic|натурален|natural)\b', '', result, flags=re.IGNORECASE)
    
    # Remove quantities
    result = re.sub(r'\b\d+\s*(г|гр|kg|кг|ml|мл|l|л|бр|pcs)\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\d+[.,]\d+\s*(л|kg|g)', '', result, flags=re.IGNORECASE)
    
    # Normalize whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


def string_similarity(a: str, b: str) -> float:
    """Calculate similarity between two strings (0-1)"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class OFFImporter:
    """Import and match Open Food Facts products"""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.client = OpenFoodFactsClient()
        
        self.stats = {
            'off_imported': 0,
            'off_updated': 0,
            'matches_barcode': 0,
            'matches_brand_name': 0,
            'matches_name': 0,
            'no_match': 0,
        }
    
    def import_off_product(self, product: OFFProduct) -> Optional[int]:
        """
        Import or update OFF product in database.
        
        Returns: off_product_id
        """
        cursor = self.conn.cursor()
        
        # Check if exists
        cursor.execute("SELECT id FROM off_products WHERE barcode = ?", (product.barcode,))
        existing = cursor.fetchone()
        
        if existing:
            # Update
            cursor.execute("""
                UPDATE off_products SET
                    name = ?,
                    generic_name = ?,
                    brands = ?,
                    categories = ?,
                    image_url = ?,
                    image_small_url = ?,
                    quantity = ?,
                    packaging = ?,
                    ingredients_text = ?,
                    nutriscore_grade = ?,
                    countries = ?,
                    updated_at = datetime('now')
                WHERE barcode = ?
            """, (
                product.name,
                product.generic_name,
                product.brands,
                product.categories,
                product.image_url,
                product.image_small_url,
                product.quantity,
                product.packaging,
                product.ingredients_text,
                product.nutriscore_grade,
                product.countries,
                product.barcode,
            ))
            self.stats['off_updated'] += 1
            return existing['id']
        else:
            # Insert
            cursor.execute("""
                INSERT INTO off_products (
                    barcode, name, generic_name, brands, categories,
                    image_url, image_small_url, quantity, packaging,
                    ingredients_text, nutriscore_grade, countries
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product.barcode,
                product.name,
                product.generic_name,
                product.brands,
                product.categories,
                product.image_url,
                product.image_small_url,
                product.quantity,
                product.packaging,
                product.ingredients_text,
                product.nutriscore_grade,
                product.countries,
            ))
            self.stats['off_imported'] += 1
            return cursor.lastrowid
    
    def match_to_products(self, off_product: OFFProduct, off_id: int) -> List[Tuple[int, str, float]]:
        """
        Find matching products in our database.
        
        Returns: List of (product_id, match_type, confidence)
        """
        cursor = self.conn.cursor()
        matches = []
        
        # Strategy 1: Exact barcode match
        if off_product.barcode:
            cursor.execute(
                "SELECT id FROM products WHERE barcode_ean = ?",
                (off_product.barcode,)
            )
            for row in cursor.fetchall():
                matches.append((row['id'], 'barcode', 1.0))
                self.stats['matches_barcode'] += 1
        
        if matches:
            return matches  # Barcode is definitive
        
        # Strategy 2: Brand + name match
        off_name = normalize_name(off_product.name)
        off_brand = (off_product.brands or '').lower().strip()
        
        if off_brand and off_name:
            # Find products with matching brand
            cursor.execute("""
                SELECT id, name, normalized_name, brand 
                FROM products 
                WHERE LOWER(brand) LIKE ?
            """, (f'%{off_brand}%',))
            
            for row in cursor.fetchall():
                our_name = normalize_name(row['name'])
                similarity = string_similarity(off_name, our_name)
                
                if similarity >= 0.6:  # 60% threshold
                    matches.append((row['id'], 'brand_name', similarity))
                    self.stats['matches_brand_name'] += 1
        
        # Strategy 3: Name-only match (lower confidence)
        if not matches and off_name and len(off_name) >= 4:
            cursor.execute("""
                SELECT id, name, normalized_name 
                FROM products 
                WHERE normalized_name LIKE ?
                LIMIT 50
            """, (f'%{off_name[:20]}%',))
            
            for row in cursor.fetchall():
                our_name = normalize_name(row['name'])
                similarity = string_similarity(off_name, our_name)
                
                if similarity >= 0.7:  # Higher threshold for name-only
                    matches.append((row['id'], 'name', similarity * 0.8))  # Penalize confidence
                    self.stats['matches_name'] += 1
        
        if not matches:
            self.stats['no_match'] += 1
        
        return matches
    
    def save_matches(self, off_id: int, matches: List[Tuple[int, str, float]]):
        """Save product matches to database"""
        cursor = self.conn.cursor()
        
        for product_id, match_type, confidence in matches:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO product_off_matches
                    (product_id, off_product_id, match_type, match_confidence)
                    VALUES (?, ?, ?, ?)
                """, (product_id, off_id, match_type, confidence))
            except Exception as e:
                logger.warning(f"Failed to save match: {e}")
        
        self.conn.commit()
    
    def update_product_images(self):
        """
        Update products with images from OFF matches.
        Only updates products without existing images.
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            UPDATE products 
            SET image_url = (
                SELECT off.image_url 
                FROM product_off_matches m
                JOIN off_products off ON m.off_product_id = off.id
                WHERE m.product_id = products.id
                AND off.image_url IS NOT NULL
                AND m.match_confidence >= 0.7
                ORDER BY m.match_confidence DESC
                LIMIT 1
            )
            WHERE image_url IS NULL
            AND EXISTS (
                SELECT 1 FROM product_off_matches m
                JOIN off_products off ON m.off_product_id = off.id
                WHERE m.product_id = products.id
                AND off.image_url IS NOT NULL
            )
        """)
        
        updated = cursor.rowcount
        self.conn.commit()
        logger.info(f"Updated {updated} product images from OFF")
        return updated
    
    def import_bulgarian_products(self, limit: Optional[int] = None) -> int:
        """
        Import Bulgarian products from Open Food Facts.
        
        Args:
            limit: Maximum products to import (None = all)
            
        Returns:
            Number of products imported
        """
        logger.info("Starting OFF import for Bulgarian products...")
        
        page = 1
        page_size = 100
        total_imported = 0
        
        while True:
            products, total_count = self.client.get_bulgarian_products(page, page_size)
            
            if not products:
                break
            
            logger.info(f"Page {page}: {len(products)} products (total: {total_count:,})")
            
            for product in products:
                if not product.barcode:
                    continue
                
                # Import OFF product
                off_id = self.import_off_product(product)
                
                if off_id:
                    # Find and save matches
                    matches = self.match_to_products(product, off_id)
                    if matches:
                        self.save_matches(off_id, matches)
                    
                    total_imported += 1
                
                if limit and total_imported >= limit:
                    break
            
            self.conn.commit()
            
            if limit and total_imported >= limit:
                break
            
            if page * page_size >= total_count:
                break
            
            page += 1
        
        # Update product images
        self.update_product_images()
        
        logger.info(f"Import complete: {total_imported} products")
        return total_imported
    
    def get_stats(self) -> Dict:
        """Get import statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM off_products")
        off_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM product_off_matches")
        match_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM products WHERE image_url IS NOT NULL")
        products_with_images = cursor.fetchone()[0]
        
        return {
            **self.stats,
            'off_products_total': off_count,
            'matches_total': match_count,
            'products_with_images': products_with_images,
            'api_stats': self.client.get_stats(),
        }


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Import Open Food Facts products')
    parser.add_argument('--limit', type=int, help='Limit import count')
    parser.add_argument('--match-only', action='store_true', help='Only run matching')
    parser.add_argument('--update-images', action='store_true', help='Only update images')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Open Food Facts Import")
    print("=" * 60)
    
    importer = OFFImporter()
    
    if args.update_images:
        updated = importer.update_product_images()
        print(f"\n✅ Updated {updated} product images")
    elif args.match_only:
        # TODO: Implement re-matching
        print("Match-only mode not yet implemented")
    else:
        importer.import_bulgarian_products(limit=args.limit)
    
    stats = importer.get_stats()
    
    print("\n📊 Statistics:")
    print("-" * 40)
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
