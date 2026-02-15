"""
Cross-Store Product Matching Pipeline v2
=========================================
With category filtering to prevent garbage matches.

Improvements over v1:
- Category classification layer
- Higher threshold (0.90)
- Bidirectional matching requirement
- Better stats tracking

Author: Cookie
Date: 2026-02-15
"""

import sqlite3
import re
from collections import defaultdict
from datetime import datetime
from category_classifier import classify_product, categories_compatible, get_category_display

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False
    print("Warning: sentence_transformers not available")


class CrossStoreMatcherV2:
    """Matches products across multiple stores with category filtering."""
    
    STORES = ['Kaufland', 'Lidl', 'Billa']
    STORE_COLS = ['kaufland_product_id', 'lidl_product_id', 'billa_product_id']
    
    # Matching thresholds
    EMBEDDING_THRESHOLD = 0.90  # Raised from 0.85
    PRICE_RATIO_MAX = 3.0  # Max price difference ratio
    
    def __init__(self, db_path: str, model_cache: str = None):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.model_cache = model_cache
        self.model = None
        self.stats = defaultdict(int)
        
    def setup_schema(self):
        """Create/recreate cross_store_matches table."""
        cur = self.conn.cursor()
        cur.execute("DROP TABLE IF EXISTS cross_store_matches")
        
        cur.execute("""
            CREATE TABLE cross_store_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kaufland_product_id INTEGER,
                lidl_product_id INTEGER,
                billa_product_id INTEGER,
                canonical_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                category TEXT,
                match_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("CREATE INDEX idx_csm_kaufland ON cross_store_matches(kaufland_product_id)")
        cur.execute("CREATE INDEX idx_csm_lidl ON cross_store_matches(lidl_product_id)")
        cur.execute("CREATE INDEX idx_csm_billa ON cross_store_matches(billa_product_id)")
        
        self.conn.commit()
        print("✓ Schema created")
        
    def load_products(self):
        """Load all products with categories and prices."""
        cur = self.conn.cursor()
        
        self.products_by_store = {}
        self.products_by_id = {}
        
        for store in self.STORES:
            cur.execute("""
                SELECT p.id, p.name, p.normalized_name, pr.current_price
                FROM products p
                JOIN store_products sp ON p.id = sp.product_id
                JOIN stores s ON sp.store_id = s.id
                LEFT JOIN prices pr ON pr.store_product_id = sp.id
                WHERE s.name = ?
            """, (store,))
            
            products = []
            for row in cur.fetchall():
                prod = dict(row)
                prod['store'] = store
                # Classify product
                cat, cat_conf = classify_product(prod['name'])
                prod['category'] = cat
                prod['category_conf'] = cat_conf
                products.append(prod)
                self.products_by_id[prod['id']] = prod
            
            self.products_by_store[store] = products
            
            # Category distribution
            cat_counts = defaultdict(int)
            for p in products:
                cat_counts[p['category']] += 1
            
            print(f"  {store}: {len(products)} products")
            top_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:5]
            for cat, cnt in top_cats:
                print(f"    {get_category_display(cat)}: {cnt}")
        
        return self.products_by_store
    
    def _load_model(self):
        """Load embedding model."""
        import os
        if self.model_cache:
            os.environ['TRANSFORMERS_CACHE'] = self.model_cache
            os.environ['HF_HOME'] = self.model_cache
        
        print("  Loading embedding model...")
        self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        print("  ✓ Model loaded")
    
    def match_stores(self, store1: str, store2: str, already_matched: set):
        """Match products between two stores with category filtering."""
        prods1 = [p for p in self.products_by_store[store1] if p['id'] not in already_matched]
        prods2 = [p for p in self.products_by_store[store2] if p['id'] not in already_matched]
        
        if not prods1 or not prods2:
            return []
        
        print(f"\n  {store1} ({len(prods1)}) vs {store2} ({len(prods2)})")
        
        # Encode all products
        texts1 = [p['name'] for p in prods1]
        texts2 = [p['name'] for p in prods2]
        
        emb1 = self.model.encode(texts1, convert_to_numpy=True, batch_size=64, show_progress_bar=False)
        emb2 = self.model.encode(texts2, convert_to_numpy=True, batch_size=64, show_progress_bar=False)
        
        # Compute all similarities
        sims = np.dot(emb1, emb2.T)
        
        matches = []
        used1 = set()
        used2 = set()
        
        # Find best bidirectional matches
        for idx1 in range(len(prods1)):
            if idx1 in used1:
                continue
            
            prod1 = prods1[idx1]
            
            # Find best match for prod1
            best_idx2 = -1
            best_sim = 0
            
            for idx2 in range(len(prods2)):
                if idx2 in used2:
                    continue
                
                sim = sims[idx1][idx2]
                if sim < self.EMBEDDING_THRESHOLD:
                    continue
                
                prod2 = prods2[idx2]
                
                # CATEGORY CHECK
                if not categories_compatible(prod1['category'], prod2['category']):
                    self.stats['blocked_category'] += 1
                    continue
                
                # PRICE CHECK (if both have prices)
                if prod1['current_price'] and prod2['current_price']:
                    p1, p2 = prod1['current_price'], prod2['current_price']
                    if min(p1, p2) > 0:
                        ratio = max(p1, p2) / min(p1, p2)
                        if ratio > self.PRICE_RATIO_MAX:
                            self.stats['blocked_price'] += 1
                            continue
                
                # BIDIRECTIONAL CHECK: is prod2's best match also prod1?
                best_for_prod2 = np.argmax(sims[:, idx2])
                if best_for_prod2 != idx1:
                    # Not mutual best match
                    self.stats['blocked_bidirectional'] += 1
                    continue
                
                if sim > best_sim:
                    best_sim = sim
                    best_idx2 = idx2
            
            if best_idx2 >= 0:
                prod2 = prods2[best_idx2]
                
                match = {
                    store1: prod1,
                    store2: prod2,
                    'similarity': best_sim,
                    'category': prod1['category'] if prod1['category'] != 'other' else prod2['category'],
                }
                matches.append(match)
                
                used1.add(idx1)
                used2.add(best_idx2)
                already_matched.add(prod1['id'])
                already_matched.add(prod2['id'])
        
        print(f"    → {len(matches)} matches")
        return matches
    
    def run(self):
        """Run full matching pipeline."""
        print("="*60)
        print("CROSS-STORE MATCHING PIPELINE v2 (with categories)")
        print("="*60)
        print(f"Threshold: {self.EMBEDDING_THRESHOLD}")
        print(f"Max price ratio: {self.PRICE_RATIO_MAX}x")
        
        self.setup_schema()
        self.load_products()
        
        if not HAS_EMBEDDINGS:
            print("ERROR: No embedding support")
            return
        
        self._load_model()
        
        matched_ids = set()
        all_matches = []
        
        # Match all store pairs
        print("\n=== MATCHING ===")
        pairs = [
            ('Kaufland', 'Lidl'),
            ('Kaufland', 'Billa'),
            ('Lidl', 'Billa'),
        ]
        
        for store1, store2 in pairs:
            matches = self.match_stores(store1, store2, matched_ids)
            all_matches.extend(matches)
            self.stats[f'{store1}_vs_{store2}'] = len(matches)
        
        # Insert matches
        cur = self.conn.cursor()
        for match in all_matches:
            stores_in_match = [s for s in self.STORES if s in match]
            
            kaufland_id = match.get('Kaufland', {}).get('id')
            lidl_id = match.get('Lidl', {}).get('id')
            billa_id = match.get('Billa', {}).get('id')
            
            canonical = match.get('Kaufland') or match.get('Lidl') or match.get('Billa')
            
            cur.execute("""
                INSERT INTO cross_store_matches 
                (kaufland_product_id, lidl_product_id, billa_product_id,
                 canonical_name, confidence, category, match_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                kaufland_id, lidl_id, billa_id,
                canonical['name'], match['similarity'],
                match['category'], 'embedding_v2'
            ))
        
        self.conn.commit()
        
        # Report
        print("\n" + "="*60)
        print("RESULTS")
        print("="*60)
        print(f"\nTotal matches: {len(all_matches)}")
        
        print(f"\nBy store pair:")
        for store1, store2 in pairs:
            key = f'{store1}_vs_{store2}'
            print(f"  {store1} vs {store2}: {self.stats[key]}")
        
        print(f"\nFiltering stats:")
        print(f"  Blocked by category: {self.stats['blocked_category']}")
        print(f"  Blocked by price: {self.stats['blocked_price']}")
        print(f"  Blocked by bidirectional: {self.stats['blocked_bidirectional']}")
        
        print(f"\nBy category:")
        cat_counts = defaultdict(int)
        for m in all_matches:
            cat_counts[m['category']] += 1
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"  {get_category_display(cat)}: {cnt}")
        
        print(f"\nTop matches (by confidence):")
        for m in sorted(all_matches, key=lambda x: -x['similarity'])[:15]:
            stores = [s for s in self.STORES if s in m]
            store_str = '+'.join([s[0] for s in stores])
            cat = get_category_display(m['category'])
            name1 = m[stores[0]]['name'][:35]
            name2 = m[stores[1]]['name'][:35]
            print(f"  [{m['similarity']:.3f}] {cat:15} {store_str}")
            print(f"          {name1}")
            print(f"          {name2}")
        
        return self.stats


if __name__ == '__main__':
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/promobg.db'
    cache_path = '/host-workspace/.model-cache'
    
    matcher = CrossStoreMatcherV2(db_path, model_cache=cache_path)
    matcher.run()
