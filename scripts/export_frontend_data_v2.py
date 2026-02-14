"""
Export frontend data from SQLite to JSON for GitHub Pages.
V2: Fixed issues with duplicates, bad discounts, and grouping.
"""
import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from unit_price import get_unit_prices, parse_quantity

# Paths
REPO_ROOT = Path(__file__).parent.parent
PROMOBG_DB = REPO_ROOT / "data" / "promobg.db"
OFF_DB = REPO_ROOT / "data" / "off_bulgaria.db"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "products.json"
DOCS_OUTPUT = REPO_ROOT / "docs" / "data" / "products.json"


def get_off_data(off_conn: sqlite3.Connection) -> dict:
    """Load OFF products into a lookup dict by id."""
    cur = off_conn.cursor()
    cur.execute("""
        SELECT id, barcode, product_name, brands, categories, nutriscore_grade, ingredients_text
        FROM off_products
    """)
    
    off_by_id = {}
    for row in cur.fetchall():
        off_by_id[row[0]] = {
            "barcode": row[1],
            "name": row[2],
            "brand": row[3],
            "categories": row[4],
            "nutriscore": row[5],
            "ingredients": row[6][:200] if row[6] else None
        }
    return off_by_id


def validate_discount(current_price, old_price, discount_pct):
    """
    Validate discount data. Return corrected values.
    Fixes: absurd old_price values like 132.99 for a 2€ item.
    """
    if not current_price or current_price <= 0:
        return None, None, 0
    
    # If old_price is absurdly high (more than 5x current), it's garbage
    if old_price and old_price > current_price * 5:
        return None, None, 0
    
    # If old_price is less than current_price, it's wrong
    if old_price and old_price < current_price:
        return None, None, 0
    
    # Recalculate discount if old_price is valid
    if old_price and old_price > current_price:
        correct_discount = int((1 - current_price / old_price) * 100)
        return round(current_price, 2), round(old_price, 2), correct_discount
    
    return round(current_price, 2), None, 0


def export_data():
    """Main export function."""
    print("Connecting to databases...")
    conn = sqlite3.connect(PROMOBG_DB)
    off_conn = sqlite3.connect(OFF_DB)
    conn.row_factory = sqlite3.Row
    
    # Load OFF data
    print("Loading OFF data...")
    off_by_id = get_off_data(off_conn)
    
    # Query products - use DISTINCT and get only latest/best price per store-product combo
    # Also filter out duplicates by using MIN price per store+product_name combo
    print("Querying products...")
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand, p.image_url, p.barcode_ean,
            s.name as store_name,
            pr.current_price, pr.old_price, pr.discount_percent,
            pom.off_product_id, pom.match_type, pom.match_confidence,
            sp.id as store_product_id
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        JOIN prices pr ON sp.id = pr.store_product_id
        LEFT JOIN product_off_matches pom ON p.id = pom.product_id
        WHERE pr.current_price IS NOT NULL
        ORDER BY p.name, s.name, pr.current_price ASC
    """)
    
    # Dedupe: keep only one entry per store+product_name
    seen = set()  # (store, product_name)
    products = []
    off_lookup = {}
    groups_by_off_id = {}
    
    for row in cur.fetchall():
        # Dedupe key: store + normalized product name
        dedupe_key = (row["store_name"], row["name"].lower().strip())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        
        # Validate and fix discount data
        price, old_price, discount = validate_discount(
            row["current_price"], 
            row["old_price"], 
            row["discount_percent"]
        )
        
        # Skip absurd prices (scraper bugs)
        if not price or price > 200:
            continue
        if price > 200:
            continue
        
        # Parse unit prices
        unit_prices = get_unit_prices(row["name"], price)
        qty, unit = parse_quantity(row["name"])
        
        # Get OFF barcode if matched
        off_barcode = None
        if row["off_product_id"] and row["off_product_id"] in off_by_id:
            off_data = off_by_id[row["off_product_id"]]
            off_barcode = off_data["barcode"]
            
            if off_barcode and off_barcode not in off_lookup:
                off_lookup[off_barcode] = {
                    "name": off_data["name"],
                    "brand": off_data["brand"],
                    "nutriscore": off_data["nutriscore"],
                    "categories": off_data["categories"],
                    "ingredients": off_data["ingredients"]
                }
            
            # Track for cross-store groups
            off_id = row["off_product_id"]
            if off_id not in groups_by_off_id:
                groups_by_off_id[off_id] = []
            groups_by_off_id[off_id].append(len(products))
        
        # Generate group_id
        group_id = None
        if off_barcode:
            group_id = f"g_{hashlib.md5(off_barcode.encode()).hexdigest()[:8]}"
        
        product = {
            "id": row["id"],
            "name": row["name"],
            "store": row["store_name"],
            "price": price,
            "old_price": old_price,
            "discount_pct": discount,
            "image_url": row["image_url"],
            "off_barcode": off_barcode,
            "group_id": group_id,
            "match_type": row["match_type"],
            "match_confidence": round(row["match_confidence"], 2) if row["match_confidence"] else None,
            "quantity_g": int(qty) if qty and unit == "g" else None,
            "quantity_ml": int(qty) if qty and unit == "ml" else None,
            "price_per_kg": unit_prices["price_per_kg"],
            "price_per_l": unit_prices["price_per_liter"]
        }
        products.append(product)
    
    # Build cross-store groups - require 2+ DIFFERENT stores
    groups = {}
    for off_id, product_indices in groups_by_off_id.items():
        off_data = off_by_id.get(off_id, {})
        off_barcode = off_data.get("barcode")
        if not off_barcode:
            continue
        
        # Get DISTINCT stores
        stores = set()
        prices = []
        product_ids = []
        for idx in product_indices:
            p = products[idx]
            stores.add(p["store"])
            product_ids.append(p["id"])
            if p["price"]:
                prices.append(p["price"])
        
        # Only include if 2+ different stores
        if len(stores) >= 2:
            group_id = f"g_{hashlib.md5(off_barcode.encode()).hexdigest()[:8]}"
            groups[group_id] = {
                "off_barcode": off_barcode,
                "product_ids": product_ids,
                "stores": sorted(stores),
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None
            }
    
    # Sort products by discount (descending), then name
    products.sort(key=lambda p: (-p["discount_pct"], p["name"]))
    
    # Build output - removed "matched_products" stat per user request
    output = {
        "meta": {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_products": len(products),
            "cross_store_groups": len(groups),
            "stores": ["Kaufland", "Lidl", "Billa"]
        },
        "products": products,
        "off": off_lookup,
        "groups": groups
    }
    
    # Write to both locations
    for outfile in [OUTPUT_FILE, DOCS_OUTPUT]:
        print(f"Writing to {outfile}...")
        outfile.parent.mkdir(parents=True, exist_ok=True)
        with open(outfile, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    
    # Stats
    file_size = OUTPUT_FILE.stat().st_size
    print(f"\n=== Export Complete ===")
    print(f"Total distinct products: {len(products)}")
    print(f"Products with OFF match: {sum(1 for p in products if p['off_barcode'])}")
    print(f"Cross-store groups: {len(groups)}")
    print(f"File size: {file_size / 1024:.1f} KB")
    
    # Show discount distribution
    with_discount = [p for p in products if p["discount_pct"] > 0]
    print(f"\nProducts with valid discount: {len(with_discount)}")
    
    conn.close()
    off_conn.close()


if __name__ == "__main__":
    export_data()
