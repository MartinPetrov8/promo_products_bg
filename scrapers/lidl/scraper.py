#!/usr/bin/env python3
"""
Lidl Scraper - Production Version v2

Data structure in NUXT_DATA:
- Bulgarian name appears BEFORE product ID
- Price sequence: old_price_EUR, old_price_BGN, ..., current_price_EUR, current_price_BGN
- Quantity in keyfacts description
"""

import re
import json
import html
import time
import logging
import requests
from typing import List, Dict
from pathlib import Path
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scrapers.base import BaseScraper, Store, RawProduct

EUR_BGN = 1.95583

CATEGORY_URLS = [
    "https://www.lidl.bg/c/khrani-i-napitki/s10068374",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0',
    'Accept': 'text/html,application/xhtml+xml',
}


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
    
    def _parse_nuxt_data(self, html_content: str) -> Dict[str, dict]:
        """Extract products from NUXT_DATA."""
        match = re.search(r'id="__NUXT_DATA__"[^>]*>(\[.+?\])</script>', html_content, re.DOTALL)
        if not match:
            return {}
        
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
        
        products = {}
        
        # Find all product IDs first
        product_indices = {}  # pid -> index in data array
        for i, item in enumerate(data):
            if isinstance(item, int) and 10000000 <= item <= 19999999:
                pid = str(item)
                if pid not in product_indices:
                    product_indices[pid] = i
        
        # For each product, extract data
        for pid, idx in product_indices.items():
            p = {'id': pid}
            
            # Look BEFORE product ID for name (Cyrillic text, 5-100 chars)
            for j in range(idx-1, max(0, idx-10), -1):
                item = data[j]
                if isinstance(item, str) and 5 < len(item) < 100:
                    if re.search(r'[а-яА-Я]', item) and '<' not in item and 'http' not in item:
                        p['name'] = item.strip()
                        break
            
            # Look for URL/slug
            for j in range(max(0, idx-20), idx):
                item = data[j]
                if isinstance(item, str):
                    url_match = re.search(r'/p/([^/]+)/p' + pid, item)
                    if url_match:
                        p['slug'] = url_match.group(1)
                        p['url'] = f"https://www.lidl.bg/p/{p['slug']}/p{pid}"
                        break
            
            # Look AFTER product ID for quantity and prices
            prices_eur = []
            for j in range(idx+1, min(len(data), idx+50)):
                item = data[j]
                
                # Quantity
                if isinstance(item, str) and '/опаковка' in item:
                    qty_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)/опаковка', item, re.I)
                    if qty_match:
                        p['quantity_value'] = float(qty_match.group(1).replace(',', '.'))
                        p['quantity_unit'] = qty_match.group(2).lower()
                
                # Prices (collect EUR prices, they come in pairs: old, current)
                if isinstance(item, (int, float)) and 0.1 < item < 200:
                    # Check if next item is BGN price (roughly 2x EUR)
                    if j+1 < len(data):
                        next_item = data[j+1]
                        if isinstance(next_item, (int, float)) and 1.9 < next_item/item < 2.1:
                            prices_eur.append(item)
            
            # Assign prices: lower = current, higher = old
            if prices_eur:
                prices_eur.sort()
                p['price_eur'] = prices_eur[0]
                p['price_bgn'] = round(prices_eur[0] * EUR_BGN, 2)
                if len(prices_eur) > 1 and prices_eur[-1] > prices_eur[0]:
                    p['old_price_eur'] = prices_eur[-1]
                    p['old_price_bgn'] = round(prices_eur[-1] * EUR_BGN, 2)
            
            # Only keep if we have name and price
            if p.get('name') and p.get('price_bgn'):
                products[pid] = p
            elif p.get('slug') and p.get('price_bgn'):
                # Fallback to slug-based name
                p['name'] = unquote(p['slug']).replace('-', ' ').title()
                products[pid] = p
        
        return products
    
    def _scrape_category_pages(self, session: requests.Session) -> Dict[str, dict]:
        """Scrape all category pages."""
        all_products = {}
        
        for cat_url in CATEGORY_URLS:
            logger.info(f"Scraping: {cat_url}")
            
            for offset in range(0, 300, 12):
                page_url = f"{cat_url}?offset={offset}" if offset > 0 else cat_url
                
                try:
                    resp = session.get(page_url, headers=HEADERS, timeout=30)
                    if resp.status_code != 200:
                        break
                    
                    products = self._parse_nuxt_data(resp.text)
                    if not products:
                        break
                    
                    new_count = 0
                    for pid, p in products.items():
                        if pid not in all_products:
                            all_products[pid] = p
                            new_count += 1
                    
                    if new_count == 0:
                        break
                    
                    logger.info(f"  +{new_count} (total: {len(all_products)})")
                    time.sleep(0.3)
                    
                except Exception as e:
                    logger.warning(f"Failed {page_url}: {e}")
                    break
        
        return all_products
    
    def scrape(self) -> List[RawProduct]:
        """Scrape all Lidl products."""
        session = requests.Session()
        all_products = self._scrape_category_pages(session)
        
        results = []
        for p in all_products.values():
            results.append(RawProduct(
                store=self.store.value,
                sku=RawProduct.generate_sku(p['name']),
                raw_name=p['name'],
                price_bgn=p['price_bgn'],
                old_price_bgn=p.get('old_price_bgn'),
                quantity_value=p.get('quantity_value'),
                quantity_unit=p.get('quantity_unit'),
                product_url=p.get('url'),
            ))
        
        logger.info(f"Lidl: {len(results)} products")
        return results


def main():
    scraper = LidlScraper()
    products = scraper.scrape()
    
    with_qty = sum(1 for p in products if p.quantity_value)
    with_old = sum(1 for p in products if p.old_price_bgn)
    
    print(f"\n=== LIDL ===")
    print(f"Total: {len(products)}")
    print(f"Quantity: {with_qty} ({100*with_qty/len(products):.1f}%)")
    print(f"Old price: {with_old} ({100*with_old/len(products):.1f}%)")
    
    print(f"\n=== SAMPLE ===")
    for p in products[:15]:
        qty = f"{p.quantity_value} {p.quantity_unit}" if p.quantity_value else '-'
        old = f"(was {p.old_price_bgn:.2f})" if p.old_price_bgn else ''
        print(f"{p.raw_name[:40]:40} | {p.price_bgn:.2f}лв {old:15} | {qty}")


if __name__ == '__main__':
    main()
