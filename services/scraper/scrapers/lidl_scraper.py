"""
Lidl.bg Scraper - JSON API Version

Uses the public Lidl API for reliable data extraction.
Fully integrated with scraping infrastructure for anti-detection.

API Discovery: 2026-02-12
Endpoint: https://www.lidl.bg/p/api/gridboxes/BG/bg
"""

import json
import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry
from services.scraper.core.retry_handler import RetryHandler

logger = logging.getLogger(__name__)

# ============================================
# Data Models
# ============================================

@dataclass
class LidlProduct:
    """Product data from Lidl API"""
    product_id: int
    name: str
    brand: Optional[str]
    category: str
    quantity: Optional[str]
    price_eur: float
    price_bgn: float
    old_price_eur: float
    old_price_bgn: float
    discount_pct: int
    image_url: Optional[str]
    product_url: str
    availability: Optional[str]
    internal_code: Optional[str]
    
    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> Optional['LidlProduct']:
        """Parse product from API response"""
        try:
            # Extract price data
            price_data = data.get('price', {})
            if not price_data.get('price'):
                return None
            
            price_eur = float(price_data.get('price', 0))
            price_bgn = float(price_data.get('priceSecond', price_eur * 1.95583))
            old_price_eur = float(price_data.get('oldPrice', 0))
            old_price_bgn = float(price_data.get('oldPriceSecond', old_price_eur * 1.95583))
            
            # Calculate discount
            discount = 0
            if old_price_eur > 0 and old_price_eur > price_eur:
                discount = round((1 - price_eur / old_price_eur) * 100)
            
            # Extract availability
            availability = None
            stock = data.get('stockAvailability', {})
            badges = stock.get('badgeInfo', {}).get('badges', [])
            if badges:
                availability = badges[0].get('text')
            
            # Extract internal codes
            ians = data.get('ians', [])
            internal_code = ians[0] if ians else None
            
            return cls(
                product_id=data.get('productId') or data.get('itemId'),
                name=data.get('fullTitle', ''),
                brand=data.get('brand', {}).get('name'),
                category=data.get('category', 'Без категория'),
                quantity=data.get('keyfacts', {}).get('description'),
                price_eur=price_eur,
                price_bgn=price_bgn,
                old_price_eur=old_price_eur,
                old_price_bgn=old_price_bgn,
                discount_pct=discount,
                image_url=data.get('image'),
                product_url=f"https://www.lidl.bg{data.get('canonicalUrl', '')}",
                availability=availability,
                internal_code=internal_code,
            )
        except Exception as e:
            logger.warning(f"Failed to parse product: {e}")
            return None


# ============================================
# Scraper Class
# ============================================

