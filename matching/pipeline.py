"""
Cross-Store Matching Pipeline v2.3

Matches products across Kaufland, Lidl, and Billa stores.
Uses category blocking to reduce search space and improve accuracy.

Changes in v2.3:
- Raised embedding threshold to 0.90 (from 0.85)
- Added bidirectional match confirmation
- Added brand-less exact matching for generic products
"""

import os
import sqlite3
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from datetime import datetime

# Set model cache before importing sentence_transformers
cache_path = '/host-workspace/.model-cache'
os.makedirs(cache_path, exist_ok=True)
os.environ['TRANSFORMERS_CACHE'] = cache_path
os.environ['HF_HOME'] = cache_path
os.environ['SENTENCE_TRANSFORMERS_HOME'] = cache_path

import numpy as np


def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between two embedding matrices."""
    norm1 = emb1 / np.linalg.norm(emb1, axis=1, keepdims=True)
    norm2 = emb2 / np.linalg.norm(emb2, axis=1, keepdims=True)
    return np.dot(norm1, norm2.T)


class CrossStoreMatcher:
    """
    Cross-store product matcher with category blocking.
    
    Phases:
    1a. Exact (branded): Same brand + similar name + compatible quantity
    1b. Exact (generic): Same normalized_name (no brand required)
    2. Brand Fuzzy: Same brand + embedding similarity
    3. Embedding Only: Category-blocked bidirectional embedding matching
    """
    
    STORES = ['Kaufland', 'Lidl', 'Billa']
    
    # Thresholds (v2.3: raised embedding from 0.85 to 0.90)
    EXACT_NAME_SIM = 0.95
    BRAND_FUZZY_SIM = 0.80
    EMBEDDING_SIM = 0.90  # Raised from 0.85
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.model = None
        
    def _load_model(self):
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            print("Loading embedding model...")
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            print("✓ Model loaded")
    
    def run(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        self._setup_schema(conn)
        products = self._load_products(conn)
        
        stats = {
            'total_products': sum(len(p) for p in products.values()),
            'by_store': {s: len(products[s]) for s in self.STORES},
            'matches': {'exact_branded': 0, 'exact_generic': 0, 'brand_fuzzy': 0, 'embedding': 0},
            'total_matches': 0,
        }
        
        matched_ids: Set[int] = set()
        
        # Phase 1a: Exact branded matches
        print("\n=== Phase 1a: Exact Branded Matching ===")
        exact_b = self._phase_exact_branded(products, matched_ids)
        self._insert_matches(conn, exact_b, 'exact_branded')
        stats['matches']['exact_branded'] = len(exact_b)
        
        # Phase 1b: Exact generic matches (NEW)
        print("\n=== Phase 1b: Exact Generic Matching ===")
        exact_g = self._phase_exact_generic(products, matched_ids)
        self._insert_matches(conn, exact_g, 'exact_generic')
        stats['matches']['exact_generic'] = len(exact_g)
        
        # Phase 2: Brand + Fuzzy
        print("\n=== Phase 2: Brand Fuzzy Matching ===")
        self._load_model()
        fuzzy = self._phase_brand_fuzzy(products, matched_ids)
        self._insert_matches(conn, fuzzy, 'brand_fuzzy')
        stats['matches']['brand_fuzzy'] = len(fuzzy)
        
        # Phase 3: Embedding with bidirectional confirmation
        print("\n=== Phase 3: Embedding Matching (bidirectional) ===")
        emb = self._phase_embedding_bidirectional(products, matched_ids)
        self._insert_matches(conn, emb, 'embedding')
        stats['matches']['embedding'] = len(emb)
        
        conn.commit()
        conn.close()
        
        stats['total_matches'] = sum(stats['matches'].values())
        return stats
    
    def _setup_schema(self, conn):
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS cross_store_matches")
        cur.execute("""
            CREATE TABLE cross_store_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kaufland_product_id INTEGER,
                lidl_product_id INTEGER,
                billa_product_id INTEGER,
                canonical_name TEXT NOT NULL,
                canonical_brand TEXT,
                category_code TEXT,
                match_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                store_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    
    def _load_products(self, conn) -> Dict[str, List[dict]]:
        cur = conn.cursor()
        products = {s: [] for s in self.STORES}
        
        for store in self.STORES:
            cur.execute("""
                SELECT p.id, p.name, p.normalized_name, p.brand, 
                       p.quantity, p.unit, p.category_code
                FROM products p
                JOIN store_products sp ON p.id = sp.product_id
                JOIN stores s ON sp.store_id = s.id
                WHERE s.name = ? AND sp.deleted_at IS NULL
            """, (store,))
            
            for row in cur.fetchall():
                products[store].append({
                    'id': row['id'],
                    'name': row['name'],
                    'normalized_name': row['normalized_name'] or row['name'],
                    'brand': row['brand'],
                    'quantity': row['quantity'],
                    'unit': row['unit'],
                    'category': row['category_code'],
                    'store': store,
                })
            
            print(f"  {store}: {len(products[store])} products")
        
        return products
    
    def _phase_exact_branded(self, products: Dict, matched: Set[int]) -> List[dict]:
        """Phase 1a: Exact brand + name + quantity matches."""
        matches = []
        by_key = defaultdict(lambda: defaultdict(list))
        
        for store, prods in products.items():
            for p in prods:
                if not p['brand']:
                    continue
                key = (
                    p['brand'].lower(),
                    (p['normalized_name'] or '')[:50],
                    str(p['quantity']),
                    p['unit'] or ''
                )
                by_key[key][store].append(p)
        
        for key, store_prods in by_key.items():
            if len(store_prods) < 2:
                continue
            
            match = {'_confidence': 1.0}
            for store, prods in store_prods.items():
                if prods[0]['id'] not in matched:
                    match[store] = prods[0]
                    matched.add(prods[0]['id'])
            
            if len([k for k in match if k != '_confidence']) >= 2:
                matches.append(match)
        
        print(f"  ✓ {len(matches)} exact branded matches")
        return matches
    
    def _phase_exact_generic(self, products: Dict, matched: Set[int]) -> List[dict]:
        """Phase 1b: Exact normalized_name matches (no brand required)."""
        matches = []
        by_name = defaultdict(lambda: defaultdict(list))
        
        for store, prods in products.items():
            for p in prods:
                if p['id'] in matched:
                    continue
                # Use first 60 chars of normalized name as key
                name_key = (p['normalized_name'] or '')[:60].strip().lower()
                if len(name_key) < 5:  # Skip very short names
                    continue
                by_name[name_key][store].append(p)
        
        for name_key, store_prods in by_name.items():
            if len(store_prods) < 2:
                continue
            
            match = {'_confidence': 0.98}  # Slightly less than branded
            for store, prods in store_prods.items():
                if prods[0]['id'] not in matched:
                    match[store] = prods[0]
                    matched.add(prods[0]['id'])
            
            if len([k for k in match if k != '_confidence']) >= 2:
                matches.append(match)
        
        print(f"  ✓ {len(matches)} exact generic matches")
        return matches
    
    def _phase_brand_fuzzy(self, products: Dict, matched: Set[int]) -> List[dict]:
        """Phase 2: Same brand, fuzzy name match."""
        matches = []
        by_brand = defaultdict(lambda: defaultdict(list))
        
        for store, prods in products.items():
            for p in prods:
                if p['id'] in matched or not p['brand']:
                    continue
                by_brand[p['brand'].lower()][store].append(p)
        
        for brand, store_prods in by_brand.items():
            if len(store_prods) < 2:
                continue
            
            stores = list(store_prods.keys())
            for i, s1 in enumerate(stores):
                for s2 in stores[i+1:]:
                    prods1 = [p for p in store_prods[s1] if p['id'] not in matched]
                    prods2 = [p for p in store_prods[s2] if p['id'] not in matched]
                    
                    if not prods1 or not prods2:
                        continue
                    
                    emb1 = self.model.encode([p['normalized_name'] for p in prods1])
                    emb2 = self.model.encode([p['normalized_name'] for p in prods2])
                    sims = cosine_similarity(emb1, emb2)
                    
                    used2 = set()
                    for idx1, p1 in enumerate(prods1):
                        if p1['id'] in matched:
                            continue
                        
                        best_idx = np.argmax(sims[idx1])
                        best_sim = float(sims[idx1][best_idx])
                        
                        if best_sim >= self.BRAND_FUZZY_SIM and best_idx not in used2:
                            p2 = prods2[best_idx]
                            if p2['id'] not in matched:
                                matches.append({s1: p1, s2: p2, '_confidence': best_sim})
                                matched.add(p1['id'])
                                matched.add(p2['id'])
                                used2.add(best_idx)
        
        print(f"  ✓ {len(matches)} brand+fuzzy matches")
        return matches
    
    def _phase_embedding_bidirectional(self, products: Dict, matched: Set[int]) -> List[dict]:
        """Phase 3: Embedding matching with bidirectional confirmation."""
        matches = []
        by_category = defaultdict(lambda: defaultdict(list))
        
        for store, prods in products.items():
            for p in prods:
                if p['id'] in matched:
                    continue
                cat = p['category'] or 'other'
                by_category[cat][store].append(p)
        
        skip_categories = {'99000000', 'other'}
        
        for category, store_prods in by_category.items():
            if category in skip_categories or len(store_prods) < 2:
                continue
            
            stores = list(store_prods.keys())
            for i, s1 in enumerate(stores):
                for s2 in stores[i+1:]:
                    prods1 = [p for p in store_prods[s1] if p['id'] not in matched]
                    prods2 = [p for p in store_prods[s2] if p['id'] not in matched]
                    
                    if not prods1 or not prods2:
                        continue
                    
                    emb1 = self.model.encode([p['normalized_name'] for p in prods1], batch_size=64)
                    emb2 = self.model.encode([p['normalized_name'] for p in prods2], batch_size=64)
                    sims = cosine_similarity(emb1, emb2)
                    
                    # Bidirectional: find pairs where each is the other's best match
                    best_for_1 = np.argmax(sims, axis=1)  # Best in prods2 for each in prods1
                    best_for_2 = np.argmax(sims, axis=0)  # Best in prods1 for each in prods2
                    
                    for idx1, idx2 in enumerate(best_for_1):
                        # Check bidirectional: prods1[idx1]'s best is prods2[idx2]
                        # AND prods2[idx2]'s best is prods1[idx1]
                        if best_for_2[idx2] != idx1:
                            continue
                        
                        sim = float(sims[idx1][idx2])
                        if sim < self.EMBEDDING_SIM:
                            continue
                        
                        p1, p2 = prods1[idx1], prods2[idx2]
                        if p1['id'] in matched or p2['id'] in matched:
                            continue
                        
                        matches.append({s1: p1, s2: p2, '_confidence': sim})
                        matched.add(p1['id'])
                        matched.add(p2['id'])
        
        print(f"  ✓ {len(matches)} embedding matches (bidirectional)")
        return matches
    
    def _insert_matches(self, conn, matches: List[dict], match_type: str):
        cur = conn.cursor()
        
        for match in matches:
            k_id = match.get('Kaufland', {}).get('id')
            l_id = match.get('Lidl', {}).get('id')
            b_id = match.get('Billa', {}).get('id')
            confidence = match.get('_confidence', 0.5)
            canonical = match.get('Kaufland') or match.get('Lidl') or match.get('Billa')
            store_count = sum(1 for x in [k_id, l_id, b_id] if x)
            
            cur.execute("""
                INSERT INTO cross_store_matches 
                (kaufland_product_id, lidl_product_id, billa_product_id,
                 canonical_name, canonical_brand, category_code,
                 match_type, confidence, store_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                k_id, l_id, b_id,
                canonical['name'], canonical.get('brand'), canonical.get('category'),
                match_type, confidence, store_count
            ))


def run_matching_pipeline(db_path: str = 'data/promobg.db') -> Dict:
    print("=" * 60)
    print("CROSS-STORE MATCHING PIPELINE v2.3")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    
    matcher = CrossStoreMatcher(db_path)
    stats = matcher.run()
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total products: {stats['total_products']}")
    print(f"By store: {stats['by_store']}")
    print(f"\nMatches by type:")
    for match_type, count in stats['matches'].items():
        print(f"  {match_type}: {count}")
    print(f"\nTotal matches: {stats['total_matches']}")
    
    return stats


if __name__ == "__main__":
    run_matching_pipeline()
