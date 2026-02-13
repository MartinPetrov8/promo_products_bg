#!/usr/bin/env python3
"""
Billa Product Name Cleaner

Strips promotional prefixes from Billa product names to enable better matching.

Before: "King оферта - Супер цена - Верея Кисело мляко 5% 400 г"
After:  "Верея Кисело мляко 5% 400 г"

IMPORTANT: Extract sizes BEFORE stripping suffixes like "За 1 кг"!
"""

import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"

# Promotional PREFIXES to strip
PROMO_PREFIXES = [
    # King оферта variants (most specific first)
    r'^king\s+оферта\s*-\s*супер\s+цена\s*-\s*',
    r'^king\s+оферта\s*-\s*само\s+с\s+billa\s+card\s*-\s*',
    r'^king\s+оферта\s*-\s*сега\s+в\s+billa\s*-\s*',
    r'^king\s+оферта\s*-\s*ново\s+в\s+billa\s*-\s*',
    r'^king\s+оферта\s*-\s*',
    # Other prefixes
    r'^супер\s+цена\s*[-–]\s*',
    r'^ниска\s+цена\s*-\s*',
    r'^промо\s+-?\s*',
    r'^-\d+%\s*-\s*',
    r'^\d+%\s+-\s*',
    r'^само\s+с\s+billa\s+card\s*-\s*',
    r'^сега\s+в\s+billa\s*-\s*',
    r'^ново\s+в\s+billa\s*-\s*',
]

# Suffixes to strip (AFTER extracting useful info)
PROMO_SUFFIXES = [
    r'\s+продукт,?\s+маркиран\s+със\s+синя\s+зв.*$',
    r'\s+от\s+топлата\s+витрина.*$',
    r'\s+от\s+деликатесната\s+витрина.*$',
    r'\s+от\s+нашата\s+пекарна.*$',
    r'\s+от\s+billa\s+пекарна.*$',
    r'\s+до\s+\d+\s*кг\s+на\s+клиент.*$',
    r'\s+до\s+\d+\s*бр\.?\s+на\s+клиент.*$',
    r'\s+произход\s*-\s*българия.*$',
    r'\s+произход.*$',
    r'\s+billa\s*$',  # "Billa" suffix
]

# Bulk pricing patterns - extract BEFORE stripping
BULK_PATTERNS = [
    (r'\s+за\s+1\s+кг\s*$', 1000, 'g', True),   # "За 1 кг" = 1kg bulk
    (r'\s+за\s+1\s+бр\.?\s*$', 1, 'бр', True),  # "За 1 бр" = per piece
    (r'\s+за\s+100\s*г\s*$', 100, 'g', True),   # "За 100 г" = per 100g
]


def extract_bulk_size(name: str) -> tuple:
    """
    Extract bulk pricing unit from name BEFORE cleaning.
    Returns (value, unit, is_bulk, remaining_name).
    """
    name_lower = name.lower()
    
    for pattern, value, unit, is_bulk in BULK_PATTERNS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            # Remove the bulk suffix from name
            cleaned = re.sub(pattern, '', name, flags=re.IGNORECASE)
            return (value, unit, is_bulk, cleaned)
    
    return (None, None, False, name)