class LidlScraper:
    """
    Lidl Bulgaria scraper using JSON API.
    
    Fully integrated with scraping infrastructure:
    - SessionManager: rotating sessions with proper headers
    - RateLimiter: adaptive delays to avoid detection
    - CircuitBreaker: fail-fast on persistent errors
    - RetryHandler: automatic retry with backoff
    """
    
    DOMAIN = "lidl.bg"
    BASE_URL = "https://www.lidl.bg"
    API_ENDPOINT = "https://www.lidl.bg/p/api/gridboxes/BG/bg"
    
    # Category URLs for additional products (HTML pages with embedded JSON)
    CATEGORY_URLS = [
        "https://www.lidl.bg/c/lidl-plus-promotsii/a10039565",
        "https://www.lidl.bg/c/hrani/s10012946",
        "https://www.lidl.bg/c/napitki/s10012962",
    ]
    
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
                max_requests=50,  # Rotate more frequently for APIs
                max_age_seconds=1200,  # 20 minutes
            )
        )
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name=self.DOMAIN,
            failure_threshold=3,
            recovery_timeout=60,
            half_open_max_calls=2,
        )
        from services.scraper.core.retry_handler import RetryConfig
        self.retry_handler = retry_handler or RetryHandler(
            config=RetryConfig(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0,
            )
        )
        
        self.stats = {
            'requests': 0,
            'successes': 0,
            'failures': 0,
            'products_scraped': 0,
        }
    
    def _make_request(self, url: str, timeout: int = 30) -> Optional[Dict]:
        """
        Make HTTP request with full infrastructure protection.
        """
        # Check circuit breaker
        if self.circuit_breaker.is_open:
            logger.warning(f"Circuit breaker OPEN for {self.DOMAIN}")
            return None
        
        # Wait for rate limiter
        wait_time = self.rate_limiter.wait(url)
        if wait_time > 0:
            logger.debug(f"Rate limiter: waited {wait_time:.2f}s")
        
        # Get session with proper headers
        session = self.session_manager.get_session(self.DOMAIN)
        
        try:
            self.stats['requests'] += 1
            start_time = time.time()
            
            # Make request through session (includes proper headers)
            response = session.get(url, timeout=timeout)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                # Success - notify circuit breaker
                self.circuit_breaker._on_success()
                self.rate_limiter.report_success(url, response_time)
                self.stats['successes'] += 1
                
                # Parse JSON
                return response.json()
            
            elif response.status_code == 404:
                # 404 is valid (page doesn't exist), not a failure
                logger.info(f"Page not found (404): {url}")
                self.circuit_breaker._on_success()  # Don't trip circuit breaker
                self.rate_limiter.report_success(url, response_time)
                return None
            
            else:
                # HTTP error
                logger.warning(f"HTTP {response.status_code} from {url}")
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                self.session_manager.report_error(self.DOMAIN, response.status_code)
                self.stats['failures'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Request failed: {e}")
            self.circuit_breaker._on_failure()
            self.rate_limiter.report_failure(url)
            self.stats['failures'] += 1
            return None
    
    def _scrape_category_page(self, url: str) -> List[LidlProduct]:
        """
        Scrape products from category page (embedded JSON in HTML).
        Falls back to HTML parsing when API doesn't cover a category.
        """
        import re
        import html
        
        # Check circuit breaker
        if self.circuit_breaker.is_open:
            return []
        
        # Wait for rate limiter
        self.rate_limiter.wait(url)
        session = self.session_manager.get_session(self.DOMAIN)
        
        try:
            self.stats['requests'] += 1
            response = session.get(url, timeout=30)
            
            if response.status_code == 404:
                logger.info(f"Category not found (404): {url}")
                self.circuit_breaker._on_success()  # Don't trip circuit breaker
                return []
            elif response.status_code != 200:
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                return []
            
            self.circuit_breaker._on_success()
            self.rate_limiter.report_success(url)
            self.stats['successes'] += 1
            
            # Parse embedded JSON from HTML
            decoded = html.unescape(response.text)
            products = []
            
            # Split by canonicalUrl to get product chunks
            chunks = decoded.split('"canonicalUrl"')[1:]
            
            for chunk in chunks[:200]:  # Limit chunks to avoid processing navigation items
                try:
                    # Extract product data using regex
                    title_match = re.search(r'"title":"([^"]+)"', chunk)
                    if not title_match or len(title_match.group(1)) < 3:
                        continue
                    
                    name = title_match.group(1)
                    
                    price_match = re.search(r'"price":([\d.]+)', chunk)
                    old_price_match = re.search(r'"oldPrice":([\d.]+)', chunk)
                    
                    if not price_match:
                        continue
                    
                    price_eur = float(price_match.group(1))
                    old_price_eur = float(old_price_match.group(1)) if old_price_match else 0
                    
                    # BGN prices
                    price_bgn_match = re.search(r'"priceSecond":([\d.]+)', chunk)
                    old_bgn_match = re.search(r'"oldPriceSecond":([\d.]+)', chunk)
                    price_bgn = float(price_bgn_match.group(1)) if price_bgn_match else price_eur * 1.95583
                    old_price_bgn = float(old_bgn_match.group(1)) if old_bgn_match else old_price_eur * 1.95583
                    
                    # Product ID
                    id_match = re.search(r'"productId":(\d+)', chunk)
                    product_id = int(id_match.group(1)) if id_match else hash(name) % 10000000
                    
                    # Calculate discount
                    discount = 0
                    if old_price_eur > 0 and old_price_eur > price_eur:
                        discount = round((1 - price_eur / old_price_eur) * 100)
                    
                    # Image
                    img_match = re.search(r'"image":"(https://[^"]+)"', chunk)
                    image_url = img_match.group(1) if img_match else None
                    
                    # URL
                    url_match = re.search(r'^":"(/p/[^"]+)"', chunk)
                    product_url = f"{self.BASE_URL}{url_match.group(1)}" if url_match else ""
                    
                    products.append(LidlProduct(
                        product_id=product_id,
                        name=name,
                        brand=None,
                        category="Lidl Plus",
                        quantity=None,
                        price_eur=price_eur,
                        price_bgn=price_bgn,
                        old_price_eur=old_price_eur,
                        old_price_bgn=old_price_bgn,
                        discount_pct=discount,
                        image_url=image_url,
                        product_url=product_url,
                        availability=None,
                        internal_code=None,
                    ))
                except Exception as e:
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Failed to scrape category {url}: {e}")
            self.circuit_breaker._on_failure()
            self.stats['failures'] += 1
            return []
    
    def scrape_products(self) -> List[LidlProduct]:
        """
        Scrape all products from Lidl API.
        
        Returns:
            List of LidlProduct objects
        """
        logger.info(f"Starting Lidl scrape from {self.API_ENDPOINT}")
        
        # Use retry handler for resilience
        data = None
        max_attempts = self.retry_handler.config.max_attempts
        for attempt in range(max_attempts):
            data = self._make_request(self.API_ENDPOINT)
            if data is not None:
                break
            
            delay = self.retry_handler.get_delay(attempt)
            logger.info(f"Retry {attempt + 1}/{max_attempts} after {delay:.1f}s")
            time.sleep(delay)
        
        if data is None:
            logger.error("Failed to fetch Lidl API data")
            return []
        
        # Parse products
        products = []
        seen_ids = set()
        
        for item in data:
            if not isinstance(item, dict):
                continue
            
            product = LidlProduct.from_api(item)
            if product and product.product_id not in seen_ids:
                products.append(product)
                seen_ids.add(product.product_id)
        
        # Also scrape category pages for more products
        logger.info("Scraping category pages for additional products...")
        for cat_url in self.CATEGORY_URLS:
            cat_products = self._scrape_category_page(cat_url)
            for p in cat_products:
                if p.product_id not in seen_ids:
                    products.append(p)
                    seen_ids.add(p.product_id)
            logger.info(f"  {cat_url.split('/')[-1]}: +{len(cat_products)} products")
        
        self.stats['products_scraped'] = len(products)
        logger.info(f"Scraped {len(products)} total products from Lidl")
        
        return products
    
    def get_stats(self) -> Dict:
        """Get scraper statistics"""
        return {
            **self.stats,
            'circuit_breaker': self.circuit_breaker.stats,
            'rate_limiter': self.rate_limiter.get_stats(self.DOMAIN),
            'session': self.session_manager.get_all_stats().get(self.DOMAIN, {}),
        }


# ============================================
# CLI Interface
# ============================================

def main():
    """Run scraper from command line"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("Lidl.bg Scraper - JSON API Version")
    print("=" * 60)
    
    scraper = LidlScraper()
    products = scraper.scrape_products()
    
    if not products:
        print("\n❌ No products scraped")
        return
    
    print(f"\n✅ Scraped {len(products)} products\n")
    
    # Sample output
    print("SAMPLE PRODUCTS:")
    print("-" * 60)
    for p in products[:15]:
        discount = f"{p.discount_pct:>3}% off" if p.discount_pct > 0 else "       "
        print(f"{p.name[:40]:<40} | {p.price_eur:>6.2f}€ | {discount}")
    
    # Save to file
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "lidl_products.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to {output_file}")
    
    # Stats
    stats = scraper.get_stats()
    print(f"\n📊 Stats:")
    print(f"   Requests: {stats['requests']}")
    print(f"   Successes: {stats['successes']}")
    print(f"   Failures: {stats['failures']}")
    print(f"   Products: {stats['products_scraped']}")
    
    # Discount analysis
    promo_products = [p for p in products if p.discount_pct > 0]
    if promo_products:
        avg_discount = sum(p.discount_pct for p in promo_products) / len(promo_products)
        max_discount = max(p.discount_pct for p in promo_products)
        print(f"\n🏷️ Promotions:")
        print(f"   Products on sale: {len(promo_products)}")
        print(f"   Avg discount: {avg_discount:.1f}%")
        print(f"   Max discount: {max_discount}%")


if __name__ == "__main__":
    main()
