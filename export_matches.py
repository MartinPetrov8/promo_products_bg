#!/usr/bin/env python3
"""
Export cross-store matches to frontend JSON.
Format matches what compare.html expects.
"""

import sqlite3
import json
from sentence_transformers import SentenceTransformer
import numpy as np
from collections import defaultdict
import os
import re

DB_PATH = 'data/promobg.db'
OUTPUT_PATH = 'api/matches.json'
MODEL_CACHE = os.environ.get('TRANSFORMERS_CACHE', '/host-workspace/.model-cache')
THRESHOLD = 0.82

def normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[®™©]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def main():
    print("Loading products from database...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Load all products with prices - ONLY those with valid prices
    cur.execute("""
        SELECT 
            p.id, p.name, p.normalized_name, p.brand,
            s.name as store,
            pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE (p.brand != 'NO_BRAND' OR p.brand IS NULL)
        AND pr.current_price IS NOT NULL
        AND pr.current_price > 0
    """)
    
    products = []
    by_store = defaultdict(list)
    for row in cur.fetchall():
        prod = dict(row)
        prod['norm'] = normalize(prod['name'])
        products.append(prod)
        by_store[prod['store']].append(prod)
    
    print(f"Loaded {len(products)} products with prices from {len(by_store)} stores")
    for store, prods in by_store.items():
        print(f"  {store}: {len(prods)}")
    
    # Load embedding model
    print("\nLoading embedding model...")
    os.environ['TRANSFORMERS_CACHE'] = MODEL_CACHE
    os.environ['HF_HOME'] = MODEL_CACHE
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', cache_folder=MODEL_CACHE)
    
    # Compute all embeddings upfront
    print("\nComputing embeddings...")
    texts = [p['name'] for p in products]
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    for i, p in enumerate(products):
        p['embedding'] = embeddings[i]
    
    # Group by brand for brand-aware matching
    by_brand = defaultdict(list)
    for p in products:
        brand = (p['brand'] or '').lower()
        if brand:
            by_brand[brand].append(p)
    
    print(f"\nMatching across {len(by_brand)} brands...")
    
    matches = []
    matched_ids = set()
    
    # For each brand, find cross-store matches
    for brand, brand_prods in by_brand.items():
        stores_in_brand = set(p['store'] for p in brand_prods)
        if len(stores_in_brand) < 2:
            continue
        
        n = len(brand_prods)
        used = set()
        
        for i in range(n):
            if i in used:
                continue
                
            cluster = [brand_prods[i]]
            cluster_stores = {brand_prods[i]['store']}
            
            for j in range(i+1, n):
                if j in used:
                    continue
                if brand_prods[j]['store'] in cluster_stores:
                    continue
                
                sim = np.dot(brand_prods[i]['embedding'], brand_prods[j]['embedding']) / (
                    np.linalg.norm(brand_prods[i]['embedding']) * np.linalg.norm(brand_prods[j]['embedding'])
                )
                
                if sim >= THRESHOLD:
                    cluster.append(brand_prods[j])
                    cluster_stores.add(brand_prods[j]['store'])
                    used.add(j)
            
            if len(cluster_stores) >= 2:
                matches.append({
                    'products': cluster,
                    'brand': brand,
                    'confidence': 0.9
                })
                for p in cluster:
                    matched_ids.add(p['id'])
                used.add(i)
    
    print(f"  Found {len(matches)} brand-based matches")
    
    # Export to JSON - format for compare.html
    print(f"\nExporting to {OUTPUT_PATH}...")
    
    output = []
    for m in matches:
        # Get best name (shortest clean one)
        names = [p['name'].split('\n')[0] for p in m['products']]
        best_name = min(names, key=len) if names else m['brand']
        
        # Build stores array for frontend
        stores_data = []
        for p in m['products']:
            stores_data.append({
                'store': p['store'],
                'price': float(p['price']),
                'name': p['name']
            })
        
        prices = [s['price'] for s in stores_data]
        min_price = min(prices)
        max_price = max(prices)
        savings = round(max_price - min_price, 2)
        
        entry = {
            'id': len(output) + 1,
            'name': best_name,
            'brand': m['brand'].title() if m.get('brand') else None,
            'stores': stores_data,  # What compare.html expects
            'store_count': len(stores_data),
            'confidence': m['confidence'],
            'min_price': min_price,
            'max_price': max_price,
            'savings': savings,
            'savings_pct': round((savings / max_price) * 100, 1) if max_price > 0 else 0
        }
        
        output.append(entry)
    
    # Sort by savings
    output.sort(key=lambda x: x.get('savings', 0), reverse=True)
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Exported {len(output)} matches")
    if output:
        print(f"   Top savings: {output[0].get('savings', 0):.2f} лв ({output[0].get('brand', 'N/A')})")
        print(f"   Avg savings: {sum(m.get('savings', 0) for m in output) / len(output):.2f} лв")
    
    conn.close()

if __name__ == '__main__':
    main()
