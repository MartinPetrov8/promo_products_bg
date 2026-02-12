#!/usr/bin/env python3
"""
Export products from SQLite to JSON for frontend consumption.
Generates docs/data/all_products.json with all store prices.
"""

import json
import sqlite3
import os
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).parent.parent.parent
DB_PATH = REPO_ROOT / "data" / "promobg.db"
OUTPUT_PATH = REPO_ROOT / "docs" / "data" / "all_products.json"

# Store name mapping (DB has lowercase, UI expects proper case)
STORE_NAMES = {
    1: "Kaufland",
    2: "Lidl", 
    3: "Billa",
    4: "Metro",
    5: "Fantastico"
}


def normalize_product_name(name: str) -> str:
    """
    Normalize product name for grouping/comparison.
    Strips quantities, brand prefixes, extra whitespace.
    """
    import re
    
    if not name:
        return ""
    
    result = name.lower()
    
    # Remove "Продукт, маркиран със синя звезда" (Billa loyalty marker)
    result = re.sub(r'продукт,?\s*маркиран\s*(със)?\s*синя\s*звезда', '', result, flags=re.IGNORECASE)
    
    # Remove common quantity patterns
    result = re.sub(r'\b\d+\s*(г|гр|kg|кг|ml|мл|l|л|бр|pcs|броя?)\b\.?', '', result, flags=re.IGNORECASE)
    
    # Remove quantity ranges like "400-500 гр"
    result = re.sub(r'\d+\s*-\s*\d+\s*(г|гр|kg|кг|ml|мл|l|л|бр)\.?', '', result, flags=re.IGNORECASE)
    
    # Remove prices if embedded
    result = re.sub(r'\d+[.,]\d+\s*(лв|€|eur|bgn)', '', result, flags=re.IGNORECASE)
    
    # Remove store-specific prefixes (case-insensitive)
    prefixes = ['k-classic', 'clever', 'king', 'lidl plus', 'billa', 'kaufland', 'tira']
    for prefix in prefixes:
        if result.strip().startswith(prefix):
            result = result[len(prefix):].lstrip(' -–')
    
    # Remove common suffixes
    result = re.sub(r'\s*-\s*\d+\s*(бр|pcs)\.?\s*$', '', result)
    
    # Normalize whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    
    # Remove leading/trailing punctuation
    result = re.sub(r'^[\s\-–—:,]+|[\s\-–—:,]+$', '', result)
    
    return result[:50]  # Cap at 50 chars for grouping


def compute_group_key(name: str) -> str:
    """
    Compute a grouping key from product name.
    Used for "cheapest wins" comparison - groups similar products.
    
    Strategy: Extract the core product type, stripping:
    - Brand names, store prefixes
    - Quantities/weights/sizes
    - Promotional phrases
    - Source/origin descriptions
    """
    import re
    
    if not name:
        return ""
    
    result = name.lower()
    
    # Remove Billa loyalty marker
    result = re.sub(r'продукт,?\s*маркиран\s*(със)?\s*синя\s*звезда', '', result, flags=re.IGNORECASE)
    
    # Remove "От ... витрина" phrases (Billa deli counter)
    result = re.sub(r'от\s+(деликатесната|топлата|студената)\s+витрина', '', result, flags=re.IGNORECASE)
    
    # Remove "За 1 кг" pricing
    result = re.sub(r'за\s+\d+\s*(кг|kg|л|l)', '', result, flags=re.IGNORECASE)
    
    # Remove "Billa Ready" and similar store labels
    result = re.sub(r'billa\s*(ready|app)?', '', result, flags=re.IGNORECASE)
    
    # Remove all quantities and weights (expanded patterns)
    result = re.sub(r'\b\d+\s*(x\s*)?\d*\s*(г|гр|kg|кг|ml|мл|l|л|бр|pcs|броя?|опаковки?|бутилки?)\b\.?', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\d+\s*-\s*\d+\s*(г|гр|kg|кг|ml|мл|l|л|бр)\.?', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\d+\s*%', '', result)  # Remove percentages (fat content etc)
    
    # Remove brand prefixes (case-insensitive, at start of string or after dash)
    brands = [
        'k-classic', 'clever', 'king оферта', 'king', 'lidl plus', 'super цена', 
        'супер цена', 'топ цена', 'tira', 'само с billa app', 'само с',
        'parkside', 'silvercrest', 'crivit', 'livarno', 'esmara', 'ernesto',
        'deutsche markenbutter', 'la provincia', 'meat revolution', 'monini',
        'саяна', 'верея', 'пастир', 'дончево', 'престиж', 'гербери'
    ]
    for brand in brands:
        result = re.sub(r'^' + re.escape(brand) + r'\s*[-–]?\s*', '', result.strip())
        result = re.sub(r'\s+' + re.escape(brand) + r'\s*$', '', result)  # At end too
    
    # Remove promotional phrases
    result = re.sub(r'\b(супер цена|промоция|намаление|оферта|акция|произход|българия)\b', '', result, flags=re.IGNORECASE)
    
    # Remove size/variant descriptors that prevent matching
    result = re.sub(r'\b(различни видове|разни|асортимент|класик|или)\b', '', result, flags=re.IGNORECASE)
    
    # Normalize whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    
    # Remove leading/trailing punctuation
    result = re.sub(r'^[\s\-–—:,]+|[\s\-–—:,]+$', '', result)
    
    # If result is very short after stripping, it's likely a generic product - keep it
    if len(result) < 3:
        return ""
    
    return result[:35]  # Shorter key for better grouping


