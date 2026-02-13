#!/usr/bin/env python3
"""
Kaufland Enhanced Scraper - Extracts detailed product data

Scrapes the offers page to get embedded JSON data with:
- Product names, descriptions, prices
- Size/weight extraction from multiple fields
- Brand detection

Infrastructure: SessionManager, RateLimiter, CircuitBreaker, RetryHandler
"""

import re
import json
import sqlite3
import time
import random
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOMAIN = "www.kaufland.bg"
KAUFLAND_STORE_ID = 1
OFFERS_URL = "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html"

# Context window sizes for JSON extraction
CONTEXT_BEFORE = 1000
CONTEXT_AFTER = 2500


@dataclass
class KauflandProduct:
    kl_nr: str
    title: str
    detail_title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    old_price: Optional[float] = None
    discount_pct: Optional[int] = None
    size_value: Optional[float] = None
    size_unit: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_size(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract size from text like '400 г', '1.5 л', '2x500 мл', '10 бр.'"""
    if not text:
        return None, None
    
    text_lower = text.lower()
    
    # Pack format: 2x500 ml, 6 x 1.5 л
    pack_patterns = [
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
    ]
    
    for pattern, unit in pack_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                count = int(match.group(1))
                value = float(match.group(2).replace(',', '.'))
                total = count * value
                if unit in ['kg', 'l']:
                    return total * 1000, 'g' if unit == 'kg' else 'ml'
                return total, 'g' if unit == 'g' else 'ml'
            except ValueError:
                continue
    
    # Single size patterns - weight/volume
    patterns = [
        (r'(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
        (r'(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
        (r'(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
        (r'(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
        (r'[Øø](\d+[.,]?\d*)\s*(см|cm)\b', 'cm'),
    ]
    
    for pattern, unit in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                # Sanity check - reject absurd values
                if unit == 'g' and value > 50000:  # 50kg max
                    continue
                if unit == 'ml' and value > 50000:  # 50L max
                    continue
                if unit == 'kg':
                    return value * 1000, 'g'
                elif unit == 'l':
                    return value * 1000, 'ml'
                return value, unit
            except ValueError:
                continue
    
    # Piece count patterns
    piece_match = re.search(r'(\d+)\s*(?:\+\s*\d+)?\s*(?:--\s*\d+)?\s*бр\.?', text_lower)
    if piece_match:
        try:
            value = float(piece_match.group(1))
            if value <= 1000:  # Sanity check
                return value, 'бр'
        except ValueError:
            pass
    
    return None, None


def extract_brand(text: str) -> Optional[str]:
    """Extract brand from product name or description"""
    if not text:
        return None
    
    text_lower = text.lower()
    
    brands = [
        ('coca-cola', 'Coca-Cola'), ('coca cola', 'Coca-Cola'),
        ('k-classic', 'K-Classic'), ('k classic', 'K-Classic'),
        ('red bull', 'Red Bull'),
        ('lay\'s', "Lay's"), ('lays', "Lay's"),
        ('milka', 'Milka'), ('nescafe', 'Nescafe'), ('jacobs', 'Jacobs'),
        ('lavazza', 'Lavazza'), ('tchibo', 'Tchibo'),
        ('pepsi', 'Pepsi'), ('fanta', 'Fanta'), ('sprite', 'Sprite'),
        ('nestle', 'Nestle'), ('nestlé', 'Nestle'),
        ('ferrero', 'Ferrero'), ('kinder', 'Kinder'),
        ('lindt', 'Lindt'), ('haribo', 'Haribo'), ('nutella', 'Nutella'),
        ('pringles', 'Pringles'), ('doritos', 'Doritos'),
        ('heineken', 'Heineken'), ('stella artois', 'Stella Artois'),
        ('pampers', 'Pampers'), ('huggies', 'Huggies'),
        ('ariel', 'Ariel'), ('lenor', 'Lenor'), ('persil', 'Persil'),
        ('finish', 'Finish'), ('fairy', 'Fairy'),
        ('emeka', 'Emeka'), ('zewa', 'Zewa'),
        ('верея', 'Верея'), ('olympus', 'Olympus'), ('олимпус', 'Olympus'),
        ('danone', 'Danone'), ('данон', 'Danone'),
        ('president', 'President'), ('президент', 'President'),
        ('hochland', 'Hochland'), ('хохланд', 'Hochland'),
        ('dr. oetker', 'Dr. Oetker'), ('knorr', 'Knorr'),
        ('maggi', 'Maggi'), ('hellmann\'s', "Hellmann's"),
        ('bonduelle', 'Bonduelle'), ('бондюел', 'Bonduelle'),
        ('barilla', 'Barilla'), ('де чеко', 'De Cecco'),
        ('aquaphor', 'Aquaphor'), ('аквафор', 'Aquaphor'),
        ('oral-b', 'Oral-B'), ('colgate', 'Colgate'),
        ('nivea', 'Nivea'), ('dove', 'Dove'), ('rexona', 'Rexona'),
        ('калиакра', 'Калиакра'), ('девин', 'Devin'),
        ('банкя', 'Bankya'), ('горна баня', 'Горна Баня'),
    ]
    
    for pattern, brand_name in brands:
        if pattern in text_lower:
            return brand_name
    
    return None


class KauflandEnhancedScraper:
    """
    Scrapes Kaufland offers page for product data.
    
    Uses embedded JSON in HTML - extracts klNr entries and associated fields.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(__file__).parent.parent.parent.parent / "data" / "promobg.db"
        self.products: List[KauflandProduct] = []
        
        # Infrastructure
        self.session_manager = SessionManager(config=SessionConfig(
            max_requests=50,
            max_age_seconds=300,
            cookie_persistence=True
        ))
        
        self.rate_limiter = DomainRateLimiter()
        self.circuit_breaker = CircuitBreaker(name="kaufland_enhanced")
        self.retry_handler = RetryHandler(RetryConfig(
            max_attempts=3,
            base_delay=5.0,
            max_delay=60.0,
            exponential_base=2.0
        ))
    
    def _fetch_with_retry(self, url: str) -> Optional[requests.Response]:
        """Fetch URL with retry logic and circuit breaker."""
        def _do_fetch():
            if self.circuit_breaker.is_open():
                raise Exception("Circuit breaker is open")
            session = self.session_manager.get_session(DOMAIN)
            response = session.get(url, timeout=60)
            response.raise_for_status()
            return response
        
        try:
            return self.retry_handler.execute(_do_fetch)
        except Exception as e:
            logger.error(f"All retries failed for {url}: {e}")
            return None
    
    def _extract_products_from_html(self, html: str) -> List[KauflandProduct]:
        """Extract products from embedded JSON in HTML."""
        products = []
        seen = set()
        
        kl_matches = list(re.finditer(r'"klNr":"([0-9]+)"', html))
        logger.info(f"Found {len(kl_matches)} klNr entries")
        
        for m in kl_matches:
            kl = m.group(1)
            if kl in seen:
                continue
            seen.add(kl)
            
            # Extract context around klNr
            start = max(0, m.start() - CONTEXT_BEFORE)
            end = min(len(html), m.start() + CONTEXT_AFTER)
            context = html[start:end]
            
            # Extract fields
            title_m = re.search(r'"title":"([^"]+)"', context)
            if not title_m:
                continue
            
            subtitle_m = re.search(r'"subtitle":"([^"]*)"', context)
            detail_title_m = re.search(r'"detailTitle":"([^"]*)"', context)
            desc_m = re.search(r'"detailDescription":"([^"]*)"', context)
            price_m = re.search(r'"price":([\d.]+)', context)
            old_price_m = re.search(r'"oldPrice":([\d.]+)', context)
            image_m = re.search(r'"listImage":"([^"]+)"', context)
            
            title = title_m.group(1)
            subtitle = subtitle_m.group(1) if subtitle_m else None
            detail_title = detail_title_m.group(1) if detail_title_m else None
            description = desc_m.group(1).replace('\\n', ' | ') if desc_m else None
            price = float(price_m.group(1)) if price_m else None
            old_price = float(old_price_m.group(1)) if old_price_m else None
            image_url = image_m.group(1) if image_m else None
            
            # Calculate discount
            discount_pct = None
            if price and old_price and old_price > price:
                discount_pct = int(100 * (old_price - price) / old_price)
            
            # Extract size - try multiple sources
            size_val, size_unit = None, None
            if subtitle:
                size_val, size_unit = extract_size(subtitle)
            if not size_val and description:
                size_val, size_unit = extract_size(description)
            if not size_val:
                size_val, size_unit = extract_size(title)
            
            # Extract brand
            brand = extract_brand(title)
            if not brand and description:
                brand = extract_brand(description)
            if not brand and detail_title:
                brand = extract_brand(detail_title)
            
            products.append(KauflandProduct(
                kl_nr=kl,
                title=title,
                detail_title=detail_title,
                subtitle=subtitle,
                description=description,
                price=price,
                old_price=old_price,
                discount_pct=discount_pct,
                size_value=size_val,
                size_unit=size_unit,
                brand=brand,
                image_url=image_url,
            ))
        
        return products
    
    def scrape(self) -> List[KauflandProduct]:
        """Scrape Kaufland offers page."""
        self.rate_limiter.wait(OFFERS_URL)
        time.sleep(random.uniform(1.0, 2.0))
        
        logger.info(f"Fetching {OFFERS_URL}")
        response = self._fetch_with_retry(OFFERS_URL)
        
        if not response:
            self.circuit_breaker.record_failure()
            logger.error("Failed to fetch Kaufland offers page")
            return []
        
        self.circuit_breaker.record_success()
        html = response.text
        logger.info(f"Page size: {len(html)} bytes")
        
        self.products = self._extract_products_from_html(html)
        logger.info(f"Extracted {len(self.products)} unique products")
        
        return self.products
    
    def save_to_db(self):
        """Save products to SQLite database."""
        if not self.products:
            logger.warning("No products to save")
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for product in self.products:
                # Try update first
                cursor.execute("""
                    UPDATE products SET
                        name = ?,
                        price = ?,
                        original_price = ?,
                        description = ?,
                        size = ?,
                        size_unit = ?,
                        image_url = ?,
                        brand = ?,
                        scraped_at = ?
                    WHERE store_id = ? AND product_code = ?
                """, (
                    product.title,
                    product.price,
                    product.old_price,
                    product.description,
                    str(product.size_value) if product.size_value else None,
                    product.size_unit,
                    product.image_url,
                    product.brand,
                    product.scraped_at,
                    KAUFLAND_STORE_ID,
                    product.kl_nr,
                ))
                
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO products (
                            store_id, product_code, name, price, original_price,
                            description, size, size_unit, image_url, brand,
                            product_url, scraped_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        KAUFLAND_STORE_ID,
                        product.kl_nr,
                        product.title,
                        product.price,
                        product.old_price,
                        product.description,
                        str(product.size_value) if product.size_value else None,
                        product.size_unit,
                        product.image_url,
                        product.brand,
                        product.product_url,
                        product.scraped_at,
                    ))
            
            conn.commit()
            logger.info(f"Saved {len(self.products)} products to database")
    
    def save_to_json(self, output_path: Optional[Path] = None):
        """Save products to JSON file (for debugging/export)."""
        output = output_path or self.db_path.parent / "kaufland_enhanced.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in self.products], f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved to {output}")


