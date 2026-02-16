#!/usr/bin/env python3
"""Phase 2 v3: Embedding-based matching with lower threshold"""
import numpy as np
import sqlite3
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import torch
import os

DATA_DIR = Path(__file__).parent.parent / 'data'
DB_PATH = DATA_DIR / 'promobg.db'
OFF_DB_PATH = DATA_DIR / 'off_bulgaria.db'

# Use persistent cache
CACHE_DIR = os.environ.get('SENTENCE_TRANSFORMERS_HOME', '/home/sandbox/.cache')

# Lower thresholds to catch more food matches
CONFIDENT_THRESHOLD = 0.85
LIKELY_THRESHOLD = 0.75  
LOW_THRESHOLD = 0.65     # New: catch more potential matches

BATCH_SIZE = 64

def get_unmatched_products():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.name FROM products p
        LEFT JOIN product_off_matches m ON p.id = m.product_id
        WHERE m.id IS NULL
    """)
    products = [{'id': row['id'], 'name': row['name']} for row in cursor.fetchall()]
    conn.close()
    return products

def get_off_products():
    conn = sqlite3.connect(OFF_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, product_name, product_name_bg FROM off_products")
    products = [{'id': row['id'], 'name': row['product_name'], 'name_bg': row['product_name_bg']} for row in cursor.fetchall()]
    conn.close()
    return products

def main():
    print("="*60)
    print("PHASE 2 v3: EMBEDDING-BASED MATCHING")
    print("="*60)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    print(f"Cache dir: {CACHE_DIR}")
    print("Loading LaBSE model...")
    model = SentenceTransformer('sentence-transformers/LaBSE', cache_folder=str(CACHE_DIR))
    print("Model loaded")
    
    # Get OFF products
    off_products = get_off_products()
    off_ids = [p['id'] for p in off_products]
    # Use Bulgarian name preferentially
    off_texts = [(p['name_bg'] or p['name'] or '').strip() for p in off_products]
    # Filter out empty/garbage entries
    valid_off = [(i, oid, txt) for i, (oid, txt) in enumerate(zip(off_ids, off_texts)) 
                 if txt and txt not in ('', 'Loading…', 'loading…')]
    print(f"Valid OFF products: {len(valid_off)} / {len(off_products)}")
    
    off_texts_clean = [txt for _, _, txt in valid_off]
    off_ids_clean = [oid for _, oid, _ in valid_off]
    
    print(f"Computing {len(off_texts_clean)} OFF embeddings...")
    off_embeddings = model.encode(off_texts_clean, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_numpy=True)
    
    # Get unmatched products
    unmatched = get_unmatched_products()
    print(f"\nUnmatched products: {len(unmatched)}")
    unmatched_ids = [p['id'] for p in unmatched]
    unmatched_texts = [p['name'].replace('\n', ' ').strip() for p in unmatched]
    
    print(f"Computing {len(unmatched_texts)} embeddings...")
    unmatched_embeddings = model.encode(unmatched_texts, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_numpy=True)
    
    print(f"\nComputing cosine similarities...")
    # Compute all similarities at once (faster than row-by-row)
    similarity_matrix = cosine_similarity(unmatched_embeddings, off_embeddings)
    
    print(f"\nFinding matches (threshold={LOW_THRESHOLD})...")
    matches = []
    for i, prod_id in enumerate(unmatched_ids):
        best_idx = np.argmax(similarity_matrix[i])
        best_score = similarity_matrix[i][best_idx]
        if best_score >= LOW_THRESHOLD:
            if best_score >= CONFIDENT_THRESHOLD:
                match_type = 'embedding_confident_v3'
            elif best_score >= LIKELY_THRESHOLD:
                match_type = 'embedding_likely_v3'
            else:
                match_type = 'embedding_low_v3'
            matches.append({
                'product_id': prod_id, 
                'off_id': off_ids_clean[best_idx], 
                'match_type': match_type, 
                'confidence': float(best_score),
                'promo_name': unmatched_texts[i],
                'off_name': off_texts_clean[best_idx]
            })
    
    confident = [m for m in matches if m['confidence'] >= CONFIDENT_THRESHOLD]
    likely = [m for m in matches if LIKELY_THRESHOLD <= m['confidence'] < CONFIDENT_THRESHOLD]
    low = [m for m in matches if LOW_THRESHOLD <= m['confidence'] < LIKELY_THRESHOLD]
    
    print(f"\nFound {len(matches)} matches:")
    print(f"  Confident (≥{CONFIDENT_THRESHOLD}): {len(confident)}")
    print(f"  Likely (≥{LIKELY_THRESHOLD}): {len(likely)}")
    print(f"  Low (≥{LOW_THRESHOLD}): {len(low)}")
    
    # Show sample matches
    if matches:
        print("\n=== Sample matches ===")
        for m in sorted(matches, key=lambda x: -x['confidence'])[:10]:
            print(f"{m['confidence']:.3f} [{m['match_type']}]")
            print(f"  Promo: {m['promo_name'][:50]}")
            print(f"  OFF:   {m['off_name'][:50]}")
    
    # Save to database
    print("\nSaving to database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    saved = 0
    for m in matches:
        try:
            cursor.execute(
                "INSERT INTO product_off_matches (product_id, off_product_id, match_type, match_confidence) VALUES (?, ?, ?, ?)",
                (m['product_id'], m['off_id'], m['match_type'], m['confidence'])
            )
            saved += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    print(f"Saved {saved} new matches")
    print("Done!")

if __name__ == '__main__':
    main()
