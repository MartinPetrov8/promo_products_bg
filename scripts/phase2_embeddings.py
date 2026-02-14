#!/usr/bin/env python3
"""
Phase 2: Embedding-based semantic matching
Uses LaBSE multilingual embeddings for Bulgarian↔English matching
"""
import sqlite3
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
import torch

BASE_DIR = Path(__file__).parent.parent / "data"
EMBEDDINGS_CACHE = BASE_DIR / "off_embeddings.npy"
OFF_IDS_CACHE = BASE_DIR / "off_ids.json"

CONFIDENT_THRESHOLD = 0.85
LIKELY_THRESHOLD = 0.75
MIN_THRESHOLD = 0.75  # Don't accept below this

def main():
    print("=" * 60)
    print("PHASE 2: EMBEDDING-BASED MATCHING")
    print("=" * 60)
    
    # Check for GPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    
    # Load model
    print("Loading LaBSE model (this may take a minute)...")
    model = SentenceTransformer('sentence-transformers/LaBSE', device=device)
    print("Model loaded ✓")
    
    prom_conn = sqlite3.connect(BASE_DIR / "promobg.db")
    off_conn = sqlite3.connect(BASE_DIR / "off_bulgaria.db")
    
    # Load or compute OFF embeddings
    if EMBEDDINGS_CACHE.exists() and OFF_IDS_CACHE.exists():
        print("Loading cached OFF embeddings...")
        off_embeddings = np.load(EMBEDDINGS_CACHE)
        with open(OFF_IDS_CACHE) as f:
            off_ids = json.load(f)
        print(f"Loaded {len(off_ids)} cached embeddings")
    else:
        print("Computing OFF embeddings (one-time)...")
        off_cur = off_conn.cursor()
        off_cur.execute('SELECT id, product_name, product_name_bg, brands FROM off_products')
        
        off_ids = []
        off_texts = []
        
        for row in off_cur.fetchall():
            off_id = row[0]
            # Combine name fields
            text = " ".join(filter(None, [row[1], row[2], row[3]]))
            if text.strip():
                off_ids.append(off_id)
                off_texts.append(text[:256])  # Truncate long texts
        
        print(f"Encoding {len(off_texts)} OFF products...")
        off_embeddings = model.encode(off_texts, show_progress_bar=True, batch_size=64)
        
        # Cache
        np.save(EMBEDDINGS_CACHE, off_embeddings)
        with open(OFF_IDS_CACHE, 'w') as f:
            json.dump(off_ids, f)
        print("Cached embeddings for future use")
    
    # Load OFF product details
    off_cur = off_conn.cursor()
    off_products = {}
    for off_id in off_ids:
        off_cur.execute('SELECT product_name, product_name_bg FROM off_products WHERE id = ?', (off_id,))
        row = off_cur.fetchone()
        if row:
            off_products[off_id] = {'name': row[0], 'name_bg': row[1]}
    
    # Load unmatched products
    cur = prom_conn.cursor()
    cur.execute('''
        SELECT p.id, p.name, p.brand
        FROM products p
        WHERE p.id NOT IN (SELECT product_id FROM product_off_matches)
    ''')
    unmatched = [{'id': r[0], 'name': r[1], 'brand': r[2]} for r in cur.fetchall()]
    print(f"\nUnmatched products to process: {len(unmatched)}")
    
    if not unmatched:
        print("No unmatched products remaining!")
        return 0
    
    # Encode unmatched products
    print("Encoding unmatched products...")
    unmatched_texts = [p['name'][:256] for p in unmatched]
    unmatched_embeddings = model.encode(unmatched_texts, show_progress_bar=True, batch_size=32)
    
    # Find best matches using cosine similarity
    print("Finding best matches...")
    
    # Normalize for cosine similarity
    off_embeddings_norm = off_embeddings / np.linalg.norm(off_embeddings, axis=1, keepdims=True)
    unmatched_embeddings_norm = unmatched_embeddings / np.linalg.norm(unmatched_embeddings, axis=1, keepdims=True)
    
    matches = []
    
    for i, prod in enumerate(unmatched):
        if (i + 1) % 100 == 0:
            print(f"Processing {i+1}/{len(unmatched)}...")
        
        # Compute similarities
        similarities = np.dot(off_embeddings_norm, unmatched_embeddings_norm[i])
        
        # Get best match
        best_idx = np.argmax(similarities)
        best_sim = similarities[best_idx]
        
        if best_sim >= MIN_THRESHOLD:
            off_id = off_ids[best_idx]
            off_prod = off_products.get(off_id, {})
            
            matches.append({
                'product_id': prod['id'],
                'product_name': prod['name'],
                'off_id': off_id,
                'off_name': off_prod.get('name') or off_prod.get('name_bg', ''),
                'confidence': float(best_sim)
            })
    
    # Results
    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"New matches found: {len(matches)}")
    
    confident = [m for m in matches if m['confidence'] >= CONFIDENT_THRESHOLD]
    likely = [m for m in matches if LIKELY_THRESHOLD <= m['confidence'] < CONFIDENT_THRESHOLD]
    
    print(f"  Confident (≥0.85): {len(confident)}")
    print(f"  Likely (0.75-0.84): {len(likely)}")
    
    # Sample matches
    print("\nSample confident matches:")
    for m in sorted(confident, key=lambda x: -x['confidence'])[:5]:
        off_name = m.get('off_name', '') or ''; print(f"  [{m['confidence']:.2f}] '{m['product_name'][:30]}' → '{off_name[:30]}'")
    
    print("\nSample likely matches:")
    for m in sorted(likely, key=lambda x: -x['confidence'])[:5]:
        off_name = m.get('off_name', '') or ''; print(f"  [{m['confidence']:.2f}] '{m['product_name'][:30]}' → '{off_name[:30]}'")
    
    # Save matches
    print("\nSaving matches...")
    saved = 0
    for m in matches:
        match_type = 'embed_confident' if m['confidence'] >= CONFIDENT_THRESHOLD else 'embed_likely'
        try:
            cur.execute('''
                INSERT INTO product_off_matches 
                (product_id, off_product_id, match_type, match_confidence, is_verified, created_at)
                VALUES (?, ?, ?, ?, 0, datetime('now'))
            ''', (m['product_id'], m['off_id'], match_type, m['confidence']))
            saved += 1
        except sqlite3.IntegrityError:
            pass
    
    prom_conn.commit()
    
    # Export results
    with open(BASE_DIR / "phase2_results.json", 'w') as f:
        json.dump({
            'total_unmatched': len(unmatched),
            'new_matches': len(matches),
            'confident': len(confident),
            'likely': len(likely),
            'matches': matches
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Phase 2 complete. Added {saved} matches.")
    return saved

if __name__ == '__main__':
    main()
