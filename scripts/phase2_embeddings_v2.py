"""
Phase 2 Embedding Matching v2 - Lower thresholds for more matches.
Uses pre-computed embeddings.
"""
import sqlite3
import numpy as np
import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent.parent
PROMOBG_DB = REPO / "data" / "promobg.db"
OFF_DB = REPO / "data" / "off_bulgaria.db"
OFF_EMBEDDINGS = REPO / "data" / "off_embeddings.npy"
OFF_IDS = REPO / "data" / "off_ids.json"

# Lower thresholds for more matches
THRESHOLD_CONFIDENT = 0.80  # Was 0.85
THRESHOLD_LIKELY = 0.70     # Was 0.75
THRESHOLD_LOW = 0.65        # New tier

def main():
    # Check embeddings exist
    if not OFF_EMBEDDINGS.exists():
        print("OFF embeddings not found. Run phase2_embeddings_fixed.py first.")
        return
    
    print("Loading pre-computed OFF embeddings...")
    off_embeddings = np.load(OFF_EMBEDDINGS)
    with open(OFF_IDS) as f:
        off_ids = json.load(f)
    print(f"  {len(off_ids)} OFF products")
    
    # Get unmatched products
    conn = sqlite3.connect(PROMOBG_DB)
    cur = conn.cursor()
    
    cur.execute("SELECT DISTINCT product_id FROM product_off_matches")
    matched_ids = {row[0] for row in cur.fetchall()}
    
    cur.execute("SELECT id, name FROM products")
    all_products = cur.fetchall()
    unmatched = [(pid, name) for pid, name in all_products if pid not in matched_ids]
    
    print(f"Unmatched products: {len(unmatched)}")
    
    if len(unmatched) == 0:
        print("No unmatched products!")
        return
    
    # Load model and compute embeddings
    print("Loading LaBSE model...")
    import os
    os.environ['TRANSFORMERS_CACHE'] = '/tmp/cache'
    os.environ['HF_HOME'] = '/tmp/hf_home'
    
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('sentence-transformers/LaBSE', cache_folder='/tmp/labse_cache')
    
    print("Computing unmatched product embeddings...")
    unmatched_names = [name for _, name in unmatched]
    unmatched_embeddings = model.encode(
        unmatched_names, 
        convert_to_numpy=True, 
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=64
    )
    
    # Find matches
    print(f"Finding matches (threshold >= {THRESHOLD_LOW})...")
    matches = []
    
    for i, (pid, name) in enumerate(unmatched):
        # Compute cosine similarity
        sims = np.dot(unmatched_embeddings[i], off_embeddings.T)
        max_idx = np.argmax(sims)
        max_sim = sims[max_idx]
        
        if max_sim >= THRESHOLD_LOW:
            off_id = off_ids[max_idx]
            
            if max_sim >= THRESHOLD_CONFIDENT:
                match_type = 'embedding_confident_v2'
            elif max_sim >= THRESHOLD_LIKELY:
                match_type = 'embedding_likely_v2'
            else:
                match_type = 'embedding_low_v2'
            
            matches.append({
                'product_id': pid,
                'off_product_id': off_id,
                'match_type': match_type,
                'match_confidence': float(max_sim)
            })
    
    print(f"\nFound {len(matches)} new matches:")
    confident = sum(1 for m in matches if m['match_type'] == 'embedding_confident_v2')
    likely = sum(1 for m in matches if m['match_type'] == 'embedding_likely_v2')
    low = sum(1 for m in matches if m['match_type'] == 'embedding_low_v2')
    print(f"  Confident (≥{THRESHOLD_CONFIDENT}): {confident}")
    print(f"  Likely (≥{THRESHOLD_LIKELY}): {likely}")
    print(f"  Low (≥{THRESHOLD_LOW}): {low}")
    
    if matches:
        # Save to database
        print("\nSaving to database...")
        for m in matches:
            cur.execute("""
                INSERT INTO product_off_matches 
                (product_id, off_product_id, match_type, match_confidence, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (m['product_id'], m['off_product_id'], m['match_type'], 
                  m['match_confidence'], datetime.now().isoformat()))
        
        conn.commit()
        print(f"Saved {len(matches)} matches")
        
        # Show samples
        print("\nSample matches:")
        for m in matches[:5]:
            cur.execute("SELECT name FROM products WHERE id=?", (m['product_id'],))
            prod_name = cur.fetchone()[0]
            print(f"  {prod_name[:40]}... ({m['match_type']}: {m['match_confidence']:.3f})")
    
    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
