#!/usr/bin/env python3
"""
Brand & Quantity Enrichment Pipeline

Post-scrape enrichment step that extracts brands and quantities from
product names and descriptions using:
1. Known Bulgarian brands whitelist
2. Known international brands whitelist  
3. Regex patterns for quantity extraction
4. Store-specific parsing rules

Run after scraping, before matching.
"""

import re
import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "promobg.db"
CONFIG_DIR = REPO_ROOT / "config"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)


# =============================================================================
# KNOWN BRANDS DATABASE
# =============================================================================

# Bulgarian brands (Cyrillic) — extracted from actual product names across all stores
BG_BRANDS = {
    # Meat & Deli
    'Тандем', 'Перелик', 'КФМ', 'Еко Мес', 'Орехите', 'Градус', 'Родопа',
    'Стара планина', 'Кен', 'Кенар', 'Маджаров', 'Елит', 'Свежест',
    'Деликатес Житница', 'Родна Стреха',
    # Dairy
    'Верея', 'Данон', 'Кремио', 'Бисер', 'Мадара', 'Българска ферма',
    'Маджаров', 'Боровец', 'Нова Загора', 'Преслав', 'Ел Би Булгарикум',
    # Oils & Condiments
    'Калиакра', 'Олинеза', 'Краси', 'Бисер Олива',
    # Beverages
    'Горна Баня', 'Девин', 'Банкя', 'Хисар', 'Загорка', 'Каменица',
    'Пиринско', 'Шуменско', 'Ариана', 'Болярка',
    # Bakery & Snacks
    'Престиж', 'Златен лъв', 'Добруджа', 'Лидер',
    # Household & Other
    'Фамилекс', 'Бела', 'Медикс',
    # Kaufland specific (Cyrillic titled brands)
    'Живкови', 'Крина', 'Пилко',
}

# International brands commonly found in Bulgarian stores
INTL_BRANDS = {
    # Food & Beverage
    'Coca-Cola', 'Pepsi', 'Fanta', 'Sprite', 'Schweppes', 'Red Bull',
    'Nestlé', 'Nestle', 'Danone', 'Activia', 'Milka', 'Oreo',
    'Barilla', 'Panzani', 'Knorr', 'Maggi', 'Hellmann', 'Heinz',
    'Nutella', 'Ferrero', 'Kinder', 'Raffaello', 'Lindt', 'Toblerone',
    'Mars', 'Snickers', 'Twix', 'Bounty', 'M&M', 'Skittles',
    'Pringles', 'Lay\'s', 'Lays', 'Doritos', 'Ruffles', 'Chio',
    'Jacobs', 'Nescafé', 'Nescafe', 'Lavazza', 'Tchibo', 'Illy',
    'Lipton', 'Ahmad', 'Twinings',
    'Philadelphia', 'Président', 'President', 'Galbani', 'Arla',
    'Bonduelle', 'Del Monte',
    # Alcohol
    'Johnnie Walker', 'Jack Daniel', 'Jim Beam', 'Jägermeister',
    'Smirnoff', 'Absolut', 'Bacardi', 'Havana Club',
    'Heineken', 'Guinness', 'Corona', 'Amstel', 'Stella Artois',
    # Household
    'Persil', 'Ariel', 'Tide', 'Fairy', 'Domestos', 'Cif',
    'Vanish', 'Finish', 'Somat', 'Calgon',
    'Colgate', 'Oral-B', 'Signal', 'Sensodyne',
    'Nivea', 'Dove', 'Rexona', 'Head & Shoulders', 'Pantene',
    'Pampers', 'Huggies',
    # Pet
    'Whiskas', 'Pedigree', 'Felix',
    # Kaufland private label
    'K-Classic', 'K-Favourites', 'K-Bio',
    # Billa
    'Billa', 'Clever',
}

# Lidl private labels (already in scraper, duplicated here for enrichment)
LIDL_BRANDS = {
    'Milbona', 'Pilos', 'Cien', 'Silvercrest', 'Parkside', 'Livarno',
    'Esmara', 'Livergy', 'Ernesto', 'Crivit', 'Baresa', 'Italiamo',
    'Vitasia', 'Kania', 'Freshona', 'Solevita', 'Freeway', 'Chef Select',
    'Snack Day', 'Tastino', 'Bellarom', 'Pikok', 'Favorina', 'Fin Carré',
    'Perlenbacher', 'Argus', 'Trattoria Alfredo', 'Combino', 'Deluxe',
    'W5', 'Formil', 'Dentalux', 'Floralys', 'Coshida', 'Orlando',
    'Lupilu', 'Toujours', 'Nevadent', 'Auriol', 'Sanino',
    'Siti', 'Purio', 'Lord Nelson', 'Tower',
}

