#!/usr/bin/env python3
"""
Billa Product Name Cleaner

Strips promotional prefixes from Billa product names to enable better matching.

Before: "King оферта - Супер цена - Верея Кисело мляко 5% 400 г"
After:  "Верея Кисело мляко 5% 400 г"
"""

import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"
OFF_DB = PROJECT_ROOT / "data" / "off_bulgaria.db"

# Promotional prefixes to strip (order matters - longer first)
PROMO_PATTERNS = [
    # King оферта variants (most specific first)
    r'^king\s+оферта\s*-\s*супер\s+цена\s*-\s*',
    r'^king\s+оферта\s*-\s*само\s+с\s+billa\s+card\s*-\s*',
    r'^king\s+оферта\s*-\s*сега\s+в\s+billa\s*-\s*',
    r'^king\s+оферта\s*-\s*ново\s+в\s+billa\s*-\s*',
    r'^king\s+оферта\s*-\s*',
    # Other prefixes
    r'^супер\s+цена\s*-\s*',
    r'^ниска\s+цена\s*-\s*',
    r'^промо\s+-?\s*',
    r'^-\d+%\s*-\s*',
    r'^\d+%\s+-\s*',
    r'^само\s+с\s+billa\s+card\s*-\s*',
    r'^сега\s+в\s+billa\s*-\s*',
    r'^ново\s+в\s+billa\s*-\s*',
    # Suffixes
    r'\s+продукт,?\s+маркиран\s+със\s+синя\s+зв.*$',
    r'\s+от\s+топлата\s+витрина.*$',
    r'\s+от\s+деликатесната\s+витрина.*$',
    r'\s+от\s+нашата\s+пекарна.*$',
    r'\s+от\s+billa\s+пекарна.*$',
    r'\s+за\s+1\s+кг\s*$',
    r'\s+за\s+1\s+бр\.?\s*$',
    r'\s+до\s+\d+\s*кг\s+на\s+клиент.*$',
    r'\s+произход\s*-\s*българия.*$',
    r'\s+произход.*$',
]


def clean_billa_name(name: str) -> str:
    """Strip promotional text from Billa product name."""
    cleaned = name
    
    for pattern in PROMO_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def extract_attributes(name: str) -> dict:
    """Extract brand, size, type from cleaned name."""
    result = {
        'brand': None,
        'size_value': None,
        'size_unit': None,
        'fat_pct': None,
        'pack_count': None,
    }
    
    name_lower = name.lower()
    
    # Extract size (e.g., "400 г", "1.5 л", "2 х 1,5 л")
    pack_match = re.search(r'(\d+)\s*[хx]\s*(\d+[.,]?\d*)\s*(г|гр|кг|мл|л|g|kg|ml|l)\b', name_lower)
    if pack_match:
        result['pack_count'] = int(pack_match.group(1))
        result['size_value'] = float(pack_match.group(2).replace(',', '.'))
        unit = pack_match.group(3)
        result['size_unit'] = 'ml' if unit in ['мл', 'л', 'ml', 'l'] else 'g'
        if unit in ['л', 'l', 'кг', 'kg']:
            result['size_value'] *= 1000
    else:
        size_match = re.search(r'(\d+[.,]?\d*)\s*(г|гр|кг|мл|л|g|kg|ml|l)\b', name_lower)
        if size_match:
            result['size_value'] = float(size_match.group(1).replace(',', '.'))
            unit = size_match.group(2)
            result['size_unit'] = 'ml' if unit in ['мл', 'л', 'ml', 'l'] else 'g'
            if unit in ['л', 'l', 'кг', 'kg']:
                result['size_value'] *= 1000
    
    # Extract fat percentage
    fat_match = re.search(r'(\d+[.,]?\d*)\s*%', name_lower)
    if fat_match:
        result['fat_pct'] = fat_match.group(1).replace(',', '.')
    
    # Extract brand
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
    ]
    
    for pattern, brand_name in brands:
        if pattern in name_lower:
            result['brand'] = brand_name
            break
    
    return result


def run_analysis():
    """Analyze Billa products before/after cleaning."""
    print("=" * 70)
    print("BILLA PRODUCT NAME CLEANING ANALYSIS")
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
    fat_found = 0
    
    for pid, name in products:
        cleaned = clean_billa_name(name)
        attrs = extract_attributes(cleaned)
        
        if attrs['brand']:
            brands_found += 1
        if attrs['size_value']:
            sizes_found += 1
        if attrs['fat_pct']:
            fat_found += 1
        
        cleaned_data.append({
            'id': pid,
            'original': name,
            'cleaned': cleaned,
            'attrs': attrs,
        })
    
    print(f"\nAfter cleaning:")
    print(f"  Brands extracted: {brands_found} ({brands_found/len(products)*100:.0f}%)")
    print(f"  Sizes extracted:  {sizes_found} ({sizes_found/len(products)*100:.0f}%)")
    print(f"  Fat % extracted:  {fat_found} ({fat_found/len(products)*100:.0f}%)")
    
    print("\n" + "=" * 70)
    print("SAMPLE TRANSFORMATIONS")
    print("=" * 70)
    
    for item in cleaned_data[:15]:
        print(f"\nBEFORE: {item['original'][:70]}")
        print(f"AFTER:  {item['cleaned'][:70]}")
        attrs = item['attrs']
        print(f"ATTRS:  brand={attrs['brand']} | size={attrs['size_value']}{attrs['size_unit'] or ''} | fat={attrs['fat_pct']}%")
    
    conn.close()
    return cleaned_data


def update_database(cleaned_data: list):
    """Update Billa products with cleaned names and attributes."""
    print("\n" + "=" * 70)
    print("UPDATING DATABASE")
    print("=" * 70)
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    updated_names = 0
    updated_attrs = 0
    
    for item in cleaned_data:
        # Update normalized_name
        cursor.execute('''
            UPDATE products 
            SET normalized_name = ?
            WHERE id = ?
        ''', (item['cleaned'].lower(), item['id']))
        
        if item['cleaned'] != item['original']:
            updated_names += 1
        
        # Update brand, unit, quantity
        attrs = item['attrs']
        if attrs['brand'] or attrs['size_value']:
            cursor.execute('''
                UPDATE products 
                SET brand = COALESCE(?, brand),
                    unit = COALESCE(?, unit),
                    quantity = COALESCE(?, quantity)
                WHERE id = ?
            ''', (
                attrs['brand'],
                attrs['size_unit'],
                attrs['size_value'],
                item['id']
            ))
            updated_attrs += 1
    
    conn.commit()
    conn.close()
    
    print(f"Updated {updated_names} products with cleaned names")
    print(f"Updated {updated_attrs} products with attributes (brand/size)")


if __name__ == '__main__':
    data = run_analysis()
    
    if '--update' in sys.argv:
        update_database(data)
