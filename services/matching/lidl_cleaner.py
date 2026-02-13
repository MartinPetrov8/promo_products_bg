#!/usr/bin/env python3
"""
Lidl Data Cleaner

Fixes Lidl product data in the database:
1. Parses HTML in unit field to extract actual sizes
2. Updates quantity/unit fields with parsed values
3. Cleans product names (removes "| LIDL" suffix)

HTML in unit field looks like:
    <ul><li>60 x 49 x 15 cm</li><li>№ 496389</li></ul>

Need to extract: dimensions, volume, weight, article number
"""

import re
import sqlite3
import json
import sys
from pathlib import Path
from html import unescape

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUR_DB = PROJECT_ROOT / "data" / "promobg.db"
LIDL_DATA = PROJECT_ROOT / "services" / "scraper" / "data" / "lidl_sitemap_products.json"


def parse_html_specs(html: str) -> dict:
    """
    Parse HTML specs to extract size/volume/weight.
    
    Input: <ul><li>Вместимост: 1.75 l</li><li>600 W</li></ul>
    Output: {'volume': 1.75, 'volume_unit': 'l', 'power': 600}
    """
    if not html:
        return {}
    
    result = {}
    
    # Unescape HTML entities
    text = unescape(html)
    
    # Remove HTML tags and get text content
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Volume patterns
    vol_match = re.search(r'(?:вместимост|обем)[:\s]*(\d+[.,]?\d*)\s*(l|л|ml|мл)', text, re.IGNORECASE)
    if vol_match:
        val = float(vol_match.group(1).replace(',', '.'))
        unit = vol_match.group(2).lower()
        if unit in ['l', 'л']:
            result['volume_ml'] = val * 1000
        else:
            result['volume_ml'] = val
    
    # Weight patterns
    weight_match = re.search(r'(\d+[.,]?\d*)\s*(kg|кг|g|г)\b', text, re.IGNORECASE)
    if weight_match and 'volume_ml' not in result:  # Don't override volume
        val = float(weight_match.group(1).replace(',', '.'))
        unit = weight_match.group(2).lower()
        if unit in ['kg', 'кг']:
            result['weight_g'] = val * 1000
        else:
            result['weight_g'] = val
    
    # Dimensions (e.g., "60 x 49 x 15 cm")
    dim_match = re.search(r'(\d+)\s*[xх×]\s*(\d+)(?:\s*[xх×]\s*(\d+))?\s*(cm|см|mm|мм)', text, re.IGNORECASE)
    if dim_match:
        result['dimensions'] = dim_match.group(0)
    
    # Article number
    art_match = re.search(r'№\s*(\d+)', text)
    if art_match:
        result['article_no'] = art_match.group(1)
    
    return result


def extract_size_from_name(name: str) -> tuple:
    """Extract size from product name like 'Руска салата XXL 1.2 kg'"""
    name_lower = name.lower()
    
    # Pack format
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
        else:
            return (count * val, 'g')
    
    # Single size
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
        else:
            return (val, 'g')
    
    return (None, None)


