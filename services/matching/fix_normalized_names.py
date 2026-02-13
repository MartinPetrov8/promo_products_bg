#!/usr/bin/env python3
"""
Fix normalized_name field - remove promo text, clean up product names.
"""

import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "promobg.db"

# Promo patterns to remove
PROMO_PATTERNS = [
    # Kaufland patterns
    r'-?\d+%\s*отстъпка\s*(с\s*)?(kaufland\s*card)?.*',
    r'с\s*kaufland\s*card.*',
    r'king\s*оферта.*',
    r'k-classic\s*$',  # Standalone K-Classic at end
    # Billa patterns
    r'супер\s*цена.*',
    r'само\s*с\s*billa\s*card.*',
    r'продукт[,\s]+маркиран.*',
    r'billa\s*card\s*цена.*',
    # Lidl patterns
    r'lidl\s*plus.*',
    # Generic patterns
    r'промоция.*',
    r'специална\s*цена.*',
    r'намаление.*',
    r'\n+',  # Newlines
    r'\s{2,}',  # Multiple spaces
]

def clean_name(name):
    """Clean product name by removing promo text."""
    if not name:
        return name
    
    original = name
    name = name.lower().strip()
    
    for pattern in PROMO_PATTERNS:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
    
    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Don't return empty string
    if not name or len(name) < 3:
        return original.lower().strip()
    
    return name


def run():
    print("=" * 60)
    print("🧹 Fixing normalized_name field")
    print("=" * 60)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    
    # Get all products
    cur.execute("""
        SELECT id, name, normalized_name 
        FROM products 
        WHERE deleted_at IS NULL
    """)
    products = cur.fetchall()
    print(f"Found {len(products)} products")
    
    # Track changes
    updated = 0
    promo_found = 0
    
    for pid, name, norm_name in products:
        # Use name if normalized_name is empty
        source = norm_name if norm_name else name
        if not source:
            continue
            
        cleaned = clean_name(source)
        
        # Check if we found promo text
        if cleaned != source.lower().strip():
            promo_found += 1
        
        # Update if different
        if cleaned != norm_name:
            cur.execute("""
                UPDATE products 
                SET normalized_name = ?
                WHERE id = ?
            """, (cleaned, pid))
            updated += 1
    
    conn.commit()
    
    print(f"\n📊 Results:")
    print(f"  Products with promo text: {promo_found}")
    print(f"  Records updated: {updated}")
    
    # Verify - show sample of cleaned names
    print(f"\n📋 Sample cleaned names:")
    cur.execute("""
        SELECT p.name, p.normalized_name, s.name as store
        FROM products p
        JOIN store_products sp ON sp.product_id = p.id
        JOIN stores s ON sp.store_id = s.id
        WHERE p.deleted_at IS NULL
        ORDER BY RANDOM()
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  [{row[2][:8]}] {row[0][:35]:<35} → {row[1][:35]}")
    
    # Check for remaining promo text
    print(f"\n🔍 Checking for remaining promo patterns...")
    cur.execute("""
        SELECT COUNT(*) FROM products 
        WHERE normalized_name LIKE '%отстъпка%' 
           OR normalized_name LIKE '%card%'
           OR normalized_name LIKE '%оферта%'
    """)
    remaining = cur.fetchone()[0]
    if remaining > 0:
        print(f"  ⚠️  {remaining} products still have promo text")
        cur.execute("""
            SELECT normalized_name FROM products 
            WHERE normalized_name LIKE '%отстъпка%' 
               OR normalized_name LIKE '%card%'
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"     {row[0][:60]}")
    else:
        print(f"  ✅ All promo text removed")
    
    conn.close()
    print(f"\n✅ Done!")


if __name__ == '__main__':
    run()
