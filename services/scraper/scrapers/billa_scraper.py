"""
Billa Scraper - Infrastructure-Integrated Version

Scrapes from ssbbilla.site (accessibility version of Billa).
Uses full scraping infrastructure for anti-detection.
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
# Add project root to path (4 levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
assert (PROJECT_ROOT / "services").exists(), f"Invalid project root: {PROJECT_ROOT}"
sys.path.insert(0, str(PROJECT_ROOT))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)

# ============================================
# Constants
# ============================================

# EUR/BGN official fixed rate (Bulgaria pegged to EUR since 1997)
EUR_BGN_RATE = 1.95583

# Discount validation range
# 70% max because higher discounts are usually data errors or "100% Арабика" false positives
# Real clearance sales rarely exceed 60-70%
MAX_REASONABLE_DISCOUNT = 70
MIN_DISCOUNT = 1

# Product name filters - these are legal/terms text, not actual products
EXCLUDED_NAME_TERMS = ['Разбир', 'условията']


# ============================================
# Data Models
# ============================================

@dataclass
class BillaProduct:
    """Product data from Billa"""
    name: str
    quantity: Optional[str]
    price_eur: float
    price_bgn: float
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    category: str = "Billa"


# ============================================
# Scraper Class
# ============================================

class BillaScraper:
    """
    Billa Bulgaria scraper using ssbbilla.site.
    
    ssbbilla.site is the accessibility version of Billa's website,
    which is more reliable for scraping and has structured data.
    
    Fully integrated with scraping infrastructure:
    - SessionManager: rotating sessions with proper headers
    - RateLimiter: adaptive delays to avoid detection
    - CircuitBreaker: fail-fast on persistent errors
    - RetryHandler: automatic retry with backoff
    """
    
    DOMAIN = "ssbbilla.site"
    BASE_URL = "https://ssbbilla.site"
    
    # Pages to scrape
    # All available brochures on ssbbilla.site (accessibility version)
    # sedmichna = weekly, predstoyashta = upcoming, proteinov = special
    CATALOG_URLS = [
        "https://ssbbilla.site/catalog/sedmichna-broshura",
        "https://ssbbilla.site/catalog/predstoyashta-broshura",  # May be empty
        "https://ssbbilla.site/catalog/proteinov-izbor-jan-2026",  # May be empty/seasonal
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
                max_requests=50,  # ssbbilla.site is more lenient
                max_age_seconds=1200,  # 20 minutes
            )
        )
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name=self.DOMAIN,
            failure_threshold=5,  # More tolerant
            recovery_timeout=60,
            half_open_max_calls=3,
        )
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
    
    def _make_request(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        Make HTTP request with full infrastructure protection.
        Returns HTML content or None on failure.
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
            
            # Make request through session
            response = session.get(url, timeout=timeout)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                self.circuit_breaker._on_success()
                self.rate_limiter.report_success(url, response_time)
                self.stats['successes'] += 1
                return response.text
            
            elif response.status_code == 404:
                # 404 is valid (page doesn't exist), not a failure
                logger.info(f"Page not found (404): {url}")
                self.circuit_breaker._on_success()  # Don't trip circuit breaker
                self.rate_limiter.report_success(url, response_time)
                return None
            
            else:
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
    
    def _parse_products(self, html: str) -> List[BillaProduct]:
        """Parse products from HTML content."""
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        product_divs = soup.find_all(class_='product')
        
        for div in product_divs:
            try:
                # Get product name
                name_el = div.find(class_='actualProduct')
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                
                # Skip headers and non-products
                if not name or name in ['Billa', ''] or len(name) < 5:
                    continue
                if any(term in name for term in EXCLUDED_NAME_TERMS):
                    continue
                
                # Get all prices (span.price elements)
                price_spans = div.find_all(class_='price')
                currency_spans = div.find_all(class_='currency')
                
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
                    except (ValueError, AttributeError) as e:
                        logger.debug(f"Price parse failed: {e}")
                        continue
                
                # Get discount
                discount_el = div.find(class_='discount')
                discount = None
                if discount_el:
                    # Look for discount pattern like "-XX%" or "XX%"
                    discount_text = discount_el.get_text()
                    match = re.search(r'-?\s*(\d{1,2})\s*%', discount_text)
                    if match:
                        discount = int(match.group(1))
                        # Validate: discount must be in reasonable range
                        if not (MIN_DISCOUNT <= discount <= MAX_REASONABLE_DISCOUNT):
                            logger.debug(f"Discount {discount}% outside valid range {MIN_DISCOUNT}-{MAX_REASONABLE_DISCOUNT}%")
                            discount = None
                
                # Assign prices (first = old, second = new for this structure)
                # Assign EUR prices - ensure old_price > current_price
                if len(prices_eur) >= 2:
                    # Sort to ensure old (higher) price is first
                    if prices_eur[0] > prices_eur[1]:
                        old_price_eur, price_eur = prices_eur[0], prices_eur[1]
                    else:
                        old_price_eur, price_eur = prices_eur[1], prices_eur[0]
                elif len(prices_eur) == 1:
                    price_eur = prices_eur[0]
                    old_price_eur = None
                else:
                    price_eur = 0
                    old_price_eur = None
                
                # Assign BGN prices - ensure old_price > current_price
                if len(prices_bgn) >= 2:
                    if prices_bgn[0] > prices_bgn[1]:
                        old_price_bgn, price_bgn = prices_bgn[0], prices_bgn[1]
                    else:
                        old_price_bgn, price_bgn = prices_bgn[1], prices_bgn[0]
                elif len(prices_bgn) == 1:
                    price_bgn = prices_bgn[0]
                    old_price_bgn = None
                else:
                    # Calculate BGN from EUR using fixed rate (BGN pegged to EUR)
                    if price_eur:
                        logger.debug(f"No BGN price for '{name[:30]}...', calculating from EUR")
                    price_bgn = round(price_eur * EUR_BGN_RATE, 2) if price_eur else 0
                    old_price_bgn = None
                
                if price_eur > 0 or price_bgn > 0:
                    # Validate discount: must have old_price to have a discount
                    validated_discount = discount
                    if discount and not old_price_eur and not old_price_bgn:
                        validated_discount = None  # No discount without old price
                    
                    products.append(BillaProduct(
                        name=name[:100],  # Truncate long names
                        quantity=None,
                        price_eur=round(price_eur, 2),
                        price_bgn=round(price_bgn, 2),
                        old_price_eur=round(old_price_eur, 2) if old_price_eur else None,
                        old_price_bgn=round(old_price_bgn, 2) if old_price_bgn else None,
                        discount_pct=validated_discount,
                        image_url=None,
                    ))
                    
            except Exception as e:
                logger.debug(f"Failed to parse product: {e}")
                continue
        
        return products
    
    def scrape_products(self) -> List[BillaProduct]:
        """
        Scrape all products from Billa.
        
        Returns:
            List of BillaProduct objects
        """
        logger.info("Starting Billa scrape from ssbbilla.site")
        
        all_products = []
        seen_names = set()
        
        for url in self.CATALOG_URLS:
            logger.info(f"Scraping: {url}")
            
            # Use retry handler for resilience
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
                logger.error(f"Failed to fetch {url}")
                continue
            
            products = self._parse_products(html)
            
            for p in products:
                if p.name not in seen_names:
                    all_products.append(p)
                    seen_names.add(p.name)
            
            logger.info(f"  Found {len(products)} products")
        
        self.stats['products_scraped'] = len(all_products)
        logger.info(f"Scraped {len(all_products)} total products from Billa")
        
        return all_products
    
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
    print("Billa Scraper - Infrastructure-Integrated")
    print("(via ssbbilla.site)")
    print("=" * 60)
    
    scraper = BillaScraper()
    products = scraper.scrape_products()
    
    if not products:
        print("\n❌ No products scraped")
        return
    
    print(f"\n✅ Scraped {len(products)} products\n")
    
    # Sample output
    print("SAMPLE PRODUCTS:")
    print("-" * 60)
    for p in products[:15]:
        discount_str = f"{p.discount_pct}% off" if p.discount_pct else "-"
        print(f"{p.name[:40]:<40} | {p.price_eur:>6.2f}€ | {discount_str}")
    
    # Save to file
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "billa_products.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to {output_file}")
    
    # Stats
    stats = scraper.get_stats()
    with_discount = [p for p in products if p.discount_pct]
    avg_discount = sum(p.discount_pct for p in with_discount) / len(with_discount) if with_discount else 0
    
    print(f"\n📊 Stats:")
    print(f"   Requests: {stats['requests']}")
    print(f"   Successes: {stats['successes']}")
    print(f"   Failures: {stats['failures']}")
    print(f"   Total products: {len(products)}")
    print(f"   With discount: {len(with_discount)}")
    print(f"   Avg discount: {avg_discount:.1f}%")


if __name__ == "__main__":
    main()
