#!/usr/bin/env python3
"""Phase 2: Embedding-based matching using LaBSE model"""
import json
import numpy as np
import sqlite3
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import torch

DATA_DIR = Path(__file__).parent.parent / 'data'
DB_PATH = DATA_DIR / 'promobg.db'
OFF_DB_PATH = DATA_DIR / 'off_bulgaria.db'
CACHE_DIR = Path('/tmp/hf_cache')
SIMILARITY_THRESHOLD = 0.75
CONFIDENT_THRESHOLD = 0.85
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
    print("PHASE 2: EMBEDDING-BASED MATCHING")
    print("="*60)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    print("Loading LaBSE model...")
    model = SentenceTransformer('sentence-transformers/LaBSE', cache_folder=str(CACHE_DIR))
    print("Model loaded")
    
    off_products = get_off_products()
    off_ids = [p['id'] for p in off_products]
    off_texts = [(p['name'] or '') + ' ' + (p['name_bg'] or '') for p in off_products]
    print(f"Computing {len(off_texts)} OFF embeddings...")
    off_embeddings = model.encode(off_texts, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_numpy=True)
    
    unmatched = get_unmatched_products()
    print(f"\nUnmatched products: {len(unmatched)}")
    unmatched_ids = [p['id'] for p in unmatched]
    unmatched_texts = [p['name'] for p in unmatched]
    print(f"Computing {len(unmatched_texts)} embeddings...")
    unmatched_embeddings = model.encode(unmatched_texts, batch_size=BATCH_SIZE, show_progress_bar=True, convert_to_numpy=True)
    
    print(f"\nFinding matches (threshold={SIMILARITY_THRESHOLD})...")
    matches = []
    for i, prod_id in enumerate(unmatched_ids):
        product_emb = unmatched_embeddings[i].reshape(1, -1)
        similarities = cosine_similarity(product_emb, off_embeddings)[0]
        best_idx = np.argmax(similarities)
        best_score = similarities[best_idx]
        if best_score >= SIMILARITY_THRESHOLD:
            match_type = 'embedding_confident' if best_score >= CONFIDENT_THRESHOLD else 'embedding_likely'
            matches.append({'product_id': prod_id, 'off_id': off_ids[best_idx], 'match_type': match_type, 'confidence': float(best_score)})
    
    print(f"Found {len(matches)} matches")
    confident = [m for m in matches if m['confidence'] >= CONFIDENT_THRESHOLD]
    likely = [m for m in matches if SIMILARITY_THRESHOLD <= m['confidence'] < CONFIDENT_THRESHOLD]
    print(f"  Confident: {len(confident)}, Likely: {len(likely)}")
    
    # Save to database FIRST
    print("Saving to database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    saved = 0
    for m in matches:
        try:
            cursor.execute("INSERT INTO product_off_matches (product_id, off_product_id, match_type, match_confidence) VALUES (?, ?, ?, ?)",
                          (m['product_id'], m['off_id'], m['match_type'], m['confidence']))
            saved += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    print(f"Saved {saved} matches")
    print("Done!")

if __name__ == '__main__':
    main()