# Combined: all known brands, sorted longest-first for matching priority
ALL_BRANDS = sorted(
    BG_BRANDS | INTL_BRANDS | LIDL_BRANDS,
    key=len, reverse=True
)


# =============================================================================
# BRAND EXTRACTION
# =============================================================================

def extract_brand(name: str, description: str = '', store: str = '') -> Optional[str]:
    """
    Extract brand from product name and/or description.
    
    Strategy (in priority order):
    1. Match against known brands list (longest match wins)
    2. Extract Latin brand from start of name
    3. Extract Latin brand from description
    """
    # Strip store-specific noise before matching
    clean_name = name
    # Billa noise phrases
    for noise in ['Продукт, маркиран със синя звезда', 'Произход - България',
                   'Произход България', 'Само с Billa Card -', 'Само с Billa App',
                   'От топлата витрина', 'От Billa пекарна', 'От деликатесната витрина',
                   'До 5 бр. на клиент*', 'До 5 кг на клиент на ден*']:
        clean_name = clean_name.replace(noise, ' ')
    
    text = f"{clean_name} {description}".strip()
    text_lower = text.lower()
    
    # Strategy 1: Known brands (most reliable)
    for brand in ALL_BRANDS:
        if brand.lower() in text_lower:
            # Verify it's a word boundary (not substring of another word)
            pattern = re.compile(r'(?:^|[\s,\-\(])' + re.escape(brand) + r'(?:[\s,\-\)\.]|$)', re.IGNORECASE)
            if pattern.search(text):
                return brand
    
    # Strategy 2: Latin text at start of name = likely brand
    if name:
        match = re.match(r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\s', name)
        if match:
            candidate = match.group(1).strip()
            # Filter out common non-brand words
            skip = {'King', 'Super', 'XXL', 'XL', 'LED', 'USB', 'Mix', 'Bio', 'Eco', 'Pro'}
            if candidate not in skip and len(candidate) >= 3:
                return candidate
    
    return None


# =============================================================================
# QUANTITY EXTRACTION (enhanced)
# =============================================================================

def extract_quantity(name: str, description: str = '') -> Tuple[Optional[float], Optional[str]]:
    """
    Extract quantity from product name and description.
    Returns (value_in_base_units, unit) where unit is 'g', 'ml', or 'count'.
    """
    text = f"{name} {description}".strip()
    
    # Skip "За 1 кг" (price-per-kg, not package weight)
    text_clean = re.sub(r'За\s+\d+\s*(кг|г|л|мл)', '', text, flags=re.IGNORECASE)
    
    # Pattern 1: "X x Y unit" (multiply) — "2 x 250 г", "4x100мл"
    match = re.search(r'(\d+)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*(г|гр|g|кг|kg|мл|ml|л|l)\b', text_clean, re.I)
    if match:
        count = int(match.group(1))
        value = float(match.group(2).replace(',', '.'))
        return _normalize_qty(count * value, match.group(3))
    
    # Pattern 2: "Y unit" — "500 г", "1,5 кг", "750 мл"
    # Be more specific to avoid matching random numbers
    match = re.search(r'(?<!\d[.,])(\d+(?:[.,]\d+)?)\s*(г|гр|g|кг|kg|мл|ml|л|l)\b', text_clean, re.I)
    if match:
        value = float(match.group(1).replace(',', '.'))
        return _normalize_qty(value, match.group(2))
    
    # Pattern 3: count — "6 бр", "10 бр."
    match = re.search(r'(\d+)\s*бр\.?', text_clean, re.I)
    if match:
        return float(match.group(1)), 'count'
    
    return None, None


def _normalize_qty(value: float, unit: str) -> Tuple[float, str]:
    """Normalize quantity to base units (grams or milliliters)."""
    unit = unit.lower()
    if unit in ('г', 'гр', 'g'):
        return value, 'g'
    elif unit in ('кг', 'kg'):
        return value * 1000, 'g'
    elif unit in ('мл', 'ml'):
        return value, 'ml'
    elif unit in ('л', 'l'):
        return value * 1000, 'ml'
    return value, unit


# =============================================================================
# DATABASE ENRICHMENT
# =============================================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def enrich_products():
    """
    Enrich all products in DB with brand and quantity from names/descriptions.
    Only updates products that are missing brand or quantity.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all products
    cursor.execute("""
        SELECT id, name, description, store, brand, quantity, quantity_unit
        FROM products
        WHERE is_active = 1
    """)
    products = cursor.fetchall()
    
    log.info(f"Enriching {len(products)} products...")
    
    brand_updated = 0
    qty_updated = 0
    
    for p in products:
        pid = p['id']
        name = p['name'] or ''
        desc = p['description'] or ''
        store = p['store'] or ''
        current_brand = p['brand']
        current_qty = p['quantity']
        
        updates = {}
        
        # Enrich brand if missing
        if not current_brand or current_brand.lower() in ('', 'unknown', 'no_brand', 'n/a', 'none'):
            brand = extract_brand(name, desc, store)
            if brand:
                updates['brand'] = brand
                brand_updated += 1
        
        # Enrich quantity if missing
        if not current_qty or current_qty == 0:
            qty_val, qty_unit = extract_quantity(name, desc)
            if qty_val and qty_val > 0:
                updates['quantity'] = qty_val
                updates['quantity_unit'] = qty_unit
                qty_updated += 1
        
        # Apply updates
        if updates:
            set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [pid]
            cursor.execute(f"UPDATE products SET {set_clause} WHERE id = ?", values)
    
    conn.commit()
    
    # Report
    log.info(f"Brand enriched: {brand_updated} products")
    log.info(f"Quantity enriched: {qty_updated} products")
    
    # Get final stats
    cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND brand IS NOT NULL AND brand != '' AND brand != 'unknown' AND brand != 'no_brand'")
    with_brand = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND quantity IS NOT NULL AND quantity > 0")
    with_qty = cursor.fetchone()[0]
    
    log.info(f"\n{'='*50}")
    log.info(f"ENRICHMENT RESULTS")
    log.info(f"{'='*50}")
    log.info(f"Total active:  {total}")
    log.info(f"With brand:    {with_brand}/{total} ({100*with_brand/total:.1f}%)")
    log.info(f"With quantity: {with_qty}/{total} ({100*with_qty/total:.1f}%)")
    
    # Per-store breakdown
    for store in ['Kaufland', 'Lidl', 'Billa']:
        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND store = ?", (store,))
        st = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND store = ? AND brand IS NOT NULL AND brand != '' AND brand != 'unknown' AND brand != 'no_brand'", (store,))
        sb = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1 AND store = ? AND quantity IS NOT NULL AND quantity > 0", (store,))
        sq = cursor.fetchone()[0]
        if st > 0:
            log.info(f"  {store:10}: {st} products | Brand {sb}/{st} ({100*sb/st:.0f}%) | Qty {sq}/{st} ({100*sq/st:.0f}%)")
    
    conn.close()
    return brand_updated, qty_updated


def report_unbranded():
    """Report products still missing brand, grouped by store."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT store, name, description 
        FROM products 
        WHERE is_active = 1 
        AND (brand IS NULL OR brand = '' OR brand = 'unknown' OR brand = 'no_brand')
        ORDER BY store, name
    """)
    rows = cursor.fetchall()
    
    by_store = {}
    for r in rows:
        store = r['store']
        if store not in by_store:
            by_store[store] = []
        by_store[store].append(r['name'])
    
    log.info(f"\n{'='*50}")
    log.info(f"UNBRANDED PRODUCTS ({len(rows)} total)")
    log.info(f"{'='*50}")
    
    for store, names in sorted(by_store.items()):
        log.info(f"\n{store} ({len(names)} unbranded):")
        for name in names[:20]:
            log.info(f"  - {name[:70]}")
        if len(names) > 20:
            log.info(f"  ... and {len(names)-20} more")
    
    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Brand & Quantity Enrichment')
    parser.add_argument('--report', action='store_true', help='Show unbranded products report')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without writing')
    args = parser.parse_args()
    
    if args.report:
        report_unbranded()
    else:
        brand_count, qty_count = enrich_products()
        print(f"\nDone: {brand_count} brands + {qty_count} quantities enriched")
