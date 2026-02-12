"""
Broshura.bg Scraper - Tier 2 Fallback

Scrapes from broshura.bg (aggregator site) as a fallback
when direct store scraping fails.

Coverage: Kaufland, Lidl, Billa, Metro, Fantastico
"""

import re
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
from pathlib import Path
from bs4 import BeautifulSoup

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)


# ============================================
# Store ID Mappings
# ============================================

STORE_MAPPINGS = {
    'kaufland': {
        'url': 'https://www.broshura.bg/h/80550-kaufland',
        'display_name': 'Kaufland',
    },
    'lidl': {
        'url': 'https://www.broshura.bg/h/83076-lidl',
        'display_name': 'Lidl',
    },
    'billa': {
        'url': 'https://www.broshura.bg/h/83013-billa',
        'display_name': 'Billa',
    },
    'metro': {
        'url': 'https://www.broshura.bg/h/80520-metro',
        'display_name': 'Metro',
    },
    'fantastico': {
        'url': 'https://www.broshura.bg/h/80640-fantastico',
        'display_name': 'Fantastico',
    },
}


# ============================================
# Data Models
# ============================================

@dataclass
class BroshuraProduct:
    """Product data from Broshura.bg"""
    name: str
    price_bgn: float
    price_eur: float
    old_price_bgn: Optional[float]
    old_price_eur: Optional[float]
    discount_pct: Optional[int]
    store: str
    valid_until: Optional[str]
    product_url: Optional[str]
    image_url: Optional[str] = None


# ============================================
# Scraper Class
# ============================================

