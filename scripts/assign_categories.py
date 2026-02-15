#!/usr/bin/env python3
"""
Assign Categories to Products

Batch categorize all products in the database using the CategoryClassifier.
Updates category_code and category_name fields.

Usage:
    python scripts/assign_categories.py [--dry-run]
"""

import sys
import sqlite3
import argparse
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from standardization.category_classifier import CategoryClassifier


def assign_categories(db_path: str, dry_run: bool = False) -> dict:
    """
    Assign categories to all products in database.
    
    Args:
        db_path: Path to SQLite database
        dry_run: If True, don't commit changes
        
    Returns:
        Statistics dict with counts per category
    """
    classifier = CategoryClassifier()
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get all products
    cur.execute("""
        SELECT id, name, brand, category_code
        FROM products
        WHERE name IS NOT NULL
    """)
    
    products = cur.fetchall()
    total = len(products)
    
    print(f"Processing {total} products...")
    
    stats = {'updated': 0, 'skipped': 0, 'by_category': {}}
    
    for i, row in enumerate(products):
        # Classify
        category_id = classifier.classify(row['name'], row['brand'])
        category_code = classifier.get_category_code(category_id)
        category_name = classifier.get_category_name(category_id)
        
        # Track stats
        if category_id not in stats['by_category']:
            stats['by_category'][category_id] = 0
        stats['by_category'][category_id] += 1
        
        # Skip if already categorized with same code
        if row['category_code'] == category_code:
            stats['skipped'] += 1
            continue
        
        # Update
        if not dry_run:
            cur.execute("""
                UPDATE products 
                SET category_code = ?, category_name = ?
                WHERE id = ?
            """, (category_code, category_name, row['id']))
        
        stats['updated'] += 1
        
        # Progress
        if (i + 1) % 1000 == 0:
            print(f"  Processed {i+1}/{total}...")
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description='Assign categories to products')
    parser.add_argument('--db', default='data/promobg.db', help='Database path')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    args = parser.parse_args()
    
    print("=" * 60)
    print("CATEGORY ASSIGNMENT")
    print("=" * 60)
    
    if args.dry_run:
        print("DRY RUN - no changes will be saved\n")
    
    stats = assign_categories(args.db, dry_run=args.dry_run)
    
    print(f"\nResults:")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped (already categorized): {stats['skipped']}")
    
    print(f"\nBy category:")
    for cat_id, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
        print(f"  {cat_id}: {count}")
    
    if args.dry_run:
        print("\n(Dry run - no changes saved)")
    else:
        print("\n✓ Categories assigned")


if __name__ == "__main__":
    main()
