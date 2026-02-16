#!/usr/bin/env python3
"""
Import ALL existing data files into products.json with proper quantity extraction.

This combines:
- data/kaufland_enhanced.json (1977 items)
- data/lidl_jsonld_batch*.json (~662 items)
- data/billa*.json (if exists)

And ensures quantities are in product names for matching.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

REPO = Path(__file__).parent.parent
DATA_DIR = REPO / "data"
OUTPUT = REPO / "docs" / "data" / "products.json"


def extract_quantity_from_text(text):
    """Extract quantity string from text"""
    if not text:
        return None
    
    patterns = [
        r'(\d+\s*[xх]\s*\d+(?:[.,]\d+)?\s*(?:мл|ml|л|l|гр?|g|кг|kg))',  # Pack: 6x330ml
        r'(\d+(?:[.,]\d+)?\s*(?:мл|ml|л|l|гр?|g|кг|kg|бр|cl|сл))',  # Single: 500ml
        r'(\d+(?:[.,]\d+)?\s*(?:cm|см))',  # Size: 30cm
    ]
    
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1)
    return None


def load_kaufland():
    """Load Kaufland data from enhanced JSON"""
    path = DATA_DIR / "kaufland_enhanced.json"
    if not path.exists():
        print(f"  ⚠️  {path} not found")
        return []
    
    with open(path) as f:
        data = json.load(f)
    
    products = []
    for item in data:
        # Combine title + subtitle for full name
        title = item.get('title', '').strip()
        subtitle = item.get('subtitle', '').strip()
        description = item.get('description', '').strip()
        
        # Try to find quantity in subtitle or description
        qty = extract_quantity_from_text(subtitle) or extract_quantity_from_text(description)
        
        # Build full name with quantity
        name = title
        if subtitle and subtitle not in title:
            name = f"{title} {subtitle}"
        
        # If we found quantity separately and it's not in name, add it
        if qty and qty not in name.lower():
            name = f"{name} {qty}"
        
        # Clean up newlines
        name = re.sub(r'\s*\n\s*', ' ', name).strip()
        
        # Get price (prefer EUR)
        price = item.get('price_eur')
        if not price:
            bgn_price = item.get('price_bgn')
            if bgn_price:
                price = round(bgn_price / 1.9558, 2)  # BGN to EUR
        
        if not name:
            continue
            
        products.append({
            'id': f"kaufland_{item.get('kl_nr', len(products))}",
            'name': name,
            'brand': item.get('brand'),
            'store': 'Kaufland',
            'price': price,
            'old_price': item.get('old_price_bgn'),
            'image_url': item.get('image_url'),
        })
    
    return products


def load_lidl():
    """Load Lidl data from JSON-LD batch files"""
    products = []
    
    # Find all Lidl batch files
    batch_files = list(DATA_DIR.glob("lidl_jsonld_batch*.json"))
    
    if not batch_files:
        print(f"  ⚠️  No Lidl batch files found in {DATA_DIR}")
        return []
    
    seen_skus = set()
    
    for batch_file in sorted(batch_files):
        with open(batch_file) as f:
            data = json.load(f)
        
        for item in data:
            sku = item.get('sku')
            if sku in seen_skus:
                continue
            seen_skus.add(sku)
            
            name = item.get('name', '').strip()
            if not name:
                continue
            
            # Lidl often has quantity in name already
            # But let's check and clean
            name = re.sub(r'\s*\|\s*LIDL\s*$', '', name, flags=re.IGNORECASE)
            name = re.sub(r'\s+', ' ', name).strip()
            
            price = item.get('price')
            currency = item.get('currency', 'BGN')
            
            # Convert BGN to EUR if needed
            if currency == 'BGN' and price:
                price = round(price / 1.9558, 2)
            
            products.append({
                'id': f"lidl_{sku or len(products)}",
                'name': name,
                'brand': item.get('brand'),
                'store': 'Lidl',
                'price': price,
                'old_price': item.get('old_price'),
                'image_url': item.get('image_url'),
            })
    
    return products


def load_billa():
    """Load Billa data from available sources"""
    # Try different possible file names
    candidates = [
        DATA_DIR / "billa.json",
        DATA_DIR / "billa_products.json", 
        DATA_DIR / "billa_enhanced.json",
    ]
    
    data = None
    for path in candidates:
        if path.exists():
            print(f"  Found Billa data: {path}")
            with open(path) as f:
                data = json.load(f)
            break
    
    if not data:
        # Check if we have Billa data embedded somewhere
        return []
    
    products = []
    for item in data:
        name = item.get('name', '').strip()
        if not name:
            continue
        
        price = item.get('price')
        
        products.append({
            'id': f"billa_{item.get('sku', len(products))}",
            'name': name,
            'brand': item.get('brand'),
            'store': 'Billa',
            'price': price,
            'old_price': item.get('old_price'),
            'image_url': item.get('image_url'),
        })
    
    return products


def main():
    print("="*60)
    print("IMPORTING ALL DATA")
    print("="*60)
    
    # Load from all sources
    print("\nLoading Kaufland...")
    kaufland = load_kaufland()
    print(f"  Loaded {len(kaufland)} products")
    
    print("\nLoading Lidl...")
    lidl = load_lidl()
    print(f"  Loaded {len(lidl)} products")
    
    print("\nLoading Billa...")
    billa = load_billa()
    print(f"  Loaded {len(billa)} products")
    
    # Combine
    all_products = kaufland + lidl + billa
    
    # Assign numeric IDs
    for i, p in enumerate(all_products):
        p['id'] = i + 1
    
    # Filter out products without prices
    valid_products = [p for p in all_products if p.get('price') and p['price'] > 0]
    
    print(f"\nTotal valid products: {len(valid_products)}")
    
    # Stats
    by_store = defaultdict(int)
    with_qty = 0
    for p in valid_products:
        by_store[p['store']] += 1
        if extract_quantity_from_text(p['name']):
            with_qty += 1
    
    print("\nBy store:")
    for store, count in by_store.items():
        print(f"  {store}: {count}")
    
    print(f"\nWith quantity in name: {with_qty} ({with_qty/len(valid_products)*100:.1f}%)")
    
    # Sample products with quantities
    print("\nSample products WITH quantity:")
    count = 0
    for p in valid_products:
        qty = extract_quantity_from_text(p['name'])
        if qty:
            print(f"  {p['store']}: {p['name'][:60]} | €{p['price']}")
            count += 1
            if count >= 10:
                break
    
    # Build output
    output = {
        'meta': {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'total_products': len(valid_products),
            'cross_store_groups': 0,
            'stores': list(by_store.keys())
        },
        'products': valid_products,
        'groups': {}
    }
    
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Saved to {OUTPUT}")
    return len(valid_products)


if __name__ == '__main__':
    main()
