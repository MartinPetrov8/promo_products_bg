"""
PromoBG API - FastAPI backend for product search
"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import json
import os

app = FastAPI(
    title="PromoBG API",
    description="Bulgarian grocery price comparison API",
    version="0.1.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load product data
DATA_PATH = os.path.join(os.path.dirname(__file__), "../scraper/data/all_products.json")

def load_products():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

PRODUCTS = load_products()

@app.get("/")
def root():
    return {
        "name": "PromoBG API",
        "version": "0.1.0",
        "products": len(PRODUCTS)
    }

@app.get("/api/products")
def get_products(
    store: Optional[str] = None,
    min_discount: Optional[int] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0
):
    """Get products with optional filtering"""
    results = PRODUCTS
    
    if store:
        results = [p for p in results if p["store"].lower() == store.lower()]
    
    if min_discount:
        results = [p for p in results if (p.get("discount_pct") or 0) >= min_discount]
    
    # Sort by discount (highest first)
    results = sorted(results, key=lambda x: x.get("discount_pct") or 0, reverse=True)
    
    total = len(results)
    results = results[offset:offset + limit]
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": results
    }

@app.get("/api/products/search")
def search_products(
    q: str = Query(..., min_length=2),
    store: Optional[str] = None,
    limit: int = Query(default=50, le=200)
):
    """Search products by name"""
    query = q.lower()
    
    results = []
    for p in PRODUCTS:
        name = p["name"].lower()
        if query in name:
            if store and p["store"].lower() != store.lower():
                continue
            results.append(p)
    
    # Sort by relevance (exact match first, then by discount)
    def relevance(p):
        name = p["name"].lower()
        if name.startswith(query):
            return (0, -(p.get("discount_pct") or 0))
        return (1, -(p.get("discount_pct") or 0))
    
    results = sorted(results, key=relevance)[:limit]
    
    return {
        "query": q,
        "total": len(results),
        "products": results
    }

@app.get("/api/stores")
def get_stores():
    """Get list of stores with product counts"""
    stores = {}
    for p in PRODUCTS:
        store = p["store"]
        if store not in stores:
            stores[store] = {"name": store, "count": 0, "with_discount": 0}
        stores[store]["count"] += 1
        if p.get("discount_pct"):
            stores[store]["with_discount"] += 1
    
    return {"stores": list(stores.values())}

@app.get("/api/deals")
def get_best_deals(limit: int = Query(default=20, le=100)):
    """Get products with highest discounts"""
    with_discount = [p for p in PRODUCTS if p.get("discount_pct")]
    sorted_deals = sorted(with_discount, key=lambda x: x["discount_pct"], reverse=True)
    return {"deals": sorted_deals[:limit]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
