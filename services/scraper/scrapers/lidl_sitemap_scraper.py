#!/usr/bin/env python3
"""
Lidl.bg Sitemap Scraper

Uses the product sitemap to discover all 800+ products,
then fetches details from individual product pages.

Sitemap URL: https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz
"""

import gzip
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import requests

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz"
DOMAIN = "www.lidl.bg"


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
    """Scrape all Lidl products via sitemap"""
    
    def __init__(self):
        self.session_manager = SessionManager(
            config=SessionConfig(max_requests=100, max_age_seconds=1800)
        )
        self.rate_limiter = DomainRateLimiter()
        self.circuit_breaker = CircuitBreaker(
            name=DOMAIN,
            failure_threshold=5,
            recovery_timeout=60,
        )
        self.stats = {
            'urls_found': 0,
            'products_scraped': 0,
            'failures': 0,
        }
    
    def get_product_urls(self) -> List[str]:
        """Fetch and parse product sitemap"""
        logger.info(f"Fetching sitemap: {SITEMAP_URL}")
        
        try:
            response = requests.get(SITEMAP_URL, timeout=30)
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
        """Scrape individual product page for details"""
        
        if self.circuit_breaker.is_open:
            return None
        
        self.rate_limiter.wait(url)
        session = self.session_manager.get_session(DOMAIN)
        
        try:
            response = session.get(url, timeout=20)
            
            if response.status_code == 404:
                # Product no longer exists
                self.circuit_breaker._on_success()
                return None
            elif response.status_code != 200:
                self.circuit_breaker._on_failure()
                self.stats['failures'] += 1
                return None
            
            self.circuit_breaker._on_success()
            
            # Extract product ID from URL
            product_id = url.split('/')[-1]
            
            # Parse HTML for product data
            import html
            content = html.unescape(response.text)
            
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
                brand=None,
            )
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self.stats['failures'] += 1
            return None
    
    def scrape_all(self, limit: Optional[int] = None) -> List[LidlProduct]:
        """Scrape all products from sitemap"""
        urls = self.get_product_urls()
        
        if limit:
            urls = urls[:limit]
        
        products = []
        total = len(urls)
        
        for i, url in enumerate(urls):
            if i > 0 and i % 50 == 0:
                logger.info(f"Progress: {i}/{total} ({len(products)} products)")
            
            product = self.scrape_product_page(url)
            if product:
                products.append(product)
                self.stats['products_scraped'] += 1
        
        logger.info(f"Scraped {len(products)} products from {total} URLs")
        return products
    
    def save_products(self, products: List[LidlProduct], filepath: str):
        """Save products to JSON"""
        data = [asdict(p) for p in products]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(products)} products to {filepath}")


def main():
    """CLI entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    import argparse
    parser = argparse.ArgumentParser(description='Lidl Sitemap Scraper')
    parser.add_argument('--limit', type=int, help='Limit number of products to scrape')
    parser.add_argument('--output', default='services/scraper/data/lidl_sitemap_products.json')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Lidl.bg Sitemap Scraper")
    print(f"Sitemap: {SITEMAP_URL}")
    print("=" * 60)
    
    scraper = LidlSitemapScraper()
    products = scraper.scrape_all(limit=args.limit)
    
    # Save to file
    output_path = Path(__file__).parent.parent.parent.parent / args.output
    scraper.save_products(products, str(output_path))
    
    print(f"\n✅ Scraped {len(products)} products")
    print(f"📁 Saved to {output_path}")
    print(f"\n📊 Stats: {scraper.stats}")


if __name__ == "__main__":
    main()
