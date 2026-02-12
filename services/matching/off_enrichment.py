#!/usr/bin/env python3 -u
"""
Open Food Facts Barcode Enrichment Script

Enriches our product database with barcodes from Open Food Facts.
See docs/MATCHING_STRATEGY.md for full documentation.

Usage:
    python3 -u services/matching/off_enrichment.py [--limit N] [--dry-run]
"""

import os
import sys

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
import re
import json
import time
import sqlite3
import argparse
import requests
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import quote
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Constants
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
DB_PATH = PROJECT_ROOT / "data" / "promobg.db"
RESULTS_PATH = PROJECT_ROOT / "services" / "matching" / "data" / "enrichment_results.json"

# Rate limiting - be nice to OFF
REQUEST_DELAY = 1.0  # seconds between requests
MAX_RETRIES = 3

# Matching thresholds
CONFIDENCE_THRESHOLD = 0.55  # Accept matches above this score (lowered for Bulgarian products)
BRAND_WEIGHT = 0.4
TERMS_WEIGHT = 0.4  # 0.1 per term, max 4 terms
QUANTITY_WEIGHT = 0.2


class OFFEnrichment:
    """Enriches products with barcodes from Open Food Facts."""
    
    def __init__(self, db_path: str = None, dry_run: bool = False):
        self.db_path = db_path or str(DB_PATH)
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PromoBG/1.0 (https://github.com/MartinPetrov8/promo_products_bg; contact@promobg.com)'
        })
        
        # Stats
        self.stats = {
            'total_products': 0,
            'already_have_barcode': 0,
            'searched': 0,
            'matches_found': 0,
            'high_confidence': 0,
            'low_confidence': 0,
            'no_match': 0,
            'errors': 0,
            'barcodes_saved': 0,
            'bulk_products_skipped': 0
        }
        
        # Results for review
        self.results = []
        
    def normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        text = text.lower()
        # Remove special characters but keep Cyrillic
        text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', text)
        # Collapse whitespace
        text = ' '.join(text.split())
        return text.strip()
    
    # Known brand mappings (Bulgarian → English/International for OFF search)
    BRAND_MAPPINGS = {
        'верея': 'vereia',
        'олимпус': 'olympus',
        'данон': 'danone',
        'нестле': 'nestle',
        'кока-кола': 'coca-cola',
        'пепси': 'pepsi',
        'фанта': 'fanta',
        'милка': 'milka',
        'орео': 'oreo',
        'якобс': 'jacobs',
        'бондюел': 'bonduelle',
        'кнор': 'knorr',
        'маги': 'maggi',
        'хайнц': 'heinz',
        'хелман': 'hellmanns',
        'президент': 'president',
        'активиа': 'activia',
        'арла': 'arla',
        'алпро': 'alpro',
        'барила': 'barilla',
        'нутела': 'nutella',
        'липтон': 'lipton',
        'ахмад': 'ahmad',
        'девня': 'devnya',
        'девин': 'devin',
        'банкя': 'bankya',
        'горна баня': 'gorna banya',
        'хисаря': 'hisarya',
        'боженци': 'bozhentsi',
        'маджаров': 'madjarov',
        'елена': 'elena',
        'пирин': 'pirin',
        'загорка': 'zagorka',
        'каменица': 'kamenitza',
        'шуменско': 'shumensko',
    }
    
    # Brands that should search exactly as-is (already English/international)
    EXACT_BRANDS = [
        'coca-cola', 'pepsi', 'fanta', 'sprite', 'nestle', 'lion', 'kitkat', 'kit kat',
        'danone', 'activia', 'milka', 'oreo', 'jacobs', 'lavazza', 'nescafe',
        'bonduelle', 'knorr', 'maggi', 'heinz', 'hellmann', 'president',
        'arla', 'alpro', 'barilla', 'de cecco', 'nutella', 'ferrero',
        'lipton', 'ahmad', 'twinings', 'red bull', 'monster',
        'olympus', 'vereia', 'devin', 'bankya', 'gorna banya',
        'hochland', 'philadelphia', 'kiri', 'buko',
        'kellog', 'cheerios', 'snickers', 'mars', 'twix', 'bounty',
        'haribo', 'mentos', 'orbit', 'trident', 'tic tac',
        'pringles', 'lays', 'doritos', 'cheetos',
    ]
    
    def extract_brand(self, name: str, brand_field: str = None) -> str:
        """Extract brand from product."""
        if brand_field:
            return self.normalize_text(brand_field)
        
        name_lower = name.lower()
        
        # Check exact brands first (international names)
        for brand in self.EXACT_BRANDS:
            if brand in name_lower:
                return brand
        
        # Check Bulgarian → English mappings
        for bg_brand, en_brand in self.BRAND_MAPPINGS.items():
            if bg_brand in name_lower:
                return en_brand
        
        return ""
    
    def extract_terms(self, name: str) -> list:
        """Extract key product terms from name."""
        name = self.normalize_text(name)
        
        # Remove common noise words
        noise = ['продукт', 'маркиран', 'синя', 'звезда', 'промо', 'promo', 
                 'нов', 'new', 'био', 'organic', 'еко', 'eco']
        
        words = name.split()
        terms = [w for w in words if w not in noise and len(w) > 2]
        
        return terms[:6]  # Max 6 terms
    
    def extract_quantity(self, name: str) -> str:
        """Extract quantity/size from product name."""
        # Match patterns like "500 г", "1 л", "0.5л", "330 мл"
        patterns = [
            r'(\d+(?:[.,]\d+)?)\s*(кг|г|гр|л|мл|ml|l|g|kg)',
            r'(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(г|гр|мл|ml)',
            r'(\d+)\s*бр'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, name.lower())
            if match:
                return match.group(0)
        return ""
    
    def is_bulk_product(self, product: dict) -> bool:
        """Detect if product is bulk (no barcode possible)."""
        name = product.get('name', '').lower()
        unit = product.get('unit', '')
        
        bulk_indicators = [
            unit == 'кг',
            'на кг' in name,
            'пресен' in name or 'прясна' in name,
            any(term in name for term in ['банани', 'портокали', 'ябълки', 'домати', 
                                          'краставици', 'картофи', 'моркови', 'лук',
                                          'чушки', 'тиквички', 'патладжан'])
        ]
        
        return sum(bulk_indicators) >= 2
    
    def search_off(self, brand: str, terms: list, page_size: int = 10) -> list:
        """Search Open Food Facts for matching products."""
        # Build search query
        search_terms = ' '.join(terms)
        if brand:
            search_terms = f"{brand} {search_terms}"
        
        params = {
            'search_terms': search_terms,
            'tagtype_0': 'countries',
            'tag_contains_0': 'contains',
            'tag_0': 'bulgaria',
            'json': '1',
            'page_size': page_size,
            'fields': 'code,product_name,brands,quantity,categories_tags,image_url'
        }
        
        try:
            time.sleep(REQUEST_DELAY)
            response = self.session.get(OFF_SEARCH_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('products', [])
        except Exception as e:
            print(f"    ⚠ OFF search error: {e}")
            return []
    
    def search_off_global(self, brand: str, terms: list) -> list:
        """Search OFF globally (fallback when Bulgaria filter returns nothing)."""
        search_terms = ' '.join(terms)
        if brand:
            search_terms = f"{brand} {search_terms}"
        
        params = {
            'search_terms': search_terms,
            'json': '1',
            'page_size': 5,
            'fields': 'code,product_name,brands,quantity,categories_tags,image_url'
        }
        
        try:
            time.sleep(REQUEST_DELAY)
            response = self.session.get(OFF_SEARCH_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('products', [])
        except Exception as e:
            print(f"    ⚠ OFF global search error: {e}")
            return []
    
    def calculate_confidence(self, off_product: dict, our_product: dict) -> float:
        """Calculate match confidence score."""
        score = 0.0
        
        off_name = self.normalize_text(off_product.get('product_name', ''))
        off_brands = self.normalize_text(off_product.get('brands', ''))
        our_name = self.normalize_text(our_product.get('name', ''))
        our_brand = self.extract_brand(our_product.get('name', ''), our_product.get('brand'))
        
        # Brand match: +0.4
        if our_brand and off_brands:
            if our_brand in off_brands or off_brands in our_brand:
                score += BRAND_WEIGHT
            elif SequenceMatcher(None, our_brand, off_brands).ratio() > 0.8:
                score += BRAND_WEIGHT * 0.8
        
        # Terms match: +0.1 each (max 0.4)
        our_terms = self.extract_terms(our_product.get('name', ''))
        terms_matched = 0
        for term in our_terms[:4]:
            if term in off_name or term in off_brands:
                terms_matched += 1
        score += min(terms_matched * 0.1, TERMS_WEIGHT)
        
        # Quantity match: +0.2
        our_qty = self.extract_quantity(our_product.get('name', ''))
        off_qty = self.normalize_text(off_product.get('quantity', ''))
        if our_qty and off_qty:
            # Normalize quantities for comparison
            our_qty_norm = re.sub(r'\s+', '', our_qty)
            off_qty_norm = re.sub(r'\s+', '', off_qty)
            if our_qty_norm in off_qty_norm or off_qty_norm in our_qty_norm:
                score += QUANTITY_WEIGHT
            elif SequenceMatcher(None, our_qty_norm, off_qty_norm).ratio() > 0.7:
                score += QUANTITY_WEIGHT * 0.5
        
        # Overall name similarity bonus (up to 0.2)
        name_sim = SequenceMatcher(None, our_name, off_name).ratio()
        score += name_sim * 0.2
        
        return min(score, 1.0)
    
    def find_best_match(self, product: dict) -> tuple:
        """Find best matching OFF product. Returns (barcode, confidence, off_product)."""
        brand = self.extract_brand(product.get('name', ''), product.get('brand'))
        terms = self.extract_terms(product.get('name', ''))
        
        if not brand and not terms:
            return None, 0, None
        
        results = []
        
        # Strategy 1: Brand-only search (most effective for international brands)
        if brand:
            # Search by brand with product type terms
            product_type_terms = [t for t in terms if t in [
                'мляко', 'сирене', 'кашкавал', 'кисело', 'сок', 'вода', 'бира',
                'шоколад', 'бисквити', 'чипс', 'кафе', 'чай', 'паста', 'макарони',
                'milk', 'cheese', 'yogurt', 'juice', 'water', 'beer', 'chocolate',
                'coffee', 'tea', 'pasta', 'chips', 'biscuits', 'cookies'
            ]][:2]
            
            search_terms = [brand] + product_type_terms
            results = self.search_off(brand, search_terms)
            
            # Try global if Bulgaria filter returns nothing
            if not results:
                results = self.search_off_global(brand, search_terms)
        
        # Strategy 2: Full terms search if brand-only didn't work
        if not results and terms:
            results = self.search_off(brand, terms)
            if not results:
                results = self.search_off_global(brand, terms)
        
        if not results:
            return None, 0, None
        
        # Find best match
        best_match = None
        best_confidence = 0
        
        for off_product in results:
            confidence = self.calculate_confidence(off_product, product)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = off_product
        
        if best_match and best_confidence >= CONFIDENCE_THRESHOLD:
            return best_match.get('code'), best_confidence, best_match
        
        return None, best_confidence, best_match
    
    def get_products(self, limit: int = None) -> list:
        """Fetch products from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = """
            SELECT p.id, p.name, p.normalized_name, p.brand, p.barcode_ean, 
                   p.unit, p.quantity, s.name as store_name
            FROM products p
            JOIN store_products sp ON p.id = sp.product_id
            JOIN stores s ON sp.store_id = s.id
            WHERE p.deleted_at IS NULL
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        products = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Deduplicate by product id
        seen = set()
        unique = []
        for p in products:
            if p['id'] not in seen:
                seen.add(p['id'])
                unique.append(p)
        
        return unique
    
    def save_barcode(self, product_id: int, barcode: str, confidence: float):
        """Save barcode to database."""
        if self.dry_run:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE products 
            SET barcode_ean = ?, match_confidence = ?, updated_at = ?
            WHERE id = ?
        """, (barcode, confidence, datetime.now().isoformat(), product_id))
        
        conn.commit()
        conn.close()
        self.stats['barcodes_saved'] += 1
    
    def save_results(self):
        """Save detailed results for review."""
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        output = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.stats,
            'results': self.results
        }
        
        with open(RESULTS_PATH, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 Detailed results saved to: {RESULTS_PATH}")
    
    def run(self, limit: int = None):
        """Run enrichment process."""
        print("=" * 60)
        print("🔍 Open Food Facts Barcode Enrichment")
        print("=" * 60)
        
        if self.dry_run:
            print("⚠️  DRY RUN - no changes will be saved\n")
        
        products = self.get_products(limit)
        self.stats['total_products'] = len(products)
        
        print(f"📦 Found {len(products)} products to process\n")
        
        for i, product in enumerate(products, 1):
            name = product['name'][:50] + ('...' if len(product['name']) > 50 else '')
            print(f"[{i}/{len(products)}] {name}")
            
            # Skip if already has barcode
            if product.get('barcode_ean'):
                print(f"    ✓ Already has barcode: {product['barcode_ean']}")
                self.stats['already_have_barcode'] += 1
                continue
            
            # Skip bulk products
            if self.is_bulk_product(product):
                print(f"    ⏭ Bulk product (no barcode possible)")
                self.stats['bulk_products_skipped'] += 1
                continue
            
            # Search OFF
            self.stats['searched'] += 1
            barcode, confidence, off_product = self.find_best_match(product)
            
            result = {
                'product_id': product['id'],
                'product_name': product['name'],
                'product_brand': product.get('brand'),
                'store': product.get('store_name'),
                'barcode_found': barcode,
                'confidence': round(confidence, 3),
                'off_product_name': off_product.get('product_name') if off_product else None,
                'off_brands': off_product.get('brands') if off_product else None
            }
            self.results.append(result)
            
            if barcode:
                self.stats['matches_found'] += 1
                if confidence >= 0.8:
                    self.stats['high_confidence'] += 1
                    print(f"    ✅ MATCH: {barcode} (confidence: {confidence:.0%})")
                    print(f"       OFF: {off_product.get('product_name', 'N/A')}")
                    self.save_barcode(product['id'], barcode, confidence)
                else:
                    self.stats['low_confidence'] += 1
                    print(f"    🟡 Low confidence: {barcode} ({confidence:.0%})")
                    print(f"       OFF: {off_product.get('product_name', 'N/A')}")
                    # Still save, but flag for review
                    self.save_barcode(product['id'], barcode, confidence)
            else:
                self.stats['no_match'] += 1
                if off_product:
                    print(f"    ❌ No match (best: {confidence:.0%})")
                else:
                    print(f"    ❌ No results found")
        
        # Print summary
        self.print_summary()
        self.save_results()
    
    def print_summary(self):
        """Print final summary."""
        print("\n" + "=" * 60)
        print("📊 ENRICHMENT SUMMARY")
        print("=" * 60)
        print(f"Total products:           {self.stats['total_products']}")
        print(f"Already had barcode:      {self.stats['already_have_barcode']}")
        print(f"Bulk products (skipped):  {self.stats['bulk_products_skipped']}")
        print(f"Searched in OFF:          {self.stats['searched']}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Matches found:            {self.stats['matches_found']}")
        print(f"  - High confidence:      {self.stats['high_confidence']}")
        print(f"  - Low confidence:       {self.stats['low_confidence']}")
        print(f"No match:                 {self.stats['no_match']}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Barcodes saved:           {self.stats['barcodes_saved']}")
        
        if self.stats['searched'] > 0:
            match_rate = self.stats['matches_found'] / self.stats['searched'] * 100
            print(f"Match rate:               {match_rate:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='Enrich products with barcodes from Open Food Facts')
    parser.add_argument('--limit', type=int, help='Limit number of products to process')
    parser.add_argument('--dry-run', action='store_true', help='Do not save changes to database')
    args = parser.parse_args()
    
    enricher = OFFEnrichment(dry_run=args.dry_run)
    enricher.run(limit=args.limit)


if __name__ == '__main__':
    main()
