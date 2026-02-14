"""
Lidl.bg Scraper - FIXED VERSION

Fixes:
1. Price validation - reject schema indices (>100€ for groceries suspicious, >500€ definitely wrong)
2. Old price validation - must be reasonable (< 5x current price)
3. Discount validation - reject >80% as garbage data
4. Better regex - match nested price object structure when possible
"""

import json
import logging
import re
import time
import html
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler

logger = logging.getLogger(__name__)

# ============================================
# Price Validation Constants
# ============================================
MAX_REASONABLE_PRICE = 200  # Most grocery items < 200€
MAX_SCHEMA_INDEX = 100      # Schema indices are typically 100-1500
MAX_OLD_PRICE_RATIO = 4     # old_price should be at most 4x current
MAX_DISCOUNT_PCT = 75       # Discounts > 75% are suspicious for groceries


# ============================================
# Data Models
# ============================================

@dataclass
class LidlProduct:
    """Product data from Lidl"""
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
        """Parse product from gridboxes API response"""
        try:
            price_data = data.get('price', {})
            if not price_data.get('price'):
                return None
            
            price_eur = float(price_data.get('price', 0))
            price_bgn = float(price_data.get('priceSecond', price_eur * 1.95583))
            old_price_eur = float(price_data.get('oldPrice', 0))
            old_price_bgn = float(price_data.get('oldPriceSecond', old_price_eur * 1.95583))
            
            # === VALIDATION ===
            # Skip if price looks like schema index
            if price_eur > MAX_REASONABLE_PRICE:
                logger.debug(f"Skipping product with price {price_eur}€ (likely schema index)")
                return None
            
            # Validate old_price
            if old_price_eur > 0:
                # Check if old_price is reasonable
                if old_price_eur > MAX_REASONABLE_PRICE:
                    logger.debug(f"Resetting garbage old_price {old_price_eur}€")
                    old_price_eur = 0
                    old_price_bgn = 0
                elif old_price_eur > price_eur * MAX_OLD_PRICE_RATIO:
                    logger.debug(f"Resetting old_price {old_price_eur}€ (>{MAX_OLD_PRICE_RATIO}x current)")
                    old_price_eur = 0
                    old_price_bgn = 0
            
            # Calculate discount with validation
            discount = 0
            if old_price_eur > 0 and old_price_eur > price_eur:
                discount = round((1 - price_eur / old_price_eur) * 100)
                if discount > MAX_DISCOUNT_PCT:
                    logger.debug(f"Discount {discount}% too high, resetting old_price")
                    old_price_eur = 0
                    old_price_bgn = 0
                    discount = 0
            
            # Extract other fields
            availability = None
            stock = data.get('stockAvailability', {})
            badges = stock.get('badgeInfo', {}).get('badges', [])
            if badges:
                availability = badges[0].get('text')
            
            ians = data.get('ians', [])
            internal_code = ians[0] if ians else None
            
            return cls(
                product_id=data.get('productId') or data.get('itemId'),
                name=data.get('fullTitle', ''),
                brand=data.get('brand', {}).get('name') if isinstance(data.get('brand'), dict) else None,
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


class LidlScraperFixed:
    """
    Fixed Lidl Bulgaria scraper with proper validation.
    """
    
    DOMAIN = "lidl.bg"
    BASE_URL = "https://www.lidl.bg"
    API_ENDPOINT = "https://www.lidl.bg/p/api/gridboxes/BG/bg"
    
    # Only category pages with real pre-rendered product data
    # (Schema-only pages are excluded)
    CATEGORY_URLS = [
        "https://www.lidl.bg/c/lidl-plus-promotsii/a10039565",
    ]
    
    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        rate_limiter: Optional[DomainRateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        retry_handler: Optional[RetryHandler] = None,
    ):
        self.session_manager = session_manager or SessionManager(
            config=SessionConfig(max_requests=50, max_age_seconds=1200)
        )
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name=self.DOMAIN, failure_threshold=3, recovery_timeout=60
        )
        from services.scraper.core.retry_handler import RetryConfig
        self.retry_handler = retry_handler or RetryHandler(
            config=RetryConfig(max_attempts=3, base_delay=2.0, max_delay=30.0)
        )
        self.stats = {'requests': 0, 'successes': 0, 'failures': 0, 'products_scraped': 0, 'rejected': 0}
    
    def _make_request(self, url: str, timeout: int = 30) -> Optional[Dict]:
        """Make HTTP request with infrastructure protection."""
        if self.circuit_breaker.is_open:
            logger.warning(f"Circuit breaker OPEN for {self.DOMAIN}")
            return None
        
        wait_time = self.rate_limiter.wait(url)
        if wait_time > 0:
            logger.debug(f"Rate limiter: waited {wait_time:.2f}s")
        
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
                return response.json()
            elif response.status_code == 404:
                logger.info(f"Page not found: {url}")
                self.circuit_breaker._on_success()
                return None
            else:
                logger.warning(f"HTTP {response.status_code} from {url}")
                self.circuit_breaker._on_failure()
                self.stats['failures'] += 1
                return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            self.circuit_breaker._on_failure()
            self.stats['failures'] += 1
            return None
    
    def _validate_price_data(self, price_eur: float, old_price_eur: float, name: str) -> tuple:
        """
        Validate price data and return cleaned values.
        Returns: (price_eur, old_price_eur, discount, is_valid)
        """
        # Check if price looks like schema index (whole number > 100)
        if price_eur > MAX_SCHEMA_INDEX and price_eur == int(price_eur):
            logger.debug(f"Rejecting '{name}': price {price_eur}€ looks like schema index")
            return (0, 0, 0, False)
        
        # Check reasonable price range
        if price_eur > MAX_REASONABLE_PRICE:
            logger.debug(f"Rejecting '{name}': price {price_eur}€ exceeds max reasonable")
            return (0, 0, 0, False)
        
        if price_eur <= 0:
            return (0, 0, 0, False)
        
        # Validate old_price
        validated_old_price = old_price_eur
        if old_price_eur > 0:
            # Check if old_price is schema index
            if old_price_eur > MAX_SCHEMA_INDEX and old_price_eur == int(old_price_eur):
                logger.debug(f"Resetting old_price {old_price_eur}€ for '{name}' (schema index)")
                validated_old_price = 0
            # Check ratio
            elif old_price_eur > price_eur * MAX_OLD_PRICE_RATIO:
                logger.debug(f"Resetting old_price {old_price_eur}€ for '{name}' (>{MAX_OLD_PRICE_RATIO}x)")
                validated_old_price = 0
            # Check absolute max
            elif old_price_eur > MAX_REASONABLE_PRICE:
                logger.debug(f"Resetting old_price {old_price_eur}€ for '{name}' (>max reasonable)")
                validated_old_price = 0
        
        # Calculate discount
        discount = 0
        if validated_old_price > 0 and validated_old_price > price_eur:
            discount = round((1 - price_eur / validated_old_price) * 100)
            if discount > MAX_DISCOUNT_PCT:
                logger.debug(f"Discount {discount}% too high for '{name}', resetting")
                validated_old_price = 0
                discount = 0
        
        return (price_eur, validated_old_price, discount, True)
    
    def _scrape_category_page(self, url: str) -> List[LidlProduct]:
        """
        Scrape products from category page with FIXED validation.
        """
        if self.circuit_breaker.is_open:
            return []
        
        self.rate_limiter.wait(url)
        session = self.session_manager.get_session(self.DOMAIN)
        
        try:
            self.stats['requests'] += 1
            response = session.get(url, timeout=30)
            
            if response.status_code == 404:
                logger.info(f"Category not found: {url}")
                self.circuit_breaker._on_success()
                return []
            elif response.status_code != 200:
                self.circuit_breaker._on_failure()
                self.stats['failures'] += 1
                return []
            
            self.circuit_breaker._on_success()
            self.stats['successes'] += 1
            
            decoded = html.unescape(response.text)
            products = []
            
            # Count real titles to detect schema-only pages
            real_titles = re.findall(r'"fullTitle":"([^"]{5,})"', decoded)
            if len(real_titles) < 3:
                logger.info(f"Skipping schema-only page: {url}")
                return []
            
            # Try to find actual product JSON blocks first
            # Look for complete price objects: "price":{"price":X.XX,...}
            price_objects = re.findall(
                r'"price":\{"[^}]*"price":([\d.]+)[^}]*(?:"oldPrice":([\d.]+))?[^}]*\}',
                decoded
            )
            
            if price_objects:
                logger.debug(f"Found {len(price_objects)} structured price objects")
            
            # Split by canonicalUrl to get product chunks
            chunks = decoded.split('"canonicalUrl"')[1:]
            
            for chunk in chunks[:200]:
                try:
                    # Extract title
                    title_match = re.search(r'"(?:fullTitle|title)":"([^"]+)"', chunk)
                    if not title_match or len(title_match.group(1)) < 3:
                        continue
                    
                    name = title_match.group(1)
                    
                    # Try to match nested price object first (more reliable)
                    nested_price = re.search(
                        r'"price":\{[^}]*"price":([\d.]+)',
                        chunk
                    )
                    if nested_price:
                        price_eur = float(nested_price.group(1))
                    else:
                        # Fallback to simple match
                        price_match = re.search(r'"price":([\d.]+)', chunk)
                        if not price_match:
                            continue
                        price_eur = float(price_match.group(1))
                    
                    # Extract old_price (same approach)
                    nested_old = re.search(r'"price":\{[^}]*"oldPrice":([\d.]+)', chunk)
                    if nested_old:
                        old_price_eur = float(nested_old.group(1))
                    else:
                        old_match = re.search(r'"oldPrice":([\d.]+)', chunk)
                        old_price_eur = float(old_match.group(1)) if old_match else 0
                    
                    # === VALIDATION ===
                    price_eur, old_price_eur, discount, is_valid = self._validate_price_data(
                        price_eur, old_price_eur, name
                    )
                    
                    if not is_valid:
                        self.stats['rejected'] += 1
                        continue
                    
                    # BGN prices
                    bgn_match = re.search(r'"priceSecond":([\d.]+)', chunk)
                    price_bgn = float(bgn_match.group(1)) if bgn_match else price_eur * 1.95583
                    
                    old_bgn_match = re.search(r'"oldPriceSecond":([\d.]+)', chunk)
                    old_price_bgn = float(old_bgn_match.group(1)) if old_bgn_match and old_price_eur > 0 else old_price_eur * 1.95583
                    
                    # Product ID
                    id_match = re.search(r'"productId":(\d+)', chunk)
                    product_id = int(id_match.group(1)) if id_match else hash(name) % 10000000
                    
                    # Image
                    img_match = re.search(r'"image":"(https://[^"]+)"', chunk)
                    image_url = img_match.group(1) if img_match else None
                    
                    # URL
                    url_match = re.search(r'^:"(/p/[^"]+)"', chunk)
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
            
            logger.info(f"Scraped {len(products)} valid products from {url}")
            return products
            
        except Exception as e:
            logger.error(f"Failed to scrape category {url}: {e}")
            self.circuit_breaker._on_failure()
            self.stats['failures'] += 1
            return []
    
    def scrape_products(self) -> List[LidlProduct]:
        """Scrape all products from Lidl."""
        logger.info(f"Starting Lidl scrape")
        
        # Try gridboxes endpoint first
        data = None
        for attempt in range(3):
            data = self._make_request(self.API_ENDPOINT)
            if data is not None:
                break
            time.sleep(2 * (attempt + 1))
        
        products = []
        seen_ids = set()
        
        # Parse gridboxes response
        if data:
            for item in data:
                if not isinstance(item, dict):
                    continue
                product = LidlProduct.from_api(item)
                if product and product.product_id not in seen_ids:
                    products.append(product)
                    seen_ids.add(product.product_id)
            logger.info(f"Got {len(products)} products from gridboxes")
        
        # Scrape category pages
        for cat_url in self.CATEGORY_URLS:
            cat_products = self._scrape_category_page(cat_url)
            for p in cat_products:
                if p.product_id not in seen_ids:
                    products.append(p)
                    seen_ids.add(p.product_id)
        
        self.stats['products_scraped'] = len(products)
        logger.info(f"Total: {len(products)} valid products, {self.stats['rejected']} rejected")
        
        return products
    
    def get_stats(self) -> Dict:
        return self.stats


def main():
    """Run fixed scraper"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("=" * 60)
    print("Lidl.bg Scraper - FIXED VERSION")
    print("=" * 60)
    
    scraper = LidlScraperFixed()
    products = scraper.scrape_products()
    
    if not products:
        print("\n❌ No products scraped")
        return
    
    print(f"\n✅ Scraped {len(products)} valid products\n")
    
    # Show sample
    print("SAMPLE PRODUCTS:")
    print("-" * 60)
    for p in products[:15]:
        discount = f"{p.discount_pct:>3}% off" if p.discount_pct > 0 else "       "
        old = f"(was {p.old_price_eur:.2f}€)" if p.old_price_eur > 0 else ""
        print(f"{p.name[:35]:<35} | {p.price_eur:>6.2f}€ {old} {discount}")
    
    # Stats
    stats = scraper.get_stats()
    print(f"\n📊 Stats:")
    print(f"   Products: {stats['products_scraped']}")
    print(f"   Rejected: {stats['rejected']}")
    print(f"   Requests: {stats['requests']}")
    
    # Save
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "lidl_products_fixed.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to {output_file}")


if __name__ == "__main__":
    main()
