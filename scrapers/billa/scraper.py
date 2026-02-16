"""
Billa Live Scraper - from ssbbilla.site accessibility version
Cleans promo prefixes from product names
"""
import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from scrapers.base import BaseScraper, Store, RawProduct

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
            
            # Get prices
            price_spans = div.find_all(class_='price')
            currency_spans = div.find_all(class_='currency')
            
            if not price_spans:
                return None
            
            prices_eur = []
            prices_bgn = []
            
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
            
            if not prices_eur and not prices_bgn:
                return None
            
            prices_eur.sort()
            prices_bgn.sort()
            
            price_bgn = prices_bgn[0] if prices_bgn else (prices_eur[0] * EUR_BGN_RATE if prices_eur else None)
            old_price_bgn = prices_bgn[-1] if len(prices_bgn) > 1 else None
            
            if not price_bgn:
                return None
            
            seen_names.add(clean_name)
            
            img = div.find('img')
            image_url = img.get('src') if img else None
            
            return RawProduct(
                store=self.store.value,
                sku=RawProduct.generate_sku(clean_name),
                raw_name=clean_name,  # Use cleaned name
                price_bgn=round(price_bgn, 2),
                old_price_bgn=round(old_price_bgn, 2) if old_price_bgn else None,
                image_url=image_url,
            )
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None
