#!/usr/bin/env python3
"""
Build indices for OFF data to enable fast matching.
Creates brand index, quantity index, and name token index.
"""

import re
import json
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OFF_DB = PROJECT_ROOT / "data" / "off_bulgaria.db"
INDEX_DIR = PROJECT_ROOT / "data" / "indices"

# Bulgarian stopwords
STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'а', 'до', 'по', 'при', 'към', 'под', 'над'}

# Brand transliterations (BG → normalized)
BRAND_TRANSLITERATIONS = {
    'кока-кола': 'coca-cola',
    'кока кола': 'coca-cola',
    'пепси': 'pepsi',
    'фанта': 'fanta',
    'спрайт': 'sprite',
    'нестле': 'nestle',
    'нескафе': 'nescafe',
    'данон': 'danone',
    'активиа': 'activia',
    'милка': 'milka',
    'орео': 'oreo',
    'фереро': 'ferrero',
    'рафаело': 'raffaello',
    'линдт': 'lindt',
    'тоблерон': 'toblerone',
    'харибо': 'haribo',
    'сникърс': 'snickers',
    'марс': 'mars',
    'твикс': 'twix',
    'баунти': 'bounty',
    'лион': 'lion',
    'якобс': 'jacobs',
    'лаваца': 'lavazza',
    'давидоф': 'davidoff',
    'верея': 'vereia',
    'олимпус': 'olympus',
    'президент': 'president',
    'девин': 'devin',
    'банкя': 'bankya',
    'горна баня': 'gorna banya',
    'загорка': 'zagorka',
    'каменица': 'kamenitza',
    'хайнекен': 'heineken',
    'ариел': 'ariel',
    'персил': 'persil',
    'ленор': 'lenor',
    'финиш': 'finish',
    'нивеа': 'nivea',
    'гарние': 'garnier',
    'колгейт': 'colgate',
    'дав': 'dove',
    'палмолив': 'palmolive',
}


def normalize_brand(brand):
    """Normalize brand name for matching."""
    if not brand:
        return None
    brand = brand.lower().strip()
    brand = re.sub(r'[^\w\s\u0400-\u04FF-]', '', brand)
    brand = re.sub(r'\s+', ' ', brand).strip()
    # Try transliteration
    if brand in BRAND_TRANSLITERATIONS:
        return BRAND_TRANSLITERATIONS[brand]
    # Remove common suffixes
    brand = re.sub(r'\s*(ltd|inc|gmbh|ood|eood|ad)\s*$', '', brand)
    return brand if brand else None


def normalize_quantity(qty):
    """Normalize quantity for matching."""
    if not qty:
        return None
    qty = qty.lower().strip()
    # Remove spaces
    qty = re.sub(r'\s+', '', qty)
    # Cyrillic to Latin
    qty = qty.replace('кг', 'kg').replace('г', 'g')
    qty = qty.replace('мл', 'ml').replace('л', 'l')
    # Extract numeric + unit
    match = re.match(r'(\d+(?:[.,]\d+)?)(g|kg|l|ml)', qty)
    if match:
        value = match.group(1).replace(',', '.')
        unit = match.group(2)
        return f"{value}{unit}"
    return qty if qty else None


def tokenize_name(name):
    """Tokenize product name into significant words."""
    if not name:
        return []
    name = name.lower()
    # Remove special chars but keep Cyrillic
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    words = name.split()
    # Filter stopwords and short words
    return [w for w in words if w not in STOPWORDS and len(w) >= 3]


def build_indices():
    print("=" * 60)
    print("🔨 Building OFF indices for fast matching")
    print("=" * 60)
    
    # Create index directory
    INDEX_DIR.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(str(OFF_DB))
    cur = conn.cursor()
    
    # Load all OFF products
    cur.execute("""
        SELECT barcode, product_name, product_name_bg, brands, quantity
        FROM off_products
    """)
    products = cur.fetchall()
    print(f"Loaded {len(products)} OFF products")
    
    # Build indices
    brand_index = defaultdict(list)  # brand → [barcodes]
    quantity_index = defaultdict(list)  # quantity → [barcodes]
    token_index = defaultdict(list)  # token → [barcodes]
    product_data = {}  # barcode → {name, brand, quantity}
    
    for barcode, name, name_bg, brand, quantity in products:
        # Use BG name if available, else original name
        display_name = name_bg if name_bg else name
        
        # Store product data
        product_data[barcode] = {
            'name': display_name,
            'brand': brand,
            'quantity': quantity
        }
        
        # Brand index
        norm_brand = normalize_brand(brand)
        if norm_brand:
            brand_index[norm_brand].append(barcode)
        
        # Quantity index
        norm_qty = normalize_quantity(quantity)
        if norm_qty:
            quantity_index[norm_qty].append(barcode)
        
        # Token index (from both names)
        tokens = set()
        if display_name:
            tokens.update(tokenize_name(display_name))
        if name and name != display_name:
            tokens.update(tokenize_name(name))
        for token in tokens:
            token_index[token].append(barcode)
    
    # Stats
    print(f"\n📊 Index stats:")
    print(f"  Brand index: {len(brand_index)} unique brands")
    print(f"  Quantity index: {len(quantity_index)} unique quantities")
    print(f"  Token index: {len(token_index)} unique tokens")
    
    # Show top brands
    print(f"\n📋 Top indexed brands:")
    top_brands = sorted(brand_index.items(), key=lambda x: -len(x[1]))[:10]
    for brand, barcodes in top_brands:
        print(f"  {len(barcodes):>4}x {brand}")
    
    # Show top quantities
    print(f"\n📋 Top indexed quantities:")
    top_qtys = sorted(quantity_index.items(), key=lambda x: -len(x[1]))[:10]
    for qty, barcodes in top_qtys:
        print(f"  {len(barcodes):>4}x {qty}")
    
    # Save indices
    print(f"\n💾 Saving indices...")
    
    with open(INDEX_DIR / "off_brand_index.json", 'w', encoding='utf-8') as f:
        json.dump(dict(brand_index), f, ensure_ascii=False)
    
    with open(INDEX_DIR / "off_quantity_index.json", 'w', encoding='utf-8') as f:
        json.dump(dict(quantity_index), f, ensure_ascii=False)
    
    with open(INDEX_DIR / "off_token_index.json", 'w', encoding='utf-8') as f:
        json.dump(dict(token_index), f, ensure_ascii=False)
    
    with open(INDEX_DIR / "off_product_data.json", 'w', encoding='utf-8') as f:
        json.dump(product_data, f, ensure_ascii=False)
    
    # File sizes
    for f in INDEX_DIR.glob("*.json"):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}: {size_kb:.1f} KB")
    
    conn.close()
    print(f"\n✅ Indices built successfully!")
    
    return brand_index, quantity_index, token_index, product_data


if __name__ == '__main__':
    build_indices()
