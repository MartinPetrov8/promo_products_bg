"""
Lidl Live Scraper - Full catalog via sitemap + JSON-LD
Filters out products without prices
"""
import json
import gzip
import re
import time
import random
import logging
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from scrapers.base import BaseScraper, Store, RawProduct

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]
MAX_WORKERS = 10

class LidlScraper(BaseScraper):
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'bg-BG,bg;q=0.9',
        })
    
    @property
    def store(self) -> Store:
        return Store.LIDL
    
    def health_check(self) -> bool:
        try:
            resp = self.session.head("https://www.lidl.bg", timeout=10)
            return resp.status_code < 500
        except Exception:
            return False
    
    def scrape(self) -> List[RawProduct]:
        products = []
        
        urls = self._get_product_urls()
        logger.info(f"Found {len(urls)} product URLs")
        
        # Concurrent scraping
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self._scrape_product, url): url for url in urls}
            done = 0
            for future in as_completed(futures):
                done += 1
                if done % 100 == 0:
                    logger.info(f"Progress: {done}/{len(urls)}")
                product = future.result()
                if product and product.price_bgn:  # Only include products WITH price
                    products.append(product)
        
        logger.info(f"Lidl: {len(products)} products with price")
        return products
    
    def _get_product_urls(self) -> List[str]:
        try:
            logger.info(f"Fetching sitemap: {SITEMAP_URL}")
            response = self.session.get(SITEMAP_URL, timeout=30)
            response.raise_for_status()
            
            content = gzip.decompress(response.content).decode('utf-8')
            root = ET.fromstring(content)
            
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            urls = [url_elem.text for url_elem in root.findall('.//ns:loc', namespace) 
                    if url_elem.text and '/p/' in url_elem.text]
            
            return urls
        except Exception as e:
            logger.error(f"Failed to fetch sitemap: {e}")
            return []
    
    def _scrape_product(self, url: str) -> Optional[RawProduct]:
        try:
            time.sleep(random.uniform(0.1, 0.3))
            
            response = requests.get(url, timeout=15, headers={
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html',
            })
            if response.status_code != 200:
                return None
            
            html = response.text
            
            # Extract JSON-LD
            match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.+?)</script>', html, re.DOTALL)
            if not match:
                return None
            
            data = json.loads(match.group(1))
            
            # Handle @graph structure
            product_data = None
            if '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'Product':
                        product_data = item
                        break
            elif data.get('@type') == 'Product':
                product_data = data
            
            if not product_data:
                return None
            
            sku = product_data.get('sku') or url.split('/')[-1]
            name = product_data.get('name', '')
            brand = product_data.get('brand', {})
            if isinstance(brand, dict):
                brand = brand.get('name')
            
            images = product_data.get('image', [])
            image = images[0] if isinstance(images, list) else images
            
            # Handle offers (can be list or dict)
            offers = product_data.get('offers', [])
            if isinstance(offers, list) and offers:
                offer = offers[0]
                price = offer.get('price') if isinstance(offer, dict) else None
            elif isinstance(offers, dict):
                price = offers.get('price')
            else:
                price = None
            
            # Skip products without price
            if not price:
                return None
            
            return RawProduct(
                store=self.store.value,
                sku=str(sku),
                raw_name=name,
                brand=brand,
                price_bgn=float(price),
                image_url=image,
                product_url=url,
            )
        except Exception as e:
            return None