def extract_inline_size(name: str) -> tuple:
    """
    Extract inline size from product name (e.g., "500 г", "2 x 1,5 л").
    Returns (value, unit) normalized to g or ml.
    """
    name_lower = name.lower()
    
    # Pack format: "2 x 1,5 л" or "2 х 250 г"
    pack_match = re.search(r'(\d+)\s*[хx]\s*(\d+[.,]?\d*)\s*(г|гр|кг|мл|л|g|kg|ml|l)\b', name_lower)
    if pack_match:
        count = int(pack_match.group(1))
        val = float(pack_match.group(2).replace(',', '.'))
        unit = pack_match.group(3)
        
        if unit in ['л', 'l']:
            return (count * val * 1000, 'ml')
        elif unit in ['кг', 'kg']:
            return (count * val * 1000, 'g')
        elif unit in ['мл', 'ml']:
            return (count * val, 'ml')
        else:  # г, гр, g
            return (count * val, 'g')
    
    # Single size: "500 г", "1.5 л"
    size_match = re.search(r'(\d+[.,]?\d*)\s*(г|гр|кг|мл|л|g|kg|ml|l)\b', name_lower)
    if size_match:
        val = float(size_match.group(1).replace(',', '.'))
        unit = size_match.group(2)
        
        if unit in ['л', 'l']:
            return (val * 1000, 'ml')
        elif unit in ['кг', 'kg']:
            return (val * 1000, 'g')
        elif unit in ['мл', 'ml']:
            return (val, 'ml')
        else:  # г, гр, g
            return (val, 'g')
    
    return (None, None)


def clean_billa_name(name: str) -> str:
    """Strip promotional text from Billa product name."""
    cleaned = name
    
    # Strip prefixes
    for pattern in PROMO_PREFIXES:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Strip suffixes
    for pattern in PROMO_SUFFIXES:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Strip bulk patterns (but we already extracted size from them)
    for pattern, _, _, _ in BULK_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def extract_brand(name: str) -> str:
    """Extract brand from product name."""
    name_lower = name.lower()
    
    brands = [
        ('верея', 'Верея'), ('olympus', 'Olympus'), ('олимпус', 'Olympus'),
        ('данон', 'Danone'), ('danone', 'Danone'), ('активиа', 'Activia'),
        ('president', 'President'), ('президент', 'President'),
        ('coca-cola', 'Coca-Cola'), ('coca cola', 'Coca-Cola'), ('кока-кола', 'Coca-Cola'),
        ('pepsi', 'Pepsi'), ('пепси', 'Pepsi'),
        ('nescafe', 'Nescafe'), ('нескафе', 'Nescafe'),
        ('jacobs', 'Jacobs'), ('якобс', 'Jacobs'),
        ('lavazza', 'Lavazza'), ('лаваца', 'Lavazza'),
        ('milka', 'Milka'), ('милка', 'Milka'),
        ('ferrero', 'Ferrero'), ('фереро', 'Ferrero'),
        ('lindt', 'Lindt'), ('линдт', 'Lindt'),
        ('nestle', 'Nestle'), ('нестле', 'Nestle'),
        ('devin', 'Devin'), ('девин', 'Devin'),
        ('bankya', 'Bankya'), ('банкя', 'Bankya'),
        ('hochland', 'Hochland'), ('хохланд', 'Hochland'),
        ('président', 'President'),
        ('emeka', 'Emeka'), ('емека', 'Emeka'),
        ('маджаров', 'Маджаров'), ('madjarov', 'Маджаров'),
        ('боженци', 'Боженци'),
        ('елена', 'Елена'),
        ('българска ферма', 'Българска Ферма'),
        ('la provincia', 'La Provincia'),
        ('еко мес', 'Еко Мес'),
        ('тандем', 'Тандем'),
        ('перелик', 'Перелик'),
        ('орехите', 'Орехите'),
        ('clever', 'Clever'),  # Billa store brand
        ('chef select', 'Chef Select'),
    ]
    
    for pattern, brand_name in brands:
        if pattern in name_lower:
            return brand_name
    
    return None


