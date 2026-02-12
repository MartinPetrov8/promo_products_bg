#!/usr/bin/env python3
"""
Open Food Facts Bulk Downloader

Downloads ALL Bulgarian products from OFF into local SQLite database.
Much faster than per-item API queries!

Usage:
    python3 -u bulk_download.py [--download-images]
"""

import os
import sys
import json
import sqlite3
import requests
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "off_bulgaria.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
IMAGES_DIR = PROJECT_ROOT / "data" / "off_images"

# OFF API
OFF_API_URL = "https://world.openfoodfacts.org/api/v2/search"
PAGE_SIZE = 100  # Max allowed by OFF
REQUEST_DELAY = 0.5  # Be nice to OFF

# Fields to fetch
FIELDS = [
    "code", "product_name", "product_name_bg", "product_name_en",
    "brands", "brands_tags", "categories", "categories_tags",
    "quantity", "serving_size", "packaging",
    "image_url", "image_small_url", "image_front_url", 
    "image_ingredients_url", "image_nutrition_url",
    "energy-kcal_100g", "fat_100g", "saturated-fat_100g",
    "carbohydrates_100g", "sugars_100g", "fiber_100g",
    "proteins_100g", "salt_100g",
    "nutriscore_grade", "nutriscore_score", "nova_group", "ecoscore_grade",
    "ingredients_text", "ingredients_text_bg", "allergens", "traces",
    "labels", "labels_tags", "countries", "countries_tags",
    "origins", "manufacturing_places",
    "created_t", "last_modified_t", "completeness"
]


