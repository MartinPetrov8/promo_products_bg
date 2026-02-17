"""
Billa Live Scraper - from ssbbilla.site accessibility version
Improved version with brand, quantity, discount, description extraction
"""
import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from scrapers.base import BaseScraper, Store, RawProduct, extract_brand_from_name, parse_quantity_from_name
import json as _json
from pathlib import Path as _Path

def _load_known_brands():
    try:
        config_path = _Path(__file__).parent.parent.parent / 'config' / 'brands_enrichment.json'
        with open(config_path) as f:
            cfg = _json.load(f)
        return set(cfg.get('bg_brands', []) + cfg.get('intl_brands', []) + cfg.get('lidl_brands', []))
    except Exception:
        return set()

KNOWN_BRANDS = _load_known_brands()

logger = logging.getLogger(__name__)

EUR_BGN_RATE = 1.95583
EXCLUDED_TERMS = ['Разбир', 'условията', 'Валидност:', 'Кинг оферти', 'Beverly Hills']

# Promo prefixes to remove from names
PROMO_PREFIXES = [
    r'^King оферта\s*[-–]\s*Само с Billa Card\s*[-–]\s*',
    r'^King оферта\s*[-–]\s*Супер цена\s*[-–]\s*',
    r'^King оферта\s*[-–]\s*',
    r'^Супер цена\s*[-–]\s*',
]

CATALOG_URLS = [
    "https://ssbbilla.site/catalog/sedmichna-broshura",
    "https://ssbbilla.site/catalog/predstoyashta-broshura",
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
]

def clean_product_name(name: str) -> str:
    """Remove promo prefixes from product name."""
    cleaned = name
    for pattern in PROMO_PREFIXES:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

