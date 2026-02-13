#!/usr/bin/env python3
"""
Lidl.bg Product Page Scraper

Fetches individual product pages to extract accurate data:
- BGN price from HTML (not EUR from JSON-LD!)
- Size/weight from keyfacts HTML
- Description from JSON-LD
- Detailed availability (scheduled dates, not just OutOfStock)

Research findings (2026-02-13):
- JSON-LD contains EUR price (4.60€), NOT BGN
- JSON-LD priceCurrency says "BGN" but value is EUR - MISLEADING!
- BGN price (9.00 лв) is ONLY in rendered HTML
- Size ("600 g/опаковка") is in keyfacts HTML section
- Availability like "в магазините от 16.02. - 22.02." in HTML

Usage:
    scraper = LidlProductScraper()
    products = scraper.scrape_products(product_urls)
    scraper.save_to_db()
"""

import json
import fcntl
import logging
import re
import sqlite3
import time
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

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
LIDL_STORE_ID = 2


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
    
    # Availability - detailed from HTML
    availability: Optional[str] = None  # e.g., "в магазините от 16.02. - 22.02."
    availability_type: Optional[str] = None  # SCHEDULED, IN_STORE, SOLD_OUT
    
    # Metadata
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
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
            'availability_type': self.availability_type,
            'scraped_at': self.scraped_at,
        }


