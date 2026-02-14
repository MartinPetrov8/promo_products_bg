#!/usr/bin/env python3
"""
Fast Product Matching Pipeline - Optimized version
"""
import sqlite3
import json
import re
import math
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import numpy as np
import sys

BASE_DIR = Path(__file__).parent.parent / "data"
PROMOBG_DB = BASE_DIR / "promobg.db"
OFF_DB = BASE_DIR / "off_bulgaria.db"
INDICES_DIR = BASE_DIR / "indices"

MIN_CONFIDENCE = 0.45

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
        
        # Load indices
        log("Loading indices...")
        with open(INDICES_DIR / "off_brand_index.json") as f:
            self.brand_index = json.load(f)
        with open(INDICES_DIR / "off_token_index.json") as f:
            self.token_index = json.load(f)
        log(f"  Brands: {len(self.brand_index)}, Tokens: {len(self.token_index)}")
        
        # Load OFF products
        log("Loading OFF products...")
        self.off_products = {}
        self.off_by_barcode = {}
        cur = self.off_conn.cursor()
        cur.execute('''SELECT id, barcode, product_name, product_name_bg, brands, quantity 
                      FROM off_products''')
        for row in cur.fetchall():
            self.off_products[row[0]] = {
                'id': row[0], 'barcode': row[1], 'name': row[2] or '',
                'name_bg': row[3], 'brands': row[4], 'quantity': row[5]
            }
            if row[1]:
                self.off_by_barcode[row[1]] = row[0]
        log(f"  OFF products: {len(self.off_products)}")
        
        # Build inverted index for fast token lookup
        log("Building token vectors...")
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
    
    def match_brand_tokens(self, product):
        brand = normalize(product['brand']) if product['brand'] else None
        name_tokens = set(tokenize(product['name']))
        prod_qty = extract_quantity(product['name'])
        
        # Get candidates from brand index
        candidates = set()
        if brand:
            for b_key, off_ids in self.brand_index.items():
                if brand in b_key or b_key in brand:
                    candidates.update(off_ids[:50])  # Limit per brand
        
        # Also get candidates from token index
        for token in name_tokens:
            if token in self.token_index:
                candidates.update(self.token_index[token][:30])
        
        if not candidates:
            return None
        
        best_match = None
        best_score = 0
        
        for off_id in candidates:
            if off_id not in self.off_products:
                continue
            off_prod = self.off_products[off_id]
            off_tokens = self.off_tokens.get(off_id, set())
            
            # Token overlap (Jaccard-like)
            if not off_tokens:
                continue
            common = len(name_tokens & off_tokens)
            union = len(name_tokens | off_tokens)
            token_sim = common / union if union > 0 else 0
            
            # Brand bonus
            brand_bonus = 0
            if brand and off_prod['brands']:
                off_brand = normalize(off_prod['brands'])
                if brand in off_brand or off_brand in brand:
                    brand_bonus = 0.2
            
            # Size similarity
            size_sim = 0
            if prod_qty:
                off_qty = extract_quantity(off_prod['quantity'] or '')
                if off_qty and prod_qty[1] == off_qty[1]:  # Same unit
                    ratio = min(prod_qty[0], off_qty[0]) / max(prod_qty[0], off_qty[0])
                    size_sim = ratio * 0.15
            
            score = token_sim + brand_bonus + size_sim
            
            if score > best_score:
                best_score = score
                best_match = {'off_id': off_id, 'type': 'token', 'confidence': min(score, 0.95)}
        
        if best_match and best_match['confidence'] >= MIN_CONFIDENCE:
            self.stats['token'] += 1
            return best_match
        return None
    
    def match_product(self, product):
        # Strategy 1: Barcode
        match = self.match_barcode(product)
        if match:
            return match
        
        # Strategy 2: Brand + Token matching
        match = self.match_brand_tokens(product)
        if match:
            return match
        
        self.stats['no_match'] += 1
        return None
    
    def run(self):
        log("\n" + "=" * 60)
        log("FAST MATCHING PIPELINE")
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
                match['off_name'] = self.off_products[match['off_id']]['name']
                match['off_name_bg'] = self.off_products[match['off_id']]['name_bg']
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
        log(f"  No match: {self.stats['no_match']}")
        
        # Confidence distribution
        high = sum(1 for m in matches if m['confidence'] >= 0.8)
        med = sum(1 for m in matches if 0.6 <= m['confidence'] < 0.8)
        low = sum(1 for m in matches if m['confidence'] < 0.6)
        log(f"\nConfidence distribution:")
        log(f"  High (>=0.8): {high}")
        log(f"  Medium (0.6-0.8): {med}")
        log(f"  Low (<0.6): {low}")
        
        # Sample matches
        log("\nSample high-confidence matches:")
        for m in sorted(matches, key=lambda x: -x['confidence'])[:5]:
            off_name = m.get('off_name_bg') or m.get('off_name', '')
            log(f"  [{m['type']}] {m['confidence']:.2f}: '{m['product_name'][:35]}' → '{off_name[:35]}'")
        
        log("\nSample unmatched:")
        for p in unmatched[:10]:
            log(f"  - [{p['store']}] {p['name'][:55]}")
        
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
            'matches': matches[:500],
            'unmatched': [{'id': p['id'], 'name': p['name'], 'brand': p['brand'], 'store': p['store']} 
                         for p in unmatched[:200]]
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
