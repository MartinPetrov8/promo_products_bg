"""
Cross-Store Product Matching Pipeline
=====================================
Matches products across Kaufland, Lidl, and Billa stores.

Architecture:
- cross_store_matches table: one row per unique product, columns for each store's product_id
- Multi-phase matching: exact → brand+fuzzy → embedding-only
- Confidence scoring based on match quality

Author: Cookie
Date: 2026-02-15
"""

import sqlite3
import re
from collections import defaultdict
from datetime import datetime

# Try to import sentence_transformers for embedding matching
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False
    print("Warning: sentence_transformers not available, embedding matching disabled")


class CrossStoreMatcher:
    """Matches products across multiple stores."""
    
    STORES = ['Kaufland', 'Lidl', 'Billa']
    STORE_COLS = ['kaufland_product_id', 'lidl_product_id', 'billa_product_id']
    
    def __init__(self, db_path: str, model_cache: str = None):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.model_cache = model_cache
        self.model = None
        self.stats = defaultdict(int)
        
    def setup_schema(self):
        """Create cross_store_matches table."""
        cur = self.conn.cursor()
        
        # Drop if exists for clean run
        cur.execute("DROP TABLE IF EXISTS cross_store_matches")
        
        cur.execute("""
            CREATE TABLE cross_store_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Product IDs from each store (NULL if not available in that store)
                kaufland_product_id INTEGER REFERENCES products(id),
                lidl_product_id INTEGER REFERENCES products(id),
                billa_product_id INTEGER REFERENCES products(id),
                
                -- Canonical product info (from best available source)
                canonical_name TEXT NOT NULL,
                canonical_brand TEXT,
                canonical_quantity REAL,
                canonical_unit TEXT,
                
                -- Match metadata
                match_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                store_count INTEGER NOT NULL,
                
                -- Audit
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Indexes for fast lookups
        cur.execute("CREATE INDEX idx_csm_kaufland ON cross_store_matches(kaufland_product_id)")
        cur.execute("CREATE INDEX idx_csm_lidl ON cross_store_matches(lidl_product_id)")
        cur.execute("CREATE INDEX idx_csm_billa ON cross_store_matches(billa_product_id)")
        cur.execute("CREATE INDEX idx_csm_confidence ON cross_store_matches(confidence DESC)")
        cur.execute("CREATE INDEX idx_csm_store_count ON cross_store_matches(store_count)")
        
        self.conn.commit()
        print("✓ Schema created: cross_store_matches")
        
    def load_products(self):
        """Load all products grouped by store."""
        cur = self.conn.cursor()
        
        self.products_by_store = {}
        self.products_by_id = {}
        
        for store in self.STORES:
            cur.execute("""
                SELECT p.id, p.name, p.normalized_name, p.brand, p.quantity, p.unit
                FROM products p
                JOIN store_products sp ON p.id = sp.product_id
                JOIN stores s ON sp.store_id = s.id
                WHERE s.name = ? AND sp.deleted_at IS NULL
            """, (store,))
            
            products = []
            for row in cur.fetchall():
                prod = dict(row)
                prod['store'] = store
                prod['brand_norm'] = self._normalize_brand(prod['brand'])
                prod['name_norm'] = self._normalize_name(prod['name'])
                prod['match_key'] = self._make_match_key(prod)
                products.append(prod)
                self.products_by_id[prod['id']] = prod
            
            self.products_by_store[store] = products
            print(f"  Loaded {len(products)} products from {store}")
            
        return self.products_by_store
    
    def _normalize_brand(self, brand: str) -> str:
        """Normalize brand for matching."""
        if not brand:
            return None
        brand = brand.upper().strip()
        brand = re.sub(r'\s*(БЪЛГАРИЯ|BG|BULGARIA)$', '', brand)
        return brand
    
    def _normalize_name(self, name: str) -> str:
        """Normalize product name for matching."""
        if not name:
            return ''
        name = name.lower()
        name = re.sub(r'<[^>]+>', ' ', name)
        name = re.sub(r'[^\w\sа-яА-Яa-zA-Z0-9]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    def _make_match_key(self, prod: dict) -> str:
        """Create exact match key from brand + name + quantity."""
        parts = []
        if prod['brand_norm']:
            parts.append(prod['brand_norm'])
        parts.append(prod['name_norm'])
        if prod['quantity'] and prod['unit']:
            parts.append(f"{prod['quantity']}{prod['unit']}")
        return '|'.join(parts)
    
    def phase1_exact_matching(self):
        """Phase 1: Exact match on brand + normalized name + quantity."""
        print("\n=== PHASE 1: Exact Brand+Name+Quantity Matching ===")
        
        by_key = defaultdict(lambda: defaultdict(list))
        for store, products in self.products_by_store.items():
            for prod in products:
                if prod['brand_norm']:
                    by_key[prod['match_key']][store].append(prod)
        
        matches = []
        for key, store_prods in by_key.items():
            if len(store_prods) >= 2:
                match = {store: prods[0] for store, prods in store_prods.items()}
                matches.append(match)
        
        self._insert_matches(matches, 'exact_brand_qty', confidence=0.95)
        print(f"  ✓ Phase 1: {len(matches)} exact matches")
        self.stats['phase1_exact'] = len(matches)
        
        return matches
    
    def phase2_brand_fuzzy_matching(self, already_matched: set):
        """Phase 2: Same brand, fuzzy name matching via embeddings."""
        print("\n=== PHASE 2: Brand + Fuzzy Name Matching ===")
        
        if not HAS_EMBEDDINGS:
            print("  ⚠ Skipping: embeddings not available")
            return []
        
        if self.model is None:
            self._load_model()
        
        unmatched_by_brand = defaultdict(lambda: defaultdict(list))
        for store, products in self.products_by_store.items():
            for prod in products:
                if prod['id'] not in already_matched and prod['brand_norm']:
                    unmatched_by_brand[prod['brand_norm']][store].append(prod)
        
        matches = []
        processed_brands = 0
        
        for brand, store_prods in unmatched_by_brand.items():
            if len(store_prods) < 2:
                continue
            
            processed_brands += 1
            stores_with_prods = list(store_prods.keys())
            
            for i, store1 in enumerate(stores_with_prods):
                for store2 in stores_with_prods[i+1:]:
                    prods1 = [p for p in store_prods[store1] if p['id'] not in already_matched]
                    prods2 = [p for p in store_prods[store2] if p['id'] not in already_matched]
                    
                    if not prods1 or not prods2:
                        continue
                    
                    names1 = [p['name'] for p in prods1]
                    names2 = [p['name'] for p in prods2]
                    
                    emb1 = self.model.encode(names1, convert_to_numpy=True)
                    emb2 = self.model.encode(names2, convert_to_numpy=True)
                    
                    sims = np.dot(emb1, emb2.T)
                    
                    for idx1, prod1 in enumerate(prods1):
                        if prod1['id'] in already_matched:
                            continue
                        best_idx2 = np.argmax(sims[idx1])
                        best_sim = sims[idx1][best_idx2]
                        
                        if best_sim >= 0.80:
                            prod2 = prods2[best_idx2]
                            if prod2['id'] in already_matched:
                                continue
                            if self._quantities_compatible(prod1, prod2):
                                match = {store1: prod1, store2: prod2}
                                self._insert_matches([match], 'brand_fuzzy', confidence=float(best_sim) * 0.9)
                                matches.append(match)
                                already_matched.add(prod1['id'])
                                already_matched.add(prod2['id'])
        
        print(f"  ✓ Phase 2: {len(matches)} brand+fuzzy matches (from {processed_brands} brands)")
        self.stats['phase2_brand_fuzzy'] = len(matches)
        
        return matches
    
    def phase3_embedding_matching(self, already_matched: set):
        """Phase 3: Pure embedding matching for remaining products."""
        print("\n=== PHASE 3: Embedding-Only Matching ===")
        
        if not HAS_EMBEDDINGS:
            print("  ⚠ Skipping: embeddings not available")
            return []
        
        if self.model is None:
            self._load_model()
        
        unmatched = {}
        for store, products in self.products_by_store.items():
            unmatched[store] = [p for p in products if p['id'] not in already_matched]
        
        print(f"  Unmatched: K={len(unmatched['Kaufland'])}, L={len(unmatched['Lidl'])}, B={len(unmatched['Billa'])}")
        
        matches = []
        
        matches.extend(self._embedding_match_stores('Kaufland', 'Lidl', unmatched, already_matched))
        matches.extend(self._embedding_match_stores('Kaufland', 'Billa', unmatched, already_matched))
        matches.extend(self._embedding_match_stores('Lidl', 'Billa', unmatched, already_matched))
        
        print(f"  ✓ Phase 3: {len(matches)} embedding matches")
        self.stats['phase3_embedding'] = len(matches)
        
        return matches
    
    def _embedding_match_stores(self, store1: str, store2: str, unmatched: dict, already_matched: set):
        """Match products between two stores using embeddings."""
        prods1 = [p for p in unmatched[store1] if p['id'] not in already_matched]
        prods2 = [p for p in unmatched[store2] if p['id'] not in already_matched]
        
        if not prods1 or not prods2:
            return []
        
        print(f"    Matching {store1}({len(prods1)}) vs {store2}({len(prods2)})...")
        
        texts1 = [self._make_match_text(p) for p in prods1]
        texts2 = [self._make_match_text(p) for p in prods2]
        
        emb1 = self.model.encode(texts1, convert_to_numpy=True, batch_size=64, show_progress_bar=False)
        emb2 = self.model.encode(texts2, convert_to_numpy=True, batch_size=64, show_progress_bar=False)
        
        sims = np.dot(emb1, emb2.T)
        
        matches = []
        used2 = set()
        
        flat_indices = np.argsort(sims.flatten())[::-1]
        
        for flat_idx in flat_indices:
            idx1 = flat_idx // len(prods2)
            idx2 = flat_idx % len(prods2)
            sim = sims[idx1][idx2]
            
            if sim < 0.85:
                break
            
            prod1 = prods1[idx1]
            prod2 = prods2[idx2]
            
            if prod1['id'] in already_matched or prod2['id'] in already_matched:
                continue
            if idx2 in used2:
                continue
            
            if not self._quantities_compatible(prod1, prod2):
                continue
            
            match = {store1: prod1, store2: prod2}
            self._insert_matches([match], 'embedding', confidence=float(sim) * 0.85)
            matches.append(match)
            already_matched.add(prod1['id'])
            already_matched.add(prod2['id'])
            used2.add(idx2)
        
        print(f"      → {len(matches)} matches")
        return matches
    
    def _make_match_text(self, prod: dict) -> str:
        """Create rich text for embedding matching."""
        parts = []
        if prod['brand']:
            parts.append(prod['brand'])
        parts.append(prod['name'])
        if prod['quantity'] and prod['unit']:
            parts.append(f"{prod['quantity']} {prod['unit']}")
        return ' '.join(parts)
    
    def _quantities_compatible(self, prod1: dict, prod2: dict) -> bool:
        """Check if quantities are compatible."""
        q1, u1 = prod1.get('quantity'), prod1.get('unit')
        q2, u2 = prod2.get('quantity'), prod2.get('unit')
        
        if not q1 or not q2:
            return True
        
        u1_norm = (u1 or '').lower().replace('мл', 'ml').replace('г', 'g').replace('бр', 'pcs')
        u2_norm = (u2 or '').lower().replace('мл', 'ml').replace('г', 'g').replace('бр', 'pcs')
        
        if u1_norm != u2_norm:
            return False
        
        ratio = max(q1, q2) / min(q1, q2) if min(q1, q2) > 0 else 999
        return ratio <= 1.2
    
    def _load_model(self):
        """Load LaBSE model."""
        import os
        if self.model_cache:
            os.environ['TRANSFORMERS_CACHE'] = self.model_cache
            os.environ['HF_HOME'] = self.model_cache
        
        print("  Loading LaBSE model...")
        self.model = SentenceTransformer('sentence-transformers/LaBSE')
        print("  ✓ Model loaded")
    
    def _insert_matches(self, matches: list, match_type: str, confidence: float):
        """Insert matches into database."""
        cur = self.conn.cursor()
        
        for match in matches:
            kaufland_id = match.get('Kaufland', {}).get('id')
            lidl_id = match.get('Lidl', {}).get('id')
            billa_id = match.get('Billa', {}).get('id')
            
            canonical = match.get('Kaufland') or match.get('Lidl') or match.get('Billa')
            
            store_count = sum(1 for x in [kaufland_id, lidl_id, billa_id] if x is not None)
            
            cur.execute("""
                INSERT INTO cross_store_matches 
                (kaufland_product_id, lidl_product_id, billa_product_id,
                 canonical_name, canonical_brand, canonical_quantity, canonical_unit,
                 match_type, confidence, store_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kaufland_id, lidl_id, billa_id,
                canonical['name'], canonical.get('brand'),
                canonical.get('quantity'), canonical.get('unit'),
                match_type, confidence, store_count
            ))
        
        self.conn.commit()
    
    def consolidate_3way_matches(self):
        """Combine 2-way matches into 3-way matches where possible."""
        print("\n=== CONSOLIDATING 3-WAY MATCHES ===")
        
        cur = self.conn.cursor()
        
        # Find 2-way matches that share a product
        cur.execute("""
            SELECT m1.id, m2.id,
                   m1.kaufland_product_id, m1.lidl_product_id, m1.billa_product_id,
                   m2.kaufland_product_id, m2.lidl_product_id, m2.billa_product_id,
                   m1.canonical_name, m1.canonical_brand, m1.canonical_quantity, m1.canonical_unit,
                   m1.confidence, m2.confidence
            FROM cross_store_matches m1
            JOIN cross_store_matches m2 ON m1.id < m2.id
            WHERE m1.store_count = 2 AND m2.store_count = 2
            AND (
                (m1.kaufland_product_id = m2.kaufland_product_id AND m1.kaufland_product_id IS NOT NULL) OR
                (m1.lidl_product_id = m2.lidl_product_id AND m1.lidl_product_id IS NOT NULL) OR
                (m1.billa_product_id = m2.billa_product_id AND m1.billa_product_id IS NOT NULL)
            )
        """)
        
        to_merge = cur.fetchall()
        merged_count = 0
        ids_to_delete = set()
        
        for row in to_merge:
            id1, id2, k1, l1, b1, k2, l2, b2, name, brand, qty, unit, conf1, conf2 = row
            
            if id1 in ids_to_delete or id2 in ids_to_delete:
                continue
            
            new_k = k1 or k2
            new_l = l1 or l2
            new_b = b1 or b2
            
            if sum(1 for x in [new_k, new_l, new_b] if x) == 3:
                avg_conf = (conf1 + conf2) / 2
                cur.execute("""
                    UPDATE cross_store_matches
                    SET kaufland_product_id = ?, lidl_product_id = ?, billa_product_id = ?,
                        store_count = 3, confidence = ?, match_type = 'consolidated',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_k, new_l, new_b, avg_conf, id1))
                
                ids_to_delete.add(id2)
                merged_count += 1
        
        for del_id in ids_to_delete:
            cur.execute("DELETE FROM cross_store_matches WHERE id = ?", (del_id,))
        
        self.conn.commit()
        print(f"  ✓ Merged {merged_count} pairs into 3-way matches")
        self.stats['consolidated_3way'] = merged_count
    
    def generate_report(self):
        """Generate matching statistics report."""
        print("\n" + "="*60)
        print("CROSS-STORE MATCHING REPORT")
        print("="*60)
        
        cur = self.conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM cross_store_matches")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM cross_store_matches WHERE store_count = 2")
        two_store = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM cross_store_matches WHERE store_count = 3")
        three_store = cur.fetchone()[0]
        
        print(f"\nTotal matched product groups: {total}")
        print(f"  In 2 stores: {two_store}")
        print(f"  In 3 stores: {three_store}")
        
        print(f"\nBy match type:")
        cur.execute("""
            SELECT match_type, COUNT(*), ROUND(AVG(confidence), 3)
            FROM cross_store_matches
            GROUP BY match_type
            ORDER BY COUNT(*) DESC
        """)
        for mt, cnt, conf in cur.fetchall():
            print(f"  {mt}: {cnt} matches (avg conf: {conf})")
        
        print(f"\nStore pairs (2-way matches):")
        cur.execute("""
            SELECT 
                CASE 
                    WHEN kaufland_product_id IS NOT NULL AND lidl_product_id IS NOT NULL 
                         AND billa_product_id IS NULL THEN 'Kaufland-Lidl'
                    WHEN kaufland_product_id IS NOT NULL AND billa_product_id IS NOT NULL 
                         AND lidl_product_id IS NULL THEN 'Kaufland-Billa'
                    WHEN lidl_product_id IS NOT NULL AND billa_product_id IS NOT NULL 
                         AND kaufland_product_id IS NULL THEN 'Lidl-Billa'
                END as pair,
                COUNT(*)
            FROM cross_store_matches
            WHERE store_count = 2
            GROUP BY pair
            ORDER BY COUNT(*) DESC
        """)
        for pair, cnt in cur.fetchall():
            if pair:
                print(f"  {pair}: {cnt}")
        
        print(f"\nSample 3-store matches:")
        cur.execute("""
            SELECT canonical_name, canonical_brand, canonical_quantity, canonical_unit, confidence
            FROM cross_store_matches
            WHERE store_count = 3
            ORDER BY confidence DESC
            LIMIT 10
        """)
        for name, brand, qty, unit, conf in cur.fetchall():
            qty_str = f" {qty}{unit}" if qty else ""
            brand_str = f" ({brand})" if brand else ""
            print(f"  [{conf:.2f}] {name[:50]}{brand_str}{qty_str}")
        
        print(f"\nSample 2-store matches:")
        cur.execute("""
            SELECT canonical_name, canonical_brand, confidence,
                   kaufland_product_id, lidl_product_id, billa_product_id
            FROM cross_store_matches
            WHERE store_count = 2
            ORDER BY confidence DESC
            LIMIT 10
        """)
        for name, brand, conf, k, l, b in cur.fetchall():
            stores = []
            if k: stores.append('K')
            if l: stores.append('L')
            if b: stores.append('B')
            brand_str = f" ({brand})" if brand else ""
            print(f"  [{conf:.2f}] {name[:45]}{brand_str} → {'+'.join(stores)}")
        
        print(f"\nCoverage:")
        for store, col in zip(self.STORES, self.STORE_COLS):
            cur.execute(f"SELECT COUNT(DISTINCT {col}) FROM cross_store_matches WHERE {col} IS NOT NULL")
            matched = cur.fetchone()[0]
            total_store = len(self.products_by_store.get(store, []))
            pct = 100 * matched / total_store if total_store > 0 else 0
            print(f"  {store}: {matched}/{total_store} products matched ({pct:.1f}%)")
        
        return self.stats
    
    def run(self):
        """Run full matching pipeline."""
        print("="*60)
        print("CROSS-STORE PRODUCT MATCHING PIPELINE")
        print("="*60)
        print(f"Started at: {datetime.now().isoformat()}")
        
        self.setup_schema()
        self.load_products()
        
        matched_ids = set()
        
        phase1 = self.phase1_exact_matching()
        for match in phase1:
            for store_prod in match.values():
                matched_ids.add(store_prod['id'])
        
        phase2 = self.phase2_brand_fuzzy_matching(matched_ids)
        
        phase3 = self.phase3_embedding_matching(matched_ids)
        
        self.consolidate_3way_matches()
        
        self.generate_report()
        
        print(f"\nCompleted at: {datetime.now().isoformat()}")
        
        return self.stats


if __name__ == '__main__':
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/promobg.db'
    cache_path = '/host-workspace/.model-cache'
    
    matcher = CrossStoreMatcher(db_path, model_cache=cache_path)
    matcher.run()
