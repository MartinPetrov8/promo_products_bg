#!/usr/bin/env python3
"""
Lidl.bg Product Page Scraper

Fetches individual product pages to extract accurate data:
- BGN price from HTML (not EUR from JSON-LD!)
- Size/weight from keyfacts HTML
- Description from JSON-LD
- Availability status

Research findings (2026-02-13):
- JSON-LD contains EUR price (4.60€), NOT BGN
- BGN price (9.00 лв) is ONLY in rendered HTML
- Size ("600 g/опаковка") is in keyfacts HTML section
- JSON-LD has: sku, name, description, availability, image

Usage:
    scraper = LidlProductScraper()
    products = await scraper.scrape_products(product_urls)
    scraper.save_to_db()
"""

import json
import logging
import re
import time
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import requests

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)

DOMAIN = "www.lidl.bg"


@dataclass
class LidlProductData:
    """
    Product data extracted from Lidl product page.
    
    Combines JSON-LD structured data with HTML-extracted fields.
    """
    # Identifiers
    sku: str
    product_url: str
    
    # Basic info (from JSON-LD)
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    brand: Optional[str] = None
    
    # Price - MUST be from HTML, not JSON-LD!
    price_bgn: Optional[float] = None
    old_price_bgn: Optional[float] = None
    price_eur: Optional[float] = None  # For reference only
    
    # Size/weight (from HTML keyfacts)
    size_raw: Optional[str] = None  # e.g., "600 g/опаковка"
    size_value: Optional[float] = None  # e.g., 600
    size_unit: Optional[str] = None  # e.g., "g"
    
    # Availability (from JSON-LD)
    availability: Optional[str] = None  # InStoreOnly, InStock, OutOfStock
    
    # Metadata
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'sku': self.sku,
            'product_url': self.product_url,
            'name': self.name,
            'description': self.description,
            'image_url': self.image_url,
            'brand': self.brand,
            'price_bgn': self.price_bgn,
            'old_price_bgn': self.old_price_bgn,
            'price_eur': self.price_eur,
            'size_raw': self.size_raw,
            'size_value': self.size_value,
            'size_unit': self.size_unit,
            'availability': self.availability,
            'scraped_at': self.scraped_at,
        }


