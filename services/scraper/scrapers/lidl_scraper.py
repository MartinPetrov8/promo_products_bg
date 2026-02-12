"""
Lidl.bg Scraper - Final Working Version
"""
import requests
import html
import re
import json
from dataclasses import dataclass, asdict
from typing import Optional, List

@dataclass
class Product:
    name: str
    quantity: Optional[str]
    price_eur: float
    price_bgn: float
    old_price_eur: float
    old_price_bgn: float
    discount_pct: int
    image_url: Optional[str]
    category: str = "Lidl Plus"

def scrape_lidl_page(url: str) -> List[Product]:
    """Scrape products from a Lidl page"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    
    decoded = html.unescape(resp.text)
    products = []
    
    # Split by canonicalUrl to get product chunks
    chunks = decoded.split('"canonicalUrl"')[1:]  # Skip first empty chunk
    
    for chunk in chunks:
        # Extract title
        title_match = re.search(r'"title":"([^"]+)"', chunk)
        if not title_match:
            continue
        name = title_match.group(1)
        
        # Skip non-product entries (navigation items etc)
        if len(name) < 3 or len(name) > 100:
            continue
        
        # Extract subtitle/quantity
        subtitle_match = re.search(r'"subtitle":"([^"]*)"', chunk)
        quantity = subtitle_match.group(1) if subtitle_match else None
        
        # Extract prices (EUR)
        price_match = re.search(r'"price":([\d.]+)', chunk)
        old_price_match = re.search(r'"oldPrice":([\d.]+)', chunk)
        
        if not price_match or not old_price_match:
            continue
        
        price_eur = float(price_match.group(1))
        old_price_eur = float(old_price_match.group(1))
        
        # Extract BGN prices
        price_bgn_match = re.search(r'"priceSecond":([\d.]+)', chunk)
        old_bgn_match = re.search(r'"oldPriceSecond":([\d.]+)', chunk)
        
        price_bgn = float(price_bgn_match.group(1)) if price_bgn_match else price_eur * 1.95583
        old_price_bgn = float(old_bgn_match.group(1)) if old_bgn_match else old_price_eur * 1.95583
        
        # Calculate discount
        discount = round((1 - price_eur / old_price_eur) * 100) if old_price_eur > 0 else 0
        
        # Extract image
        img_match = re.search(r'"image":"(https://[^"]+)"', chunk)
        image_url = img_match.group(1) if img_match else None
        
        products.append(Product(
            name=name,
            quantity=quantity,
            price_eur=price_eur,
            price_bgn=price_bgn,
            old_price_eur=old_price_eur,
            old_price_bgn=old_price_bgn,
            discount_pct=discount,
            image_url=image_url
        ))
    
    # Deduplicate
    seen = set()
    unique = []
    for p in products:
        if p.name not in seen:
            seen.add(p.name)
            unique.append(p)
    
    return unique

if __name__ == "__main__":
    print("Scraping Lidl.bg")
    print("=" * 60)
    
    url = "https://www.lidl.bg/c/lidl-plus-promotsii/a10039565"
    products = scrape_lidl_page(url)
    
    print(f"\n✅ Extracted {len(products)} unique products\n")
    
    print("SAMPLE PRODUCTS:")
    print("-" * 60)
    for p in products[:15]:
        print(f"{p.name[:35]:<35} | {p.price_eur:>5.2f}€ | was {p.old_price_eur:.2f}€ | {p.discount_pct:>3}% off")
    
    # Save
    output = [asdict(p) for p in products]
    with open('lidl_products.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to lidl_products.json")
    
    avg_discount = sum(p.discount_pct for p in products) / len(products) if products else 0
    max_discount = max((p.discount_pct for p in products), default=0)
    
    print(f"\n📊 Stats:")
    print(f"   Total products: {len(products)}")
    print(f"   Avg discount: {avg_discount:.1f}%")
    print(f"   Max discount: {max_discount}%")
