"""
Lidl.bg Scraper - Combined API + HTML

Uses:
1. Search API for category data (structured JSON)
2. Promotions page for promotional items (HTML parsing with validation)

Validation:
- Price validation: reject >200€ or schema indices (whole numbers >100)
- Old_price validation: reject if >4x current or >200€
- Discount validation: reject >75%
"""

import json
import logging
import re
import time
import html
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Set
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)

# Validation constants
MAX_REASONABLE_PRICE = 200
MAX_SCHEMA_INDEX = 100
MAX_OLD_PRICE_RATIO = 4
MAX_DISCOUNT_PCT = 75

# API settings
SEARCH_API = "https://www.lidl.bg/q/api/search"
GRIDBOXES_API = "https://www.lidl.bg/p/api/gridboxes/BG/bg"

# Categories to scrape via search API
FOOD_CATEGORIES = [
    "10068374",  # Food & Drinks (parent)
    "10071012",  # Fruits & Vegetables
    "10071015",  # Bread & Bakery
    "10071016",  # Fresh Meat
    "10071017",  # Milk & Dairy
    "10071018",  # Sausages/Deli
    "10071019",  # Frozen Foods
    "10071020",  # Canned & Ready Foods
    "10071021",  # Beverages
    "10071022",  # Sweets & Snacks
    "10071023",  # Spices & Sauces
]

# HTML pages with pre-rendered data
HTML_PAGES = [
    "https://www.lidl.bg/c/lidl-plus-promotsii/a10039565",
]


@dataclass
class LidlProduct:
    """Product data from Lidl"""
    product_id: str
    name: str
    brand: Optional[str]
    category: str
    quantity: Optional[str]
    price_eur: float
    price_bgn: float
    old_price_eur: float
    old_price_bgn: float
    discount_pct: int
    image_url: Optional[str]
    product_url: str
    availability: Optional[str]
    internal_code: Optional[str]


def validate_price(price_eur: float, old_price_eur: float, name: str) -> tuple:
    """Validate prices, return (price, old_price, discount, is_valid)"""
    # Reject schema indices
    if price_eur > MAX_SCHEMA_INDEX and price_eur == int(price_eur):
        logger.debug(f"Rejecting '{name}': price {price_eur}€ looks like schema index")
        return (0, 0, 0, False)
    
    if price_eur > MAX_REASONABLE_PRICE or price_eur <= 0:
        return (0, 0, 0, False)
    
    # Validate old_price
    valid_old = old_price_eur
    if old_price_eur > 0:
        if old_price_eur > MAX_SCHEMA_INDEX and old_price_eur == int(old_price_eur):
            valid_old = 0
        elif old_price_eur > price_eur * MAX_OLD_PRICE_RATIO:
            valid_old = 0
        elif old_price_eur > MAX_REASONABLE_PRICE:
            valid_old = 0
    
    # Calculate discount
    discount = 0
    if valid_old > 0 and valid_old > price_eur:
        discount = round((1 - price_eur / valid_old) * 100)
        if discount > MAX_DISCOUNT_PCT:
            valid_old = 0
            discount = 0
    
    return (price_eur, valid_old, discount, True)


