#!/usr/bin/env python3
"""
Fast Product Matching Pipeline v2 - Fixed index lookups
"""
import sqlite3
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).parent.parent / "data"
PROMOBG_DB = BASE_DIR / "promobg.db"
OFF_DB = BASE_DIR / "off_bulgaria.db"
INDICES_DIR = BASE_DIR / "indices"

MIN_CONFIDENCE = 0.40

NON_FOOD_KEYWORDS = [
    'почиств', 'препарат', 'прах за пране', 'омекотител', 'кърпи', 'хартия',
    'тоалетна', 'салфетки', 'боя', 'лепило', 'батерии', 'крушка', 'торба',
    'свещ', 'аромат', 'дезодоратор', 'шампоан', 'сапун', 'крем', 'душ гел',
    'паста за зъби', 'четка', 'памперс', 'пелена', 'бръснач', 'дезодорант',
    'парфюм', 'лосион', 'silvercrest', 'livarno', 'parkside', 'блендер',
    'тиган', 'тенджера', 'уред', 'машина', 'прахосмукач', 'ютия', 'нагревател',
    'кучешк', 'котешк', 'играчк', 'градин', 'инструмент',
]

def log(msg):
    print(msg, flush=True)

def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\sа-яА-Яa-zA-Z0-9]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def tokenize(text):
    return [t for t in normalize(text).split() if len(t) > 1]

def extract_quantity(text):
    if not text:
        return None
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', lambda m: (float(m.group(1).replace(',', '.'))*1000, 'g')),
        (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)', lambda m: (float(m.group(1).replace(',', '.')), 'g')),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l)', lambda m: (float(m.group(1).replace(',', '.'))*1000, 'ml')),
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', lambda m: (float(m.group(1).replace(',', '.')), 'ml')),
    ]
    text_lower = text.lower()
    for pattern, extractor in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return extractor(match)
    return None

