"""
Export frontend data from SQLite to JSON for GitHub Pages.
Generates products.json with OFF data and cross-store groups.
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
            "ingredients": row[6][:200] if row[6] else None  # Truncate ingredients
        }
    return off_by_id


def export_data():
    """Main export function."""
    print("Connecting to databases...")
    conn = sqlite3.connect(PROMOBG_DB)
    off_conn = sqlite3.connect(OFF_DB)
    conn.row_factory = sqlite3.Row
    
    # Load OFF data
    print("Loading OFF data...")
    off_by_id = get_off_data(off_conn)
    
    # Query products with prices and matches
    print("Querying products...")
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand, p.image_url, p.barcode_ean,
            s.name as store_name,
            pr.current_price, pr.old_price, pr.discount_percent,
            pom.off_product_id, pom.match_type, pom.match_confidence
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        JOIN prices pr ON sp.id = pr.store_product_id
        LEFT JOIN product_off_matches pom ON p.id = pom.product_id
        WHERE pr.current_price IS NOT NULL
        ORDER BY pr.discount_percent DESC NULLS LAST
    """)
    
    products = []
    off_lookup = {}  # barcode -> OFF data
    groups_by_off_id = {}  # off_product_id -> list of product indices
    
    for row in cur.fetchall():
        # Parse unit prices
        unit_prices = get_unit_prices(row["name"], row["current_price"] or 0)
        qty, unit = parse_quantity(row["name"])
        
        # Get OFF barcode if matched
        off_barcode = None
        if row["off_product_id"] and row["off_product_id"] in off_by_id:
            off_data = off_by_id[row["off_product_id"]]
            off_barcode = off_data["barcode"]
            
            # Add to OFF lookup (dedupe by barcode)
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
        
        # Generate group_id from OFF barcode
        group_id = None
        if off_barcode:
            group_id = f"g_{hashlib.md5(off_barcode.encode()).hexdigest()[:8]}"
        
        product = {
            "id": row["id"],
            "name": row["name"],
            "store": row["store_name"],
            "price": round(row["current_price"], 2) if row["current_price"] else None,
            "old_price": round(row["old_price"], 2) if row["old_price"] else None,
            "discount_pct": int(row["discount_percent"]) if row["discount_percent"] else 0,
            "image_url": row["image_url"],
            "off_barcode": off_barcode,
            "group_id": group_id,
            "match_type": row["match_type"],
            "match_confidence": round(row["match_confidence"], 2) if row["match_confidence"] else None,
            "quantity_g": int(qty) if unit == "g" else None,
            "quantity_ml": int(qty) if unit == "ml" else None,
            "price_per_kg": unit_prices["price_per_kg"],
            "price_per_l": unit_prices["price_per_liter"]
        }
        products.append(product)
    
    # Build cross-store groups (only where 2+ stores have the product)
    groups = {}
    for off_id, product_indices in groups_by_off_id.items():
        if len(product_indices) < 2:
            continue
        
        off_data = off_by_id.get(off_id, {})
        off_barcode = off_data.get("barcode")
        if not off_barcode:
            continue
        
        group_id = f"g_{hashlib.md5(off_barcode.encode()).hexdigest()[:8]}"
        
        # Get stores and prices for this group
        stores = set()
        prices = []
        product_ids = []
        for idx in product_indices:
            p = products[idx]
            stores.add(p["store"])
            product_ids.append(p["id"])
            if p["price"]:
                prices.append(p["price"])
        
        if len(stores) >= 2:  # Cross-store comparison
            groups[group_id] = {
                "off_barcode": off_barcode,
                "product_ids": product_ids,
                "stores": sorted(stores),
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None
            }
    
    # Build output
    output = {
        "meta": {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_products": len(products),
            "matched_products": sum(1 for p in products if p["off_barcode"]),
            "cross_store_groups": len(groups),
            "stores": ["Kaufland", "Lidl", "Billa"]
        },
        "products": products,
        "off": off_lookup,
        "groups": groups
    }
    
    # Write output
    print(f"Writing to {OUTPUT_FILE}...")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # Stats
    file_size = OUTPUT_FILE.stat().st_size
    print(f"\n=== Export Complete ===")
    print(f"Total products: {len(products)}")
    print(f"Matched products: {output['meta']['matched_products']}")
    print(f"OFF entries: {len(off_lookup)}")
    print(f"Cross-store groups: {len(groups)}")
    print(f"File size: {file_size / 1024:.1f} KB")
    
    conn.close()
    off_conn.close()


if __name__ == "__main__":
    export_data()