def clean_lidl_name(name: str) -> str:
    """Clean Lidl product name."""
    # Remove "| LIDL" suffix
    cleaned = re.sub(r'\s*\|\s*LIDL\s*$', '', name, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def extract_brand(name: str) -> str:
    """Extract brand from product name."""
    name_lower = name.lower()
    
    brands = [
        # Lidl store brands
        ('parkside', 'Parkside'), ('silvercrest', 'Silvercrest'),
        ('livarno', 'Livarno'), ('crivit', 'Crivit'), ('florabest', 'Florabest'),
        ('esmara', 'Esmara'), ('livergy', 'Livergy'), ('lupilu', 'Lupilu'),
        ('chef select', 'Chef Select'), ('pilos', 'Pilos'), ('milbona', 'Milbona'),
        ('dulano', 'Dulano'), ('pikok', 'Pikok'), ('mcennedy', 'McEnnedy'),
        ('vitasia', 'Vitasia'), ('italiamo', 'Italiamo'), ('deluxe', 'Deluxe'),
        # National/International brands
        ('nescafe', 'Nescafe'), ('jacobs', 'Jacobs'), ('lavazza', 'Lavazza'),
        ('coca-cola', 'Coca-Cola'), ('pepsi', 'Pepsi'),
        ('milka', 'Milka'), ('lindt', 'Lindt'), ('ferrero', 'Ferrero'),
        ('nestle', 'Nestle'), ('danone', 'Danone'),
        ('dove', 'Dove'), ('nivea', 'Nivea'), ('colgate', 'Colgate'),
        ('калиакра', 'Калиакра'), ('верея', 'Верея'),
        ('bounty', 'Bounty'), ('mars', 'Mars'), ('snickers', 'Snickers'),
        ('agi', 'Agi'), ('maestro', 'Maestro'),
    ]
    
    for pattern, brand_name in brands:
        if pattern in name_lower:
            return brand_name
    
    return None


def load_sitemap_data() -> dict:
    """Load pre-parsed data from sitemap scraper."""
    if not LIDL_DATA.exists():
        return {}
    
    with open(LIDL_DATA) as f:
        products = json.load(f)
    
    # Index by NORMALIZED NAME for matching (product codes don't match)
    # Also create entries without brand prefix for fuzzy matching
    result = {}
    for p in products:
        name = p.get('name', '').replace(' | LIDL', '').strip().lower()
        if name:
            result[name] = p
            # Also add the product name from description if different
            desc_name = p.get('description', '').split(' - ')[0].strip().lower() if p.get('description') else None
            if desc_name and desc_name != name:
                result[desc_name] = p
    
    return result


def find_in_sitemap(name: str, sitemap_data: dict) -> dict:
    """Try multiple strategies to find product in sitemap data."""
    # Strategy 1: Direct match
    lookup = clean_lidl_name(name).lower()
    if lookup in sitemap_data:
        return sitemap_data[lookup]
    
    # Strategy 2: Remove brand prefix and try again
    # DB has "Agi Бели курабии" but sitemap has "Бели курабии"
    words = lookup.split()
    if len(words) > 2:
        # Try without first word (brand)
        without_brand = ' '.join(words[1:])
        if without_brand in sitemap_data:
            return sitemap_data[without_brand]
    
    # Strategy 3: Try partial match on core product terms
    for sitemap_name, data in sitemap_data.items():
        # If our product name contains the sitemap name (or vice versa)
        if len(sitemap_name) > 5 and sitemap_name in lookup:
            return data
        if len(lookup) > 5 and lookup in sitemap_name:
            return data
    
    return None


def run_analysis():
    """Analyze Lidl products and show what would be fixed."""
    print("=" * 70)
    print("LIDL DATA CLEANING ANALYSIS")
    print("=" * 70)
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    # Load sitemap data for cross-reference
    sitemap_data = load_sitemap_data()
    print(f"Loaded {len(sitemap_data)} products from sitemap data")
    
    cursor.execute('''
        SELECT p.id, p.name, p.unit, p.quantity, p.brand, sp.store_product_code
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = 2
    ''')
    products = cursor.fetchall()
    
    print(f"Total Lidl products in DB: {len(products)}")
    
    to_update = []
    has_html_unit = 0
    fixed_size = 0
    fixed_brand = 0
    
    for pid, name, unit, quantity, brand, store_code in products:
        update = {
            'id': pid,
            'original_name': name,
            'original_unit': unit,
            'original_quantity': quantity,
            'original_brand': brand,
        }
        
        # Clean name
        update['cleaned_name'] = clean_lidl_name(name)
        
        # Check for HTML in unit field
        if unit and '<' in str(unit):
            has_html_unit += 1
            specs = parse_html_specs(unit)
            if specs.get('volume_ml'):
                update['size_value'] = specs['volume_ml']
                update['size_unit'] = 'ml'
            elif specs.get('weight_g'):
                update['size_value'] = specs['weight_g']
                update['size_unit'] = 'g'
        
        # Try to get size from sitemap data (matched by normalized name)
        if not update.get('size_value'):
            sitemap = find_in_sitemap(name, sitemap_data)
            if sitemap:
                sv = sitemap.get('size_value')
                su = sitemap.get('size_unit')
                if sv:
                    # Normalize units to g or ml
                    if su in ['kg', 'кг']:
                        update['size_value'] = sv * 1000
                        update['size_unit'] = 'g'
                    elif su in ['l', 'л']:
                        update['size_value'] = sv * 1000
                        update['size_unit'] = 'ml'
                    elif su in ['g', 'г']:
                        update['size_value'] = sv
                        update['size_unit'] = 'g'
                    elif su in ['ml', 'мл']:
                        update['size_value'] = sv
                        update['size_unit'] = 'ml'
                    else:
                        update['size_value'] = sv
                        update['size_unit'] = su
        
        # Try to extract size from name
        if not update.get('size_value'):
            sv, su = extract_size_from_name(name)
            if sv:
                update['size_value'] = sv
                update['size_unit'] = su
        
        # Extract brand if missing
        if not brand:
            update['new_brand'] = extract_brand(name)
        
        # Track improvements
        if update.get('size_value') and not quantity:
            fixed_size += 1
        if update.get('new_brand'):
            fixed_brand += 1
        
        to_update.append(update)
    
    # Summary
    print(f"\nAnalysis:")
    print(f"  Products with HTML in unit: {has_html_unit}")
    print(f"  Will add size to: {fixed_size} products")
    print(f"  Will add brand to: {fixed_brand} products")
    
    # Samples
    print("\n" + "=" * 70)
    print("SAMPLE TRANSFORMATIONS")
    print("=" * 70)
    
    # Show some with HTML units
    html_samples = [u for u in to_update if u.get('original_unit') and '<' in str(u.get('original_unit', ''))][:5]
    print("\nHTML unit parsing:")
    for item in html_samples:
        print(f"  Name: {item['original_name'][:50]}")
        print(f"  HTML: {str(item['original_unit'])[:60]}...")
        print(f"  Extracted: {item.get('size_value')} {item.get('size_unit')}")
        print()
    
    # Show some with sitemap size
    sitemap_samples = [u for u in to_update if u.get('size_value') and not u.get('original_quantity')][:5]
    print("\nSize from sitemap/name:")
    for item in sitemap_samples:
        print(f"  Name: {item['cleaned_name'][:50]}")
        print(f"  Size: {item.get('size_value')} {item.get('size_unit')}")
        print()
    
    conn.close()
    return to_update


def update_database(updates: list):
    """Apply updates to database."""
    print("\n" + "=" * 70)
    print("UPDATING DATABASE")
    print("=" * 70)
    
    conn = sqlite3.connect(str(OUR_DB))
    cursor = conn.cursor()
    
    updated_names = 0
    updated_sizes = 0
    updated_brands = 0
    
    for item in updates:
        # Update normalized name
        cursor.execute('''
            UPDATE products 
            SET normalized_name = ?
            WHERE id = ?
        ''', (item['cleaned_name'].lower(), item['id']))
        
        if item['cleaned_name'] != item['original_name']:
            updated_names += 1
        
        # Update size
        if item.get('size_value'):
            cursor.execute('''
                UPDATE products 
                SET quantity = ?, unit = ?
                WHERE id = ?
            ''', (item['size_value'], item['size_unit'], item['id']))
            updated_sizes += 1
        
        # Update brand
        if item.get('new_brand'):
            cursor.execute('''
                UPDATE products 
                SET brand = ?
                WHERE id = ?
            ''', (item['new_brand'], item['id']))
            updated_brands += 1
    
    conn.commit()
    
    # Verify
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN brand IS NOT NULL AND brand != '' THEN 1 ELSE 0 END) as with_brand,
            SUM(CASE WHEN quantity IS NOT NULL THEN 1 ELSE 0 END) as with_size
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        WHERE sp.store_id = 2
    ''')
    total, brands, sizes = cursor.fetchone()
    
    print(f"Updated {updated_names} names, {updated_sizes} sizes, {updated_brands} brands")
    print(f"\nVerification:")
    print(f"  Total Lidl products: {total}")
    print(f"  With brand: {brands}")
    print(f"  With size: {sizes}")
    
    conn.close()


if __name__ == '__main__':
    data = run_analysis()
    
    if '--update' in sys.argv:
        update_database(data)
    else:
        print("\n⚠️  Run with --update to apply changes to database")
