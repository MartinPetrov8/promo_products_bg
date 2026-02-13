#!/usr/bin/env python3
"""
Extract sizes for Billa products from product names.
Billa currently has 0% size coverage - need to parse from names.
"""

import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "promobg.db"

# Size patterns (order matters - more specific first)
SIZE_PATTERNS = [
    # Weight with space
    (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 'kg'),
    (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)\b', 'g'),
    # Volume with space
    (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)\b', 'ml'),
    (r'(\d+(?:[.,]\d+)?)\s*(л|l)\b', 'l'),
    # Pieces
    (r'(\d+)\s*(бр|броя?|pcs?)\b', 'бр'),
    # Compact formats (no space)
    (r'(\d+(?:[.,]\d+)?)(кг|kg)\b', 'kg'),
    (r'(\d+(?:[.,]\d+)?)(гр?|g)\b', 'g'),
    (r'(\d+(?:[.,]\d+)?)(мл|ml)\b', 'ml'),
    (r'(\d+(?:[.,]\d+)?)(л|l)\b', 'l'),
    # X format (e.g., "6x330мл", "4x100г")
    (r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|г|g|л|l)', 'pack'),
]


def extract_size(name):
    """Extract size from product name."""
    if not name:
        return None
    
    name_lower = name.lower()
    
    # Try each pattern
    for pattern, unit_type in SIZE_PATTERNS:
        match = re.search(pattern, name_lower, re.IGNORECASE)
        if match:
            if unit_type == 'pack':
                # Format: count x size unit
                count = match.group(1)
                size = match.group(2).replace(',', '.')
                unit = match.group(3)
                # Normalize unit
                unit = unit.replace('мл', 'ml').replace('г', 'g').replace('л', 'l')
                return f"{count}x{size}{unit}"
            else:
                value = match.group(1).replace(',', '.')
                # Normalize unit
                unit = unit_type.replace('кг', 'kg').replace('гр', 'g').replace('г', 'g')
                unit = unit.replace('мл', 'ml').replace('л', 'l')
                return f"{value}{unit}"
    
    return None


def run():
    print("=" * 60)
    print("📏 Extracting Billa sizes from product names")
    print("=" * 60)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    
    # Get Billa store ID
    cur.execute("SELECT id FROM stores WHERE name = 'Billa'")
    billa_id = cur.fetchone()[0]
    
    # Get Billa products without size
    cur.execute("""
        SELECT sp.id, p.name, sp.package_size
        FROM store_products sp
        JOIN products p ON sp.product_id = p.id
        WHERE sp.store_id = ?
          AND sp.deleted_at IS NULL
          AND (sp.package_size IS NULL OR sp.package_size = '')
    """, (billa_id,))
    products = cur.fetchall()
    
    print(f"Found {len(products)} Billa products without size")
    
    # Extract sizes
    updated = 0
    sizes_found = {}
    
    for sp_id, name, current_size in products:
        size = extract_size(name)
        if size:
            cur.execute("""
                UPDATE store_products 
                SET package_size = ?
                WHERE id = ?
            """, (size, sp_id))
            updated += 1
            sizes_found[size] = sizes_found.get(size, 0) + 1
    
    conn.commit()
    
    print(f"\n📊 Results:")
    print(f"  Sizes extracted: {updated}/{len(products)} ({updated*100//max(len(products),1)}%)")
    
    # Show size distribution
    print(f"\n📋 Top sizes found:")
    for size, count in sorted(sizes_found.items(), key=lambda x: -x[1])[:15]:
        print(f"  {count:>3}x {size}")
    
    # Show sample extractions
    print(f"\n📋 Sample extractions:")
    cur.execute("""
        SELECT p.name, sp.package_size
        FROM store_products sp
        JOIN products p ON sp.product_id = p.id
        WHERE sp.store_id = ?
          AND sp.package_size IS NOT NULL
          AND sp.package_size != ''
        ORDER BY RANDOM()
        LIMIT 10
    """, (billa_id,))
    for row in cur.fetchall():
        print(f"  {row[0][:45]:<45} → {row[1]}")
    
    # Final coverage
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN package_size IS NOT NULL AND package_size != '' THEN 1 ELSE 0 END) as with_size
        FROM store_products
        WHERE store_id = ? AND deleted_at IS NULL
    """, (billa_id,))
    total, with_size = cur.fetchone()
    print(f"\n✅ Billa size coverage: {with_size}/{total} ({with_size*100//total}%)")
    
    conn.close()


if __name__ == '__main__':
    run()
