#!/usr/bin/env python3
"""
Hybrid Product Matching Pipeline
Matches store products to OpenFoodFacts (OFF) database using multiple strategies:
1. Barcode exact match (100% confidence)
2. Brand + Size match (high confidence)
3. Token-based cosine similarity (medium confidence)
4. Fuzzy name matching (lower confidence)

Author: Cookie
Date: 2026-02-14
"""

import sqlite3
import json
import re
import math
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

# Paths
BASE_DIR = Path(__file__).parent.parent / "data"
PROMOBG_DB = BASE_DIR / "promobg.db"
OFF_DB = BASE_DIR / "off_bulgaria.db"
INDICES_DIR = BASE_DIR / "indices"

# Match confidence thresholds
CONFIDENCE_BARCODE = 1.0
CONFIDENCE_BRAND_SIZE = 0.85
CONFIDENCE_TOKEN_HIGH = 0.75
CONFIDENCE_TOKEN_MEDIUM = 0.60
CONFIDENCE_FUZZY = 0.50
MIN_CONFIDENCE = 0.45

# Non-food keywords for filtering
NON_FOOD_KEYWORDS = [
    'почиств', 'препарат', 'прах за пране', 'омекотител', 'кърпи', 'хартия',
    'тоалетна', 'салфетки', 'боя', 'лепило', 'батерии', 'крушка', 'торба',
    'свещ', 'аромат', 'дезодоратор', 'шампоан', 'сапун', 'крем', 'душ гел',
    'паста за зъби', 'четка', 'памперс', 'пелена', 'бръснач', 'дезодорант',
    'парфюм', 'лосион', 'silvercrest', 'livarno', 'parkside', 'блендер',
    'тиган', 'тенджера', 'уред', 'машина', 'прахосмукач', 'ютия', 'нагревател',
    'кучешк', 'котешк', 'играчк', 'градин', 'инструмент',
]


@dataclass
class Product:
    """Store product"""
    id: int
    name: str
    normalized_name: str
    brand: Optional[str]
    barcode: Optional[str]
    quantity: Optional[str]
    store: str
    store_product_id: int
    
    
@dataclass
class OFFProduct:
    """OpenFoodFacts product"""
    id: int
    barcode: str
    name: str
    name_bg: Optional[str]
    brands: Optional[str]
    categories: Optional[str]
    quantity: Optional[str]
    normalized_name: Optional[str]
    normalized_brand: Optional[str]


@dataclass 
class Match:
    """A product match result"""
    product_id: int
    off_id: int
    off_barcode: str
    match_type: str
    confidence: float
    details: Dict = field(default_factory=dict)


