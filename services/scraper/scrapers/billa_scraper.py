"""
Billa Scraper v2 - Fixed to match HTML structure
"""
import requests
from bs4 import BeautifulSoup
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
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    category: str = "Billa"

def scrape_billa() -> List[Product]:
    """Scrape products from ssbbilla.site"""
    url = "https://ssbbilla.site/catalog/sedmichna-broshura"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    resp = requests.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    products = []
    product_divs = soup.find_all(class_='product')
    
    for div in product_divs:
        # Get product name
        name_el = div.find(class_='actualProduct')
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        
        # Skip headers and non-products
        if not name or name in ['Billa', ''] or len(name) < 5:
            continue
        if 'Разбир' in name or 'условията' in name:
            continue
            
        # Get all prices (span.price elements)
        price_spans = div.find_all(class_='price')
        currency_spans = div.find_all(class_='currency')
        
        prices_eur = []
        prices_bgn = []
        
        for i, price_span in enumerate(price_spans):
            try:
                value = float(price_span.get_text(strip=True).replace(',', '.'))
                if i < len(currency_spans):
                    curr = currency_spans[i].get_text(strip=True)
                    if '€' in curr:
                        prices_eur.append(value)
                    elif 'лв' in curr:
                        prices_bgn.append(value)
            except:
                continue
        
        # Get discount
        discount_el = div.find(class_='discount')
        discount = None
        if discount_el:
            match = re.search(r'(\d+)', discount_el.get_text())
            if match:
                discount = int(match.group(1))
        
        # Assign prices (first = old, second = new for this structure)
        if len(prices_eur) >= 2:
            old_price_eur = prices_eur[0]
            price_eur = prices_eur[1]
        elif len(prices_eur) == 1:
            price_eur = prices_eur[0]
            old_price_eur = None
        else:
            price_eur = 0
            old_price_eur = None
            
        if len(prices_bgn) >= 2:
            old_price_bgn = prices_bgn[0]
            price_bgn = prices_bgn[1]
        elif len(prices_bgn) == 1:
            price_bgn = prices_bgn[0]
            old_price_bgn = None
        else:
            price_bgn = price_eur * 1.95583 if price_eur else 0
            old_price_bgn = None
        
        if price_eur > 0 or price_bgn > 0:
            products.append(Product(
                name=name[:100],  # Truncate long names
                quantity=None,
                price_eur=round(price_eur, 2),
                price_bgn=round(price_bgn, 2),
                old_price_eur=round(old_price_eur, 2) if old_price_eur else None,
                old_price_bgn=round(old_price_bgn, 2) if old_price_bgn else None,
                discount_pct=discount,
                image_url=None
            ))
    
    return products

if __name__ == "__main__":
    print("Scraping Billa (via ssbbilla.site)")
    print("=" * 60)
    
    products = scrape_billa()
    
    print(f"\n✅ Extracted {len(products)} products\n")
    
    print("SAMPLE PRODUCTS:")
    print("-" * 60)
    for p in products[:15]:
        discount_str = f"{p.discount_pct}% off" if p.discount_pct else "-"
        print(f"{p.name[:40]:<40} | {p.price_eur:>6.2f}€ | {discount_str}")
    
    # Save
    output = [asdict(p) for p in products]
    with open('billa_products.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to billa_products.json")
    
    with_discount = [p for p in products if p.discount_pct]
    avg_discount = sum(p.discount_pct for p in with_discount) / len(with_discount) if with_discount else 0
    
    print(f"\n📊 Stats:")
    print(f"   Total products: {len(products)}")
    print(f"   With discount: {len(with_discount)}")
    print(f"   Avg discount: {avg_discount:.1f}%")