class BroshuraScraper:
    """
    Tier 2 fallback scraper using broshura.bg aggregator.
    
    This scraper is used when direct store scraping fails.
    Data may be 1-2 days behind the official store websites.
    """
    
    DOMAIN = "broshura.bg"
    BASE_URL = "https://www.broshura.bg"
    TIER = 2
    
    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        rate_limiter: Optional[DomainRateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        retry_handler: Optional[RetryHandler] = None,
    ):
        # Initialize infrastructure
        self.session_manager = session_manager or SessionManager(
            config=SessionConfig(
                max_requests=100,  # broshura.bg is more lenient
                max_age_seconds=1800,
            )
        )
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name=self.DOMAIN,
            failure_threshold=5,
            recovery_timeout=120,
            half_open_max_calls=3,
        )
        self.retry_handler = retry_handler or RetryHandler(
            config=RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                max_delay=15.0,
            )
        )
        
        self.stats = {
            'requests': 0,
            'successes': 0,
            'failures': 0,
            'products_scraped': 0,
        }
    
    def _make_request(self, url: str, timeout: int = 30) -> Optional[str]:
        """Make HTTP request with infrastructure protection."""
        if self.circuit_breaker.is_open:
            logger.warning(f"Circuit breaker OPEN for {self.DOMAIN}")
            return None
        
        self.rate_limiter.wait(url)
        session = self.session_manager.get_session(self.DOMAIN)
        
        try:
            self.stats['requests'] += 1
            start_time = time.time()
            
            response = session.get(url, timeout=timeout)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                self.circuit_breaker._on_success()
                self.rate_limiter.report_success(url, response_time)
                self.stats['successes'] += 1
                return response.text
            elif response.status_code == 404:
                logger.info(f"Page not found (404): {url}")
                self.circuit_breaker._on_success()
                return None
            else:
                logger.warning(f"HTTP {response.status_code} from {url}")
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                self.stats['failures'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Request failed: {e}")
            self.circuit_breaker._on_failure()
            self.rate_limiter.report_failure(url)
            self.stats['failures'] += 1
            return None
    
    def _parse_price(self, text: str) -> Optional[float]:
        """Extract numeric price from text like '29,98 лв.' or '15,33 €'"""
        if not text:
            return None
        match = re.search(r'([\d]+[,.][\d]+)', text.replace(' ', ''))
        if match:
            return float(match.group(1).replace(',', '.'))
        return None
    
    def _parse_discount(self, text: str) -> Optional[int]:
        """Extract discount percentage from text like '-42%'"""
        if not text:
            return None
        match = re.search(r'-(\d+)%', text)
        if match:
            return int(match.group(1))
        return None
    
    def _parse_products(self, html: str, store: str) -> List[BroshuraProduct]:
        """Parse products from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Find all product links/cards
        # broshura.bg structure: each product is in a link with /p/ prefix
        product_links = soup.find_all('a', href=re.compile(r'/p/\d+'))
        
        for link in product_links:
            try:
                # Get product URL
                href = link.get('href', '')
                product_url = f"{self.BASE_URL}{href}" if href.startswith('/') else href
                
                # Get text content
                text = link.get_text(' ', strip=True)
                
                if not text or len(text) < 10:
                    continue
                
                # Parse discount
                discount = self._parse_discount(text)
                
                # Parse prices - look for patterns like "29,98 лв. / 15,33 €"
                prices = re.findall(r'([\d]+[,.][\d]+)\s*(?:лв\.|€)', text)
                
                if len(prices) < 2:
                    continue  # Need at least current price in both currencies
                
                # Extract name - text before price patterns
                name_match = re.match(r'^(.+?)\s*цена\s+само', text, re.IGNORECASE)
                if not name_match:
                    # Try alternative pattern
                    name_match = re.match(r'^-?\d+%\s*(.+?)\s*цена', text, re.IGNORECASE)
                
                if name_match:
                    name = name_match.group(1).strip()
                else:
                    # Fallback: take first part before numbers
                    name = re.split(r'\d', text)[0].strip()
                    if len(name) < 3:
                        continue
                
                # Clean up name
                name = re.sub(r'^-?\d+%\s*', '', name).strip()
                
                # Parse current prices
                price_bgn = float(prices[0].replace(',', '.'))
                price_eur = float(prices[1].replace(',', '.')) if len(prices) > 1 else price_bgn / 1.95583
                
                # Parse old prices if available
                old_price_bgn = None
                old_price_eur = None
                if 'вместо' in text.lower() and len(prices) >= 4:
                    old_price_bgn = float(prices[2].replace(',', '.'))
                    old_price_eur = float(prices[3].replace(',', '.'))
                
                # Parse valid until date
                valid_match = re.search(r'важи до[:\s]*([\d\-\.]+)', text, re.IGNORECASE)
                valid_until = valid_match.group(1) if valid_match else None
                
                products.append(BroshuraProduct(
                    name=name[:100],  # Truncate
                    price_bgn=round(price_bgn, 2),
                    price_eur=round(price_eur, 2),
                    old_price_bgn=round(old_price_bgn, 2) if old_price_bgn else None,
                    old_price_eur=round(old_price_eur, 2) if old_price_eur else None,
                    discount_pct=discount,
                    store=store,
                    valid_until=valid_until,
                    product_url=product_url,
                ))
                
            except Exception as e:
                logger.debug(f"Failed to parse product: {e}")
                continue
        
        return products
    
    def scrape_store(self, store_code: str) -> List[BroshuraProduct]:
        """
        Scrape products for a specific store.
        
        Args:
            store_code: One of 'kaufland', 'lidl', 'billa', 'metro', 'fantastico'
        """
        if store_code not in STORE_MAPPINGS:
            logger.error(f"Unknown store: {store_code}")
            return []
        
        store_info = STORE_MAPPINGS[store_code]
        url = store_info['url']
        display_name = store_info['display_name']
        
        logger.info(f"[Tier 2] Scraping {display_name} from broshura.bg")
        
        html = None
        max_attempts = self.retry_handler.config.max_attempts
        
        for attempt in range(max_attempts):
            html = self._make_request(url)
            if html is not None:
                break
            delay = self.retry_handler.get_delay(attempt)
            logger.info(f"Retry {attempt + 1}/{max_attempts} after {delay:.1f}s")
            time.sleep(delay)
        
        if html is None:
            logger.error(f"Failed to fetch {display_name} from broshura.bg")
            return []
        
        products = self._parse_products(html, display_name)
        logger.info(f"[Tier 2] Scraped {len(products)} products for {display_name}")
        
        return products
    
    def scrape_all_stores(self) -> Dict[str, List[BroshuraProduct]]:
        """Scrape all stores and return products grouped by store."""
        results = {}
        
        for store_code in STORE_MAPPINGS:
            products = self.scrape_store(store_code)
            results[store_code] = products
            self.stats['products_scraped'] += len(products)
        
        return results
    
    def get_stats(self) -> Dict:
        """Get scraper statistics."""
        return {
            **self.stats,
            'tier': self.TIER,
            'circuit_breaker': self.circuit_breaker.stats,
        }


# ============================================
# CLI Interface
# ============================================

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    import argparse
    parser = argparse.ArgumentParser(description='Broshura.bg Tier 2 Scraper')
    parser.add_argument('--store', type=str, help='Specific store to scrape')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Broshura.bg Scraper - Tier 2 Fallback")
    print("=" * 60)
    
    scraper = BroshuraScraper()
    
    if args.store:
        products = scraper.scrape_store(args.store)
        results = {args.store: products}
    else:
        results = scraper.scrape_all_stores()
    
    # Summary
    total = 0
    print("\n📊 Results:")
    print("-" * 40)
    for store, products in results.items():
        print(f"   {store}: {len(products)} products")
        total += len(products)
    print("-" * 40)
    print(f"   Total: {total} products")
    
    # Sample output
    if total > 0:
        print("\n📦 Sample products:")
        all_products = [p for prods in results.values() for p in prods]
        for p in all_products[:10]:
            discount = f"-{p.discount_pct}%" if p.discount_pct else ""
            print(f"   [{p.store}] {p.name[:40]:<40} {p.price_eur:.2f}€ {discount}")
    
    # Save
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    
    for store, products in results.items():
        if products:
            output_file = output_dir / f"broshura_{store}_products.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
            print(f"\n📁 Saved: {output_file}")


if __name__ == "__main__":
    main()