class TextNormalizer:
    """Normalize text for matching"""
    
    @staticmethod
    def normalize(text: str) -> str:
        """Basic text normalization"""
        if not text:
            return ""
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\sа-яА-Яa-zA-Z0-9]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Tokenize normalized text"""
        normalized = TextNormalizer.normalize(text)
        tokens = normalized.split()
        return [t for t in tokens if len(t) > 1]
    
    @staticmethod
    def extract_quantity(text: str) -> Optional[Tuple[float, str]]:
        """Extract quantity and unit from text"""
        if not text:
            return None
        
        patterns = [
            r'(\d+(?:[.,]\d+)?)\s*(кг|kg)',
            r'(\d+(?:[.,]\d+)?)\s*(гр?|g)',
            r'(\d+(?:[.,]\d+)?)\s*(л|l)',
            r'(\d+(?:[.,]\d+)?)\s*(мл|ml)',
            r'(\d+(?:[.,]\d+)?)\s*(бр|pcs?)',
            r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(гр?|g|мл|ml)',
        ]
        
        text_lower = text.lower()
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    count = int(groups[0])
                    amount = float(groups[1].replace(',', '.'))
                    unit = groups[2]
                    return (count * amount, unit)
                else:
                    amount = float(groups[0].replace(',', '.'))
                    unit = groups[1]
                    unit_map = {'гр': 'g', 'г': 'g', 'кг': 'kg', 'л': 'l', 'мл': 'ml', 'бр': 'pcs'}
                    unit = unit_map.get(unit, unit)
                    return (amount, unit)
        
        return None
    
    @staticmethod
    def normalize_quantity(qty: Tuple[float, str]) -> float:
        """Convert quantity to base units"""
        if not qty:
            return 0
        amount, unit = qty
        if unit == 'kg':
            return amount * 1000
        elif unit == 'l':
            return amount * 1000
        return amount


class CosineSimilarity:
    """Cosine similarity calculator for token vectors"""
    
    def __init__(self):
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        
    def build_vocabulary(self, documents: List[List[str]]):
        """Build vocabulary and IDF from documents"""
        doc_freq = defaultdict(int)
        all_tokens = set()
        
        for tokens in documents:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freq[token] += 1
                all_tokens.add(token)
        
        self.vocabulary = {token: idx for idx, token in enumerate(sorted(all_tokens))}
        
        n_docs = len(documents)
        self.idf = {
            token: math.log((n_docs + 1) / (freq + 1)) + 1
            for token, freq in doc_freq.items()
        }
        
    def vectorize(self, tokens: List[str]) -> np.ndarray:
        """Convert tokens to TF-IDF vector"""
        vector = np.zeros(len(self.vocabulary))
        token_counts = defaultdict(int)
        
        for token in tokens:
            token_counts[token] += 1
            
        for token, count in token_counts.items():
            if token in self.vocabulary:
                idx = self.vocabulary[token]
                tf = 1 + math.log(count) if count > 0 else 0
                idf = self.idf.get(token, 1.0)
                vector[idx] = tf * idf
                
        return vector
    
    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity"""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return float(np.dot(vec1, vec2) / (norm1 * norm2))