class LidlProductScraper:
    """
    Scrapes individual Lidl product pages for accurate data.
    
    Key insight: JSON-LD prices are in EUR, but we need BGN!
    Must extract BGN price from rendered HTML.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(__file__).parent.parent.parent.parent / "data" / "promobg.db"
        self.products: List[LidlProductData] = []
        
        # Infrastructure setup
        self.session_manager = SessionManager(config=SessionConfig(
            max_requests=50,
            max_age_seconds=300,
            cookie_persistence=True
        ))
        
        self.rate_limiter = DomainRateLimiter()
        # Uses default config for lidl.bg (10 req/min, 3s min delay)
        
        self.circuit_breaker = CircuitBreaker(name="lidl_product")
        
        self.retry_handler = RetryHandler(RetryConfig(
            max_attempts=3,
            base_delay=5.0,
            max_delay=60.0,
            exponential_base=2.0
        ))
    
    def _extract_json_ld(self, html: str) -> Optional[Dict[str, Any]]:
        """
        Extract Product schema.org JSON-LD from page.
        
        Returns dict with: sku, name, description, image, brand, offers
        Note: offers.price is in EUR, not BGN!
        """
        pattern = r'<script type="application/ld\+json">(\{"@context":"http://schema\.org","@type":"Product"[^<]+)</script>'
        match = re.search(pattern, html)
        if not match:
            return None
        
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON-LD: {e}")
            return None
    
    def _extract_bgn_price(self, html: str) -> tuple[Optional[float], Optional[float]]:
        """
        Extract BGN price from rendered HTML.
        
        The price in JSON-LD is EUR! Must get BGN from HTML.
        Looks for: <div class="ods-price__value">9.00ЛВ.*</div>
        
        Returns: (current_price, old_price)
        """
        # Current BGN price - look for лв/ЛВ after number
        current_match = re.search(
            r'ods-price__value[^>]*>(\d+[,\.]\d{2})\s*(?:лв|ЛВ)',
            html,
            re.IGNORECASE
        )
        current_price = None
        if current_match:
            try:
                current_price = float(current_match.group(1).replace(',', '.'))
            except ValueError:
                pass
        
        # Old/crossed-out price (if on sale)
        old_match = re.search(
            r'ods-price--strikethrough[^>]*>(\d+[,\.]\d{2})\s*(?:лв|ЛВ)',
            html,
            re.IGNORECASE
        )
        old_price = None
        if old_match:
            try:
                old_price = float(old_match.group(1).replace(',', '.'))
            except ValueError:
                pass
        
        return current_price, old_price
    
    def _extract_eur_price(self, html: str) -> Optional[float]:
        """Extract EUR price from HTML for reference."""
        match = re.search(r'ods-price__value[^>]*>(\d+[,\.]\d{2})€', html)
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                pass
        return None
    
    def _extract_size(self, html: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
        """
        Extract size/weight from keyfacts HTML.
        
        Patterns:
          - "600 g/опаковка"
          - "1.5 l/опаковка"  
          - "500 ml/опаковка"
          - "1 kg/опаковка"
          - "6 бр./опаковка" (pieces)
        
        Returns: (raw_size, numeric_value, unit)
        """
        # Pattern for size with unit before /опаковка
        patterns = [
            (r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|l|л)\s*/\s*опаковка', None),
            (r'(\d+(?:[,\.]\d+)?)\s*(бр)\.?\s*/\s*опаковка', 'бр'),
        ]
        
        for pattern, force_unit in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', '.'))
                    unit = force_unit or match.group(2).lower()
                    # Normalize units
                    if unit == 'л':
                        unit = 'l'
                    raw = f"{match.group(1)} {unit}/опаковка"
                    return raw, value, unit
                except (ValueError, IndexError):
                    pass
        
        return None, None, None
    
    def _extract_availability(self, json_ld: Optional[Dict]) -> Optional[str]:
        """Extract availability from JSON-LD offers."""
        if not json_ld:
            return None
        
        offers = json_ld.get('offers', [])
        if offers and isinstance(offers, list) and len(offers) > 0:
            avail = offers[0].get('availability', '')
            # Extract just the status: "InStoreOnly", "InStock", "OutOfStock"
            if 'InStoreOnly' in avail:
                return 'InStoreOnly'
            elif 'InStock' in avail:
                return 'InStock'
            elif 'OutOfStock' in avail:
                return 'OutOfStock'
        return None
    
    def _clean_description(self, desc: Optional[str]) -> Optional[str]:
        """Clean HTML from description."""
        if not desc:
            return None
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', ' ', desc)
        # Normalize whitespace
        clean = ' '.join(clean.split())
        return clean.strip() if clean else None
    
    def fetch_product(self, url: str) -> Optional[LidlProductData]:
        """
        Fetch and parse a single product page.
        
        Extracts:
          - JSON-LD: sku, name, description, image, brand, availability
          - HTML: BGN price (!important), size/weight
        """
        # Rate limiting
        self.rate_limiter.wait(url)
        
        # Add jitter
        time.sleep(random.uniform(1.0, 3.0))
        
        try:
            session = self.session_manager.get_session(DOMAIN)
            response = session.get(url, timeout=30)
            response.raise_for_status()
            html = response.text
            
            # Extract JSON-LD
            json_ld = self._extract_json_ld(html)
            if not json_ld:
                logger.warning(f"No JSON-LD found for {url}")
                return None
            
            # Extract prices from HTML (NOT from JSON-LD!)
            price_bgn, old_price_bgn = self._extract_bgn_price(html)
            price_eur = self._extract_eur_price(html)
            
            # Extract size from HTML
            size_raw, size_value, size_unit = self._extract_size(html)
            
            # Build product data
            product = LidlProductData(
                sku=json_ld.get('sku', ''),
                product_url=url,
                name=json_ld.get('name', ''),
                description=self._clean_description(json_ld.get('description')),
                image_url=json_ld.get('image', [None])[0] if isinstance(json_ld.get('image'), list) else json_ld.get('image'),
                brand=json_ld.get('brand', {}).get('name') if isinstance(json_ld.get('brand'), dict) else None,
                price_bgn=price_bgn,
                old_price_bgn=old_price_bgn,
                price_eur=price_eur,
                size_raw=size_raw,
                size_value=size_value,
                size_unit=size_unit,
                availability=self._extract_availability(json_ld),
            )
            
            logger.info(f"Scraped: {product.name} - {price_bgn} лв - {size_raw}")
            return product
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None
    
    def scrape_products(self, urls: List[str], checkpoint_every: int = 10) -> List[LidlProductData]:
        """
        Scrape multiple product pages.
        
        Args:
            urls: List of product page URLs
            checkpoint_every: Save checkpoint every N products
        
        Returns:
            List of scraped products
        """
        total = len(urls)
        logger.info(f"Starting scrape of {total} Lidl products")
        
        for i, url in enumerate(urls, 1):
            if self.circuit_breaker.is_open():
                logger.error("Circuit breaker open - stopping scrape")
                break
            
            product = self.fetch_product(url)
            if product:
                self.products.append(product)
                self.circuit_breaker.record_success()
            else:
                self.circuit_breaker.record_failure()
            
            # Progress logging
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{total} ({len(self.products)} successful)")
            
            # Checkpoint
            if checkpoint_every and i % checkpoint_every == 0:
                self._save_checkpoint(i)
            
            # Coffee break every 50 requests
            if i % 50 == 0:
                pause = random.uniform(30, 60)
                logger.info(f"Coffee break: {pause:.0f}s")
                time.sleep(pause)
        
        logger.info(f"Scrape complete: {len(self.products)}/{total} products")
        return self.products
    
    def _save_checkpoint(self, count: int):
        """Save intermediate results."""
        checkpoint_file = self.db_path.parent / f"lidl_checkpoint_{count}.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in self.products], f, ensure_ascii=False, indent=2)
        logger.info(f"Checkpoint saved: {checkpoint_file}")
    
    def save_to_db(self):
        """Save products to SQLite database."""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update existing products or insert new
        for product in self.products:
            cursor.execute("""
                UPDATE products SET
                    price = ?,
                    original_price = ?,
                    description = ?,
                    size = ?,
                    size_unit = ?,
                    image_url = ?,
                    brand = ?,
                    scraped_at = ?
                WHERE store_id = 2 AND product_code = ?
            """, (
                product.price_bgn,
                product.old_price_bgn,
                product.description,
                str(product.size_value) if product.size_value else product.size_raw,
                product.size_unit,
                product.image_url,
                product.brand,
                product.scraped_at,
                product.sku,
            ))
            
            if cursor.rowcount == 0:
                # Insert new product
                cursor.execute("""
                    INSERT INTO products (
                        store_id, product_code, name, price, original_price,
                        description, size, size_unit, image_url, brand, 
                        product_url, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    2,  # Lidl store_id
                    product.sku,
                    product.name,
                    product.price_bgn,
                    product.old_price_bgn,
                    product.description,
                    str(product.size_value) if product.size_value else product.size_raw,
                    product.size_unit,
                    product.image_url,
                    product.brand,
                    product.product_url,
                    product.scraped_at,
                ))
        
        conn.commit()
        logger.info(f"Saved {len(self.products)} products to database")
        conn.close()
    
    def get_existing_product_urls(self) -> List[str]:
        """Get URLs for products already in database that need updating."""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT product_url FROM products 
            WHERE store_id = 2 AND product_url IS NOT NULL
        """)
        
        urls = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return urls


def main():
    """Run the scraper to update existing Lidl products."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    scraper = LidlProductScraper()
    
    # Get URLs from database
    urls = scraper.get_existing_product_urls()
    
    if not urls:
        logger.warning("No Lidl product URLs found in database")
        return
    
    logger.info(f"Found {len(urls)} products to update")
    
    # Scrape products
    products = scraper.scrape_products(urls)
    
    # Save to database
    if products:
        scraper.save_to_db()
    
    # Summary
    prices_found = sum(1 for p in products if p.price_bgn)
    sizes_found = sum(1 for p in products if p.size_value)
    
    print(f"\n=== SCRAPE SUMMARY ===")
    print(f"Products scraped: {len(products)}")
    print(f"With BGN price: {prices_found} ({100*prices_found/len(products):.1f}%)")
    print(f"With size: {sizes_found} ({100*sizes_found/len(products):.1f}%)")


if __name__ == "__main__":
    main()
