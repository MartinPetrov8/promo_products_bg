"""
Kaufland.bg Scraper - Working Version
Extracts product data from weekly offers page
"""
import requests
from bs4 import BeautifulSoup
import json
import re
from dataclasses import dataclass, asdict
from typing import Optional, List

@dataclass
class Product:
    name: str
    quantity: Optional[str]
    price_eur: Optional[float]
    price_bgn: Optional[float]
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    category: Optional[str] = None

def parse_price(text: str) -> Optional[float]:
    """Extract numeric price from text like '1,78 €' or '3,48 ЛВ.'"""
    if not text:
        return None
    match = re.search(r'([\d]+[,.][\d]+)', text.replace(' ', ''))
    if match:
        return float(match.group(1).replace(',', '.'))
    return None

def parse_discount(text: str) -> Optional[int]:
    """Extract discount percentage from text like '-61%'"""
    if not text:
        return None
    match = re.search(r'-(\d+)%', text)
    if match:
        return int(match.group(1))
    return None

def scrape_kaufland(url: str) -> List[Product]:
    """Scrape products from a Kaufland offers page"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    products = []
    
    # Find all product title elements
    titles = soup.select('div.k-product-tile__title')
    
    for title_div in titles:
        # Navigate to parent tile
        tile = title_div.parent
        while tile and not any('k-product-tile' == c for c in tile.get('class', [])):
            tile = tile.parent
            if tile is None or tile.name == 'body':
                tile = title_div.parent.parent.parent.parent
                break
        
        if not tile:
            continue
            
        name = title_div.get_text(strip=True)
        if not name:
            continue
        
        # Quantity/subtitle
        subtitle = tile.select_one('div.k-product-tile__subtitle')
        quantity = subtitle.get_text(strip=True) if subtitle else None
        
        # Get both price tags (EUR and BGN)
        pricetags = tile.select('div.k-product-tile__pricetag')
        
        price_eur = old_price_eur = None
        price_bgn = old_price_bgn = None
        discount_pct = None
        
        for pt in pricetags:
            price_div = pt.select_one('div.k-price-tag__price')
            old_price_div = pt.select_one('div.k-price-tag__old-price')
            discount_div = pt.select_one('div.k-price-tag__discount')
            
            if price_div:
                text = price_div.get_text(strip=True)
                if '€' in text:
                    price_eur = parse_price(text)
                elif 'ЛВ' in text:
                    price_bgn = parse_price(text)
            
            if old_price_div:
                text = old_price_div.get_text(strip=True)
                if '€' in text:
                    old_price_eur = parse_price(text)
                elif 'ЛВ' in text:
                    old_price_bgn = parse_price(text)
            
            if discount_div and not discount_pct:
                discount_pct = parse_discount(discount_div.get_text(strip=True))
        
        # Image
        img = tile.select_one('img.k-product-tile__main-image')
        image_url = None
        if img:
            image_url = img.get('src') or img.get('data-src')
        
        product = Product(
            name=name,
            quantity=quantity,
            price_eur=price_eur,
            price_bgn=price_bgn,
            old_price_eur=old_price_eur,
            old_price_bgn=old_price_bgn,
            discount_pct=discount_pct,
            image_url=image_url
        )
        products.append(product)
    
    return products

if __name__ == "__main__":
    url = "https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html"
    print(f"Scraping: {url}")
    print("=" * 60)
    
    products = scrape_kaufland(url)
    
    print(f"\n✅ Extracted {len(products)} products\n")
    
    # Show sample with prices
    print("SAMPLE PRODUCTS WITH PRICES:")
    print("-" * 60)
    
    count = 0
    for p in products:
        if p.price_eur and count < 15:
            print(f"{p.name[:35]:<35} | {p.price_eur:>6.2f}€ | {p.discount_pct or 0:>3}% off")
            count += 1
    
    # Save all products
    output = [asdict(p) for p in products]
    with open('kaufland_products.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to kaufland_products.json")
    
    # Stats
    with_prices = [p for p in products if p.price_eur]
    with_discount = [p for p in products if p.discount_pct]
    print(f"\n📊 Stats:")
    print(f"   Total products: {len(products)}")
    print(f"   With EUR price: {len(with_prices)}")
    print(f"   With discount: {len(with_discount)}")