def main():
    scraper = KauflandEnhancedScraper()
    products = scraper.scrape()
    
    if not products:
        print("No products scraped!")
        return
    
    print(f"\n{'='*60}")
    print("KAUFLAND ENHANCED SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Total products: {len(products)}")
    
    with_size = sum(1 for p in products if p.size_value)
    with_brand = sum(1 for p in products if p.brand)
    with_price = sum(1 for p in products if p.price)
    with_desc = sum(1 for p in products if p.description)
    
    print(f"With size: {with_size} ({100*with_size/len(products):.1f}%)")
    print(f"With brand: {with_brand} ({100*with_brand/len(products):.1f}%)")
    print(f"With price: {with_price} ({100*with_price/len(products):.1f}%)")
    print(f"With description: {with_desc} ({100*with_desc/len(products):.1f}%)")
    
    # Save to both DB and JSON
    scraper.save_to_db()
    scraper.save_to_json()
    
    print(f"\n{'='*60}")
    print("SAMPLE PRODUCTS (with descriptions)")
    print(f"{'='*60}")
    
    sample = [p for p in products if p.description][:5]
    for p in sample:
        print(f"\nTitle: {p.title}")
        print(f"  Detail: {p.detail_title}")
        print(f"  Subtitle: {p.subtitle}")
        print(f"  Desc: {p.description[:80] if p.description else None}...")
        print(f"  Brand: {p.brand} | Size: {p.size_value} {p.size_unit} | Price: {p.price}")


if __name__ == '__main__':
    main()