class MatchingPipeline:
    """Main matching pipeline"""
    
    def __init__(self):
        self.promobg_conn = sqlite3.connect(PROMOBG_DB)
        self.off_conn = sqlite3.connect(OFF_DB)
        self.normalizer = TextNormalizer()
        self.cosine = CosineSimilarity()
        
        self.brand_index: Dict[str, List[int]] = {}
        self.token_index: Dict[str, List[int]] = {}
        self.load_indices()
        
        self.off_products: Dict[int, OFFProduct] = {}
        self.off_by_barcode: Dict[str, int] = {}
        self.load_off_products()
        
        self.build_similarity_model()
        
        self.stats = defaultdict(int)
        
    def load_indices(self):
        """Load pre-built indices"""
        brand_path = INDICES_DIR / "off_brand_index.json"
        token_path = INDICES_DIR / "off_token_index.json"
        
        if brand_path.exists():
            with open(brand_path) as f:
                self.brand_index = json.load(f)
            print(f"Loaded {len(self.brand_index)} brands from index")
            
        if token_path.exists():
            with open(token_path) as f:
                self.token_index = json.load(f)
            print(f"Loaded {len(self.token_index)} tokens from index")
    
    def load_off_products(self):
        """Load all OFF products into memory"""
        cur = self.off_conn.cursor()
        cur.execute('''
            SELECT id, barcode, product_name, product_name_bg, brands, 
                   categories, quantity, normalized_name, normalized_brand
            FROM off_products
        ''')
        
        for row in cur.fetchall():
            off_product = OFFProduct(
                id=row[0],
                barcode=row[1],
                name=row[2] or "",
                name_bg=row[3],
                brands=row[4],
                categories=row[5],
                quantity=row[6],
                normalized_name=row[7],
                normalized_brand=row[8]
            )
            self.off_products[off_product.id] = off_product
            if off_product.barcode:
                self.off_by_barcode[off_product.barcode] = off_product.id
                
        print(f"Loaded {len(self.off_products)} OFF products")
        
    def build_similarity_model(self):
        """Build TF-IDF model from OFF products"""
        print("Building similarity model...")
        documents = []
        self.off_token_vectors: Dict[int, np.ndarray] = {}
        
        for off_id, off_product in self.off_products.items():
            text = " ".join(filter(None, [
                off_product.name,
                off_product.name_bg,
                off_product.brands
            ]))
            tokens = self.normalizer.tokenize(text)
            documents.append(tokens)
            
        self.cosine.build_vocabulary(documents)
        
        for off_id, off_product in self.off_products.items():
            text = " ".join(filter(None, [
                off_product.name,
                off_product.name_bg,
                off_product.brands
            ]))
            tokens = self.normalizer.tokenize(text)
            self.off_token_vectors[off_id] = self.cosine.vectorize(tokens)
            
        print(f"Built vectors for {len(self.off_token_vectors)} products, vocabulary size: {len(self.cosine.vocabulary)}")
    
    def load_store_products(self) -> List[Product]:
        """Load all food products from stores"""
        cur = self.promobg_conn.cursor()
        cur.execute('''
            SELECT p.id, p.name, p.normalized_name, p.brand, p.barcode_ean, 
                   p.quantity, s.name, sp.id
            FROM store_products sp
            JOIN stores s ON sp.store_id = s.id
            JOIN products p ON sp.product_id = p.id
            WHERE sp.deleted_at IS NULL
        ''')
        
        products = []
        for row in cur.fetchall():
            name_lower = row[1].lower() if row[1] else ""
            is_food = not any(kw in name_lower for kw in NON_FOOD_KEYWORDS)
            
            if is_food:
                products.append(Product(
                    id=row[0],
                    name=row[1] or "",
                    normalized_name=row[2] or "",
                    brand=row[3],
                    barcode=row[4],
                    quantity=str(row[5]) if row[5] else None,
                    store=row[6],
                    store_product_id=row[7]
                ))
                
        print(f"Loaded {len(products)} food products from stores")
        return products
    
    def match_by_barcode(self, product: Product) -> Optional[Match]:
        """Try exact barcode match"""
        if not product.barcode:
            return None
            
        off_id = self.off_by_barcode.get(product.barcode)
        if off_id:
            off_product = self.off_products[off_id]
            self.stats['barcode_match'] += 1
            return Match(
                product_id=product.id,
                off_id=off_id,
                off_barcode=off_product.barcode,
                match_type='barcode',
                confidence=CONFIDENCE_BARCODE,
                details={'exact': True}
            )
        return None
    
    def match_by_brand_size(self, product: Product) -> Optional[Match]:
        """Match by brand + similar size"""
        if not product.brand:
            return None
            
        brand_normalized = self.normalizer.normalize(product.brand)
        
        candidates = []
        for brand_key, off_ids in self.brand_index.items():
            if brand_key == brand_normalized or brand_normalized in brand_key or brand_key in brand_normalized:
                candidates.extend(off_ids)
        
        if not candidates:
            return None
            
        product_qty = self.normalizer.extract_quantity(product.name)
        if not product_qty and product.quantity:
            product_qty = self.normalizer.extract_quantity(product.quantity)
        
        product_qty_normalized = self.normalizer.normalize_quantity(product_qty) if product_qty else 0
        
        best_match = None
        best_score = 0
        
        for off_id in set(candidates):
            off_product = self.off_products.get(off_id)
            if not off_product:
                continue
                
            off_brand = self.normalizer.normalize(off_product.brands or "")
            brand_sim = SequenceMatcher(None, brand_normalized, off_brand).ratio()
            
            off_qty = self.normalizer.extract_quantity(off_product.quantity or "")
            off_qty_normalized = self.normalizer.normalize_quantity(off_qty) if off_qty else 0
            
            size_sim = 0
            if product_qty_normalized > 0 and off_qty_normalized > 0:
                ratio = min(product_qty_normalized, off_qty_normalized) / max(product_qty_normalized, off_qty_normalized)
                size_sim = ratio
            
            product_tokens = self.normalizer.tokenize(product.name)
            off_text = " ".join(filter(None, [off_product.name, off_product.name_bg]))
            off_tokens = self.normalizer.tokenize(off_text)
            
            common_tokens = set(product_tokens) & set(off_tokens)
            name_sim = len(common_tokens) / max(len(product_tokens), 1)
            
            score = (brand_sim * 0.4) + (size_sim * 0.3) + (name_sim * 0.3)
            
            if score > best_score:
                best_score = score
                best_match = Match(
                    product_id=product.id,
                    off_id=off_id,
                    off_barcode=off_product.barcode,
                    match_type='brand_size',
                    confidence=CONFIDENCE_BRAND_SIZE * score,
                    details={
                        'brand_sim': brand_sim,
                        'size_sim': size_sim,
                        'name_sim': name_sim,
                        'off_name': off_product.name
                    }
                )
        
        if best_match and best_match.confidence >= MIN_CONFIDENCE:
            self.stats['brand_size_match'] += 1
            return best_match
            
        return None
    
    def match_by_cosine_similarity(self, product: Product) -> Optional[Match]:
        """Match using TF-IDF cosine similarity"""
        product_tokens = self.normalizer.tokenize(product.name)
        if not product_tokens:
            return None
            
        product_vector = self.cosine.vectorize(product_tokens)
        
        best_match = None
        best_similarity = 0
        
        candidate_ids = set()
        for token in product_tokens:
            if token in self.token_index:
                candidate_ids.update(self.token_index[token][:100])
        
        if not candidate_ids:
            candidate_ids = set(list(self.off_products.keys())[:500])
        
        for off_id in candidate_ids:
            if off_id not in self.off_token_vectors:
                continue
                
            off_vector = self.off_token_vectors[off_id]
            similarity = self.cosine.similarity(product_vector, off_vector)
            
            if similarity > best_similarity:
                best_similarity = similarity
                off_product = self.off_products[off_id]
                best_match = Match(
                    product_id=product.id,
                    off_id=off_id,
                    off_barcode=off_product.barcode,
                    match_type='cosine',
                    confidence=similarity,
                    details={
                        'cosine_sim': similarity,
                        'off_name': off_product.name,
                        'off_name_bg': off_product.name_bg
                    }
                )
        
        if best_match and best_match.confidence >= MIN_CONFIDENCE:
            self.stats['cosine_match'] += 1
            return best_match
            
        return None
    
    def match_by_fuzzy(self, product: Product) -> Optional[Match]:
        """Last resort: fuzzy string matching"""
        product_name = self.normalizer.normalize(product.name)
        
        best_match = None
        best_ratio = 0
        
        sample_size = min(2000, len(self.off_products))
        sampled_ids = list(self.off_products.keys())[:sample_size]
        
        for off_id in sampled_ids:
            off_product = self.off_products[off_id]
            
            for off_name in [off_product.name_bg, off_product.name]:
                if not off_name:
                    continue
                    
                off_normalized = self.normalizer.normalize(off_name)
                ratio = SequenceMatcher(None, product_name, off_normalized).ratio()
                
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = Match(
                        product_id=product.id,
                        off_id=off_id,
                        off_barcode=off_product.barcode,
                        match_type='fuzzy',
                        confidence=CONFIDENCE_FUZZY * ratio,
                        details={
                            'fuzzy_ratio': ratio,
                            'off_name': off_name
                        }
                    )
        
        if best_match and best_match.confidence >= MIN_CONFIDENCE:
            self.stats['fuzzy_match'] += 1
            return best_match
            
        return None
    
    def match_product(self, product: Product) -> Optional[Match]:
        """Run full matching pipeline for a product"""
        match = self.match_by_barcode(product)
        if match:
            return match
            
        match = self.match_by_brand_size(product)
        if match and match.confidence >= CONFIDENCE_TOKEN_HIGH:
            return match
            
        match_cosine = self.match_by_cosine_similarity(product)
        
        if match and match_cosine:
            if match.confidence >= match_cosine.confidence * 0.9:
                return match
            return match_cosine
        elif match:
            return match
        elif match_cosine:
            return match_cosine
            
        return self.match_by_fuzzy(product)
    
    def run(self) -> List[Match]:
        """Run the full pipeline"""
        print("\n" + "=" * 60)
        print("HYBRID MATCHING PIPELINE")
        print("=" * 60)
        
        products = self.load_store_products()
        matches: List[Match] = []
        unmatched: List[Product] = []
        
        for i, product in enumerate(products):
            if (i + 1) % 500 == 0:
                print(f"Processing {i+1}/{len(products)}...")
                
            match = self.match_product(product)
            if match:
                matches.append(match)
            else:
                unmatched.append(product)
                self.stats['no_match'] += 1
        
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"\nTotal food products: {len(products)}")
        print(f"Total matches: {len(matches)}")
        print(f"Match rate: {len(matches)/len(products)*100:.1f}%")
        
        print("\nMatch breakdown:")
        print(f"  Barcode (100% confidence): {self.stats['barcode_match']}")
        print(f"  Brand+Size (high conf): {self.stats['brand_size_match']}")
        print(f"  Cosine similarity: {self.stats['cosine_match']}")
        print(f"  Fuzzy matching: {self.stats['fuzzy_match']}")
        print(f"  No match: {self.stats['no_match']}")
        
        conf_high = sum(1 for m in matches if m.confidence >= 0.8)
        conf_med = sum(1 for m in matches if 0.6 <= m.confidence < 0.8)
        conf_low = sum(1 for m in matches if m.confidence < 0.6)
        
        print("\nConfidence distribution:")
        print(f"  High (>=0.8): {conf_high}")
        print(f"  Medium (0.6-0.8): {conf_med}")
        print(f"  Low (<0.6): {conf_low}")
        
        print("\nSample high-confidence matches:")
        for match in sorted(matches, key=lambda m: -m.confidence)[:5]:
            cur = self.promobg_conn.cursor()
            cur.execute('SELECT name FROM products WHERE id = ?', (match.product_id,))
            product_name = cur.fetchone()[0]
            off_name = match.details.get('off_name', self.off_products[match.off_id].name)
            print(f"  [{match.match_type}] {match.confidence:.2f}: '{product_name[:40]}' → '{off_name[:40]}'")
        
        print("\nSample unmatched products:")
        for product in unmatched[:10]:
            print(f"  - {product.name[:60]}")
        
        return matches, unmatched
    
    def save_matches(self, matches: List[Match]):
        """Save matches to database"""
        cur = self.promobg_conn.cursor()
        cur.execute('DELETE FROM product_off_matches')
        
        for match in matches:
            cur.execute('''
                INSERT INTO product_off_matches 
                (product_id, off_product_id, match_type, match_confidence, is_verified, created_at)
                VALUES (?, ?, ?, ?, 0, datetime('now'))
            ''', (match.product_id, match.off_id, match.match_type, match.confidence))
        
        self.promobg_conn.commit()
        print(f"\nSaved {len(matches)} matches to database")
        
    def export_results(self, matches: List[Match], unmatched: List[Product], output_path: Path):
        """Export results to JSON for analysis"""
        products = self.load_store_products()
        results = {
            'stats': dict(self.stats),
            'total_products': len(products),
            'total_matches': len(matches),
            'match_rate_percent': len(matches) / len(products) * 100,
            'matches': [],
            'unmatched': []
        }
        
        cur = self.promobg_conn.cursor()
        for match in matches[:500]:  # Limit for file size
            cur.execute('SELECT name, brand FROM products WHERE id = ?', (match.product_id,))
            row = cur.fetchone()
            off_product = self.off_products[match.off_id]
            
            results['matches'].append({
                'product_id': match.product_id,
                'product_name': row[0],
                'product_brand': row[1],
                'off_id': match.off_id,
                'off_barcode': match.off_barcode,
                'off_name': off_product.name,
                'off_name_bg': off_product.name_bg,
                'match_type': match.match_type,
                'confidence': match.confidence,
                'details': match.details
            })
        
        for product in unmatched[:200]:
            results['unmatched'].append({
                'product_id': product.id,
                'name': product.name,
                'brand': product.brand,
                'store': product.store
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"Exported results to {output_path}")


def main():
    pipeline = MatchingPipeline()
    matches, unmatched = pipeline.run()
    pipeline.save_matches(matches)
    pipeline.export_results(matches, unmatched, BASE_DIR / "matches_results.json")
    
    return {
        'total_food_products': len(pipeline.load_store_products()),
        'total_matches': len(matches),
        'total_unmatched': len(unmatched),
        'stats': dict(pipeline.stats),
        'match_rate': len(matches) / len(pipeline.load_store_products()) * 100
    }


if __name__ == '__main__':
    results = main()
    print(f"\n✓ Pipeline complete. Match rate: {results['match_rate']:.1f}%")
