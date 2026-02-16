"""Lidl.bg scraper - extracts from JSON-LD schema"""

import gzip
import json
import logging
import re
import xml.etree.ElementTree as ET
from .base import BaseScraper

log = logging.getLogger(__name__)

SITEMAP_URL = "https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz"


class LidlScraper(BaseScraper):
    """
    Lidl Bulgaria scraper using JSON-LD product schema.
    
    Lidl product pages contain JSON-LD with:
    - sku, name, brand.name
    - offers.price, offers.priceCurrency
    - image
    """
    
    STORE_NAME = "lidl"
    
    def scrape(self, limit=None):
        """Scrape all products from Lidl sitemap"""
        urls = self._get_product_urls()
        
        if limit:
            urls = urls[:limit]
        
        log.info(f"Scraping {len(urls)} Lidl product URLs...")
        
        products = []
        for i, url in enumerate(urls):
            if i > 0 and i % 25 == 0:
                log.info(f"Progress: {i}/{len(urls)} ({len(products)} products)")
            
            if i > 0 and i % 50 == 0:
                self.coffee_break()
            
            if i > 0 and i % 10 == 0:
                self.rotate_user_agent()
            
            product = self._scrape_product(url)
            if product:
                products.append(product)
            
            self.delay(1.0, 3.0)
        
        log.info(f"Scraped {len(products)} products from Lidl")
        return products
    
    def _get_product_urls(self):
        """Fetch product URLs from sitemap"""
        log.info(f"Fetching Lidl sitemap...")
        
        response = self.fetch(SITEMAP_URL)
        if not response:
            return []
        
        content = gzip.decompress(response.content).decode('utf-8')
        root = ET.fromstring(content)
        
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = []
        for url_elem in root.findall('.//ns:loc', namespace):
            if url_elem.text and '/p/' in url_elem.text:
                urls.append(url_elem.text)
        
        log.info(f"Found {len(urls)} product URLs in sitemap")
        return urls
    
    def _scrape_product(self, url):
        """Scrape single product page"""
        response = self.fetch(url)
        if not response:
            return None
        
        # Extract JSON-LD
        jsonld = self._extract_jsonld(response.text)
        if not jsonld:
            return None
        
        product_data = self._find_product_schema(jsonld)
        if not product_data:
            return None
        
        # Extract fields
        name = product_data.get('name', '').strip()
        if not name:
            return None
        
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
        
        if offers:
            offer = offers[0]
            price_str = offer.get('price')
            if price_str:
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    pass
            currency = offer.get('priceCurrency', 'BGN')
        
        self.stats['products_found'] += 1
        
        # Return in standard format
        return {
            'name': name,
            'brand': brand,
            'price': price,
            'currency': currency,
            'old_price': None,
            'image_url': image_url,
            'product_url': url,
            'sku': product_data.get('sku'),
        }
    
    def _extract_jsonld(self, html):
        """Extract JSON-LD objects from HTML"""
        pattern = r'<script\s+type=["\']?application/ld\+json["\']?\s*>(.+?)</script>'
        objects = []
        
        for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(match.group(1).strip())
                objects.append(data)
            except json.JSONDecodeError:
                continue
        
        return objects
    
    def _find_product_schema(self, jsonld_objects):
        """Find Product schema from JSON-LD objects"""
        for obj in jsonld_objects:
            if isinstance(obj, dict):
                if obj.get('@type') == 'Product':
                    return obj
                if '@graph' in obj:
                    for item in obj['@graph']:
                        if item.get('@type') == 'Product':
                            return item
        return None
