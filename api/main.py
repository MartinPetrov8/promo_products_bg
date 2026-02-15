"""
PromoBG API - Price Comparison Endpoints
Serves data directly from SQLite database.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json

app = FastAPI(title="PromoBG API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent.parent / "data" / "promobg.db"
HTML_PATH = Path(__file__).parent


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
async def root():
    return FileResponse(HTML_PATH / "compare.html")


@app.get("/api/stats")
async def get_stats():
    """Get overall statistics."""
    conn = get_db()
    cur = conn.cursor()
    
    # Total products
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    
    # Products by store
    cur.execute("""
        SELECT s.name, COUNT(*) 
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        GROUP BY s.name
    """)
    by_store = {row[0]: row[1] for row in cur.fetchall()}
    
    # Brand coverage
    cur.execute("""
        SELECT 
            SUM(CASE WHEN brand IS NOT NULL AND brand != '' AND brand != 'NO_BRAND' THEN 1 ELSE 0 END) as branded,
            SUM(CASE WHEN brand = 'NO_BRAND' THEN 1 ELSE 0 END) as no_brand,
            COUNT(*) as total
        FROM products
    """)
    row = cur.fetchone()
    
    conn.close()
    
    return {
        "total_products": total_products,
        "by_store": by_store,
        "branded": row[0],
        "no_brand": row[1],
        "brand_coverage_pct": round((row[0] / row[2]) * 100, 1) if row[2] > 0 else 0
    }


@app.get("/api/products")
async def get_products(
    store: Optional[str] = None,
    brand: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500)
):
    """Get products with optional filters."""
    conn = get_db()
    cur = conn.cursor()
    
    query = """
        SELECT p.id, p.name, p.brand, s.name as store, pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE 1=1
    """
    params = []
    
    if store:
        query += " AND s.name = ?"
        params.append(store)
    if brand:
        query += " AND LOWER(p.brand) = LOWER(?)"
        params.append(brand)
    if search:
        query += " AND LOWER(p.name) LIKE ?"
        params.append(f"%{search.lower()}%")
    
    query += f" LIMIT {limit}"
    
    cur.execute(query, params)
    products = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return products


@app.get("/api/brands")
async def get_brands(multi_store: bool = False):
    """Get all brands, optionally only those in multiple stores."""
    conn = get_db()
    cur = conn.cursor()
    
    if multi_store:
        cur.execute("""
            SELECT LOWER(p.brand) as brand, GROUP_CONCAT(DISTINCT s.name) as stores, COUNT(*) as count
            FROM products p
            JOIN store_products sp ON p.id = sp.product_id
            JOIN stores s ON sp.store_id = s.id
            WHERE p.brand IS NOT NULL AND p.brand != '' AND p.brand != 'NO_BRAND'
            GROUP BY LOWER(p.brand)
            HAVING COUNT(DISTINCT s.name) >= 2
            ORDER BY count DESC
        """)
    else:
        cur.execute("""
            SELECT LOWER(p.brand) as brand, COUNT(*) as count
            FROM products p
            WHERE p.brand IS NOT NULL AND p.brand != '' AND p.brand != 'NO_BRAND'
            GROUP BY LOWER(p.brand)
            ORDER BY count DESC
        """)
    
    brands = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return brands


@app.get("/api/matches")
async def get_matches(min_savings: float = 0):
    """
    Get cross-store price comparisons.
    Finds same brand+similar products across stores with price differences.
    """
    conn = get_db()
    cur = conn.cursor()
    
    # Get brands that appear in multiple stores with prices
    cur.execute("""
        SELECT LOWER(p.brand) as brand
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        JOIN prices pr ON pr.store_product_id = sp.id
        WHERE p.brand IS NOT NULL AND p.brand != '' AND p.brand != 'NO_BRAND'
        AND pr.current_price IS NOT NULL AND pr.current_price > 0
        GROUP BY LOWER(p.brand)
        HAVING COUNT(DISTINCT s.name) >= 2
    """)
    multi_store_brands = [row[0] for row in cur.fetchall()]
    
    matches = []
    
    for brand in multi_store_brands:
        # Get all products for this brand with prices
        cur.execute("""
            SELECT p.id, p.name, p.brand, s.name as store, pr.current_price as price
            FROM products p
            JOIN store_products sp ON p.id = sp.product_id
            JOIN stores s ON sp.store_id = s.id
            JOIN prices pr ON pr.store_product_id = sp.id
            WHERE LOWER(p.brand) = ?
            AND pr.current_price IS NOT NULL AND pr.current_price > 0
            ORDER BY s.name
        """, (brand,))
        
        products = [dict(row) for row in cur.fetchall()]
        
        if len(products) < 2:
            continue
        
        # Group by store
        by_store = {}
        for p in products:
            store = p['store']
            if store not in by_store:
                by_store[store] = []
            by_store[store].append(p)
        
        if len(by_store) < 2:
            continue
        
        # Find best price per store (lowest)
        store_prices = []
        for store, prods in by_store.items():
            best = min(prods, key=lambda x: x['price'])
            store_prices.append({
                'store': store,
                'price': best['price'],
                'name': best['name']
            })
        
        prices = [s['price'] for s in store_prices]
        min_price = min(prices)
        max_price = max(prices)
        savings = round(max_price - min_price, 2)
        
        if savings >= min_savings:
            # Use shortest product name as display name
            names = [s['name'].split('\n')[0] for s in store_prices]
            display_name = min(names, key=len)
            
            matches.append({
                'name': display_name,
                'brand': brand.title(),
                'stores': store_prices,
                'store_count': len(store_prices),
                'min_price': min_price,
                'max_price': max_price,
                'savings': savings,
                'savings_pct': round((savings / max_price) * 100, 1) if max_price > 0 else 0,
                'confidence': 0.9
            })
    
    # Sort by savings
    matches.sort(key=lambda x: x['savings'], reverse=True)
    
    conn.close()
    
    return {
        'count': len(matches),
        'matches': matches
    }


@app.get("/api/compare/{brand}")
async def compare_brand(brand: str):
    """Compare prices for a specific brand across stores."""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.id, p.name, p.brand, s.name as store, pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE LOWER(p.brand) = LOWER(?)
        ORDER BY pr.current_price
    """, (brand,))
    
    products = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return {
        'brand': brand,
        'count': len(products),
        'products': products
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