def export_products():
    """Export all products with store info to JSON."""
    
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query all products with their store prices
    # Schema: products -> store_products -> prices
    query = """
        SELECT 
            p.id,
            p.name,
            p.normalized_name,
            p.brand,
            p.unit,
            p.quantity,
            p.image_url,
            s.id as store_id,
            s.name as store_name,
            pr.current_price as price_eur,
            pr.old_price as old_price_eur,
            pr.discount_percent as discount_pct,
            sp.store_product_url as url
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON sp.id = pr.store_product_id
        WHERE pr.current_price > 0
        ORDER BY pr.discount_percent DESC NULLS LAST, p.name
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    EUR_TO_BGN = 1.9558  # Fixed exchange rate
    
    products = []
    for row in rows:
        price_eur = row["price_eur"]
        old_price_eur = row["old_price_eur"]
        name = row["name"] or ""
        
        # Calculate discount only if we have old_price and it's higher
        discount_pct = None
        if old_price_eur and old_price_eur > price_eur:
            discount_pct = int(round((1 - price_eur / old_price_eur) * 100))
        elif row["discount_pct"] and row["discount_pct"] < 100:  # Ignore 100% discounts as data errors
            discount_pct = int(row["discount_pct"])
        
        product = {
            "id": row["id"],
            "name": name,
            "normalized_name": normalize_product_name(name),
            "group_key": compute_group_key(name),  # For "cheapest wins" grouping
            "brand": row["brand"],
            "unit": row["unit"],
            "quantity": row["quantity"],
            "store": row["store_name"],
            "store_id": row["store_id"],
            "price_eur": round(price_eur, 2) if price_eur else None,
            "price_bgn": round(price_eur * EUR_TO_BGN, 2) if price_eur else None,
            "old_price_eur": round(old_price_eur, 2) if old_price_eur else None,
            "old_price_bgn": round(old_price_eur * EUR_TO_BGN, 2) if old_price_eur else None,
            "discount_pct": discount_pct,
            "image_url": row["image_url"],
            "url": row["url"]
        }
        products.append(product)
    
    conn.close()
    
    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Write JSON
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    # Stats
    stores = {}
    for p in products:
        store = p["store"]
        stores[store] = stores.get(store, 0) + 1
    
    print(f"✅ Exported {len(products)} products to {OUTPUT_PATH}")
    print(f"   By store: {stores}")
    print(f"   With discount: {sum(1 for p in products if p.get('discount_pct'))}")
    
    return True


if __name__ == "__main__":
    export_products()
