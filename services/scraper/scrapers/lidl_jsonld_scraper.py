#!/usr/bin/env python3
"""
Lidl.bg JSON-LD Scraper - Extracts product data from JSON-LD schema

Lidl product pages embed JSON-LD Product schema with:
- sku (product ID)
- name
- brand.name
- image
- offers.price, offers.priceCurrency

This scraper focuses on reliable JSON-LD extraction with minimal parsing.
"""

import gzip
import json
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Set
import html as html_module

import requests

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz"
DOMAIN = "www.lidl.bg"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


@dataclass
class LidlProduct:
    """Product data from Lidl JSON-LD"""
    product_id: str
    name: str
    brand: Optional[str]
    price: Optional[float]  # Current price
    currency: str  # BGN or EUR
    old_price: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    product_url: str
    availability: Optional[str]


class LidlJsonLdScraper:
    """
    Simple Lidl scraper focused on JSON-LD extraction.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        self.stats = {
            'urls_found': 0,
            'products_scraped': 0,
            'failures': 0,
            'no_jsonld': 0,
        }
    
    def get_product_urls(self) -> List[str]:
        """Fetch and parse product sitemap"""
        logger.info(f"Fetching sitemap: {SITEMAP_URL}")
        
        try:
            response = self.session.get(SITEMAP_URL, timeout=30)
            response.raise_for_status()
            
            content = gzip.decompress(response.content).decode('utf-8')
            root = ET.fromstring(content)
            
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
    
    def _extract_jsonld(self, html: str) -> List[dict]:
        """Extract all JSON-LD objects from HTML"""
        jsonld_objects = []
        
        # Find all JSON-LD script tags
        pattern = r'<script\s+type=["\']?application/ld\+json["\']?\s*>(.+?)</script>'
        
        for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            try:
                content = match.group(1).strip()
                data = json.loads(content)
                jsonld_objects.append(data)
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON-LD: {e}")
                continue
        
        return jsonld_objects
    
    def _find_product_jsonld(self, jsonld_objects: List[dict]) -> Optional[dict]:
        """Find the Product schema from JSON-LD objects"""
        for obj in jsonld_objects:
            if isinstance(obj, dict):
                if obj.get('@type') == 'Product':
                    return obj
                if '@graph' in obj:
                    for item in obj['@graph']:
                        if item.get('@type') == 'Product':
                            return item
        return None
    
    def scrape_product_page(self, url: str) -> Optional[LidlProduct]:
        """Scrape product page and extract JSON-LD data"""
        
        try:
            time.sleep(random.uniform(1.0, 3.0))
            
            if random.random() < 0.1:
                self.session.headers['User-Agent'] = random.choice(USER_AGENTS)
            
            response = self.session.get(url, timeout=20)
            
            if response.status_code == 404:
                logger.debug(f"Product not found (404): {url}")
                return None
            
            if response.status_code != 200:
                logger.warning(f"HTTP {response.status_code} for {url}")
                self.stats['failures'] += 1
                return None
            
            html = response.text
            jsonld_objects = self._extract_jsonld(html)
            
            if not jsonld_objects:
                logger.debug(f"No JSON-LD found in {url}")
                self.stats['no_jsonld'] += 1
                return None
            
            product_data = self._find_product_jsonld(jsonld_objects)
            
            if not product_data:
                logger.debug(f"No Product schema in JSON-LD for {url}")
                self.stats['no_jsonld'] += 1
                return None
            
            product_id = product_data.get('sku', url.split('/')[-1])
            name = product_data.get('name', '')
            
            brand_obj = product_data.get('brand', {})
            brand = brand_obj.get('name') if isinstance(brand_obj, dict) else None
            
            images = product_data.get('image', [])
            image_url = images[0] if isinstance(images, list) and images else (
                images if isinstance(images, str) else None
            )
            
            offers = product_data.get('offers', [])
            if isinstance(offers, dict):
                offers = [offers]
            
            price = None
            currency = 'BGN'
            availability = None
            
            if offers:
                offer = offers[0]
                price_str = offer.get('price')
                if price_str:
                    try:
                        price = float(price_str)
                    except (ValueError, TypeError):
                        pass
                currency = offer.get('priceCurrency', 'BGN')
                availability = offer.get('availability', '').replace('https://schema.org/', '').replace('http://schema.org/', '')
            
            if not name:
                logger.debug(f"No product name for {url}")
                return None
            
            self.stats['products_scraped'] += 1
            
            return LidlProduct(
                product_id=str(product_id),
                name=name,
                brand=brand,
                price=price,
                currency=currency,
                old_price=None,
                discount_pct=None,
                image_url=image_url,
                product_url=url,
                availability=availability,
            )
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout: {url}")
            self.stats['failures'] += 1
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self.stats['failures'] += 1
            return None
    
    def scrape_batch(self, urls: List[str], progress_interval: int = 25) -> List[LidlProduct]:
        """Scrape a batch of URLs"""
        products = []
        total = len(urls)
        
        for i, url in enumerate(urls):
            if i > 0 and i % progress_interval == 0:
                logger.info(f"Progress: {i}/{total} ({len(products)} products)")
            
            if i > 0 and i % 50 == 0:
                pause = random.uniform(10, 20)
                logger.info(f"Pause: {pause:.1f}s")
                time.sleep(pause)
            
            product = self.scrape_product_page(url)
            if product:
                products.append(product)
        
        return products
    
    def save_products(self, products: List[LidlProduct], filepath: str):
        """Save products to JSON"""
        data = [asdict(p) for p in products]
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(products)} products to {filepath}")


def test_single_url():
    """Test scraping a single product URL"""
    logging.basicConfig(level=logging.DEBUG)
    
    scraper = LidlJsonLdScraper()
    
    test_url = "https://www.lidl.bg/p/toffifee-bonboni/p10051969"
    print(f"\nTesting: {test_url}\n")
    
    product = scraper.scrape_product_page(test_url)
    
    if product:
        print("Product found:")
        for key, value in asdict(product).items():
            print(f"  {key}: {value}")
    else:
        print("No product extracted")
    
    print(f"\nStats: {scraper.stats}")


def main():
    """CLI entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    import argparse
    parser = argparse.ArgumentParser(description='Lidl JSON-LD Scraper')
    parser.add_argument('--test', action='store_true', help='Test single URL')
    parser.add_argument('--limit', type=int, help='Limit number of products')
    parser.add_argument('--output', default='lidl_jsonld_products.json')
    args = parser.parse_args()
    
    if args.test:
        test_single_url()
        return
    
    scraper = LidlJsonLdScraper()
    
    urls = scraper.get_product_urls()
    if not urls:
        print("No URLs found")
        return
    
    random.shuffle(urls)
    
    if args.limit:
        urls = urls[:args.limit]
    
    print(f"Scraping {len(urls)} products...")
    products = scraper.scrape_batch(urls)
    
    scraper.save_products(products, args.output)
    
    print(f"\nScraped {len(products)} products")
    print(f"Stats: {scraper.stats}")


if __name__ == "__main__":
    main()
