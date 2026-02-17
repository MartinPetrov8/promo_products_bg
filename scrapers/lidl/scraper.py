#!/usr/bin/env python3
"""
Lidl Scraper - Production Version (API-based with detail page enrichment)

1. Fetches product list from Lidl's internal search API
2. Enriches with detail page data (brand, quantity, OCR description)
3. Caches detail page data to avoid re-fetching known products
"""

import re
import json
import html
import time
import logging
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from scrapers.base import BaseScraper, Store, RawProduct, parse_quantity_from_name, extract_brand_from_name

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

PAGE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'text/html,application/xhtml+xml',
}


# Known Lidl private-label and common brands for OCR matching
KNOWN_BRANDS = {
    'Milbona', 'Pilos', 'Cien', 'Silvercrest', 'Parkside', 'Livarno',
    'Esmara', 'Livergy', 'Ernesto', 'Crivit', 'Baresa', 'Italiamo',
    'Vitasia', 'Kania', 'Freshona', 'Solevita', 'Freeway', 'Chef Select',
    'Snack Day', 'Tastino', 'Bellarom', 'Pikok', 'Favorina', 'Fin Carré',
    'Perlenbacher', 'Argus', 'Trattoria Alfredo', 'Combino', 'Deluxe',
    'W5', 'Formil', 'Dentalux', 'Floralys', 'Coshida', 'Orlando',
    'Lupilu', 'Toujours', 'Nevadent', 'Auriol', 'Sanino',
    'Siti', 'Purio', 'Lord Nelson', 'Tower',
    'Schogetten', 'Philadelphia', 'Coca-Cola', 'Pepsi', 'Fanta',
    'Sprite', 'Heineken', 'Guinness', 'Jim Beam', 'Lavazza',
    'Kinder', 'Lindt', 'Ruffles', 'Maggi', 'Toffifee', 'Maretti',
}

# Cache file for detail page data (persistent across runs)
CACHE_PATH = Path(__file__).parent.parent.parent / 'data' / 'lidl_detail_cache.json'


def strip_html_tags(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text).strip()


def load_detail_cache() -> Dict[str, dict]:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning("Failed to load detail cache, starting fresh")
    return {}


