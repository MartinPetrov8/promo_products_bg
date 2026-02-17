#!/usr/bin/env python3
"""
Lidl Scraper - Production Version (API-based with improved quantity extraction)

Uses Lidl's internal search API as primary source, with enhanced quantity extraction
from product names and keyfacts descriptions.
"""

import re
import json
import html
import time
import logging
import requests
from typing import List, Dict, Optional
from scrapers.base import BaseScraper, Store, RawProduct, parse_quantity_from_name

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

def strip_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', ' ', text).strip()

def extract_quantity_from_keyfacts(keyfacts_desc: str, product_name: str = '') -> tuple:
    """
    Extract quantity value and unit from keyfacts description or product name.
    Enhanced to handle more patterns.
    """
    if not keyfacts_desc:
        return None, None
    
    # Decode HTML entities and strip tags
    desc = html.unescape(keyfacts_desc)
    desc_clean = strip_html_tags(desc)
    
    # Pattern 1: "XXX g/опаковка" or "XXX ml/опаковка"
    match = re.search(r'[≈~]?\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)/опаковка', desc_clean, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2).lower()
        
        # Normalize to base units
        if unit == 'kg':
            return value * 1000, 'g'
        elif unit == 'l':
            return value * 1000, 'ml'
        else:
            return value, unit
    
    # Pattern 2: "X x Y g" (e.g., "2 x 500 g")
    match = re.search(r'(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\b', desc_clean, re.I)
    if match:
        count = int(match.group(1))
        value = float(match.group(2).replace(',', '.'))
        unit = match.group(3).lower()
        total = count * value
        
        # Normalize
        if unit == 'kg':
            return total * 1000, 'g'
        elif unit == 'l':
            return total * 1000, 'ml'
        elif unit == 'g':
            return total, 'g'
        elif unit == 'ml':
            return total, 'ml'
    
    # Pattern 3: "XXXg" or "XXX g" (without /опаковка)
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\b', desc_clean, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2).lower()
        
        # Normalize to base units
        if unit == 'kg':
            return value * 1000, 'g'
        elif unit == 'l':
            return value * 1000, 'ml'
        else:
            return value, unit
    
    # Pattern 4: "X бр" or "X бр."
    match = re.search(r'(\d+)\s*бр\.?', desc_clean, re.I)
    if match:
        return float(match.group(1)), 'count'
    
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
        keyfacts_desc = keyfacts.get('description', '')
        
        # Try multiple strategies for quantity extraction
        qty_val, qty_unit = None, None
        
        # Strategy 1: keyfacts description
        if keyfacts_desc:
            qty_val, qty_unit = extract_quantity_from_keyfacts(keyfacts_desc, name)
        
        # Strategy 2: parse from product name (fallback)
        if not qty_val:
            qty_val, qty_unit = parse_quantity_from_name(name)
        
        # Strategy 3: check if name contains quantity patterns that keyfacts might reference
        # E.g., "Моцарела XXL 500 г" where keyfacts just says "Настъргана"
        if not qty_val:
            # Look for common patterns in name
            name_lower = name.lower()
            # Pattern: "продукт 500г", "продукт 500 г", "продукт 1.5кг"
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(г|g|кг|kg|мл|ml|л|l)\b', name_lower)
            if match:
                value = float(match.group(1).replace(',', '.'))
                unit = match.group(2)
                
                if unit in ('кг', 'kg'):
                    qty_val, qty_unit = value * 1000, 'g'
                elif unit in ('л', 'l'):
                    qty_val, qty_unit = value * 1000, 'ml'
                elif unit in ('г', 'g'):
                    qty_val, qty_unit = value, 'g'
                elif unit in ('мл', 'ml'):
                    qty_val, qty_unit = value, 'ml'
        
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
        
        # Use keyfacts description or product name as raw_description
        # Clean HTML tags for better readability
        raw_description = strip_html_tags(keyfacts_desc) if keyfacts_desc else name
        
        return {
            'id': str(data.get('productId') or data.get('itemId')),
            'name': name,
            'brand': brand,
            'category': keyfacts.get('analyticsCategory') or data.get('category'),
            'raw_description': raw_description,
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


class LidlScraper(BaseScraper):
    
    @property
    def store(self) -> Store:
        return Store.LIDL
    
    def health_check(self) -> bool:
        try:
            resp = requests.get("https://www.lidl.bg", headers=HEADERS, timeout=10)
            return resp.status_code < 500
        except:
            return False
    
    def scrape(self) -> List[RawProduct]:
        """Scrape all Lidl products using API."""
        products_data = scrape_all()
        
        results = []
        for p in products_data:
            results.append(RawProduct(
                store=self.store.value,
                sku=p['id'],
                raw_name=p['name'],
                raw_description=p.get('raw_description'),
                brand=p.get('brand'),
                price_bgn=p['price_bgn'],
                old_price_bgn=p.get('old_price_bgn'),
                discount_pct=p.get('discount_pct'),
                quantity_value=p.get('quantity_value'),
                quantity_unit=p.get('quantity_unit'),
                product_url=p.get('product_url'),
                image_url=p.get('image_url'),
            ))
        
        logger.info(f"Lidl: {len(results)} products")
        return results


def main():
    logging.basicConfig(level=logging.INFO)
    scraper = LidlScraper()
    products = scraper.scrape()
    
    with_qty = sum(1 for p in products if p.quantity_value)
    with_brand = sum(1 for p in products if p.brand)
    with_desc = sum(1 for p in products if p.raw_description)
    with_old = sum(1 for p in products if p.old_price_bgn)
    with_disc = sum(1 for p in products if p.discount_pct)
    
    print(f"\n{'='*70}")
    print(f"LIDL SCRAPER RESULTS (API-based)")
    print(f"{'='*70}")
    print(f"Total products:      {len(products)}")
    print(f"With brand:          {with_brand:4d} ({100*with_brand/len(products):5.1f}%)")
    print(f"With quantity:       {with_qty:4d} ({100*with_qty/len(products):5.1f}%)")
    print(f"With description:    {with_desc:4d} ({100*with_desc/len(products):5.1f}%)")
    print(f"With old_price:      {with_old:4d} ({100*with_old/len(products):5.1f}%)")
    print(f"With discount:       {with_disc:4d} ({100*with_disc/len(products):5.1f}%)")
    
    print(f"\n{'='*70}")
    print(f"SAMPLE PRODUCTS (first 5)")
    print(f"{'='*70}")
    for i, p in enumerate(products[:5], 1):
        qty = f"{p.quantity_value} {p.quantity_unit}" if p.quantity_value else '-'
        old = f"(was {p.old_price_bgn:.2f})" if p.old_price_bgn else ''
        disc = f"-{p.discount_pct}%" if p.discount_pct else ''
        brand = p.brand or '-'
        desc = (p.raw_description[:50] + '...') if p.raw_description and len(p.raw_description) > 50 else (p.raw_description or '-')
        
        print(f"\n[{i}] {p.raw_name}")
        print(f"    Brand:       {brand}")
        print(f"    Price:       {p.price_bgn:.2f}лв {old} {disc}")
        print(f"    Quantity:    {qty}")
        print(f"    Description: {desc}")


if __name__ == '__main__':
    main()
