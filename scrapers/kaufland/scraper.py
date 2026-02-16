"""
Kaufland Live Scraper - Extracts from offers page
Filters out loyalty-only offers without prices
"""
import json
import re
import time
import random
import logging
import requests
from typing import List, Optional, Dict
from scrapers.base import BaseScraper, Store, RawProduct

logger = logging.getLogger(__name__)

OFFERS_URL = "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
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

class KauflandScraper(BaseScraper):
    
    @property
    def store(self) -> Store:
        return Store.KAUFLAND
    
    def health_check(self) -> bool:
        try:
            resp = requests.head("https://www.kaufland.bg", timeout=10, 
                               headers={'User-Agent': random.choice(USER_AGENTS)})
            return resp.status_code < 500
        except Exception as e:
            logger.error(f"Health check failed: {e}")
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
            
            html = response.text
            logger.info(f"Got {len(html):,} bytes")
            
            offers = self._extract_offers(html)
            logger.info(f"Found {len(offers)} unique offers")
            
            for offer in offers:
                product = self._parse_offer(offer)
                if product and product.price_bgn:  # Only include products WITH price
                    products.append(product)
            
            logger.info(f"Products with price: {len(products)}")
            
        except Exception as e:
            logger.error(f"Scrape failed: {e}")
        
        return products
    
    def _extract_offers(self, html: str) -> List[Dict]:
        all_offers = []
        seen_klnr = set()
        
        for m in re.finditer(r'"offers":\[', html):
            start = m.end() - 1
            depth = 0
            end = start
            for i, c in enumerate(html[start:start+500000]):
                if c == '[': depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        end = start + i + 1
                        break
            
            try:
                offers = json.loads(html[start:end])
                for offer in offers:
                    klnr = offer.get('klNr')
                    if klnr and klnr not in seen_klnr:
                        seen_klnr.add(klnr)
                        all_offers.append(offer)
            except json.JSONDecodeError:
                continue
        
        return all_offers
    
    def _parse_offer(self, offer: Dict) -> Optional[RawProduct]:
        kl_nr = offer.get('klNr')
        title = offer.get('title')
        
        if not kl_nr or not title:
            return None
        
        subtitle = offer.get('subtitle', '')
        
        # Extract BGN prices
        prices = offer.get('prices', {}).get('alternative', {}).get('formatted', {})
        price_bgn = parse_bgn_price(prices.get('standard'))
        old_price_bgn = parse_bgn_price(prices.get('old'))
        
        # Skip offers without price (loyalty-only offers)
        if not price_bgn:
            return None
        
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
            image_url=image_url,
        )