def save_detail_cache(cache: Dict[str, dict]):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_detail_page(session: requests.Session, product_url: str) -> Optional[dict]:
    """
    Fetch a Lidl product detail page and extract:
    - OCR description (from NUXT_DATA)
    - Keyfact quantity (from NUXT_DATA)  
    - Brand (from OCR description)
    """
    try:
        resp = session.get(product_url, headers=PAGE_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        
        result = {}
        
        nuxt = re.search(r'id="__NUXT_DATA__"[^>]*>(\[.+?\])</script>', resp.text, re.DOTALL)
        if not nuxt:
            return None
            
        data = json.loads(nuxt.group(1))
        
        # Find OCR description (long Cyrillic string with product details)
        for item in data:
            if isinstance(item, str) and len(item) > 25:
                if re.search(r'[а-яА-Я]', item) and 'http' not in item and '<' not in item:
                    if any(kw in item.lower() for kw in ['score', 'гр', 'ml', 'g ', 'кг', 'бр', 'опаковк', ',']):
                        result['ocr_description'] = item.strip()
                        break
        
        # Find keyfact quantity
        for item in data:
            if isinstance(item, str):
                # "250 g/опаковка" or "250 ml/опаковка"
                m = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\s*/\s*опаковка', item, re.I)
                if m:
                    value = float(m.group(1).replace(',', '.'))
                    unit = m.group(2).lower()
                    if unit == 'kg':
                        result['quantity_value'] = value * 1000
                        result['quantity_unit'] = 'g'
                    elif unit == 'l':
                        result['quantity_value'] = value * 1000
                        result['quantity_unit'] = 'ml'
                    else:
                        result['quantity_value'] = value
                        result['quantity_unit'] = unit
                    break
        
        # "250 или 300 g/опаковка" pattern
        if 'quantity_value' not in result:
            for item in data:
                if isinstance(item, str):
                    m = re.search(r'(\d+)\s+или\s+(\d+)\s*(g|ml|kg|l)\s*/\s*опаковка', item, re.I)
                    if m:
                        value = float(m.group(1))
                        unit = m.group(3).lower()
                        if unit == 'kg':
                            result['quantity_value'] = value * 1000
                            result['quantity_unit'] = 'g'
                        elif unit == 'l':
                            result['quantity_value'] = value * 1000
                            result['quantity_unit'] = 'ml'
                        else:
                            result['quantity_value'] = value
                            result['quantity_unit'] = unit
                        break
        
        # Extract brand from OCR description
        if result.get('ocr_description'):
            ocr = result['ocr_description']
            
            # Strategy 1: Check known brands list (most reliable)
            ocr_lower = ocr.lower()
            for known_brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
                if known_brand.lower() in ocr_lower:
                    result['brand'] = known_brand
                    break
            
            # Strategy 2: Extract Latin brand from start of text
            if 'brand' not in result:
                brand = extract_brand_from_name(ocr)
                if brand:
                    result['brand'] = brand
            
            # Strategy 3: "Опаковка на <Brand>" pattern
            if 'brand' not in result:
                m = re.search(r'(?:Опаковка на|Бутилка|Буркан|Кутия|Пакет(?:че)?|Торба)\s+(?:на\s+|с\s+)?([A-Za-z][A-Za-z\s&\'\-\.]+?)[\s,]', ocr)
                if m and len(m.group(1).strip()) >= 2:
                    result['brand'] = m.group(1).strip()
        
        return result if result else None
        
    except Exception as e:
        logger.debug(f"Failed to fetch detail page {product_url}: {e}")
        return None


def extract_quantity_from_keyfacts(keyfacts_desc: str) -> Tuple[Optional[float], Optional[str]]:
    if not keyfacts_desc:
        return None, None
    
    desc = strip_html_tags(html.unescape(keyfacts_desc))
    
    match = re.search(r'[≈~]?\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)/опаковка', desc, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2).lower()
        if unit == 'kg': return value * 1000, 'g'
        elif unit == 'l': return value * 1000, 'ml'
        else: return value, unit
    
    match = re.search(r'(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\b', desc, re.I)
    if match:
        total = int(match.group(1)) * float(match.group(2).replace(',', '.'))
        unit = match.group(3).lower()
        if unit == 'kg': return total * 1000, 'g'
        elif unit == 'l': return total * 1000, 'ml'
        else: return total, unit
    
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\b', desc, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2).lower()
        if unit == 'kg': return value * 1000, 'g'
        elif unit == 'l': return value * 1000, 'ml'
        else: return value, unit
    
    return None, None


def parse_product(item: dict) -> Optional[dict]:
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
        
        qty_val, qty_unit = extract_quantity_from_keyfacts(keyfacts_desc)
        if not qty_val:
            qty_val, qty_unit = parse_quantity_from_name(name)
        
        price_bgn = price_data.get('priceSecond') or (price_data.get('price', 0) * 1.95583)
        old_price_bgn = price_data.get('oldPriceSecond')
        
        discount_pct = None
        discount = price_data.get('discount', {})
        if discount.get('percentageDiscount'):
            discount_pct = discount['percentageDiscount']
        
        brand = None
        brand_data = data.get('brand', {})
        if brand_data.get('showBrand') and brand_data.get('name'):
            brand = brand_data['name']
        
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


def fetch_api_products(session: requests.Session) -> List[dict]:
    all_products = {}
    
    products, total = _fetch_page(session, offset=0)
    logger.info(f"Lidl API: {total} products available")
    
    for p in products:
        all_products[p['id']] = p
    
    offset = 100
    while offset < total and offset < 1000:
        time.sleep(0.3)
        products, _ = _fetch_page(session, offset=offset)
        if not products:
            break
        for p in products:
            all_products[p['id']] = p
        logger.info(f"  Fetched {len(all_products)}/{total}")
        offset += 100
    
    return list(all_products.values())


def _fetch_page(session: requests.Session, offset: int) -> tuple:
    params = {**API_PARAMS, 'offset': offset, 'fetchsize': 100}
    try:
        response = session.get(API_URL, params=params, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            return [], 0
        data = response.json()
        items = data.get('items', [])
        total = data.get('numFound', 0)
        products = [p for p in (parse_product(item) for item in items) if p]
        return products, total
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return [], 0


def enrich_from_detail_pages(session: requests.Session, products: List[dict], cache: Dict[str, dict]) -> int:
    """Enrich products from detail pages. Uses cache to skip known products."""
    fetched = 0
    
    for p in products:
        pid = p['id']
        
        # Check cache first
        if pid in cache:
            cached = cache[pid]
            if not p.get('brand') and cached.get('brand'):
                p['brand'] = cached['brand']
            if not p.get('quantity_value') and cached.get('quantity_value'):
                p['quantity_value'] = cached['quantity_value']
                p['quantity_unit'] = cached.get('quantity_unit')
            if cached.get('ocr_description'):
                p['raw_description'] = cached['ocr_description']
            continue
        
        # Only fetch if missing brand OR quantity
        if p.get('brand') and p.get('quantity_value'):
            continue
        
        url = p.get('product_url')
        if not url:
            continue
        
        detail = fetch_detail_page(session, url)
        if detail:
            cache[pid] = detail
            if not p.get('brand') and detail.get('brand'):
                p['brand'] = detail['brand']
            if not p.get('quantity_value') and detail.get('quantity_value'):
                p['quantity_value'] = detail['quantity_value']
                p['quantity_unit'] = detail.get('quantity_unit')
            if detail.get('ocr_description'):
                p['raw_description'] = detail['ocr_description']
        else:
            cache[pid] = {}
        
        fetched += 1
        time.sleep(0.25)
        
        if fetched % 50 == 0:
            logger.info(f"  Detail pages fetched: {fetched}")
    
    return fetched


class LidlScraper(BaseScraper):
    
    @property
    def store(self) -> Store:
        return Store.LIDL
    
    def health_check(self) -> bool:
        try:
            resp = requests.get("https://www.lidl.bg", headers=PAGE_HEADERS, timeout=10)
            return resp.status_code < 500
        except:
            return False
    
    def scrape(self) -> List[RawProduct]:
        """Scrape all Lidl products: API + detail page enrichment with cache."""
        session = requests.Session()
        
        # Step 1: Fetch from API
        products_data = fetch_api_products(session)
        logger.info(f"API returned {len(products_data)} products")
        
        # Step 2: Load cache and enrich from detail pages
        cache = load_detail_cache()
        cache_before = len(cache)
        
        fetched = enrich_from_detail_pages(session, products_data, cache)
        
        # Step 3: Save updated cache
        if fetched > 0:
            save_detail_cache(cache)
            logger.info(f"Detail cache: {cache_before} -> {len(cache)} entries ({fetched} new pages fetched)")
        else:
            logger.info(f"All products served from cache ({len(cache)} entries)")
        
        # Step 4: Convert to RawProduct
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
    
    total = len(products)
    with_qty = sum(1 for p in products if p.quantity_value)
    with_brand = sum(1 for p in products if p.brand)
    with_desc = sum(1 for p in products if p.raw_description)
    with_old = sum(1 for p in products if p.old_price_bgn)
    
    print(f"\n{'='*70}")
    print(f"LIDL SCRAPER RESULTS (API + Detail Page Cache)")
    print(f"{'='*70}")
    print(f"Total products:      {total}")
    print(f"With brand:          {with_brand:4d} ({100*with_brand/total:5.1f}%)")
    print(f"With quantity:       {with_qty:4d} ({100*with_qty/total:5.1f}%)")
    print(f"With description:    {with_desc:4d} ({100*with_desc/total:5.1f}%)")
    print(f"With old_price:      {with_old:4d} ({100*with_old/total:5.1f}%)")
    
    print(f"\n=== SAMPLE ===")
    for p in products[:10]:
        qty = f"{p.quantity_value} {p.quantity_unit}" if p.quantity_value else '-'
        brand = p.brand or '-'
        print(f"  {brand:20} | {p.raw_name[:30]:30} | {p.price_bgn:.2f}лв | {qty}")


if __name__ == '__main__':
    main()