def extract_all_attributes(original_name: str) -> dict:
    """
    Extract all attributes from ORIGINAL name (before cleaning).
    This ensures we don't lose bulk size info.
    """
    result = {
        'brand': None,
        'size_value': None,
        'size_unit': None,
        'is_bulk': False,
        'cleaned_name': None,
    }
    
    # Step 1: Check for bulk pricing pattern FIRST
    bulk_val, bulk_unit, is_bulk, name_after_bulk = extract_bulk_size(original_name)
    result['is_bulk'] = is_bulk
    
    # Step 2: Try to extract inline size from name (before or after bulk strip)
    inline_val, inline_unit = extract_inline_size(original_name)
    
    # Step 3: Clean the name
    result['cleaned_name'] = clean_billa_name(original_name)
    
    # Step 4: Determine size - prefer inline size, fall back to bulk
    if inline_val:
        result['size_value'] = inline_val
        result['size_unit'] = inline_unit
    elif bulk_val:
        result['size_value'] = bulk_val
        result['size_unit'] = bulk_unit
    
    # Step 5: Extract brand from cleaned name
    result['brand'] = extract_brand(result['cleaned_name'])
    
    return result


def run_analysis():
    """Analyze Billa products before/after cleaning."""
    print("=" * 70)
    print("BILLA PRODUCT NAME CLEANING ANALYSIS (v2)")
    print("=" * 70)
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.name
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = 3
    ''')
    products = cursor.fetchall()
    
    print(f"\nTotal Billa products: {len(products)}")
    
    cleaned_data = []
    brands_found = 0
    sizes_found = 0
    bulk_found = 0
    
    for pid, name in products:
        attrs = extract_all_attributes(name)
        
        if attrs['brand']:
            brands_found += 1
        if attrs['size_value']:
            sizes_found += 1
        if attrs['is_bulk']:
            bulk_found += 1
        
        cleaned_data.append({
            'id': pid,
            'original': name,
            'cleaned': attrs['cleaned_name'],
            'attrs': attrs,
        })
    
    print(f"\nAfter cleaning:")
    print(f"  Brands extracted: {brands_found} ({brands_found/len(products)*100:.0f}%)")
    print(f"  Sizes extracted:  {sizes_found} ({sizes_found/len(products)*100:.0f}%)")
    print(f"  Bulk products:    {bulk_found} ({bulk_found/len(products)*100:.0f}%)")
    
    print("\n" + "=" * 70)
    print("SAMPLE TRANSFORMATIONS")
    print("=" * 70)
    
    for item in cleaned_data[:20]:
        print(f"\nBEFORE: {item['original'][:75]}")
        print(f"AFTER:  {item['cleaned'][:75]}")
        attrs = item['attrs']
        print(f"ATTRS:  brand={attrs['brand']} | size={attrs['size_value']}{attrs['size_unit'] or ''} | bulk={attrs['is_bulk']}")
    
    conn.close()
    return cleaned_data


def update_database(cleaned_data: list):
    """Update Billa products with cleaned names and attributes."""
    print("\n" + "=" * 70)
    print("UPDATING DATABASE")
    print("=" * 70)
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    updated = 0
    
    for item in cleaned_data:
        attrs = item['attrs']
        
        # Update product with all extracted info
        cursor.execute('''
            UPDATE products 
            SET normalized_name = ?,
                brand = COALESCE(?, brand),
                unit = COALESCE(?, unit),
                quantity = COALESCE(?, quantity)
            WHERE id = ?
        ''', (
            item['cleaned'].lower(),
            attrs['brand'],
            attrs['size_unit'],
            attrs['size_value'],
            item['id']
        ))
        updated += 1
    
    conn.commit()
    
    # Verify counts
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN brand IS NOT NULL AND brand != '' THEN 1 ELSE 0 END) as with_brand,
            SUM(CASE WHEN quantity IS NOT NULL THEN 1 ELSE 0 END) as with_size
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = 3
    ''')
    total, brands, sizes = cursor.fetchone()
    
    print(f"Updated {updated} products")
    print(f"\nVerification:")
    print(f"  Total Billa products: {total}")
    print(f"  With brand: {brands}")
    print(f"  With size: {sizes}")
    
    conn.close()


if __name__ == '__main__':
    data = run_analysis()
    
    if '--update' in sys.argv:
        update_database(data)
    else:
        print("\n⚠️  Run with --update to apply changes to database")
