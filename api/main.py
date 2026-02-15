"""
PromoBG API - Price Comparison Endpoints
"""

import sqlite3
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="PromoBG API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent.parent / "data" / "promobg.db"
HTML_PATH = Path(__file__).parent / "index.html"


class StorePrice(BaseModel):
    store: str
    price: float
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price_per_unit: Optional[float] = None
    product_name: str


class MatchedProduct(BaseModel):
    match_id: int
    canonical_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    match_type: str
    confidence: float
    prices: List[StorePrice]
    best_value: Optional[str] = None
    savings_percent: Optional[float] = None


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/", response_class=HTMLResponse)
def root():
    return HTML_PATH.read_text()


@app.get("/matches", response_model=List[MatchedProduct])
def get_matches(
    category: Optional[str] = Query(None),
    min_confidence: float = Query(0.9),
    limit: int = Query(50, le=200),
):
    conn = get_db()
    cur = conn.cursor()
    
    query = """
        SELECT id, canonical_name, canonical_brand, category_code,
               match_type, confidence, kaufland_product_id, lidl_product_id, billa_product_id
        FROM cross_store_matches
        WHERE confidence >= ?
    """
    params = [min_confidence]
    
    if category:
        query += " AND category_code = ?"
        params.append(category)
    
    query += " ORDER BY confidence DESC LIMIT ?"
    params.append(limit)
    
    matches = cur.execute(query, params).fetchall()
    results = []
    
    for match in matches:
        prices = []
        best_ppu = None
        best_store = None
        
        for store, pid_col in [('Kaufland', 'kaufland_product_id'), 
                                ('Lidl', 'lidl_product_id'), 
                                ('Billa', 'billa_product_id')]:
            pid = match[pid_col]
            if not pid:
                continue
            
            row = cur.execute("""
                SELECT p.name, p.quantity, p.unit, pr.current_price, pr.price_per_unit
                FROM products p
                JOIN store_products sp ON p.id = sp.product_id
                JOIN stores s ON sp.store_id = s.id
                JOIN prices pr ON sp.id = pr.store_product_id
                WHERE p.id = ? AND s.name = ? AND sp.deleted_at IS NULL
            """, (pid, store)).fetchone()
            
            if row and row['current_price']:
                # Skip obviously wrong Lidl prices
                if row['current_price'] > 100 and store == 'Lidl':
                    continue
                
                qty = row['quantity']
                ppu = row['price_per_unit']
                if not ppu and qty and qty > 0:
                    ppu = row['current_price'] / qty
                
                prices.append(StorePrice(
                    store=store,
                    price=row['current_price'],
                    quantity=qty,
                    unit=row['unit'],
                    price_per_unit=ppu,
                    product_name=row['name'][:60] if row['name'] else ''
                ))
                
                if ppu and (best_ppu is None or ppu < best_ppu):
                    best_ppu = ppu
                    best_store = store
        
        savings = None
        if len(prices) >= 2 and best_ppu:
            ppus = [p.price_per_unit for p in prices if p.price_per_unit]
            if len(ppus) >= 2:
                worst_ppu = max(ppus)
                savings = (worst_ppu - best_ppu) / worst_ppu * 100
        
        if len(prices) >= 2:
            results.append(MatchedProduct(
                match_id=match['id'],
                canonical_name=match['canonical_name'],
                brand=match['canonical_brand'],
                category=match['category_code'],
                match_type=match['match_type'],
                confidence=match['confidence'],
                prices=prices,
                best_value=best_store,
                savings_percent=round(savings, 1) if savings else None
            ))
    
    conn.close()
    return results


@app.get("/categories")
def get_categories():
    conn = get_db()
    rows = conn.execute("""
        SELECT category_code, COUNT(*) as cnt
        FROM cross_store_matches
        WHERE category_code IS NOT NULL AND category_code != '99000000'
        GROUP BY category_code ORDER BY cnt DESC
    """).fetchall()
    conn.close()
    return [{"code": r[0], "matches": r[1]} for r in rows]


@app.get("/stats")
def get_stats():
    conn = get_db()
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_matches = conn.execute("SELECT COUNT(*) FROM cross_store_matches").fetchone()[0]
    by_type = conn.execute("""
        SELECT match_type, COUNT(*), AVG(confidence)
        FROM cross_store_matches GROUP BY match_type
    """).fetchall()
    conn.close()
    return {
        "total_products": total_products,
        "total_matches": total_matches,
        "by_type": {r[0]: {"count": r[1], "avg_confidence": round(r[2], 3)} for r in by_type}
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
