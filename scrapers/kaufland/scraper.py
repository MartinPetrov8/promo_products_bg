"""
Kaufland Live Scraper - Extracts from offers page
Now with quantity extraction from unit field
"""
import json
import re
import time
import random
import logging
import requests
from typing import List, Optional, Dict, Tuple
from scrapers.base import BaseScraper, Store, RawProduct

logger = logging.getLogger(__name__)

OFFERS_URL = "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
]

def parse_bgn_price(text: str) -> Optional[float]:
    if not text:
        return None
    match = re.search(r'([\d,\.]+)\s*(?:ЛВ\.?|лв\.?)', text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except:
            pass
    return None

def parse_quantity(unit: str) -> Tuple[Optional[float], Optional[str]]:
    """Parse quantity from unit field like '500 г', '1,5 кг', 'кг'."""
    if not unit:
        return None, None
    
    unit = unit.strip().lower()
    
    # Pattern: "500 г", "1,5 кг", "100 мл", "2 л"
    match = re.search(r'([\d,\.]+)\s*(г|кг|мл|л|g|kg|ml|l)\b', unit)
    if match:
        value = float(match.group(1).replace(',', '.'))
        u = match.group(2)
        # Normalize
        if u in ('г', 'g'):
            return value, 'g'
        elif u in ('кг', 'kg'):
            return value * 1000, 'g'
        elif u in ('мл', 'ml'):
            return value, 'ml'
        elif u in ('л', 'l'):
            return value * 1000, 'ml'
    
    # Pattern: just "кг" or "г" (price per unit)
    if unit in ('кг', 'kg'):
        return 1000, 'g'  # per kg
    if unit in ('г', 'g'):
        return 1, 'g'
    
    return None, None

class KauflandScraper(BaseScraper):
    
    @property
    def store(self) -> Store:
        return Store.KAUFLAND
    
    def health_check(self) -> bool:
        try:
            resp = requests.head("https://www.kaufland.bg", timeout=10, 
                               headers={'User-Agent': random.choice(USER_AGENTS)})
            return resp.status_code < 500
        except:
            return False
    
    def scrape(self) -> List[RawProduct]:
        products = []
        
        try:
            logger.info(f"Fetching {OFFERS_URL}")
            time.sleep(random.uniform(1, 2))
            
            response = requests.get(OFFERS_URL, timeout=60, headers={
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'bg-BG,bg;q=0.9',
            })
            response.raise_for_status()
            
            offers = self._extract_offers(response.text)
            logger.info(f"Found {len(offers)} offers")
            
            for offer in offers:
                product = self._parse_offer(offer)
                if product and product.price_bgn:
                    products.append(product)
            
            logger.info(f"Kaufland: {len(products)} products")
            
        except Exception as e:
            logger.error(f"Scrape failed: {e}")
        
        return products
    
    def _extract_offers(self, html: str) -> List[Dict]:
        all_offers = []
        seen_klnr = set()
        
        for m in re.finditer(r'"offers":\[', html):
            start = m.end() - 1
            depth = 0
            for i, c in enumerate(html[start:start+500000]):
                if c == '[': depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        try:
                            offers = json.loads(html[start:start+i+1])
                            for offer in offers:
                                klnr = offer.get('klNr')
                                if klnr and klnr not in seen_klnr:
                                    seen_klnr.add(klnr)
                                    all_offers.append(offer)
                        except:
                            pass
                        break
        
        return all_offers
    
    def _parse_offer(self, offer: Dict) -> Optional[RawProduct]:
        kl_nr = offer.get('klNr')
        title = offer.get('title')
        
        if not kl_nr or not title:
            return None
        
        subtitle = offer.get('subtitle', '')
        
        # Extract prices
        prices = offer.get('prices', {}).get('alternative', {}).get('formatted', {})
        price_bgn = parse_bgn_price(prices.get('standard'))
        old_price_bgn = parse_bgn_price(prices.get('old'))
        
        if not price_bgn:
            return None
        
        # Extract quantity from unit field
        unit_text = offer.get('unit', '')
        qty_value, qty_unit = parse_quantity(unit_text)
        
        # Image
        images = offer.get('detailImages', [])
        image_url = images[0] if images else None
        
        return RawProduct(
            store=self.store.value,
            sku=str(kl_nr),
            raw_name=title,
            raw_subtitle=subtitle,
            brand=offer.get('brand'),
            price_bgn=price_bgn,
            old_price_bgn=old_price_bgn,
            quantity_value=qty_value,
            quantity_unit=qty_unit,
            image_url=image_url,
        )


def main():
    logging.basicConfig(level=logging.INFO)
    scraper = KauflandScraper()
    products = scraper.scrape()
    
    with_qty = sum(1 for p in products if p.quantity_value)
    print(f"\nKaufland: {len(products)} products, {with_qty} with quantity ({100*with_qty/len(products):.0f}%)")
    
    print("\n=== SAMPLE ===")
    for p in products[:10]:
        qty = f"{p.quantity_value} {p.quantity_unit}" if p.quantity_value else '-'
        print(f"{p.raw_name[:35]:35} | {p.price_bgn:.2f}лв | {qty}")

if __name__ == '__main__':
    main()
