#!/usr/bin/env python3
"""
Kaufland Enhanced Scraper - Extracts detailed product data

CRITICAL: The `price` field in Kaufland's JSON is EUR, not BGN!
BGN prices are in: prices.alternative.formatted.standard/old

Parsing strategy:
- Find all "offers":[] arrays in HTML (44+ arrays)
- Parse each as JSON
- Extract klNr, title, subtitle, unit, prices.alternative.formatted
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOMAIN = "www.kaufland.bg"
KAUFLAND_STORE_ID = 1
OFFERS_URL = "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html"
MAX_RETRIES = 3


@dataclass
class KauflandProduct:
    kl_nr: str
    title: str
    subtitle: Optional[str] = None
    detail_title: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    price_bgn: Optional[float] = None
    old_price_bgn: Optional[float] = None
    price_eur: Optional[float] = None
    discount_pct: Optional[int] = None
    size_value: Optional[float] = None
    size_unit: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_bgn_price(text: str) -> Optional[float]:
    """Parse BGN price from text like '12,38 ЛВ.'"""
    if not text:
        return None
    match = re.search(r'([\d,\.]+)\s*(?:ЛВ\.?|лв\.?)', text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except ValueError:
            pass
    return None


def extract_size(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract size from text like '400 г', '1.5 л', '2x500 мл'"""
    if not text:
        return None, None
    
    text_lower = text.lower()
    
    # Pack format
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
    
    # Single size
    patterns = [
        (r'(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
        (r'(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
        (r'(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
        (r'(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
    ]
    
    for pattern, unit in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                if unit == 'g' and value > 50000:
                    continue
                if unit == 'ml' and value > 50000:
                    continue
                if unit == 'kg':
                    return value * 1000, 'g'
                elif unit == 'l':
                    return value * 1000, 'ml'
                return value, unit
            except ValueError:
                continue
    
    # Piece count
    piece_match = re.search(r'(\d+)\s*(?:\+\s*\d+)?\s*бр\.?', text_lower)
    if piece_match:
        try:
            value = float(piece_match.group(1))
            if value <= 1000:
                return value, 'бр'
        except ValueError:
            pass
    
    return None, None


def extract_brand(text: str) -> Optional[str]:
    """Extract brand from text"""
    if not text:
        return None
    
    text_lower = text.lower()
    
    brands = [
        ('coca-cola', 'Coca-Cola'), ('coca cola', 'Coca-Cola'),
        ('k-classic', 'K-Classic'), ('k classic', 'K-Classic'),
        ('red bull', 'Red Bull'), ('milka', 'Milka'),
        ('nescafe', 'Nescafe'), ('jacobs', 'Jacobs'),
        ('lavazza', 'Lavazza'), ('tchibo', 'Tchibo'),
        ('pepsi', 'Pepsi'), ('fanta', 'Fanta'), ('sprite', 'Sprite'),
        ('nestle', 'Nestle'), ('ferrero', 'Ferrero'), ('kinder', 'Kinder'),
        ('haribo', 'Haribo'), ('nutella', 'Nutella'),
        ('pringles', 'Pringles'), ('pampers', 'Pampers'),
        ('ariel', 'Ariel'), ('lenor', 'Lenor'), ('persil', 'Persil'),
        ('верея', 'Верея'), ('olympus', 'Olympus'),
        ('danone', 'Danone'), ('president', 'President'),
        ('hochland', 'Hochland'), ('bonduelle', 'Bonduelle'),
        ('frezco', 'Frezco'), ('frezko', 'Frezco'),
        ('димитър маджаров', 'Димитър Маджаров'),
        ('девин', 'Devin'), ('банкя', 'Bankya'),
    ]
    
    for pattern, brand_name in brands:
        if pattern in text_lower:
            return brand_name
    
    return None


class KauflandEnhancedScraper:
    """Scrapes Kaufland offers page for product data using JSON array parsing."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(__file__).parent.parent.parent.parent / "data" / "promobg.db"
        self.products: List[KauflandProduct] = []
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0',
            'Accept-Language': 'bg-BG,bg;q=0.9',
        })
    
    def _fetch_with_retry(self, url: str) -> Optional[requests.Response]:
        """Fetch with simple retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=120)
                response.raise_for_status()
                return response
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(5 * (attempt + 1))
        return None
    
    def _extract_offers_from_json_arrays(self, html: str) -> List[Dict]:
        """Extract all offers from embedded JSON arrays in HTML."""
        all_offers = []
        seen_klnr = set()
        
        # Find all "offers":[ array starts
        for m in re.finditer(r'"offers":\[', html):
            start = m.end() - 1  # Include the [
            
            # Find matching closing bracket
            depth = 0
            end = start
            for i, c in enumerate(html[start:start+500000]):
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        end = start + i + 1
                        break
            
            array_str = html[start:end]
            
            try:
                offers = json.loads(array_str)
                for offer in offers:
                    klnr = offer.get('klNr')
                    if klnr and klnr not in seen_klnr:
                        seen_klnr.add(klnr)
                        all_offers.append(offer)
            except json.JSONDecodeError:
                continue
        
        logger.info(f"Extracted {len(all_offers)} unique offers from JSON arrays")
        return all_offers
    
    def _offer_to_product(self, offer: Dict) -> Optional[KauflandProduct]:
        """Convert JSON offer dict to KauflandProduct."""
        kl_nr = offer.get('klNr')
        title = offer.get('title')
        
        if not kl_nr or not title:
            return None
        
        subtitle = offer.get('subtitle')
        unit = offer.get('unit')
        
        # Extract BGN prices from prices.alternative.formatted
        prices = offer.get('prices', {}).get('alternative', {}).get('formatted', {})
        price_bgn = parse_bgn_price(prices.get('standard'))
        old_price_bgn = parse_bgn_price(prices.get('old'))
        
        # Extract size from unit field first, then subtitle, then title
        size_val, size_unit_str = None, None
        if unit:
            size_val, size_unit_str = extract_size(unit)
        if not size_val and subtitle:
            size_val, size_unit_str = extract_size(subtitle)
        if not size_val:
            size_val, size_unit_str = extract_size(title)
        
        # Extract brand - title often IS the brand for single-word titles
        brand = None
        if title and len(title.split()) <= 2:
            brand = title
        if not brand:
            brand = extract_brand(title)
        if not brand and subtitle:
            brand = extract_brand(subtitle)
        
        return KauflandProduct(
            kl_nr=kl_nr,
            title=title,
            subtitle=subtitle,
            detail_title=offer.get('detailTitle'),
            description=offer.get('detailDescription', '').replace('\\n', ' | ') if offer.get('detailDescription') else None,
            unit=unit,
            price_bgn=price_bgn,
            old_price_bgn=old_price_bgn,
            price_eur=offer.get('price'),
            discount_pct=offer.get('discount'),
            size_value=size_val,
            size_unit=size_unit_str,
            brand=brand,
            image_url=offer.get('listImage'),
            date_from=offer.get('dateFrom'),
            date_to=offer.get('dateTo'),
        )
    
    def scrape(self) -> List[KauflandProduct]:
        """Scrape Kaufland offers page."""
        time.sleep(random.uniform(1.0, 2.0))
        
        logger.info(f"Fetching {OFFERS_URL}")
        response = self._fetch_with_retry(OFFERS_URL)
        
        if not response:
            logger.error("Failed to fetch Kaufland offers page")
            return []
        
        html = response.text
        logger.info(f"Page size: {len(html):,} bytes")
        
        # Extract all offers from JSON arrays
        offers = self._extract_offers_from_json_arrays(html)
        
        # Convert to products
        self.products = []
        for offer in offers:
            product = self._offer_to_product(offer)
            if product:
                self.products.append(product)
        
        logger.info(f"Converted {len(self.products)} offers to products")
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
                # Validate price before processing
                if product.price_bgn and not self._validate_price(product.price_bgn):
                    logger.warning(f"Invalid price {product.price_bgn} for {product.kl_nr}, skipping")
                    skipped += 1
                    continue
                full_name = f"{product.title} {product.subtitle}" if product.subtitle else product.title
                
                # Find existing store_product
                cursor.execute("""
                    SELECT sp.id, sp.product_id FROM store_products sp
                    WHERE sp.store_id = ? AND sp.store_product_code = ?
                """, (KAUFLAND_STORE_ID, product.kl_nr))
                
                row = cursor.fetchone()
                
                if row:
                    store_product_id, product_id = row
                    
                    # Update store_product
                    cursor.execute("""
                        UPDATE store_products SET
                            store_image_url = ?,
                            package_size = ?,
                            last_seen_at = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (product.image_url, product.unit, now, now, store_product_id))
                    
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
                    cursor.execute("""
                        SELECT id FROM prices 
                        WHERE store_product_id = ? 
                        ORDER BY created_at DESC LIMIT 1
                    """, (store_product_id,))
                    
                    price_row = cursor.fetchone()
                    if price_row and product.price_bgn:
                        cursor.execute("""
                            UPDATE prices SET
                                current_price = ?,
                                old_price = ?,
                                discount_percent = ?,
                                currency = 'BGN',
                                valid_from = ?,
                                valid_to = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (product.price_bgn, product.old_price_bgn, product.discount_pct,
                              product.date_from, product.date_to, now, price_row[0]))
                    elif product.price_bgn:
                        cursor.execute("""
                            INSERT INTO prices (
                                store_product_id, current_price, old_price, discount_percent,
                                currency, valid_from, valid_to, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, 'BGN', ?, ?, ?, ?)
                        """, (store_product_id, product.price_bgn, product.old_price_bgn,
                              product.discount_pct, product.date_from, product.date_to, now, now))
                    
                    updated += 1
                else:
                    # Insert new product
                    cursor.execute("""
                        INSERT INTO products (name, normalized_name, brand, quantity, unit, description, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (full_name, full_name.lower(), product.brand, product.size_value, 
                          product.size_unit or 'бр', product.description, now, now))
                    
                    product_id = cursor.lastrowid
                    
                    # Insert store_product
                    cursor.execute("""
                        INSERT INTO store_products (
                            product_id, store_id, store_product_code, store_image_url,
                            package_size, last_seen_at, first_seen_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (product_id, KAUFLAND_STORE_ID, product.kl_nr, product.image_url,
                          product.unit, now, now, now, now))
                    
                    store_product_id = cursor.lastrowid
                    
                    # Insert price
                    if product.price_bgn:
                        cursor.execute("""
                            INSERT INTO prices (
                                store_product_id, current_price, old_price, discount_percent,
                                currency, valid_from, valid_to, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, 'BGN', ?, ?, ?, ?)
                        """, (store_product_id, product.price_bgn, product.old_price_bgn,
                              product.discount_pct, product.date_from, product.date_to, now, now))
                    
                    inserted += 1
            
            conn.commit()
            logger.info(f"Saved to database: {updated} updated, {inserted} inserted, {skipped} skipped")
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error, transaction rolled back: {e}")
            raise
        finally:
            conn.close()
    
    def save_to_json(self, output_path: Optional[Path] = None):
        """Save products to JSON file."""
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
    
    with_bgn_price = sum(1 for p in products if p.price_bgn)
    with_size = sum(1 for p in products if p.size_value)
    with_brand = sum(1 for p in products if p.brand)
    with_unit = sum(1 for p in products if p.unit)
    with_discount = sum(1 for p in products if p.discount_pct)
    
    print(f"With BGN price: {with_bgn_price} ({100*with_bgn_price/len(products):.1f}%)")
    print(f"With size value: {with_size} ({100*with_size/len(products):.1f}%)")
    print(f"With unit field: {with_unit} ({100*with_unit/len(products):.1f}%)")
    print(f"With brand: {with_brand} ({100*with_brand/len(products):.1f}%)")
    print(f"With discount: {with_discount} ({100*with_discount/len(products):.1f}%)")
    
    scraper.save_to_db()
    scraper.save_to_json()
    
    print(f"\n{'='*60}")
    print("SAMPLE PRODUCTS")
    print(f"{'='*60}")
    
    # Find kiwi specifically
    kiwi = next((p for p in products if p.kl_nr == '09700101'), None)
    if kiwi:
        print(f"\n🥝 KIWI (09700101):")
        print(f"  {kiwi.title} - {kiwi.subtitle}")
        print(f"  Price: {kiwi.price_bgn} лв (was {kiwi.old_price_bgn} лв)")
        print(f"  Unit: {kiwi.unit}")
    
    # More samples
    sample = [p for p in products if p.price_bgn and p.old_price_bgn][:5]
    for p in sample:
        print(f"\n{p.title} - {p.subtitle}")
        print(f"  Price: {p.price_bgn} лв (was {p.old_price_bgn} лв) -{p.discount_pct}%")
        print(f"  Unit: {p.unit} | Size: {p.size_value} {p.size_unit}")


if __name__ == '__main__':
    main()