class LidlProductScraper:
    """
    Scrapes individual Lidl product pages for accurate data.
    
    Key insights:
    - JSON-LD price is EUR (even when priceCurrency says BGN!)
    - Must extract BGN price from rendered HTML
    - Availability text like "в магазините от X - Y" is in HTML
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(__file__).parent.parent.parent.parent / "data" / "promobg.db"
        self.products: List[LidlProductData] = []
        self.checkpoint_file = self.db_path.parent / "lidl_checkpoint.json"
        
        # Infrastructure setup
        self.session_manager = SessionManager(config=SessionConfig(
            max_requests=50,
            max_age_seconds=300,
            cookie_persistence=True
        ))
        
        self.rate_limiter = DomainRateLimiter()
        self.circuit_breaker = CircuitBreaker(name="lidl_product")
        self.retry_handler = RetryHandler(RetryConfig(
            max_attempts=3,
            base_delay=5.0,
            max_delay=60.0,
            exponential_base=2.0
        ))
    
    def _extract_json_ld(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract Product schema.org JSON-LD from page."""
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
        
        JSON-LD price is EUR even when priceCurrency says BGN!
        Must get real BGN from HTML: <div class="ods-price__value">9.00ЛВ.*</div>
        """
        # Current BGN price
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
        
        # Old/crossed-out price
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
        
        Patterns: "600 g/опаковка", "1.5 l/опаковка", "1 kg/опаковка"
        """
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
                    if unit == 'л':
                        unit = 'l'
                    raw = f"{match.group(1)} {unit}/опаковка"
                    return raw, value, unit
                except (ValueError, IndexError):
                    pass
        
        return None, None, None
    
    def _extract_availability_detailed(self, html: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract detailed availability from HTML.
        
        Lidl has special availability types:
        - "в магазините от 16.02. - 22.02." = scheduled/upcoming
        - "Налично в магазина" = in store now
        - "Изчерпано" = sold out
        
        Returns: (availability_text, availability_type)
        """
        # Look for scheduled availability (future date range)
        scheduled = re.search(
            r'в магазините от (\d{2}\.\d{2}\.?\s*-\s*\d{2}\.\d{2}\.?)',
            html
        )
        if scheduled:
            return f"в магазините от {scheduled.group(1)}", "SCHEDULED"
        
        # Look for "available from" single date
        from_date = re.search(r'от\s+(\d{2}\.\d{2}\.)', html)
        if from_date:
            return f"от {from_date.group(1)}", "UPCOMING"
        
        # Check for in-store availability
        if re.search(r'наличн[оа]\s+в\s+магазин', html, re.IGNORECASE):
            return "Налично в магазина", "IN_STORE"
        
        # Check for sold out
        if re.search(r'изчерпан[оа]', html, re.IGNORECASE):
            return "Изчерпано", "SOLD_OUT"
        
        return None, None
    
    def _extract_availability_jsonld(self, json_ld: Optional[Dict]) -> Optional[str]:
        """Extract availability from JSON-LD (fallback)."""
        if not json_ld:
            return None
        
        offers = json_ld.get('offers', [])
        if offers and isinstance(offers, list) and len(offers) > 0:
            avail = offers[0].get('availability', '')
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
        clean = re.sub(r'<[^>]+>', ' ', desc)
        clean = ' '.join(clean.split())
        return clean.strip() if clean else None
    
    def _fetch_with_retry(self, url: str) -> Optional[requests.Response]:
        """Fetch URL with retry logic and circuit breaker."""
        def _do_fetch():
            if self.circuit_breaker.is_open:
                raise Exception("Circuit breaker is open")
            session = self.session_manager.get_session(DOMAIN)
            response = session.get(url, timeout=30)
            response.raise_for_status()
            return response
        
        try:
            return self.retry_handler.execute(_do_fetch)
        except Exception as e:
            logger.error(f"All retries failed for {url}: {e}")
            return None
    
    def fetch_product(self, url: str) -> Optional[LidlProductData]:
        """
        Fetch and parse a single product page.
        
        Extracts from JSON-LD: sku, name, description, image, brand
        Extracts from HTML: BGN price, size, detailed availability
        """
        # Rate limiting
        self.rate_limiter.wait(url)
        
        # Add jitter
        time.sleep(random.uniform(1.0, 3.0))
        
        try:
            response = self._fetch_with_retry(url)
            if not response:
                self.circuit_breaker.record_failure()
                return None
            
            html = response.text
            
            # Extract JSON-LD
            json_ld = self._extract_json_ld(html)
            if not json_ld:
                logger.warning(f"No JSON-LD found for {url}")
                return None
            
            # Validate SKU exists
            sku = json_ld.get('sku')
            if not sku:
                logger.warning(f"Missing SKU for {url}")
                return None
            
            # Extract prices from HTML (NOT from JSON-LD!)
            price_bgn, old_price_bgn = self._extract_bgn_price(html)
            price_eur = self._extract_eur_price(html)
            
            # Extract size from HTML
            size_raw, size_value, size_unit = self._extract_size(html)
            
            # Extract detailed availability from HTML
            avail_text, avail_type = self._extract_availability_detailed(html)
            if not avail_text:
                avail_text = self._extract_availability_jsonld(json_ld)
            
            # Build product data
            product = LidlProductData(
                sku=sku,
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
                availability=avail_text,
                availability_type=avail_type,
            )
            
            self.circuit_breaker.record_success()
            logger.info(f"Scraped: {product.name} - {price_bgn} лв - {size_raw} - {avail_text}")
            return product
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            self.circuit_breaker.record_failure()
            return None
        except Exception as e:
            logger.exception(f"Error parsing {url}")
            self.circuit_breaker.record_failure()
            return None
    
    def _save_checkpoint(self, processed_urls: List[str]):
        """Save checkpoint - OVERWRITES existing file."""
        checkpoint_data = {
            'processed_urls': processed_urls,
            'products': [p.to_dict() for p in self.products],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Checkpoint saved: {len(processed_urls)} processed")
    
    def _load_checkpoint(self) -> tuple[List[str], List[LidlProductData]]:
        """Load checkpoint if exists."""
        if not self.checkpoint_file.exists():
            return [], []
        
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            products = [LidlProductData(**p) for p in data.get('products', [])]
            return data.get('processed_urls', []), products
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return [], []
    
    def _delete_checkpoint(self):
        """Delete checkpoint file on successful completion."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            logger.info("Checkpoint file deleted")
    
    def scrape_products(self, urls: List[str], checkpoint_every: int = 10) -> List[LidlProductData]:
        """Scrape multiple product pages with checkpoint support."""
        # Load checkpoint
        processed_urls, self.products = self._load_checkpoint()
        if processed_urls:
            logger.info(f"Resuming from checkpoint: {len(processed_urls)} already processed")
        
        # Filter already processed
        remaining = [u for u in urls if u not in processed_urls]
        total = len(urls)
        
        logger.info(f"Starting scrape: {len(remaining)} remaining of {total} total")
        
        for i, url in enumerate(remaining, len(processed_urls) + 1):
            if self.circuit_breaker.is_open:
                logger.error("Circuit breaker open - stopping scrape")
                break
            
            product = self.fetch_product(url)
            if product:
                self.products.append(product)
            
            processed_urls.append(url)
            
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{total} ({len(self.products)} successful)")
            
            if checkpoint_every and i % checkpoint_every == 0:
                self._save_checkpoint(processed_urls)
            
            if i % 50 == 0:
                pause = random.uniform(30, 60)
                logger.info(f"Coffee break: {pause:.0f}s")
                time.sleep(pause)
        
        logger.info(f"Scrape complete: {len(self.products)}/{total} products")
        return self.products
    
    def _validate_price(self, price: float) -> bool:
        """Validate price is within reasonable bounds."""
        return price is not None and 0.01 <= price <= 10000.0
    
    def save_to_db(self):
        """Save products to normalized SQLite database with transaction safety."""
        if not self.products:
            logger.warning("No products to save")
            return
        
        now = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("BEGIN TRANSACTION")
            updated = 0
            inserted = 0
            skipped = 0
            
            for product in self.products:
                # Validate price
                if product.price_bgn and not self._validate_price(product.price_bgn):
                    logger.warning(f"Invalid price {product.price_bgn} for {product.sku}, skipping")
                    skipped += 1
                    continue
                
                # Find existing store_product by SKU
                cursor.execute("""
                    SELECT sp.id, sp.product_id FROM store_products sp
                    WHERE sp.store_id = ? AND sp.store_product_code = ?
                """, (LIDL_STORE_ID, product.sku))
                
                row = cursor.fetchone()
                
                if row:
                    store_product_id, product_id = row
                    
                    # Update store_product
                    cursor.execute("""
                        UPDATE store_products SET
                            store_product_url = COALESCE(?, store_product_url),
                            store_image_url = COALESCE(?, store_image_url),
                            package_size = COALESCE(?, package_size),
                            last_seen_at = ?,
                            scraped_at = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (product.product_url, product.image_url, product.size_raw,
                          now, now, now, store_product_id))
                    
                    # Update product
                    cursor.execute("""
                        UPDATE products SET
                            brand = COALESCE(?, brand),
                            quantity = COALESCE(?, quantity),
                            unit = COALESCE(?, unit),
                            description = COALESCE(?, description),
                            updated_at = ?
                        WHERE id = ?
                    """, (product.brand, product.size_value, product.size_unit,
                          product.description, now, product_id))
                    
                    # Update or insert price
                    if product.price_bgn:
                        cursor.execute("""
                            SELECT id FROM prices 
                            WHERE store_product_id = ? 
                            ORDER BY created_at DESC LIMIT 1
                        """, (store_product_id,))
                        
                        price_row = cursor.fetchone()
                        discount_pct = None
                        if product.old_price_bgn and product.old_price_bgn > product.price_bgn:
                            discount_pct = round((1 - product.price_bgn / product.old_price_bgn) * 100, 1)
                        
                        if price_row:
                            cursor.execute("""
                                UPDATE prices SET
                                    current_price = ?,
                                    old_price = ?,
                                    discount_percent = ?,
                                    currency = 'BGN',
                                    updated_at = ?
                                WHERE id = ?
                            """, (product.price_bgn, product.old_price_bgn, discount_pct,
                                  now, price_row[0]))
                        else:
                            cursor.execute("""
                                INSERT INTO prices (
                                    store_product_id, current_price, old_price, discount_percent,
                                    currency, valid_from, created_at, updated_at
                                ) VALUES (?, ?, ?, ?, 'BGN', ?, ?, ?)
                            """, (store_product_id, product.price_bgn, product.old_price_bgn,
                                  discount_pct, now, now, now))
                    
                    updated += 1
                else:
                    # Insert new product
                    cursor.execute("""
                        INSERT INTO products (name, normalized_name, brand, quantity, unit, 
                                            description, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (product.name, product.name.lower(), product.brand, product.size_value,
                          product.size_unit or 'бр', product.description, now, now))
                    
                    product_id = cursor.lastrowid
                    
                    # Insert store_product
                    cursor.execute("""
                        INSERT INTO store_products (
                            product_id, store_id, store_product_code, store_product_url,
                            store_image_url, package_size, last_seen_at, first_seen_at,
                            scraped_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (product_id, LIDL_STORE_ID, product.sku, product.product_url,
                          product.image_url, product.size_raw, now, now, now, now, now))
                    
                    store_product_id = cursor.lastrowid
                    
                    # Insert price
                    if product.price_bgn:
                        discount_pct = None
                        if product.old_price_bgn and product.old_price_bgn > product.price_bgn:
                            discount_pct = round((1 - product.price_bgn / product.old_price_bgn) * 100, 1)
                        
                        cursor.execute("""
                            INSERT INTO prices (
                                store_product_id, current_price, old_price, discount_percent,
                                currency, valid_from, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, 'BGN', ?, ?, ?)
                        """, (store_product_id, product.price_bgn, product.old_price_bgn,
                              discount_pct, now, now, now))
                    
                    inserted += 1
            
            conn.commit()
            logger.info(f"Saved to database: {updated} updated, {inserted} inserted, {skipped} skipped")
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error, transaction rolled back: {e}")
            raise
        finally:
            conn.close()
        
        # Delete checkpoint on successful save
        self._delete_checkpoint()
    
    def get_existing_product_urls(self) -> List[str]:
        """Get URLs for products already in database (from store_products table)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT store_product_url FROM store_products 
                WHERE store_id = ? AND store_product_url IS NOT NULL
            """, (LIDL_STORE_ID,))
            return [row[0] for row in cursor.fetchall()]


def main():
    """Run the scraper to update existing Lidl products."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    scraper = LidlProductScraper()
    urls = scraper.get_existing_product_urls()
    
    if not urls:
        logger.warning("No Lidl product URLs found in database")
        return
    
    logger.info(f"Found {len(urls)} products to update")
    products = scraper.scrape_products(urls)
    
    if products:
        scraper.save_to_db()
    
    prices_found = sum(1 for p in products if p.price_bgn)
    sizes_found = sum(1 for p in products if p.size_value)
    
    print(f"\n=== SCRAPE SUMMARY ===")
    print(f"Products scraped: {len(products)}")
    print(f"With BGN price: {prices_found} ({100*prices_found/len(products):.1f}%)" if products else "")
    print(f"With size: {sizes_found} ({100*sizes_found/len(products):.1f}%)" if products else "")


if __name__ == "__main__":
    main()