class BillaScraper(BaseScraper):
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml',
        })
    
    @property
    def store(self) -> Store:
        return Store.BILLA
    
    def health_check(self) -> bool:
        try:
            resp = self.session.get("https://ssbbilla.site", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False
    
    def scrape(self) -> List[RawProduct]:
        products = []
        seen_names = set()
        
        for url in CATALOG_URLS:
            try:
                logger.info(f"Fetching {url}")
                time.sleep(random.uniform(1, 2))
                
                response = self.session.get(url, timeout=30)
                if response.status_code != 200:
                    logger.warning(f"Got {response.status_code} for {url}")
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                product_divs = soup.find_all(class_='product')
                
                for div in product_divs:
                    product = self._parse_product(div, seen_names)
                    if product:
                        products.append(product)
                
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")
        
        logger.info(f"Billa: {len(products)} products")
        return products
    
    def _parse_product(self, div, seen_names: set) -> Optional[RawProduct]:
        try:
            name_el = div.find(class_='actualProduct')
            if not name_el:
                return None
            
            raw_name = name_el.get_text(strip=True)
            
            if not raw_name or raw_name in ['Billa', ''] or len(raw_name) < 5:
                return None
            if any(term in raw_name for term in EXCLUDED_TERMS):
                return None
            
            # Clean promo prefixes
            clean_name = clean_product_name(raw_name)
            if not clean_name or len(clean_name) < 3:
                return None
            
            if clean_name in seen_names:
                return None
            
            # Extract brand from cleaned name
            # Strip Billa noise phrases before brand extraction
            brand_text = clean_name
            for noise in ['Продукт, маркиран със синя звезда', 'Произход - България',
                          'Произход България', 'Само с Billa Card', 'Само с Billa App',
                          'От топлата витрина', 'От Billa пекарна', 'От деликатесната витрина',
                          'До 5 бр. на клиент*', 'До 5 кг на клиент на ден*', 'Billa Ready']:
                brand_text = brand_text.replace(noise, ' ')
            brand_text = ' '.join(brand_text.split())
            brand = extract_brand_from_name(brand_text, known_brands=KNOWN_BRANDS)
            
            # Extract quantity from cleaned name
            qty_value, qty_unit = parse_quantity_from_name(clean_name)
            
            # Extract discount percentage
            discount_pct = None
            discount_div = div.find(class_='discount')
            if discount_div:
                discount_text = discount_div.get_text(strip=True)
                # Pattern: "- 56%" or "56%"
                match = re.search(r'[-–]?\s*(\d+)\s*%', discount_text)
                if match:
                    discount_pct = float(match.group(1))
            
            # Get prices - need to handle old/new price pairs better
            price_divs = div.find_all('div')
            
            prices_eur = []
            prices_bgn = []
            
            # Look for price text indicators
            old_price_bgn = None
            current_price_bgn = None
            
            for i, price_div in enumerate(price_divs):
                text = price_div.get_text(strip=True)
                
                # Check if this is a price label
                if text in ['ПРЕДИШНАЦЕНА', 'НОВАЦЕНА']:
                    # Next div should have the price
                    if i + 1 < len(price_divs):
                        next_div = price_divs[i + 1]
                        price_text = next_div.get_text(strip=True)
                        
                        # Parse EUR and BGN from combined text like "8.18€16.00лв."
                        eur_match = re.search(r'([\d,\.]+)\s*€', price_text)
                        bgn_match = re.search(r'([\d,\.]+)\s*лв', price_text, re.IGNORECASE)
                        
                        if bgn_match:
                            price = float(bgn_match.group(1).replace(',', '.'))
                            if text == 'ПРЕДИШНАЦЕНА':
                                old_price_bgn = price
                            elif text == 'НОВАЦЕНА':
                                current_price_bgn = price
            
            # Fallback: use old method if new parsing didn't work
            if not current_price_bgn:
                price_spans = div.find_all(class_='price')
                currency_spans = div.find_all(class_='currency')
                
                for i, price_span in enumerate(price_spans):
                    try:
                        value = float(price_span.get_text(strip=True).replace(',', '.'))
                        if i < len(currency_spans):
                            curr = currency_spans[i].get_text(strip=True)
                            if '€' in curr:
                                prices_eur.append(value)
                            elif 'лв' in curr:
                                prices_bgn.append(value)
                    except (ValueError, AttributeError):
                        continue
                
                if prices_bgn:
                    prices_bgn.sort()
                    current_price_bgn = prices_bgn[0]
                    if len(prices_bgn) > 1:
                        old_price_bgn = prices_bgn[-1]
                elif prices_eur:
                    prices_eur.sort()
                    current_price_bgn = prices_eur[0] * EUR_BGN_RATE
                    if len(prices_eur) > 1:
                        old_price_bgn = prices_eur[-1] * EUR_BGN_RATE
            
            if not current_price_bgn:
                return None
            
            seen_names.add(clean_name)
            
            img = div.find('img')
            image_url = img.get('src') if img else None
            
            return RawProduct(
                store=self.store.value,
                sku=RawProduct.generate_sku(clean_name),
                raw_name=clean_name,
                raw_description=clean_name,  # Best we have for Billa
                brand=brand,
                price_bgn=round(current_price_bgn, 2),
                old_price_bgn=round(old_price_bgn, 2) if old_price_bgn else None,
                discount_pct=discount_pct,
                quantity_value=qty_value,
                quantity_unit=qty_unit,
                image_url=image_url,
            )
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None


def main():
    logging.basicConfig(level=logging.INFO)
    scraper = BillaScraper()
    products = scraper.scrape()
    
    with_qty = sum(1 for p in products if p.quantity_value)
    with_brand = sum(1 for p in products if p.brand)
    with_desc = sum(1 for p in products if p.raw_description)
    with_old = sum(1 for p in products if p.old_price_bgn)
    with_disc = sum(1 for p in products if p.discount_pct)
    
    print(f"\n{'='*70}")
    print(f"BILLA SCRAPER RESULTS")
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
        
        print(f"\n[{i}] {p.raw_name}")
        print(f"    Brand:       {brand}")
        print(f"    Price:       {p.price_bgn:.2f}лв {old} {disc}")
        print(f"    Quantity:    {qty}")

if __name__ == '__main__':
    main()
