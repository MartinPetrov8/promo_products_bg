#!/usr/bin/env python3
"""
Lidl.bg API Scraper

Uses the discovered search API endpoint instead of HTML parsing.
Returns clean, structured JSON data with proper size/weight fields.

API Endpoint: https://www.lidl.bg/q/api/search
Parameters:
  - assortment=BG
  - locale=bg_BG
  - version=v2.0.0
  - category.id=<category_id>
  - fetchSize=50

Data quality is MUCH better than HTML parsing:
  - Size/Weight: price.packaging.text (clean strings like "500 g/опаковка")
  - Prices: Dual currency (EUR + BGN) 
  - Discounts: Structured percentages
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

import requests

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)

API_BASE = "https://www.lidl.bg/q/api/search"
DOMAIN = "www.lidl.bg"

# Food categories discovered during testing
FOOD_CATEGORIES = {
    "10068374": "Храни и напитки (Food & Drinks - Parent)",
    "10071012": "Плодове и зеленчуци (Fruits & Vegetables)",
    "10071015": "Хляб и тестени изделия (Bread & Bakery)",
    "10071016": "Прясно месо (Fresh Meat)",
    "10071017": "Мляко и млечни продукти (Milk & Dairy)",
    "10071018": "Колбаси (Sausages/Deli)",
    "10071019": "Замразени храни (Frozen Foods)",
    "10071020": "Консерви и готови храни (Canned & Ready Foods)",
    "10071021": "Напитки (Beverages)",
    "10071022": "Сладкиши и снаксове (Sweets & Snacks)",
    "10071023": "Подправки и сосове (Spices & Sauces)",
}


@dataclass
class LidlProduct:
    """Clean product data from Lidl API"""
    product_id: str
    name: str
    brand: Optional[str]
    size: Optional[str]  # Clean size string from price.packaging.text
    size_unit: Optional[str]  # Parsed unit (g, ml, l, kg)
    size_value: Optional[float]  # Parsed numeric value
    price_eur: float
    price_bgn: Optional[float]
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_percent: Optional[int]
    description: Optional[str]
    category: Optional[str]
    image_url: Optional[str]
    product_url: Optional[str]
    ians: List[str]  # Product identifiers (barcodes/IANs)
    availability: Optional[str]
    raw_keyfacts: Optional[str]  # Original keyfacts HTML for parsing additional data


class LidlApiScraper:
    """
    Scrapes Lidl.bg using the search API.
    
    Much cleaner than HTML parsing - returns structured JSON.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(__file__).parent.parent.parent.parent / "data" / "promobg.db"
        self.products: List[LidlProduct] = []
        self.seen_ids: Set[str] = set()
        
        # Infrastructure setup
        self.session_manager = SessionManager(config=SessionConfig(
            max_requests=100,
            max_age_seconds=300,
            cookie_persistence=True
        ))
        
        self.rate_limiter = DomainRateLimiter()
        # Uses default config for lidl.bg (10 req/min, 3s min delay)
        
        self.circuit_breaker = CircuitBreaker(name="lidl_api")
        
        self.retry_handler = RetryHandler(RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=2.0
        ))
    
    def _parse_size(self, packaging_text: Optional[str]) -> tuple[Optional[str], Optional[float], Optional[str]]:
        """
        Parse size from packaging text.
        
        Examples:
          "500 g/опаковка" -> ("500 g", 500.0, "g")
          "1 l/опаковка" -> ("1 l", 1.0, "l")
          "≈ 650 g/опаковка" -> ("650 g", 650.0, "g")
          "10 бр. х 8 - 17 г" -> complex, return raw
        
        Returns: (clean_size, numeric_value, unit)
        """
        if not packaging_text:
            return None, None, None
        
        # Remove "≈" and "/опаковка" suffix
        text = packaging_text.replace("≈", "").replace("/опаковка", "").strip()
        
        # Try standard patterns: "500 g", "1.5 l", "1 kg"
        match = re.match(r'^([\d.,]+)\s*(g|kg|ml|l|бр)\.?$', text, re.IGNORECASE)
        if match:
            value_str = match.group(1).replace(",", ".")
            unit = match.group(2).lower()
            try:
                value = float(value_str)
                clean = f"{value_str} {unit}"
                return clean, value, unit
            except ValueError:
                pass
        
        # Return original if can't parse
        return text if text else None, None, None
    
    def _parse_keyfacts(self, keyfacts_html: Optional[str]) -> Dict[str, Any]:
        """
        Parse keyfacts HTML for additional product details.
        
        Example input: "<ul><li>3.5% масленост</li><li>UHT</li></ul>"
        
        Returns dict with extracted values like:
          {"fat_content": "3.5%", "features": ["UHT"]}
        """
        result = {"features": [], "fat_content": None, "origin": None}
        
        if not keyfacts_html:
            return result
        
        # Extract all <li> items
        items = re.findall(r'<li>([^<]+)</li>', keyfacts_html)
        
        for item in items:
            item = item.strip()
            
            # Fat content: "3.5% масленост" or "4% масленост"
            fat_match = re.search(r'([\d.,]+%)\s*масленост', item)
            if fat_match:
                result["fat_content"] = fat_match.group(1)
                continue
            
            # Origin: "Произход: ..." or "Българско"
            if "Произход" in item or "Българск" in item.lower():
                result["origin"] = item
                continue
            
            # Everything else is a feature
            result["features"].append(item)
        
        return result
    
    def _extract_product(self, item: Dict[str, Any]) -> Optional[LidlProduct]:
        """Extract a LidlProduct from API response item"""
        try:
            product_id = str(item.get("productId", ""))
            if not product_id or product_id in self.seen_ids:
                return None
            
            self.seen_ids.add(product_id)
            
            # Basic info
            name = item.get("fullTitle", "").strip()
            
            # Brand (sometimes nested, sometimes in keyfacts)
            brand = None
            if "brand" in item and isinstance(item["brand"], dict):
                brand = item["brand"].get("name")
            
            # Price data
            price_data = item.get("price", {})
            price_eur = price_data.get("price")
            price_bgn = price_data.get("priceSecond")
            old_price_eur = price_data.get("oldPrice")
            old_price_bgn = price_data.get("oldPriceSecond")
            
            # Discount
            discount = None
            if "discount" in price_data and isinstance(price_data["discount"], dict):
                discount = price_data["discount"].get("percentageDiscount")
            
            # Size from packaging
            packaging = price_data.get("packaging", {})
            packaging_text = packaging.get("text") if isinstance(packaging, dict) else None
            clean_size, size_value, size_unit = self._parse_size(packaging_text)
            
            # Keyfacts (description HTML)
            keyfacts = item.get("keyfacts", {})
            keyfacts_html = keyfacts.get("description") if isinstance(keyfacts, dict) else None
            keyfacts_data = self._parse_keyfacts(keyfacts_html)
            
            # If fat content found, append to name for better matching
            description = None
            if keyfacts_data["fat_content"]:
                description = f"{keyfacts_data['fat_content']} масленост"
            if keyfacts_data["features"]:
                feature_str = ", ".join(keyfacts_data["features"])
                description = f"{description}, {feature_str}" if description else feature_str
            
            # Category
            category = None
            meta = item.get("meta", {})
            if isinstance(meta, dict):
                breadcrumbs = meta.get("wonCategoryBreadcrumbs")
                if breadcrumbs:
                    category = breadcrumbs
            
            # Image
            image_url = item.get("image")
            
            # Product URL
            canonical = item.get("canonicalUrl")
            product_url = f"https://www.lidl.bg{canonical}" if canonical else None
            
            # IANs (product identifiers/barcodes)
            ians = item.get("ians", [])
            if not isinstance(ians, list):
                ians = []
            
            # Availability
            availability = None
            stock = item.get("stockAvailability", {})
            if isinstance(stock, dict):
                badge_info = stock.get("badgeInfo", {})
                if isinstance(badge_info, dict):
                    badges = badge_info.get("badges", [])
                    if badges and isinstance(badges, list) and len(badges) > 0:
                        availability = badges[0].get("text")
            
            return LidlProduct(
                product_id=product_id,
                name=name,
                brand=brand,
                size=clean_size,
                size_unit=size_unit,
                size_value=size_value,
                price_eur=price_eur,
                price_bgn=price_bgn,
                old_price_eur=old_price_eur,
                old_price_bgn=old_price_bgn,
                discount_percent=discount,
                description=description,
                category=category,
                image_url=image_url,
                product_url=product_url,
                ians=ians,
                availability=availability,
                raw_keyfacts=keyfacts_html
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract product: {e}")
            return None
    
    def _fetch_category(self, category_id: str, fetch_size: int = 50) -> List[Dict[str, Any]]:
        """Fetch all products from a category via API"""
        all_items = []
        offset = 0
        
        while True:
            # Rate limit - wait before request
            self.rate_limiter.wait(f"https://{DOMAIN}/")
            
            # Circuit breaker check
            if self.circuit_breaker.is_open:
                logger.warning("Circuit breaker open, waiting...")
                time.sleep(60)
                continue
            
            params = {
                "assortment": "BG",
                "locale": "bg_BG",
                "version": "v2.0.0",
                "category.id": category_id,
                "fetchSize": fetch_size,
                "offset": offset
            }
            
            session = self.session_manager.get_session(DOMAIN)
            
            try:
                def make_request():
                    resp = session.get(
                        API_BASE,
                        params=params,
                        timeout=30,
                        headers={
                            "Accept": "application/json",
                            "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
                            "Referer": "https://www.lidl.bg/c/hrani-i-napitki/c10068374"
                        }
                    )
                    resp.raise_for_status()
                    return resp.json()
                
                data = self.retry_handler.execute(make_request)
                self.circuit_breaker._on_success()
                
                items = data.get("items", [])
                if not items:
                    break
                
                all_items.extend(items)
                logger.info(f"Category {category_id}: fetched {len(items)} items (total: {len(all_items)})")
                
                # Check if more pages
                total = data.get("totalCount", 0)
                if len(all_items) >= total:
                    break
                
                offset += fetch_size
                
                # Human-like delay
                time.sleep(random.uniform(1.0, 2.5))
                
            except Exception as e:
                self.circuit_breaker._on_failure()
                logger.error(f"Failed to fetch category {category_id} offset {offset}: {e}")
                break
        
        return all_items
    
    def scrape_all_categories(self, categories: Optional[List[str]] = None) -> List[LidlProduct]:
        """
        Scrape all food categories.
        
        Args:
            categories: List of category IDs to scrape, or None for all food categories
        
        Returns:
            List of LidlProduct objects
        """
        if categories is None:
            categories = list(FOOD_CATEGORIES.keys())
        
        logger.info(f"Starting scrape of {len(categories)} categories")
        
        for cat_id in categories:
            cat_name = FOOD_CATEGORIES.get(cat_id, cat_id)
            logger.info(f"Scraping category: {cat_name}")
            
            items = self._fetch_category(cat_id)
            
            for item in items:
                product = self._extract_product(item)
                if product:
                    self.products.append(product)
            
            # Coffee break between categories
            time.sleep(random.uniform(3.0, 6.0))
        
        logger.info(f"Scrape complete: {len(self.products)} unique products")
        return self.products
    
    def save_to_json(self, output_path: Optional[Path] = None) -> Path:
        """Save products to JSON file"""
        if output_path is None:
            output_path = Path(__file__).parent.parent.parent.parent / "data" / "lidl_api_products.json"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = [asdict(p) for p in self.products]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.products)} products to {output_path}")
        return output_path
    
    def save_to_db(self) -> int:
        """Save products to SQLite database"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted = 0
        updated = 0
        
        for p in self.products:
            # Check if exists
            cursor.execute("SELECT id FROM products WHERE store_id = 2 AND external_id = ?", (p.product_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Update
                cursor.execute("""
                    UPDATE products SET
                        name = ?,
                        brand = ?,
                        size = ?,
                        size_unit = ?,
                        size_value = ?,
                        regular_price = ?,
                        promo_price = ?,
                        discount_percent = ?,
                        description = ?,
                        category = ?,
                        image_url = ?,
                        product_url = ?,
                        barcode = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    p.name, p.brand, p.size, p.size_unit, p.size_value,
                    p.old_price_bgn or p.price_bgn, p.price_bgn,
                    p.discount_percent, p.description, p.category,
                    p.image_url, p.product_url,
                    p.ians[0] if p.ians else None,
                    existing[0]
                ))
                updated += 1
            else:
                # Insert
                cursor.execute("""
                    INSERT INTO products (
                        store_id, external_id, name, brand, size, size_unit, size_value,
                        regular_price, promo_price, discount_percent, description,
                        category, image_url, product_url, barcode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    2, p.product_id, p.name, p.brand, p.size, p.size_unit, p.size_value,
                    p.old_price_bgn or p.price_bgn, p.price_bgn,
                    p.discount_percent, p.description, p.category,
                    p.image_url, p.product_url,
                    p.ians[0] if p.ians else None
                ))
                inserted += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database: {inserted} inserted, {updated} updated")
        return inserted + updated


def main():
    """Run the scraper"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    scraper = LidlApiScraper()
    
    # Test with one category first
    # products = scraper.scrape_all_categories(["10071017"])  # Milk & Dairy only
    
    # Full scrape
    products = scraper.scrape_all_categories()
    
    # Save results
    scraper.save_to_json()
    scraper.save_to_db()
    
    # Summary
    print(f"\n{'='*50}")
    print(f"LIDL API SCRAPE COMPLETE")
    print(f"{'='*50}")
    print(f"Total products: {len(products)}")
    
    # Stats
    with_size = sum(1 for p in products if p.size)
    with_brand = sum(1 for p in products if p.brand)
    with_ians = sum(1 for p in products if p.ians)
    with_discount = sum(1 for p in products if p.discount_percent)
    
    print(f"With size: {with_size} ({100*with_size/len(products):.1f}%)")
    print(f"With brand: {with_brand} ({100*with_brand/len(products):.1f}%)")
    print(f"With IANs: {with_ians} ({100*with_ians/len(products):.1f}%)")
    print(f"With discount: {with_discount} ({100*with_discount/len(products):.1f}%)")


if __name__ == "__main__":
    main()
