#!/usr/bin/env python3
"""
Lidl.bg Sitemap Scraper - BULLETPROOF VERSION

Uses the product sitemap to discover all 800+ products,
then fetches details from individual product pages.

ANTI-DETECTION FEATURES:
- Random URL order (no predictable patterns)
- Checkpoint/resume capability (survives interruption)
- Coffee breaks every N requests
- Referer chain simulation
- Decoy homepage requests
- Full infrastructure integration (rate limiter, circuit breaker, etc.)

Sitemap URL: https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz
"""

import gzip
import json
import logging
import pickle
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from urllib.parse import urlparse

import requests

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz"
DOMAIN = "www.lidl.bg"

# Anti-detection configuration
COFFEE_BREAK_INTERVAL = 50  # Take break every N requests
COFFEE_BREAK_MIN = 15  # Minimum break duration (seconds)
COFFEE_BREAK_MAX = 45  # Maximum break duration (seconds)
CHECKPOINT_INTERVAL = 10  # Save progress every N products
DECOY_PROBABILITY = 0.03  # 3% chance of decoy request

# Decoy URLs to visit occasionally (appear more human)
DECOY_URLS = [
    "https://www.lidl.bg/",
    "https://www.lidl.bg/c/lidl-plus-promotsii/a10039565",
    "https://www.lidl.bg/c/khrani-i-napitki/s10068374",
    "https://www.lidl.bg/c/dom-i-obzavezhdane/s10068371",
]


@dataclass
class LidlProduct:
    """Product data from Lidl"""
    product_id: str
    name: str
    price_eur: Optional[float]
    price_bgn: Optional[float]
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    product_url: str
    category: Optional[str]
    description: Optional[str]
    brand: Optional[str]