class LidlScraper:
    """Combined Lidl scraper using API + HTML"""
    
    DOMAIN = "lidl.bg"
    BASE_URL = "https://www.lidl.bg"
    
    def __init__(self):
        self.session_manager = SessionManager(
            config=SessionConfig(max_requests=100, max_age_seconds=1200)
        )
        self.rate_limiter = DomainRateLimiter()
        self.circuit_breaker = CircuitBreaker(name=self.DOMAIN, failure_threshold=5, recovery_timeout=60)
        self.seen_ids: Set[str] = set()
        self.stats = {'requests': 0, 'successes': 0, 'failures': 0, 'products': 0, 'rejected': 0}
    
    def _get_session(self):
        return self.session_manager.get_session(self.DOMAIN)
    
    def _scrape_search_api(self, category_id: str) -> List[LidlProduct]:
        """Scrape products from search API"""
        if self.circuit_breaker.is_open:
            return []
        
        self.rate_limiter.wait(SEARCH_API)
        
        params = {
            "assortment": "BG",
            "locale": "bg_BG",
            "version": "v2.0.0",
            "category.id": category_id,
            "fetchSize": "100"
        }
        
        try:
            self.stats['requests'] += 1
            session = self._get_session()
            r = session.get(SEARCH_API, params=params, timeout=30)
            
            if r.status_code != 200:
                self.circuit_breaker._on_failure()
                self.stats['failures'] += 1
                return []
            
            self.circuit_breaker._on_success()
            self.stats['successes'] += 1
            
            data = r.json()
            items = data.get("items", [])
            products = []
            
            for item in items:
                try:
                    # Navigate to gridbox.data
                    gd = item.get("gridbox", {}).get("data", {})
                    if not gd:
                        continue
                    
                    product_id = str(gd.get("productId", ""))
                    if not product_id or product_id in self.seen_ids:
                        continue
                    
                    name = gd.get("fullTitle", "").strip()
                    if not name or len(name) < 3:
                        continue
                    
                    # Price data
                    price_data = gd.get("price", {})
                    price_eur = float(price_data.get("price", 0))
                    price_bgn = float(price_data.get("priceSecond", price_eur * 1.95583))
                    old_price_eur = float(price_data.get("oldPrice", 0) or 0)
                    old_price_bgn = float(price_data.get("oldPriceSecond", 0) or 0)
                    
                    # Validate
                    price_eur, old_price_eur, discount, valid = validate_price(price_eur, old_price_eur, name)
                    if not valid:
                        self.stats['rejected'] += 1
                        continue
                    
                    # Adjust BGN if old_price was reset
                    if old_price_eur == 0:
                        old_price_bgn = 0
                    
                    self.seen_ids.add(product_id)
                    
                    # Brand
                    brand = None
                    if isinstance(gd.get("brand"), dict):
                        brand = gd["brand"].get("name")
                    
                    # Barcodes
                    ians = gd.get("ians", [])
                    internal_code = ians[0] if ians else None
                    
                    products.append(LidlProduct(
                        product_id=product_id,
                        name=name,
                        brand=brand,
                        category=gd.get("category", ""),
                        quantity=gd.get("keyfacts", {}).get("description"),
                        price_eur=price_eur,
                        price_bgn=price_bgn,
                        old_price_eur=old_price_eur,
                        old_price_bgn=old_price_bgn,
                        discount_pct=discount,
                        image_url=gd.get("image"),
                        product_url=f"{self.BASE_URL}{gd.get('canonicalUrl', '')}",
                        availability=None,
                        internal_code=internal_code,
                    ))
                except Exception as e:
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Search API error: {e}")
            self.circuit_breaker._on_failure()
            self.stats['failures'] += 1
            return []
    
    def _scrape_html_page(self, url: str) -> List[LidlProduct]:
        """Scrape products from HTML page (promotions)"""
        if self.circuit_breaker.is_open:
            return []
        
        self.rate_limiter.wait(url)
        
        try:
            self.stats['requests'] += 1
            session = self._get_session()
            r = session.get(url, timeout=30)
            
            if r.status_code != 200:
                self.circuit_breaker._on_failure()
                self.stats['failures'] += 1
                return []
            
            self.circuit_breaker._on_success()
            self.stats['successes'] += 1
            
            decoded = html.unescape(r.text)
            products = []
            
            # Split by canonicalUrl
            chunks = decoded.split('"canonicalUrl"')[1:]
            
            for chunk in chunks[:300]:
                try:
                    # Extract title
                    title_match = re.search(r'"(?:fullTitle|title)":"([^"]+)"', chunk)
                    if not title_match or len(title_match.group(1)) < 3:
                        continue
                    
                    name = title_match.group(1)
                    
                    # Try nested price first
                    nested = re.search(r'"price":\{[^}]*"price":([\d.]+)', chunk)
                    if nested:
                        price_eur = float(nested.group(1))
                    else:
                        pm = re.search(r'"price":([\d.]+)', chunk)
                        if not pm:
                            continue
                        price_eur = float(pm.group(1))
                    
                    # Old price
                    nested_old = re.search(r'"price":\{[^}]*"oldPrice":([\d.]+)', chunk)
                    if nested_old:
                        old_price_eur = float(nested_old.group(1))
                    else:
                        om = re.search(r'"oldPrice":([\d.]+)', chunk)
                        old_price_eur = float(om.group(1)) if om else 0
                    
                    # Validate
                    price_eur, old_price_eur, discount, valid = validate_price(price_eur, old_price_eur, name)
                    if not valid:
                        self.stats['rejected'] += 1
                        continue
                    
                    # Product ID
                    id_match = re.search(r'"productId":(\d+)', chunk)
                    product_id = str(id_match.group(1)) if id_match else str(hash(name) % 10000000)
                    
                    if product_id in self.seen_ids:
                        continue
                    self.seen_ids.add(product_id)
                    
                    # BGN
                    bgn_m = re.search(r'"priceSecond":([\d.]+)', chunk)
                    price_bgn = float(bgn_m.group(1)) if bgn_m else price_eur * 1.95583
                    
                    old_bgn_m = re.search(r'"oldPriceSecond":([\d.]+)', chunk)
                    old_price_bgn = float(old_bgn_m.group(1)) if old_bgn_m and old_price_eur > 0 else 0
                    
                    # URL
                    url_m = re.search(r'^:"(/p/[^"]+)"', chunk)
                    product_url = f"{self.BASE_URL}{url_m.group(1)}" if url_m else ""
                    
                    # Image
                    img_m = re.search(r'"image":"(https://[^"]+)"', chunk)
                    
                    products.append(LidlProduct(
                        product_id=product_id,
                        name=name,
                        brand=None,
                        category="Промоции",
                        quantity=None,
                        price_eur=price_eur,
                        price_bgn=price_bgn,
                        old_price_eur=old_price_eur,
                        old_price_bgn=old_price_bgn,
                        discount_pct=discount,
                        image_url=img_m.group(1) if img_m else None,
                        product_url=product_url,
                        availability=None,
                        internal_code=None,
                    ))
                except Exception:
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"HTML scrape error: {e}")
            self.circuit_breaker._on_failure()
            self.stats['failures'] += 1
            return []
    
    def _scrape_gridboxes(self) -> List[LidlProduct]:
        """Scrape from gridboxes API (homepage promotions)"""
        if self.circuit_breaker.is_open:
            return []
        
        self.rate_limiter.wait(GRIDBOXES_API)
        
        try:
            self.stats['requests'] += 1
            session = self._get_session()
            r = session.get(GRIDBOXES_API, timeout=30)
            
            if r.status_code != 200:
                self.circuit_breaker._on_failure()
                self.stats['failures'] += 1
                return []
            
            self.circuit_breaker._on_success()
            self.stats['successes'] += 1
            
            data = r.json()
            products = []
            
            for item in data:
                if not isinstance(item, dict):
                    continue
                
                try:
                    price_data = item.get("price", {})
                    if not price_data.get("price"):
                        continue
                    
                    product_id = str(item.get("productId") or item.get("itemId") or "")
                    if not product_id or product_id in self.seen_ids:
                        continue
                    
                    name = item.get("fullTitle", "")
                    if not name:
                        continue
                    
                    price_eur = float(price_data.get("price", 0))
                    price_bgn = float(price_data.get("priceSecond", price_eur * 1.95583))
                    old_price_eur = float(price_data.get("oldPrice", 0) or 0)
                    old_price_bgn = float(price_data.get("oldPriceSecond", 0) or 0)
                    
                    # Validate
                    price_eur, old_price_eur, discount, valid = validate_price(price_eur, old_price_eur, name)
                    if not valid:
                        self.stats['rejected'] += 1
                        continue
                    
                    if old_price_eur == 0:
                        old_price_bgn = 0
                    
                    self.seen_ids.add(product_id)
                    
                    brand = None
                    if isinstance(item.get("brand"), dict):
                        brand = item["brand"].get("name")
                    
                    ians = item.get("ians", [])
                    
                    products.append(LidlProduct(
                        product_id=product_id,
                        name=name,
                        brand=brand,
                        category=item.get("category", ""),
                        quantity=item.get("keyfacts", {}).get("description"),
                        price_eur=price_eur,
                        price_bgn=price_bgn,
                        old_price_eur=old_price_eur,
                        old_price_bgn=old_price_bgn,
                        discount_pct=discount,
                        image_url=item.get("image"),
                        product_url=f"{self.BASE_URL}{item.get('canonicalUrl', '')}",
                        availability=None,
                        internal_code=ians[0] if ians else None,
                    ))
                except Exception:
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Gridboxes API error: {e}")
            self.circuit_breaker._on_failure()
            self.stats['failures'] += 1
            return []
    
    def scrape_products(self) -> List[LidlProduct]:
        """Scrape all products from all sources"""
        logger.info("Starting Lidl scrape")
        all_products = []
        
        # 1. Gridboxes API (homepage)
        gridbox_products = self._scrape_gridboxes()
        all_products.extend(gridbox_products)
        logger.info(f"Gridboxes API: {len(gridbox_products)} products")
        
        # 2. Search API (all categories)
        for cat_id in FOOD_CATEGORIES:
            products = self._scrape_search_api(cat_id)
            all_products.extend(products)
            logger.info(f"Category {cat_id}: {len(products)} products")
            time.sleep(0.5)  # Be nice
        
        # 3. HTML pages (promotions)
        for url in HTML_PAGES:
            products = self._scrape_html_page(url)
            all_products.extend(products)
            logger.info(f"HTML page: {len(products)} products")
        
        self.stats['products'] = len(all_products)
        logger.info(f"Total: {len(all_products)} products, {self.stats['rejected']} rejected")
        
        return all_products
    
    def get_stats(self) -> Dict:
        return self.stats


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("=" * 60)
    print("Lidl.bg Scraper - Combined API + HTML")
    print("=" * 60)
    
    scraper = LidlScraper()
    products = scraper.scrape_products()
    
    if not products:
        print("\n❌ No products scraped")
        return
    
    print(f"\n✅ Scraped {len(products)} valid products\n")
    
    # Show sample
    print("SAMPLE PRODUCTS:")
    print("-" * 60)
    for p in products[:15]:
        discount = f"{p.discount_pct:>3}% off" if p.discount_pct > 0 else "       "
        old = f"(was {p.old_price_eur:.2f}€)" if p.old_price_eur > 0 else ""
        print(f"{p.name[:35]:<35} | {p.price_eur:>6.2f}€ {old} {discount}")
    
    # Stats
    stats = scraper.get_stats()
    print(f"\n📊 Stats:")
    print(f"   Products: {stats['products']}")
    print(f"   Rejected: {stats['rejected']}")
    print(f"   Requests: {stats['requests']}")
    
    # Save
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "lidl_products.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to {output_file}")


if __name__ == "__main__":
    main()
