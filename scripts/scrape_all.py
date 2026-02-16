#!/usr/bin/env python3
"""
Scrape ALL products from Kaufland, Lidl, Billa
Output: raw JSON per store
"""
import requests
import json
import re
import time
import random
import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/json',
    'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.7',
}

def scrape_kaufland():
    """Scrape Kaufland from their offers API"""
    print("Scraping Kaufland...", flush=True)
    
    data_file = Path(__file__).parent.parent / "data" / "kaufland_enhanced.json"
    if data_file.exists():
        with open(data_file) as f:
            data = json.load(f)
        print(f"  Loaded {len(data)} products from existing data", flush=True)
        
        products = []
        for item in data:
            products.append({
                'store': 'Kaufland',
                'sku': item.get('kl_nr'),
                'raw_name': item.get('title', ''),
                'raw_subtitle': item.get('subtitle', ''),
                'raw_description': item.get('description', ''),
                'raw_unit': item.get('unit', ''),
                'brand': item.get('brand'),  # Include brand if available
                'price_bgn': item.get('price_bgn'),
                'price_eur': item.get('price_eur'),
                'old_price_bgn': item.get('old_price_bgn'),
                'image_url': item.get('image_url'),
                'product_url': item.get('url'),
                'scraped_at': datetime.now().isoformat(),
            })
        return products
    return []


def scrape_lidl():
    """Scrape Lidl from sitemap + product pages"""
    print("Scraping Lidl...", flush=True)
    
    data_dir = Path(__file__).parent.parent / "data"
    products = []
    seen = set()
    
    # Load from JSON-LD batches
    for batch_file in sorted(data_dir.glob("lidl_jsonld_batch*.json")):
        with open(batch_file) as f:
            data = json.load(f)
        for item in data:
            pid = item.get('product_id')
            if pid in seen:
                continue
            seen.add(pid)
            
            products.append({
                'store': 'Lidl',
                'sku': pid,
                'raw_name': item.get('name', ''),
                'raw_subtitle': '',
                'raw_description': item.get('description', ''),
                'raw_unit': '',
                'brand': item.get('brand'),  # Include brand from JSON-LD
                'price_bgn': item.get('price'),
                'price_eur': round(item.get('price', 0) / 1.9558, 2) if item.get('price') else None,
                'old_price_bgn': item.get('old_price'),
                'image_url': item.get('image_url'),
                'product_url': item.get('product_url'),
                'scraped_at': datetime.now().isoformat(),
            })
    
    # Also merge lidl_fresh.json if exists (has more brands)
    fresh_file = data_dir / "lidl_fresh.json"
    if fresh_file.exists():
        with open(fresh_file) as f:
            fresh_data = json.load(f)
        for item in fresh_data:
            pid = item.get('product_id')
            if pid in seen:
                # Update existing with brand if missing
                for p in products:
                    if p['sku'] == pid and not p['brand'] and item.get('brand'):
                        p['brand'] = item['brand']
                continue
            seen.add(pid)
            
            products.append({
                'store': 'Lidl',
                'sku': pid,
                'raw_name': item.get('name', ''),
                'raw_subtitle': '',
                'raw_description': item.get('description', ''),
                'raw_unit': '',
                'brand': item.get('brand'),
                'price_bgn': item.get('price'),
                'price_eur': round(item.get('price', 0) / 1.9558, 2) if item.get('price') else None,
                'old_price_bgn': item.get('old_price'),
                'image_url': item.get('image_url'),
                'product_url': item.get('product_url'),
                'scraped_at': datetime.now().isoformat(),
            })
    
    print(f"  Loaded {len(products)} products", flush=True)
    return products


def scrape_billa():
    """Scrape Billa from database"""
    print("Scraping Billa...", flush=True)
    
    import sqlite3
    db_path = Path(__file__).parent.parent / "data" / "promobg.db"
    
    if not db_path.exists():
        print("  No database found", flush=True)
        return []
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.id, p.name, p.brand, sp.image_url, sp.product_url, pr.current_price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE s.name = 'Billa'
    """)
    
    products = []
    for row in cur.fetchall():
        products.append({
            'store': 'Billa',
            'sku': str(row['id']),
            'raw_name': row['name'] or '',
            'raw_subtitle': '',
            'raw_description': '',
            'raw_unit': '',
            'brand': row['brand'],  # Include brand from DB
            'price_bgn': round(row['current_price'] * 1.9558, 2) if row['current_price'] else None,
            'price_eur': row['current_price'],
            'old_price_bgn': None,
            'image_url': row['image_url'],
            'product_url': row['product_url'],
            'scraped_at': datetime.now().isoformat(),
        })
    
    conn.close()
    print(f"  Loaded {len(products)} products from database", flush=True)
    return products


def main():
    print("="*60, flush=True)
    print("SCRAPING ALL STORES", flush=True)
    print("="*60, flush=True)
    
    all_products = []
    
    kaufland = scrape_kaufland()
    all_products.extend(kaufland)
    
    lidl = scrape_lidl()
    all_products.extend(lidl)
    
    billa = scrape_billa()
    all_products.extend(billa)
    
    # Count brands
    with_brand = sum(1 for p in all_products if p.get('brand'))
    
    print(f"\nTotal raw products: {len(all_products)}", flush=True)
    print(f"  Kaufland: {len(kaufland)}", flush=True)
    print(f"  Lidl: {len(lidl)}", flush=True)
    print(f"  Billa: {len(billa)}", flush=True)
    print(f"  With brand: {with_brand} ({with_brand*100/len(all_products):.1f}%)", flush=True)
    
    output_file = OUTPUT_DIR / "raw_products.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved to {output_file}", flush=True)
    return all_products


if __name__ == '__main__':
    main()
