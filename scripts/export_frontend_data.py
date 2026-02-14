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
OUTPUT_FILE = REPO_ROOT / "docs" / "data" / "products.json"


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
    off_lookup = {}
    
    for row in cur.fetchall():
        unit_prices = get_unit_prices(row["name"], row["current_price"] or 0)
        qty, unit = parse_quantity(row["name"])
        
        # Get OFF barcode if matched
        off_barcode = None
        off_id = None
        if row["off_product_id"] and row["off_product_id"] in off_by_id:
            off_data = off_by_id[row["off_product_id"]]
            off_barcode = off_data["barcode"]
            off_id = row["off_product_id"]
            
            if off_barcode and off_barcode not in off_lookup:
                off_lookup[off_barcode] = {
                    "name": off_data["name"],
                    "brand": off_data["brand"],
                    "nutriscore": off_data["nutriscore"],
                    "categories": off_data["categories"],
                    "ingredients": off_data["ingredients"]
                }
        
        group_id = None
        if off_barcode:
            group_id = f"g_{hashlib.md5(off_barcode.encode()).hexdigest()[:8]}"
        
        # === DATA VALIDATION ===
        old_price = row["old_price"]
        current_price = row["current_price"]
        discount_pct = row["discount_percent"] or 0
        
        # Rule 1: If old_price > 5x current, it's garbage
        if old_price and current_price and old_price > current_price * 3:
            old_price = None
            discount_pct = 0
        
        # Rule 2: If no old_price, discount must be 0
        if not old_price:
            discount_pct = 0
        
        # Rule 3: Cap max discount at 70% (higher = garbage)
        if discount_pct > 70:
            old_price = None
            discount_pct = 0
        
        product = {
            "id": row["id"],
            "name": row["name"],
            "store": row["store_name"],
            "price": round(current_price, 2) if current_price else None,
            "old_price": round(old_price, 2) if old_price else None,
            "discount_pct": int(discount_pct),
            "image_url": row["image_url"],
            "off_barcode": off_barcode,
            "off_id": off_id,
            "group_id": group_id,
            "match_type": row["match_type"],
            "match_confidence": round(row["match_confidence"], 2) if row["match_confidence"] else None,
            "quantity_g": int(qty) if unit == "g" else None,
            "quantity_ml": int(qty) if unit == "ml" else None,
            "price_per_kg": unit_prices["price_per_kg"],
            "price_per_l": unit_prices["price_per_liter"]
        }
        products.append(product)
    
    # Deduplicate: keep only best match per store per group_id
    print("Deduplicating same-store products in groups...")
    seen = {}
    deduped = []
    
    for p in products:
        if not p["group_id"]:
            deduped.append(p)
            continue
        
        key = (p["store"], p["group_id"])
        if key not in seen:
            seen[key] = p
            deduped.append(p)
        else:
            existing = seen[key]
            if (p["match_confidence"] or 0) > (existing["match_confidence"] or 0):
                deduped.remove(existing)
                seen[key] = p
                deduped.append(p)
    
    print(f"  Kept {len(deduped)} products (removed {len(products) - len(deduped)} duplicates)")
    products = deduped
    
    # Build cross-store groups
    print("Building cross-store groups...")
    groups_by_id = {}
    
    for p in products:
        if p["group_id"]:
            if p["group_id"] not in groups_by_id:
                groups_by_id[p["group_id"]] = []
            groups_by_id[p["group_id"]].append(p)
    
    groups = {}
    for group_id, group_products in groups_by_id.items():
        stores = set(p["store"] for p in group_products)
        
        if len(stores) >= 2:
            prices = [p["price"] for p in group_products if p["price"]]
            off_barcode = group_products[0]["off_barcode"]
            
            groups[group_id] = {
                "off_barcode": off_barcode,
                "product_ids": [p["id"] for p in group_products],
                "stores": sorted(stores),
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None
            }
    
    # Remove internal off_id field
    for p in products:
        p.pop("off_id", None)
    
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
    
    print(f"Writing to {OUTPUT_FILE}...")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
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
