"""
Combined Scraper - Fetches from all stores and merges data
"""
import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List
import sys
import os

# Add scrapers to path
sys.path.insert(0, os.path.dirname(__file__))

@dataclass
class Product:
    id: str
    name: str
    store: str
    price_eur: float
    price_bgn: float
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    quantity: Optional[str]
    category: str
    image_url: Optional[str]
    scraped_at: str

def generate_id(store: str, name: str) -> str:
    """Generate unique ID from store + name"""
    key = f"{store}:{name}".lower()
    return hashlib.md5(key.encode()).hexdigest()[:12]

def scrape_kaufland() -> List[Product]:
    """Scrape Kaufland products"""
    from scrapers.kaufland_scraper import scrape_kaufland as _scrape
    url = "https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html"
    raw = _scrape(url)
    
    products = []
    for p in raw:
        products.append(Product(
            id=generate_id("kaufland", p.name),
            name=p.name,
            store="Kaufland",
            price_eur=p.price_eur or 0,
            price_bgn=p.price_bgn or 0,
            old_price_eur=p.old_price_eur,
            old_price_bgn=p.old_price_bgn,
            discount_pct=p.discount_pct,
            quantity=p.quantity,
            category=p.category or "Оферти",
            image_url=p.image_url,
            scraped_at=datetime.utcnow().isoformat()
        ))
    return products

def scrape_lidl() -> List[Product]:
    """Scrape Lidl products"""
    from scrapers.lidl_scraper import scrape_lidl_page
    url = "https://www.lidl.bg/c/lidl-plus-promotsii/a10039565"
    raw = scrape_lidl_page(url)
    
    products = []
    for p in raw:
        products.append(Product(
            id=generate_id("lidl", p.name),
            name=p.name,
            store="Lidl",
            price_eur=p.price_eur,
            price_bgn=p.price_bgn,
            old_price_eur=p.old_price_eur,
            old_price_bgn=p.old_price_bgn,
            discount_pct=p.discount_pct,
            quantity=p.quantity,
            category=p.category,
            image_url=p.image_url,
            scraped_at=datetime.utcnow().isoformat()
        ))
    return products

def scrape_billa() -> List[Product]:
    """Scrape Billa products"""
    from scrapers.billa_scraper import scrape_billa
    raw = scrape_billa()
    
    products = []
    for p in raw:
        products.append(Product(
            id=generate_id("billa", p.name),
            name=p.name,
            store="Billa",
            price_eur=p.price_eur,
            price_bgn=p.price_bgn,
            old_price_eur=p.old_price_eur,
            old_price_bgn=p.old_price_bgn,
            discount_pct=p.discount_pct,
            quantity=p.quantity,
            category=p.category,
            image_url=p.image_url,
            scraped_at=datetime.utcnow().isoformat()
        ))
    return products

def scrape_all() -> List[Product]:
    """Scrape all stores"""
    all_products = []
    
    print("Scraping Kaufland...")
    try:
        all_products.extend(scrape_kaufland())
        print(f"  ✓ Kaufland: {len([p for p in all_products if p.store == 'Kaufland'])} products")
    except Exception as e:
        print(f"  ✗ Kaufland failed: {e}")
    
    print("Scraping Lidl...")
    try:
        all_products.extend(scrape_lidl())
        print(f"  ✓ Lidl: {len([p for p in all_products if p.store == 'Lidl'])} products")
    except Exception as e:
        print(f"  ✗ Lidl failed: {e}")
    
    print("Scraping Billa...")
    try:
        all_products.extend(scrape_billa())
        print(f"  ✓ Billa: {len([p for p in all_products if p.store == 'Billa'])} products")
    except Exception as e:
        print(f"  ✗ Billa failed: {e}")
    
    return all_products

if __name__ == "__main__":
    print("=" * 60)
    print("Combined Scraper - PromoBG")
    print("=" * 60)
    
    products = scrape_all()
    
    print(f"\n✅ Total: {len(products)} products")
    
    # Save combined data
    output = [asdict(p) for p in products]
    with open('data/all_products.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"📁 Saved to data/all_products.json")
    
    # Stats by store
    print("\n📊 By Store:")
    for store in ["Kaufland", "Lidl", "Billa"]:
        store_products = [p for p in products if p.store == store]
        with_discount = [p for p in store_products if p.discount_pct]
        print(f"   {store}: {len(store_products)} products, {len(with_discount)} with discount")