class FastMatcher:
    def __init__(self):
        log("Loading databases...")
        self.prom_conn = sqlite3.connect(PROMOBG_DB)
        self.off_conn = sqlite3.connect(OFF_DB)
        
        # Load OFF products - index by barcode
        log("Loading OFF products...")
        self.off_products = {}  # id -> product
        self.off_by_barcode = {}  # barcode -> id
        cur = self.off_conn.cursor()
        cur.execute('''SELECT id, barcode, product_name, product_name_bg, brands, quantity 
                      FROM off_products''')
        for row in cur.fetchall():
            prod = {
                'id': row[0], 'barcode': row[1], 'name': row[2] or '',
                'name_bg': row[3], 'brands': row[4], 'quantity': row[5]
            }
            self.off_products[row[0]] = prod
            if row[1]:
                self.off_by_barcode[row[1]] = row[0]
        log(f"  OFF products: {len(self.off_products)}")
        
        # Load indices (these map to BARCODES, not IDs)
        log("Loading indices...")
        with open(INDICES_DIR / "off_brand_index.json") as f:
            self.brand_to_barcodes = json.load(f)  # brand -> [barcodes]
        with open(INDICES_DIR / "off_token_index.json") as f:
            self.token_to_barcodes = json.load(f)  # token -> [barcodes]
        log(f"  Brands: {len(self.brand_to_barcodes)}, Tokens: {len(self.token_to_barcodes)}")
        
        # Build token sets for each OFF product for fast matching
        log("Building token sets...")
        self.off_tokens = {}  # off_id -> set of tokens
        for off_id, off_prod in self.off_products.items():
            text = " ".join(filter(None, [off_prod['name'], off_prod['name_bg'], off_prod['brands']]))
            self.off_tokens[off_id] = set(tokenize(text))
        log("  Done")
        
        self.stats = defaultdict(int)
        
    def load_products(self):
        cur = self.prom_conn.cursor()
        cur.execute('''
            SELECT p.id, p.name, p.brand, p.barcode_ean, p.quantity, s.name, sp.id
            FROM store_products sp
            JOIN stores s ON sp.store_id = s.id
            JOIN products p ON sp.product_id = p.id
            WHERE sp.deleted_at IS NULL
        ''')
        products = []
        for row in cur.fetchall():
            name_lower = (row[1] or "").lower()
            is_food = not any(kw in name_lower for kw in NON_FOOD_KEYWORDS)
            if is_food:
                products.append({
                    'id': row[0], 'name': row[1] or '', 'brand': row[2],
                    'barcode': row[3], 'quantity': row[4], 'store': row[5]
                })
        return products
    
    def match_barcode(self, product):
        if not product['barcode']:
            return None
        off_id = self.off_by_barcode.get(product['barcode'])
        if off_id:
            self.stats['barcode'] += 1
            return {'off_id': off_id, 'type': 'barcode', 'confidence': 1.0}
        return None
    
    def match_by_tokens(self, product):
        """Match using token overlap with TF-IDF-like scoring"""
        name_tokens = set(tokenize(product['name']))
        if not name_tokens:
            return None
        
        # Get candidate barcodes from token index
        candidate_barcodes = set()
        token_hits = defaultdict(int)  # barcode -> how many tokens matched
        
        for token in name_tokens:
            if token in self.token_to_barcodes:
                for bc in self.token_to_barcodes[token][:100]:  # Limit per token
                    candidate_barcodes.add(bc)
                    token_hits[bc] += 1
        
        # Also check brand index
        if product['brand']:
            brand_norm = normalize(product['brand'])
            for brand_key, barcodes in self.brand_to_barcodes.items():
                # Partial brand match
                if brand_norm in brand_key or brand_key in brand_norm or \
                   SequenceMatcher(None, brand_norm, brand_key).ratio() > 0.7:
                    for bc in barcodes[:50]:
                        candidate_barcodes.add(bc)
                        token_hits[bc] += 2  # Brand match bonus
        
        if not candidate_barcodes:
            return None
        
        # Score candidates
        best_match = None
        best_score = 0
        prod_qty = extract_quantity(product['name'])
        
        for barcode in candidate_barcodes:
            off_id = self.off_by_barcode.get(barcode)
            if not off_id or off_id not in self.off_products:
                continue
            
            off_prod = self.off_products[off_id]
            off_tokens = self.off_tokens.get(off_id, set())
            
            if not off_tokens:
                continue
            
            # Jaccard similarity
            common = len(name_tokens & off_tokens)
            union = len(name_tokens | off_tokens)
            jaccard = common / union if union > 0 else 0
            
            # Token hit bonus (how many of our tokens appeared in this product's index)
            hit_bonus = token_hits.get(barcode, 0) / len(name_tokens) * 0.3
            
            # Size match bonus
            size_bonus = 0
            if prod_qty:
                off_qty = extract_quantity(off_prod['quantity'] or '')
                if off_qty and prod_qty[1] == off_qty[1]:
                    ratio = min(prod_qty[0], off_qty[0]) / max(prod_qty[0], off_qty[0])
                    if ratio > 0.8:
                        size_bonus = 0.15
            
            # Combined score
            score = jaccard * 0.6 + hit_bonus + size_bonus
            
            if score > best_score:
                best_score = score
                best_match = {
                    'off_id': off_id,
                    'type': 'token',
                    'confidence': min(score + 0.2, 0.95),  # Boost confidence
                    'jaccard': jaccard,
                    'hits': token_hits.get(barcode, 0)
                }
        
        if best_match and best_match['confidence'] >= MIN_CONFIDENCE:
            self.stats['token'] += 1
            return best_match
        
        return None
    
    def match_fuzzy_fallback(self, product):
        """Fuzzy string match as last resort - but only check top candidates"""
        name_norm = normalize(product['name'])
        name_tokens = set(tokenize(product['name']))
        
        if len(name_tokens) < 2:
            return None
        
        # Get some candidates based on first significant token
        candidates = []
        for token in list(name_tokens)[:3]:
            if token in self.token_to_barcodes:
                for bc in self.token_to_barcodes[token][:30]:
                    off_id = self.off_by_barcode.get(bc)
                    if off_id:
                        candidates.append(off_id)
        
        if not candidates:
            return None
        
        best_match = None
        best_ratio = 0
        
        for off_id in set(candidates):
            off_prod = self.off_products.get(off_id)
            if not off_prod:
                continue
            
            # Try Bulgarian name first
            for off_name in [off_prod['name_bg'], off_prod['name']]:
                if not off_name:
                    continue
                off_norm = normalize(off_name)
                ratio = SequenceMatcher(None, name_norm, off_norm).ratio()
                
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = {
                        'off_id': off_id,
                        'type': 'fuzzy',
                        'confidence': ratio * 0.8,  # Scale down fuzzy confidence
                        'ratio': ratio
                    }
        
        if best_match and best_match['confidence'] >= MIN_CONFIDENCE:
            self.stats['fuzzy'] += 1
            return best_match
        
        return None
    
    def match_product(self, product):
        # Strategy 1: Barcode (100% confidence)
        match = self.match_barcode(product)
        if match:
            return match
        
        # Strategy 2: Token matching
        match = self.match_by_tokens(product)
        if match:
            return match
        
        # Strategy 3: Fuzzy fallback
        match = self.match_fuzzy_fallback(product)
        if match:
            return match
        
        self.stats['no_match'] += 1
        return None
    
    def run(self):
        log("\n" + "=" * 60)
        log("FAST MATCHING PIPELINE v2")
        log("=" * 60)
        
        products = self.load_products()
        log(f"Loaded {len(products)} food products")
        
        matches = []
        unmatched = []
        
        for i, product in enumerate(products):
            if (i + 1) % 500 == 0:
                log(f"Processing {i+1}/{len(products)}...")
            
            match = self.match_product(product)
            if match:
                match['product_id'] = product['id']
                match['product_name'] = product['name']
                match['product_brand'] = product['brand']
                match['store'] = product['store']
                off_prod = self.off_products[match['off_id']]
                match['off_name'] = off_prod['name']
                match['off_name_bg'] = off_prod['name_bg']
                match['off_barcode'] = off_prod['barcode']
                matches.append(match)
            else:
                unmatched.append(product)
        
        # Results
        log("\n" + "=" * 60)
        log("RESULTS")
        log("=" * 60)
        log(f"\nTotal food products: {len(products)}")
        log(f"Total matches: {len(matches)}")
        log(f"Match rate: {len(matches)/len(products)*100:.1f}%")
        
        log("\nMatch breakdown:")
        log(f"  Barcode (100%): {self.stats['barcode']}")
        log(f"  Token matching: {self.stats['token']}")
        log(f"  Fuzzy matching: {self.stats['fuzzy']}")
        log(f"  No match: {self.stats['no_match']}")
        
        # Confidence distribution
        high = sum(1 for m in matches if m['confidence'] >= 0.8)
        med = sum(1 for m in matches if 0.6 <= m['confidence'] < 0.8)
        low = sum(1 for m in matches if m['confidence'] < 0.6)
        log(f"\nConfidence distribution:")
        log(f"  High (>=0.8): {high}")
        log(f"  Medium (0.6-0.8): {med}")
        log(f"  Low (<0.6): {low}")
        
        # Sample matches by type
        log("\nSample barcode matches:")
        for m in [x for x in matches if x['type'] == 'barcode'][:3]:
            log(f"  '{m['product_name'][:35]}' → '{(m['off_name_bg'] or m['off_name'])[:35]}'")
        
        log("\nSample token matches:")
        for m in sorted([x for x in matches if x['type'] == 'token'], key=lambda x: -x['confidence'])[:5]:
            off_name = m.get('off_name_bg') or m.get('off_name', '')
            log(f"  [{m['confidence']:.2f}] '{m['product_name'][:30]}' → '{off_name[:30]}'")
        
        log("\nSample fuzzy matches:")
        for m in sorted([x for x in matches if x['type'] == 'fuzzy'], key=lambda x: -x['confidence'])[:3]:
            off_name = m.get('off_name_bg') or m.get('off_name', '')
            log(f"  [{m['confidence']:.2f}] '{m['product_name'][:30]}' → '{off_name[:30]}'")
        
        log("\nSample unmatched (by store):")
        by_store = defaultdict(list)
        for p in unmatched:
            by_store[p['store']].append(p)
        for store, prods in by_store.items():
            log(f"  {store}: {len(prods)} unmatched")
            for p in prods[:3]:
                log(f"    - {p['name'][:50]}")
        
        return matches, unmatched, products
    
    def save_matches(self, matches):
        cur = self.prom_conn.cursor()
        cur.execute('DELETE FROM product_off_matches')
        
        for m in matches:
            cur.execute('''
                INSERT INTO product_off_matches 
                (product_id, off_product_id, match_type, match_confidence, is_verified, created_at)
                VALUES (?, ?, ?, ?, 0, datetime('now'))
            ''', (m['product_id'], m['off_id'], m['type'], m['confidence']))
        
        self.prom_conn.commit()
        log(f"\nSaved {len(matches)} matches to database")
    
    def export_results(self, matches, unmatched, products):
        results = {
            'stats': dict(self.stats),
            'total_products': len(products),
            'total_matches': len(matches),
            'match_rate_percent': round(len(matches) / len(products) * 100, 1),
            'confidence_distribution': {
                'high': sum(1 for m in matches if m['confidence'] >= 0.8),
                'medium': sum(1 for m in matches if 0.6 <= m['confidence'] < 0.8),
                'low': sum(1 for m in matches if m['confidence'] < 0.6),
            },
            'matches': matches[:500],
            'unmatched': [{'id': p['id'], 'name': p['name'], 'brand': p['brand'], 'store': p['store']} 
                         for p in unmatched]
        }
        
        with open(BASE_DIR / "matches_results.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        log(f"Exported to {BASE_DIR / 'matches_results.json'}")

def main():
    matcher = FastMatcher()
    matches, unmatched, products = matcher.run()
    matcher.save_matches(matches)
    matcher.export_results(matches, unmatched, products)
    log(f"\n✓ Complete. Match rate: {len(matches)/len(products)*100:.1f}%")

if __name__ == '__main__':
    main()
