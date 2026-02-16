#!/usr/bin/env python3
"""
Lidl API Scraper - Production Version

Uses Lidl's internal search API to get all products with:
- Name, brand, category
- Current and old price (BGN)
- Quantity from keyfacts
- Product images and URLs
"""

import re
import json
import html
import time
import logging
import requests
from typing import List, Dict, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_URL = "https://www.lidl.bg/q/api/search"
API_PARAMS = {
    "assortment": "BG",
    "locale": "bg_BG",
    "version": "v2.0.0",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'bg-BG,bg;q=0.9',
    'Referer': 'https://www.lidl.bg/',
    'Origin': 'https://www.lidl.bg',
}

def extract_quantity(keyfacts_desc: str) -> tuple:
    """Extract quantity value and unit from keyfacts description."""
    if not keyfacts_desc:
        return None, None
    
    desc = html.unescape(keyfacts_desc)
    
    # Pattern: "XXX g/опаковка" or "XXX ml/опаковка"
    match = re.search(r'[≈~]?\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)/опаковка', desc, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2).lower()
        return value, unit
    
    # Fallback: "XXXg" or "XXX g"
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\b', desc, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2).lower()
        return value, unit
    
    return None, None

def parse_product(item: dict) -> Optional[dict]:
    """Parse API item into product dict."""
    try:
        data = item.get('gridbox', {}).get('data', {})
        if not data:
            return None
        
        price_data = data.get('price', {})
        if not price_data.get('price'):
            return None
        
        name = data.get('fullTitle') or data.get('title', '')
        if not name:
            return None
        
        keyfacts = data.get('keyfacts', {})
        qty_val, qty_unit = extract_quantity(keyfacts.get('description', ''))
        
        # API returns EUR as primary, BGN as secondary
        price_bgn = price_data.get('priceSecond') or (price_data.get('price', 0) * 1.95583)
        old_price_bgn = price_data.get('oldPriceSecond')
        
        discount_pct = None
        discount = price_data.get('discount', {})
        if discount.get('percentageDiscount'):
            discount_pct = discount['percentageDiscount']
        
        # Get brand if available
        brand = None
        brand_data = data.get('brand', {})
        if brand_data.get('showBrand') and brand_data.get('name'):
            brand = brand_data['name']
        
        return {
            'id': str(data.get('productId') or data.get('itemId')),
            'name': name,
            'brand': brand,
            'category': keyfacts.get('analyticsCategory') or data.get('category'),
            'price_bgn': round(price_bgn, 2),
            'old_price_bgn': round(old_price_bgn, 2) if old_price_bgn else None,
            'discount_pct': discount_pct,
            'quantity_value': qty_val,
            'quantity_unit': qty_unit,
            'image_url': data.get('image'),
            'product_url': f"https://www.lidl.bg{data.get('canonicalUrl', '')}",
        }
        
    except Exception as e:
        logger.debug(f"Failed to parse item: {e}")
        return None

def fetch_products(session: requests.Session, offset: int = 0, fetchsize: int = 100) -> tuple:
    """Fetch products from API."""
    params = {**API_PARAMS, 'offset': offset, 'fetchsize': fetchsize}
    
    try:
        response = session.get(API_URL, params=params, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            logger.warning(f"API returned {response.status_code}")
            return [], 0
        
        data = response.json()
        items = data.get('items', [])
        total = data.get('numFound', 0)
        
        products = [p for p in (parse_product(item) for item in items) if p]
        return products, total
        
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return [], 0

def scrape_all() -> List[dict]:
    """Scrape all products from Lidl API."""
    session = requests.Session()
    all_products = {}
    
    products, total = fetch_products(session, offset=0, fetchsize=100)
    logger.info(f"Total products available: {total}")
    
    for p in products:
        all_products[p['id']] = p
    
    offset = 100
    while offset < total and offset < 1000:
        time.sleep(0.3)
        products, _ = fetch_products(session, offset=offset, fetchsize=100)
        
        if not products:
            break
        
        for p in products:
            all_products[p['id']] = p
        
        logger.info(f"  Fetched {len(all_products)}/{total}")
        offset += 100
    
    return list(all_products.values())

def main():
    print("=" * 60)
    print("Lidl API Scraper")
    print("=" * 60)
    
    products = scrape_all()
    
    if not products:
        print("\n❌ No products scraped")
        return
    
    with_price = [p for p in products if p.get('price_bgn')]
    with_qty = [p for p in products if p.get('quantity_value')]
    with_old = [p for p in products if p.get('old_price_bgn')]
    
    print(f"\n=== RESULTS ===")
    print(f"Total: {len(products)}")
    print(f"With price: {len(with_price)} ({100*len(with_price)/len(products):.1f}%)")
    print(f"With quantity: {len(with_qty)} ({100*len(with_qty)/len(products):.1f}%)")
    print(f"With old_price: {len(with_old)} ({100*len(with_old)/len(products):.1f}%)")
    
    print(f"\n=== SAMPLE ===")
    for p in products[:15]:
        qty = f"{p.get('quantity_value', '')} {p.get('quantity_unit', '')}" if p.get('quantity_value') else '-'
        old = f"(was {p['old_price_bgn']:.2f})" if p.get('old_price_bgn') else ''
        print(f"{p['name'][:40]:40} | {p['price_bgn']:.2f}лв {old:15} | {qty}")
    
    output_path = Path(__file__).parent.parent.parent / 'data' / 'lidl_api_products.json'
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {output_path}")

if __name__ == '__main__':
    main()
