#!/usr/bin/env python3
"""
Rebuild frontend data from latest scraper outputs.
Outputs docs/all_products.json for GitHub Pages.
"""
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "services" / "scraper" / "data"
OUTPUT_FILE = PROJECT_ROOT / "docs" / "all_products.json"

# EUR to BGN conversion (fixed rate since Jan 2024)
EUR_TO_BGN = 1.95583

def generate_id(store: str, name: str) -> str:
    key = f"{store}:{name}".lower()
    return hashlib.md5(key.encode()).hexdigest()[:12]

def extract_size(text: str):
    """Extract size from text."""
    if not text:
        return None, None
    text_lower = text.lower()
    
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
                return value, unit
            except ValueError:
                continue
    return None, None

def clean_billa_name(name: str) -> str:
    """Strip promotional prefixes from Billa names."""
    patterns = [
        r'^king\s+оферта\s*-\s*супер\s+цена\s*-\s*',
        r'^king\s+оферта\s*-\s*само\s+с\s+billa\s+card\s*-\s*',
        r'^king\s+оферта\s*-\s*сега\s+в\s+billa\s*-\s*',
        r'^king\s+оферта\s*-\s*ново\s+в\s+billa\s*-\s*',
        r'^king\s+оферта\s*-\s*',
        r'^супер\s+цена\s*-\s*',
        r'\s+за\s+1\s+кг\s*$',
        r'\s+за\s+1\s+бр\.?\s*$',
    ]
    cleaned = name
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', cleaned).strip()

def load_kaufland():
    """Load Kaufland from quick scraper."""
    path = DATA_DIR / "kaufland_quick.json"
    if not path.exists():
        return []
    
    with open(path) as f:
        raw = json.load(f)
    
    products = []
    for p in raw:
        if not p.get('price'):
            continue
        
        price_bgn = p['price']
        price_eur = price_bgn / EUR_TO_BGN
        
        products.append({
            'id': generate_id('kaufland', p['name']),
            'name': p['name'],
            'store': 'Kaufland',
            'price_bgn': round(price_bgn, 2),
            'price_eur': round(price_eur, 2),
            'old_price_bgn': None,  # Not available in quick scraper
            'old_price_eur': None,
            'discount_pct': None,
            'brand': p.get('brand'),
            'size_value': p.get('size_value'),
            'size_unit': p.get('size_unit'),
            'category': p.get('category'),
            'image_url': None,
            'product_url': None,
        })
    
    return products

def load_lidl():
    """Load Lidl from sitemap scraper."""
    path = DATA_DIR / "lidl_sitemap_products.json"
    if not path.exists():
        return []
    
    with open(path) as f:
        raw = json.load(f)
    
    products = []
    for p in raw:
        price_bgn = p.get('price_bgn')
        price_eur = p.get('price_eur')
        
        # Skip if no valid price
        if not price_bgn and not price_eur:
            continue
        
        if not price_bgn and price_eur:
            price_bgn = price_eur * EUR_TO_BGN
        if not price_eur and price_bgn:
            price_eur = price_bgn / EUR_TO_BGN
        
        # Calculate discount (if old price exists and is reasonable)
        old_price_bgn = p.get('old_price_bgn')
        old_price_eur = p.get('old_price_eur')
        discount_pct = None
        
        # Filter out unrealistic old prices (the 96% discounts)
        if old_price_bgn and old_price_bgn > price_bgn and old_price_bgn < price_bgn * 3:
            discount_pct = int(100 * (old_price_bgn - price_bgn) / old_price_bgn)
        else:
            old_price_bgn = None
            old_price_eur = None
        
        # Clean name (remove "| LIDL" suffix)
        name = p.get('name', '').replace(' | LIDL', '').strip()
        
        products.append({
            'id': generate_id('lidl', name),
            'name': name,
            'store': 'Lidl',
            'price_bgn': round(price_bgn, 2) if price_bgn else None,
            'price_eur': round(price_eur, 2) if price_eur else None,
            'old_price_bgn': round(old_price_bgn, 2) if old_price_bgn else None,
            'old_price_eur': round(old_price_eur, 2) if old_price_eur else None,
            'discount_pct': discount_pct,
            'brand': p.get('brand'),
            'size_value': p.get('size_value'),
            'size_unit': p.get('size_unit'),
            'category': p.get('category'),
            'image_url': p.get('image_url'),
            'product_url': p.get('product_url'),
        })
    
    return products

def load_billa():
    """Load Billa from billa scraper with cleaning."""
    path = DATA_DIR / "billa_products.json"
    if not path.exists():
        return []
    
    with open(path) as f:
        raw = json.load(f)
    
    products = []
    for p in raw:
        raw_name = p.get('name', '')
        name = clean_billa_name(raw_name)
        
        price_bgn = p.get('price_bgn') or p.get('price')
        price_eur = p.get('price_eur')
        
        if not price_bgn and not price_eur:
            continue
        
        if not price_bgn and price_eur:
            price_bgn = price_eur * EUR_TO_BGN
        if not price_eur and price_bgn:
            price_eur = price_bgn / EUR_TO_BGN
        
        # Extract size from name if not present
        size_val = p.get('size_value')
        size_unit = p.get('size_unit')
        if not size_val:
            size_val, size_unit = extract_size(name)
        
        old_price_bgn = p.get('old_price_bgn')
        old_price_eur = p.get('old_price_eur')
        discount_pct = p.get('discount_pct')
        
        products.append({
            'id': generate_id('billa', name),
            'name': name,
            'store': 'Billa',
            'price_bgn': round(price_bgn, 2) if price_bgn else None,
            'price_eur': round(price_eur, 2) if price_eur else None,
            'old_price_bgn': round(old_price_bgn, 2) if old_price_bgn else None,
            'old_price_eur': round(old_price_eur, 2) if old_price_eur else None,
            'discount_pct': discount_pct,
            'brand': p.get('brand'),
            'size_value': size_val,
            'size_unit': size_unit,
            'category': p.get('category'),
            'image_url': p.get('image_url'),
            'product_url': p.get('product_url'),
        })
    
    return products

def main():
    print("=" * 60)
    print("REBUILDING FRONTEND DATA")
    print("=" * 60)
    
    # Load from each store
    kaufland = load_kaufland()
    print(f"Kaufland: {len(kaufland)} products")
    
    lidl = load_lidl()
    print(f"Lidl: {len(lidl)} products")
    
    billa = load_billa()
    print(f"Billa: {len(billa)} products")
    
    # Combine
    all_products = kaufland + lidl + billa
    print(f"\nTotal: {len(all_products)} products")
    
    # Stats
    with_price = sum(1 for p in all_products if p.get('price_bgn'))
    with_discount = sum(1 for p in all_products if p.get('discount_pct'))
    with_brand = sum(1 for p in all_products if p.get('brand'))
    with_size = sum(1 for p in all_products if p.get('size_value'))
    
    print(f"\nData quality:")
    print(f"  With price: {with_price} ({100*with_price/len(all_products):.1f}%)")
    print(f"  With discount: {with_discount} ({100*with_discount/len(all_products):.1f}%)")
    print(f"  With brand: {with_brand} ({100*with_brand/len(all_products):.1f}%)")
    print(f"  With size: {with_size} ({100*with_size/len(all_products):.1f}%)")
    
    # Save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Saved to {OUTPUT_FILE}")
    print(f"   File size: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")

if __name__ == '__main__':
    main()