class LidlSitemapScraper:
    """
    Bulletproof Lidl product scraper with anti-detection features.
    
    Features:
    - Shuffled URL order to avoid predictable patterns
    - Checkpoint/resume capability for long runs
    - Periodic coffee breaks to appear human
    - Referer chain simulation
    - Decoy requests to homepage/categories
    """
    
    def __init__(self, checkpoint_dir: Optional[Path] = None):
        # Infrastructure components
        self.session_manager = SessionManager(
            config=SessionConfig(
                max_requests=50,  # More frequent rotation for safety
                max_age_seconds=900,  # 15 minutes max session life
            )
        )
        self.rate_limiter = DomainRateLimiter()
        self.circuit_breaker = CircuitBreaker(
            name=DOMAIN,
            failure_threshold=5,
            recovery_timeout=120,  # 2 minutes recovery
        )
        self.retry_handler = RetryHandler(
            config=RetryConfig(
                max_attempts=3,
                base_delay=5.0,
                max_delay=60.0,
                jitter='full',
            )
        )
        
        # Checkpoint system
        self.checkpoint_dir = checkpoint_dir or Path(__file__).parent.parent / "data" / "checkpoints"
        self.checkpoint_file = self.checkpoint_dir / "lidl_sitemap_checkpoint.pkl"
        self.completed_urls: Set[str] = self._load_checkpoint()
        
        # Referer chain tracking
        self.last_url: Optional[str] = "https://www.lidl.bg/"  # Start from homepage
        
        # Failed URL tracking (for retry limits)
        self.url_retry_counts: Dict[str, int] = {}
        self.MAX_RETRIES_PER_URL = 3
        
        # Statistics
        self.stats = {
            'urls_found': 0,
            'urls_skipped': 0,  # From checkpoint
            'products_scraped': 0,
            'failures': 0,
            'retries': 0,
            'gave_up': 0,  # URLs that exceeded retry limit
            'coffee_breaks': 0,
            'decoy_requests': 0,
            'session_rotations': 0,
        }
    
    def _load_checkpoint(self) -> Set[str]:
        """Load completed URLs from checkpoint file"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'rb') as f:
                    data = pickle.load(f)
                    logger.info(f"Loaded checkpoint: {len(data)} URLs already completed")
                    return data
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
        return set()
    
    def _save_checkpoint(self):
        """Save completed URLs to checkpoint file"""
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_file, 'wb') as f:
                pickle.dump(self.completed_urls, f)
            logger.debug(f"Checkpoint saved: {len(self.completed_urls)} URLs")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def clear_checkpoint(self):
        """Clear checkpoint to start fresh"""
        self.completed_urls.clear()
        self.url_retry_counts.clear()
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
        logger.info("Checkpoint cleared")
    
    def _track_retry(self, url: str) -> bool:
        """
        Track retry count for a URL.
        Returns True if should retry, False if gave up.
        """
        self.url_retry_counts[url] = self.url_retry_counts.get(url, 0) + 1
        self.stats['retries'] += 1
        
        if self.url_retry_counts[url] >= self.MAX_RETRIES_PER_URL:
            logger.warning(f"Max retries ({self.MAX_RETRIES_PER_URL}) exceeded for {url}, giving up")
            self.completed_urls.add(url)  # Don't retry again
            self.stats['gave_up'] += 1
            self._save_checkpoint()
            return False  # Gave up
        
        # Backoff based on retry count
        backoff = random.uniform(5, 15) * self.url_retry_counts[url]
        logger.info(f"Retry {self.url_retry_counts[url]}/{self.MAX_RETRIES_PER_URL} for {url}, waiting {backoff:.1f}s")
        time.sleep(backoff)
        return True  # Will retry
    
    def _coffee_break(self, request_count: int):
        """Take a human-like coffee break"""
        duration = random.uniform(COFFEE_BREAK_MIN, COFFEE_BREAK_MAX)
        logger.info(f"☕ Coffee break after {request_count} requests: pausing {duration:.1f}s")
        time.sleep(duration)
        
        # Rotate session during break for extra safety
        self.session_manager.rotate_session(DOMAIN)
        self.stats['session_rotations'] += 1
        self.stats['coffee_breaks'] += 1
        
        # Reset referer to homepage after break (like reopening browser)
        self.last_url = "https://www.lidl.bg/"
    
    def _maybe_decoy_request(self):
        """Occasionally make decoy request to appear more human"""
        if random.random() < DECOY_PROBABILITY:
            decoy_url = random.choice(DECOY_URLS)
            logger.debug(f"🎭 Decoy request to {decoy_url}")
            
            try:
                self.rate_limiter.wait(decoy_url)
                session = self.session_manager.get_session(DOMAIN)
                
                headers = {'Referer': self.last_url} if self.last_url else {}
                session.get(decoy_url, timeout=15, headers=headers)
                
                self.last_url = decoy_url
                self.stats['decoy_requests'] += 1
                
                # Small pause after decoy
                time.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.debug(f"Decoy request failed (ignoring): {e}")
    
    def get_product_urls(self) -> List[str]:
        """Fetch and parse product sitemap"""
        logger.info(f"Fetching sitemap: {SITEMAP_URL}")
        
        try:
            # Use session manager for sitemap fetch too
            self.rate_limiter.wait(SITEMAP_URL)
            session = self.session_manager.get_session(DOMAIN)
            
            response = session.get(SITEMAP_URL, timeout=30)
            response.raise_for_status()
            
            # Decompress gzip
            content = gzip.decompress(response.content).decode('utf-8')
            
            # Parse XML
            root = ET.fromstring(content)
            
            # Extract URLs (namespace handling)
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            urls = []
            for url_elem in root.findall('.//ns:loc', namespace):
                if url_elem.text and '/p/' in url_elem.text:
                    urls.append(url_elem.text)
            
            self.stats['urls_found'] = len(urls)
            logger.info(f"Found {len(urls)} product URLs in sitemap")
            return urls
            
        except Exception as e:
            logger.error(f"Failed to fetch sitemap: {e}")
            return []
    
    def scrape_product_page(self, url: str) -> Optional[LidlProduct]:
        """Scrape individual product page with full anti-detection"""
        
        # Skip already completed
        if url in self.completed_urls:
            return None
        
        # Check circuit breaker
        if self.circuit_breaker.is_open:
            logger.warning("Circuit breaker open, pausing...")
            time.sleep(self.circuit_breaker.recovery_timeout)
            return None
        
        # Maybe do a decoy request first
        self._maybe_decoy_request()
        
        # Rate limit
        self.rate_limiter.wait(url)
        
        # Get session
        session = self.session_manager.get_session(DOMAIN)
        
        try:
            # Build headers with referer chain
            headers = {}
            if self.last_url:
                headers['Referer'] = self.last_url
            
            # Make request
            response = session.get(url, timeout=20, headers=headers)
            
            # Update referer chain
            self.last_url = url
            
            if response.status_code == 404:
                # Product no longer exists - not an error
                self.circuit_breaker._on_success()
                self.rate_limiter.report_success(url)
                self.completed_urls.add(url)
                return None
                
            elif response.status_code == 429:
                # Rate limited - back off aggressively
                logger.warning(f"Rate limited (429) on {url}")
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, 429)
                
                # Track retry count
                self._track_retry(url)
                
                # Emergency pause
                emergency_pause = random.uniform(30, 60)
                logger.info(f"🚨 Emergency pause: {emergency_pause:.1f}s")
                time.sleep(emergency_pause)
                return None
            
            elif response.status_code in (502, 503, 504):
                # Server error - back off and retry later
                logger.warning(f"Server error ({response.status_code}) on {url}")
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                
                # Track retry count - give up after MAX_RETRIES
                if self._track_retry(url):
                    return None  # Will retry on resume
                else:
                    return None  # Gave up, marked as completed
                
            elif response.status_code != 200:
                logger.warning(f"HTTP {response.status_code} on {url}")
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                self._track_retry(url)
                self.stats['failures'] += 1
                return None
            
            # Success
            self.circuit_breaker._on_success()
            self.rate_limiter.report_success(url)
            
            # Parse product data
            product = self._parse_product_page(url, response.text)
            
            if product:
                self.completed_urls.add(url)
                self.stats['products_scraped'] += 1
                
                # Periodic checkpoint save
                if self.stats['products_scraped'] % CHECKPOINT_INTERVAL == 0:
                    self._save_checkpoint()
                
                return product
            else:
                # Page exists but no product data - still mark as completed
                self.completed_urls.add(url)
                return None
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on {url}")
            self.rate_limiter.report_failure(url)
            self._track_retry(url)
            self.stats['failures'] += 1
            return None
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection dropped for {url}: {e}")
            self.rate_limiter.report_failure(url)
            self._track_retry(url)
            # Extra wait for network recovery
            time.sleep(random.uniform(5, 10))
            self.stats['failures'] += 1
            return None
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self._track_retry(url)
            self.stats['failures'] += 1
            return None
    
    def _parse_product_page(self, url: str, html: str) -> Optional[LidlProduct]:
        """Parse product data from HTML"""
        import html as html_module
        content = html_module.unescape(html)
        
        # Extract product ID from URL
        product_id = url.split('/')[-1]
        
        # Extract title
        title_match = re.search(r'<title>([^<]+)</title>', content)
        name = title_match.group(1).replace(' | Lidl', '').strip() if title_match else None
        
        if not name or len(name) < 3:
            return None
        
        # Extract price from JSON-LD or embedded data
        price_eur = None
        old_price_eur = None
        
        # Try JSON-LD first
        jsonld_match = re.search(r'<script type="application/ld\+json">([^<]+)</script>', content)
        if jsonld_match:
            try:
                jsonld = json.loads(jsonld_match.group(1))
                if isinstance(jsonld, dict):
                    offers = jsonld.get('offers', {})
                    if isinstance(offers, dict):
                        price_str = offers.get('price')
                        if price_str:
                            price_eur = float(price_str)
            except:
                pass
        
        # Fallback: extract from inline JSON
        if not price_eur:
            price_match = re.search(r'"price":([\d.]+)', content)
            if price_match:
                price_eur = float(price_match.group(1))
        
        old_price_match = re.search(r'"oldPrice":([\d.]+)', content)
        if old_price_match:
            old_price_eur = float(old_price_match.group(1))
        
        # Calculate discount
        discount_pct = None
        if old_price_eur and price_eur and old_price_eur > price_eur:
            discount_pct = int(round((1 - price_eur / old_price_eur) * 100))
        
        # Extract image
        image_match = re.search(r'"image":"([^"]+)"', content)
        image_url = image_match.group(1) if image_match else None
        
        # Extract category
        category_match = re.search(r'"category":"([^"]+)"', content)
        category = category_match.group(1) if category_match else None
        
        # Extract description
        desc_match = re.search(r'<meta name="description" content="([^"]+)"', content)
        description = desc_match.group(1) if desc_match else None
        
        # Extract brand
        brand_match = re.search(r'"brand":\s*\{[^}]*"name":\s*"([^"]+)"', content)
        brand = brand_match.group(1) if brand_match else None
        
        # BGN conversion
        EUR_TO_BGN = 1.9558
        price_bgn = round(price_eur * EUR_TO_BGN, 2) if price_eur else None
        old_price_bgn = round(old_price_eur * EUR_TO_BGN, 2) if old_price_eur else None
        
        return LidlProduct(
            product_id=product_id,
            name=name,
            price_eur=price_eur,
            price_bgn=price_bgn,
            old_price_eur=old_price_eur,
            old_price_bgn=old_price_bgn,
            discount_pct=discount_pct,
            image_url=image_url,
            product_url=url,
            category=category,
            description=description,
            brand=brand,
        )
    
    def scrape_all(self, limit: Optional[int] = None, shuffle: bool = True) -> List[LidlProduct]:
        """
        Scrape all products with full anti-detection measures.
        
        Args:
            limit: Maximum number of products to scrape (for testing)
            shuffle: Randomize URL order (default True - HIGHLY RECOMMENDED)
        """
        urls = self.get_product_urls()
        
        if not urls:
            logger.error("No URLs found in sitemap")
            return []
        
        # Filter out already completed
        original_count = len(urls)
        urls = [u for u in urls if u not in self.completed_urls]
        skipped = original_count - len(urls)
        self.stats['urls_skipped'] = skipped
        
        if skipped > 0:
            logger.info(f"Resuming: {skipped} URLs already completed, {len(urls)} remaining")
        
        if limit:
            urls = urls[:limit]
        
        # CRITICAL: Shuffle URLs to avoid predictable patterns
        if shuffle:
            random.shuffle(urls)
            logger.info("URLs shuffled for anti-detection")
        
        products = []
        total = len(urls)
        request_count = 0
        
        logger.info(f"Starting scrape of {total} URLs...")
        
        for i, url in enumerate(urls):
            # Progress logging
            if i > 0 and i % 25 == 0:
                logger.info(f"Progress: {i}/{total} ({len(products)} products, {self.stats['failures']} failures)")
            
            # COFFEE BREAK: Every N requests
            request_count += 1
            if request_count >= COFFEE_BREAK_INTERVAL:
                self._coffee_break(request_count)
                request_count = 0
            
            # Scrape product
            product = self.scrape_product_page(url)
            if product:
                products.append(product)
        
        # Final checkpoint save
        self._save_checkpoint()
        
        logger.info(f"Scrape complete: {len(products)} products from {total} URLs")
        return products
    
    def save_products(self, products: List[LidlProduct], filepath: str):
        """Save products to JSON"""
        data = [asdict(p) for p in products]
        
        # Ensure directory exists
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(products)} products to {filepath}")
    
    def get_stats(self) -> Dict:
        """Get comprehensive scraper statistics"""
        return {
            **self.stats,
            'checkpoint_urls': len(self.completed_urls),
            'circuit_breaker': {
                'state': self.circuit_breaker.state.name,
                'failures': self.circuit_breaker._failure_count,
            },
            'rate_limiter': self.rate_limiter.get_stats(DOMAIN),
        }


def main():
    """CLI entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    import argparse
    parser = argparse.ArgumentParser(description='Lidl Sitemap Scraper (Bulletproof)')
    parser.add_argument('--limit', type=int, help='Limit number of products to scrape')
    parser.add_argument('--output', default='services/scraper/data/lidl_sitemap_products.json')
    parser.add_argument('--clear-checkpoint', action='store_true', help='Clear checkpoint and start fresh')
    parser.add_argument('--no-shuffle', action='store_true', help='Do not shuffle URLs (NOT recommended)')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Lidl.bg Sitemap Scraper - BULLETPROOF VERSION")
    print(f"Sitemap: {SITEMAP_URL}")
    print("=" * 60)
    print()
    print("Anti-detection features:")
    print(f"  ✓ URL shuffling: {'disabled' if args.no_shuffle else 'enabled'}")
    print(f"  ✓ Coffee breaks: every {COFFEE_BREAK_INTERVAL} requests")
    print(f"  ✓ Checkpoint/resume: enabled")
    print(f"  ✓ Referer chain: enabled")
    print(f"  ✓ Decoy requests: {DECOY_PROBABILITY*100:.0f}% probability")
    print()
    
    scraper = LidlSitemapScraper()
    
    if args.clear_checkpoint:
        scraper.clear_checkpoint()
    
    products = scraper.scrape_all(
        limit=args.limit,
        shuffle=not args.no_shuffle
    )
    
    # Save to file
    output_path = Path(__file__).parent.parent.parent.parent / args.output
    scraper.save_products(products, str(output_path))
    
    print()
    print(f"✅ Scraped {len(products)} products")
    print(f"📁 Saved to {output_path}")
    print()
    print("📊 Statistics:")
    stats = scraper.get_stats()
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"   {key}:")
            for k, v in value.items():
                print(f"     {k}: {v}")
        else:
            print(f"   {key}: {value}")


if __name__ == "__main__":
    main()
