#!/usr/bin/env python3
"""
Lidl Category Page Scraper

Scrapes product data from Lidl category pages which contain:
- Product name
- Price
- Quantity (e.g., "250 g/опаковка")
- Product URL

This is more reliable than sitemap scraping because category pages
have structured NUXT_DATA with all product details.
"""

import re
import json
import time
import logging
import requests
from urllib.parse import unquote
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# EUR to BGN fixed rate
EUR_BGN = 1.95583

# Category pages to scrape (food and drinks main categories)
CATEGORY_URLS = [
    "https://www.lidl.bg/c/khrani-i-napitki/s10068374",
    "https://www.lidl.bg/c/napitki/s10068375",
    "https://www.lidl.bg/c/sladkarnitsi/s10068376",
    "https://www.lidl.bg/c/meso-i-kolbasi/s10068377",
    "https://www.lidl.bg/c/mlechni-produkti/s10068378",
    "https://www.lidl.bg/c/khliab-i-pechiva/s10068379",
    "https://www.lidl.bg/c/plodove-i-zelenchutsi/s10068380",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8',
}

def parse_nuxt_data(html: str) -> List[Dict]:
    """Extract products from NUXT_DATA embedded in page."""
    
    match = re.search(r'id="__NUXT_DATA__"[^>]*>(\[.+?\])</script>', html, re.DOTALL)
    if not match:
        logger.warning("No NUXT_DATA found in page")
        return []
    
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse NUXT_DATA: {e}")
        return []
    
    products = {}
    
    # Pass 1: Find product URLs and IDs
    for i, item in enumerate(data):
        if isinstance(item, str):
            url_match = re.search(r'/p/([^/]+)/p(\d+)', item)
            if url_match:
                slug, pid = url_match.groups()
                if pid not in products:
                    # Convert slug to readable name
                    name = unquote(slug).replace('-', ' ').title()
                    products[pid] = {
                        'id': pid,
                        'slug': slug,
                        'name': name,
                        'url': f"https://www.lidl.bg/p/{slug}/p{pid}"
                    }
    
    # Pass 2: Find quantities
    for i, item in enumerate(data):
        if isinstance(item, str):
            # Quantity patterns
            qty_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)/опаковка', item, re.I)
            if qty_match:
                qty_val = float(qty_match.group(1).replace(',', '.'))
                qty_unit = qty_match.group(2).lower()
                
                # Normalize units
                if qty_unit == 'l':
                    qty_val *= 1000
                    qty_unit = 'ml'
                elif qty_unit == 'kg':
                    qty_val *= 1000
                    qty_unit = 'g'
                
                # Find nearest product ID
                for j in range(i-1, max(0, i-100), -1):
                    if isinstance(data[j], int) and 10000000 <= data[j] <= 19999999:
                        pid = str(data[j])
                        if pid in products:
                            products[pid]['quantity_value'] = qty_val
                            products[pid]['quantity_unit'] = qty_unit
                        break
    
    # Pass 3: Find prices (look for price patterns near product IDs)
    for i, item in enumerate(data):
        if isinstance(item, (int, float)) and 0.1 < item < 500:
            # Could be a price - check context
            for j in range(max(0, i-30), i):
                if isinstance(data[j], int) and 10000000 <= data[j] <= 19999999:
                    pid = str(data[j])
                    if pid in products and 'price_eur' not in products[pid]:
                        products[pid]['price_eur'] = float(item)
                        products[pid]['price_bgn'] = round(float(item) * EUR_BGN, 2)
                    break
    
    # Pass 4: Find better product names from fullTitle
    for i, item in enumerate(data):
        if isinstance(item, str) and len(item) > 15 and '<' not in item and 'http' not in item and '/' not in item:
            # Check if this looks like a product name (has Cyrillic)
            if re.search(r'[а-яА-Я]', item) and len(item) < 100:
                # Find nearby product ID
                for j in range(max(0, i-30), i):
                    if isinstance(data[j], int) and 10000000 <= data[j] <= 19999999:
                        pid = str(data[j])
                        if pid in products:
                            # Only update if current name is from slug
                            current = products[pid].get('name', '')
                            if not re.search(r'[а-яА-Я]', current):
                                products[pid]['name'] = item
                        break
    
    return list(products.values())

def fetch_category(url: str, session: requests.Session, offset: int = 0) -> List[Dict]:
    """Fetch a category page and extract products."""
    
    page_url = f"{url}?offset={offset}" if offset > 0 else url
    
    try:
        response = session.get(page_url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Got {response.status_code} for {page_url}")
            return []
        
        products = parse_nuxt_data(response.text)
        logger.info(f"  {page_url}: {len(products)} products")
        return products
        
    except Exception as e:
        logger.error(f"Failed to fetch {page_url}: {e}")
        return []

def scrape_all_categories() -> List[Dict]:
    """Scrape all category pages."""
    
    session = requests.Session()
    all_products = {}
    
    for cat_url in CATEGORY_URLS:
        logger.info(f"Scraping category: {cat_url}")
        
        # Fetch first page
        products = fetch_category(cat_url, session)
        
        for p in products:
            if p['id'] not in all_products:
                all_products[p['id']] = p
        
        # Fetch additional pages (offset by 12)
        for offset in [12, 24, 36, 48]:
            time.sleep(0.5)  # Rate limit
            page_products = fetch_category(cat_url, session, offset)
            if not page_products:
                break
            for p in page_products:
                if p['id'] not in all_products:
                    all_products[p['id']] = p
    
    return list(all_products.values())

def main():
    print("=" * 60)
    print("Lidl Category Scraper")
    print("=" * 60)
    
    products = scrape_all_categories()
    
    # Stats
    with_price = [p for p in products if p.get('price_bgn')]
    with_qty = [p for p in products if p.get('quantity_value')]
    
    print(f"\n=== RESULTS ===")
    print(f"Total products: {len(products)}")
    print(f"With price: {len(with_price)} ({100*len(with_price)/len(products):.1f}%)")
    print(f"With quantity: {len(with_qty)} ({100*len(with_qty)/len(products):.1f}%)")
    
    # Sample
    print(f"\n=== SAMPLE ===")
    for p in products[:10]:
        qty = f"{p.get('quantity_value', '?')} {p.get('quantity_unit', '')}" if p.get('quantity_value') else '-'
        print(f"{p.get('name', '?')[:40]:40} | {p.get('price_bgn', 0):.2f}лв | {qty}")
    
    # Save
    with open('data/lidl_category_products.json', 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: data/lidl_category_products.json")

if __name__ == '__main__':
    main()
