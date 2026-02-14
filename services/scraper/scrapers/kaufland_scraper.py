"""
Kaufland.bg Scraper - Infrastructure-Integrated Version

Extracts product data from weekly offers pages.
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
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)


# ============================================
# Data Models
# ============================================

@dataclass
class KauflandProduct:
    """Product data from Kaufland"""
    name: str
    quantity: Optional[str]
    price_eur: Optional[float]
    price_bgn: Optional[float]
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    category: Optional[str] = None
    product_url: Optional[str] = None


# ============================================
# Helper Functions
# ============================================

def parse_price(text: str) -> Optional[float]:
    """Extract numeric price from text like '1,78 €' or '3,48 ЛВ.'"""
    if not text:
        return None
    match = re.search(r'([\d]+[,.][\d]+)', text.replace(' ', ''))
    if match:
        return float(match.group(1).replace(',', '.'))
    return None


def parse_discount(text: str) -> Optional[int]:
    """Extract discount percentage from text like '-61%'"""
    if not text:
        return None
    match = re.search(r'-(\d+)%', text)
    if match:
        return int(match.group(1))
    return None


# ============================================
# Scraper Class
# ============================================

class KauflandScraper:
    """
    Kaufland Bulgaria scraper using HTML parsing.
    
    Fully integrated with scraping infrastructure:
    - SessionManager: rotating sessions with proper headers
    - RateLimiter: adaptive delays to avoid detection
    - CircuitBreaker: fail-fast on persistent errors
    - RetryHandler: automatic retry with backoff
    """
    
    DOMAIN = "kaufland.bg"
    BASE_URL = "https://www.kaufland.bg"
    
    # Offer pages to scrape
    # Current Kaufland offer pages (updated 2026-02-14)
    # Note: ot-sryada and vikend pages removed, oferti.html is the main listing
    OFFER_URLS = [
        "https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html",
        "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html",
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
                max_requests=30,  # Rotate frequently
                max_age_seconds=900,  # 15 minutes
            )
        )
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name=self.DOMAIN,
            failure_threshold=3,
            recovery_timeout=90,  # Longer for Kaufland
            half_open_max_calls=2,
        )
        self.retry_handler = retry_handler or RetryHandler(
            config=RetryConfig(
                max_attempts=3,
                base_delay=3.0,  # Longer delays for Kaufland
                max_delay=60.0,
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
                # 404 is a valid response (page doesn't exist), not a failure
                logger.info(f"Page not found (404): {url}")
                self.circuit_breaker._on_success()  # Don't trip circuit breaker
                self.rate_limiter.report_success(url, response_time)
                return None  # But still return None (no content)
            
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
    
    def _parse_products(self, html: str, source_url: str) -> List[KauflandProduct]:
        """Parse products from HTML content."""
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Find all product title elements
        titles = soup.select('div.k-product-tile__title')
        
        for title_div in titles:
            try:
                # Navigate to parent tile
                tile = title_div.parent
                while tile and not any('k-product-tile' == c for c in tile.get('class', [])):
                    tile = tile.parent
                    if tile is None or tile.name == 'body':
                        tile = title_div.parent.parent.parent.parent
                        break
                
                if not tile:
                    continue
                
                name = title_div.get_text(strip=True)
                if not name:
                    continue
                
                # Quantity/subtitle
                subtitle = tile.select_one('div.k-product-tile__subtitle')
                quantity = subtitle.get_text(strip=True) if subtitle else None
                
                # Get both price tags (EUR and BGN)
                pricetags = tile.select('div.k-product-tile__pricetag')
                
                price_eur = old_price_eur = None
                price_bgn = old_price_bgn = None
                discount_pct = None
                
                for pt in pricetags:
                    price_div = pt.select_one('div.k-price-tag__price')
                    old_price_div = pt.select_one('div.k-price-tag__old-price')
                    discount_div = pt.select_one('div.k-price-tag__discount')
                    
                    if price_div:
                        text = price_div.get_text(strip=True)
                        if '€' in text:
                            price_eur = parse_price(text)
                        elif 'ЛВ' in text:
                            price_bgn = parse_price(text)
                    
                    if old_price_div:
                        text = old_price_div.get_text(strip=True)
                        if '€' in text:
                            old_price_eur = parse_price(text)
                        elif 'ЛВ' in text:
                            old_price_bgn = parse_price(text)
                    
                    if discount_div and not discount_pct:
                        discount_pct = parse_discount(discount_div.get_text(strip=True))
                
                # Image
                img = tile.select_one('img.k-product-tile__main-image')
                image_url = None
                if img:
                    image_url = img.get('src') or img.get('data-src')
                
                # Product link
                link = tile.select_one('a.k-product-tile__link')
                product_url = None
                if link and link.get('href'):
                    href = link.get('href')
                    if href.startswith('/'):
                        product_url = f"{self.BASE_URL}{href}"
                    else:
                        product_url = href
                
                products.append(KauflandProduct(
                    name=name,
                    quantity=quantity,
                    price_eur=price_eur,
                    price_bgn=price_bgn,
                    old_price_eur=old_price_eur,
                    old_price_bgn=old_price_bgn,
                    discount_pct=discount_pct,
                    image_url=image_url,
                    product_url=product_url,
                ))
                
            except Exception as e:
                logger.debug(f"Failed to parse product: {e}")
                continue
        
        return products
    
    def scrape_page(self, url: str) -> List[KauflandProduct]:
        """
        Scrape a single Kaufland offer page.
        
        Args:
            url: URL of the offers page
            
        Returns:
            List of KauflandProduct objects
        """
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
            return []
        
        products = self._parse_products(html, url)
        logger.info(f"  Found {len(products)} products")
        
        return products
    
    def scrape_all_offers(self) -> List[KauflandProduct]:
        """
        Scrape all offer pages.
        
        Returns:
            Combined list of all products (deduplicated by name)
        """
        logger.info("Starting Kaufland full scrape...")
        
        all_products = []
        seen_names = set()
        
        for url in self.OFFER_URLS:
            products = self.scrape_page(url)
            
            for p in products:
                if p.name not in seen_names:
                    all_products.append(p)
                    seen_names.add(p.name)
        
        self.stats['products_scraped'] = len(all_products)
        logger.info(f"Scraped {len(all_products)} total unique products from Kaufland")
        
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
    print("Kaufland.bg Scraper - Infrastructure-Integrated")
    print("=" * 60)
    
    scraper = KauflandScraper()
    products = scraper.scrape_all_offers()
    
    if not products:
        print("\n❌ No products scraped")
        return
    
    print(f"\n✅ Scraped {len(products)} unique products\n")
    
    # Sample output
    print("SAMPLE PRODUCTS WITH PRICES:")
    print("-" * 60)
    
    count = 0
    for p in products:
        if p.price_eur and count < 15:
            discount = f"{p.discount_pct:>3}% off" if p.discount_pct else "       "
            print(f"{p.name[:40]:<40} | {p.price_eur:>6.2f}€ | {discount}")
            count += 1
    
    # Save to file
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "kaufland_products.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to {output_file}")
    
    # Stats
    stats = scraper.get_stats()
    with_prices = [p for p in products if p.price_eur]
    with_discount = [p for p in products if p.discount_pct]
    
    print(f"\n📊 Stats:")
    print(f"   Requests: {stats['requests']}")
    print(f"   Successes: {stats['successes']}")
    print(f"   Failures: {stats['failures']}")
    print(f"   Total products: {len(products)}")
    print(f"   With EUR price: {len(with_prices)}")
    print(f"   With discount: {len(with_discount)}")


if __name__ == "__main__":
    main()