class OFFBulkDownloader:
    """Downloads all Bulgarian products from Open Food Facts."""
    
    def __init__(self, db_path: str = None, download_images: bool = False):
        self.db_path = db_path or str(DB_PATH)
        self.download_images = download_images
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PromoBG/1.0 (https://github.com/MartinPetrov8/promo_products_bg)'
        })
        
        self.stats = {
            'pages_fetched': 0,
            'products_downloaded': 0,
            'products_saved': 0,
            'images_queued': 0,
            'errors': 0,
        }
    
    def init_db(self):
        """Initialize database with schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        with open(SCHEMA_PATH, 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print(f"✓ Database initialized: {self.db_path}")
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def fetch_page(self, page: int) -> dict:
        """Fetch a single page of products."""
        params = {
            'countries_tags_en': 'bulgaria',
            'fields': ','.join(FIELDS),
            'page_size': PAGE_SIZE,
            'page': page,
            'json': 1,
        }
        
        try:
            response = self.session.get(OFF_API_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"    ⚠ Error fetching page {page}: {e}")
            self.stats['errors'] += 1
            return {'products': [], 'count': 0}
    
    def save_products(self, products: list, conn: sqlite3.Connection):
        """Save products to database."""
        cursor = conn.cursor()
        
        for p in products:
            try:
                barcode = p.get('code')
                if not barcode:
                    continue
                
                # Normalize for matching
                name = p.get('product_name') or p.get('product_name_bg') or p.get('product_name_en') or ''
                brand = p.get('brands') or ''
                
                cursor.execute('''
                    INSERT OR REPLACE INTO off_products (
                        barcode, product_name, product_name_bg, product_name_en,
                        brands, brands_tags, categories, categories_tags,
                        quantity, serving_size, packaging,
                        image_url, image_small_url, image_front_url,
                        image_ingredients_url, image_nutrition_url,
                        energy_kcal, fat, saturated_fat, carbohydrates, sugars,
                        fiber, proteins, salt,
                        nutriscore_grade, nutriscore_score, nova_group, ecoscore_grade,
                        ingredients_text, ingredients_text_bg, allergens, traces,
                        labels, labels_tags, countries, countries_tags,
                        origins, manufacturing_places,
                        created_t, last_modified_t, completeness,
                        normalized_name, normalized_brand, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    barcode,
                    p.get('product_name'),
                    p.get('product_name_bg'),
                    p.get('product_name_en'),
                    p.get('brands'),
                    json.dumps(p.get('brands_tags', [])),
                    p.get('categories'),
                    json.dumps(p.get('categories_tags', [])),
                    p.get('quantity'),
                    p.get('serving_size'),
                    p.get('packaging'),
                    p.get('image_url'),
                    p.get('image_small_url'),
                    p.get('image_front_url'),
                    p.get('image_ingredients_url'),
                    p.get('image_nutrition_url'),
                    p.get('energy-kcal_100g'),
                    p.get('fat_100g'),
                    p.get('saturated-fat_100g'),
                    p.get('carbohydrates_100g'),
                    p.get('sugars_100g'),
                    p.get('fiber_100g'),
                    p.get('proteins_100g'),
                    p.get('salt_100g'),
                    p.get('nutriscore_grade'),
                    p.get('nutriscore_score'),
                    p.get('nova_group'),
                    p.get('ecoscore_grade'),
                    p.get('ingredients_text'),
                    p.get('ingredients_text_bg'),
                    p.get('allergens'),
                    p.get('traces'),
                    p.get('labels'),
                    json.dumps(p.get('labels_tags', [])),
                    p.get('countries'),
                    json.dumps(p.get('countries_tags', [])),
                    p.get('origins'),
                    p.get('manufacturing_places'),
                    p.get('created_t'),
                    p.get('last_modified_t'),
                    p.get('completeness'),
                    self.normalize_text(name),
                    self.normalize_text(brand),
                    datetime.now().isoformat(),
                ))
                self.stats['products_saved'] += 1
                
                # Queue images if requested
                if self.download_images:
                    for img_type, url_key in [
                        ('main', 'image_url'),
                        ('front', 'image_front_url'),
                        ('ingredients', 'image_ingredients_url'),
                        ('nutrition', 'image_nutrition_url'),
                    ]:
                        url = p.get(url_key)
                        if url:
                            cursor.execute('''
                                INSERT OR IGNORE INTO off_images (barcode, image_type, url)
                                VALUES (?, ?, ?)
                            ''', (barcode, img_type, url))
                            self.stats['images_queued'] += 1
                
            except Exception as e:
                print(f"    ⚠ Error saving product {p.get('code')}: {e}")
                self.stats['errors'] += 1
        
        conn.commit()
    
    def run(self):
        """Download all Bulgarian products."""
        print("=" * 60)
        print("📥 Open Food Facts Bulk Download - Bulgaria")
        print("=" * 60)
        
        self.init_db()
        conn = sqlite3.connect(self.db_path)
        
        # Get total count first
        print("\n🔍 Checking total products...")
        first_page = self.fetch_page(1)
        total = first_page.get('count', 0)
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        
        print(f"📦 Total products: {total:,}")
        print(f"📄 Total pages: {total_pages}")
        print(f"⏱  Estimated time: ~{total_pages * REQUEST_DELAY / 60:.1f} minutes\n")
        
        # Save download state
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO off_download_state 
            (id, total_products, downloaded_products, last_page, started_at, status)
            VALUES (1, ?, 0, 0, ?, 'running')
        ''', (total, datetime.now().isoformat()))
        conn.commit()
        
        # Download all pages
        start_time = time.time()
        
        for page in range(1, total_pages + 1):
            print(f"[{page}/{total_pages}] Fetching page {page}...", end=' ')
            
            if page == 1:
                data = first_page  # Reuse first page
            else:
                time.sleep(REQUEST_DELAY)
                data = self.fetch_page(page)
            
            products = data.get('products', [])
            self.stats['pages_fetched'] += 1
            self.stats['products_downloaded'] += len(products)
            
            self.save_products(products, conn)
            
            print(f"✓ {len(products)} products")
            
            # Update state
            cursor.execute('''
                UPDATE off_download_state 
                SET downloaded_products = ?, last_page = ?
                WHERE id = 1
            ''', (self.stats['products_saved'], page))
            conn.commit()
        
        # Mark complete
        elapsed = time.time() - start_time
        cursor.execute('''
            UPDATE off_download_state 
            SET completed_at = ?, status = 'completed'
            WHERE id = 1
        ''', (datetime.now().isoformat(),))
        conn.commit()
        conn.close()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 DOWNLOAD COMPLETE")
        print("=" * 60)
        print(f"Pages fetched:      {self.stats['pages_fetched']}")
        print(f"Products downloaded:{self.stats['products_downloaded']:,}")
        print(f"Products saved:     {self.stats['products_saved']:,}")
        print(f"Images queued:      {self.stats['images_queued']:,}")
        print(f"Errors:             {self.stats['errors']}")
        print(f"Time elapsed:       {elapsed:.1f} seconds")
        print(f"Database:           {self.db_path}")
        print(f"Database size:      {os.path.getsize(self.db_path) / 1024 / 1024:.1f} MB")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Download Bulgarian products from Open Food Facts')
    parser.add_argument('--download-images', action='store_true', help='Also queue images for download')
    args = parser.parse_args()
    
    downloader = OFFBulkDownloader(download_images=args.download_images)
    downloader.run()


if __name__ == '__main__':
    main()
