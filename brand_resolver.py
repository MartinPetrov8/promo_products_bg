"""
Brand Resolution Pipeline

Resolves product brands using multiple strategies to minimize OCR costs:
1. Name pattern matching (free)
2. House brand detection (free)
3. Image hash cache (free after initial OCR)
4. OCR extraction (last resort, ~$0.002/image)

Usage:
    resolver = BrandResolver('data/promobg.db')
    brand_info = resolver.resolve(product_name, store, image_url)
"""

import re
import sqlite3
import json
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime

# House brands per store (private labels)
HOUSE_BRANDS = {
    'Lidl': [
        'Milbona', 'Pilos', 'Crivit', 'Parkside', 'Kania', 'Freshona',
        'W5', 'Cien', 'Dulano', 'Tronic', 'Solevita', 'Bellarom',
        'Sondey', 'Crownfield', 'Floralys', 'Crivit Pro', 'Livarno',
        'Silvercrest', 'Esmara', 'Livergy', 'Lupilu', 'Chef Select',
        'Ocean Sea', 'Biotrend', 'Snack Day', 'Tower', 'Fin Carré',
        'PIKOK', 'Pikok', 'Mister Choc', 'Gelatelli', 'Italiamo',
        'Sol & Mar', 'Deluxe', 'Harvest Basket', 'Simply', 'Combino'
    ],
    'Kaufland': [
        'K-Classic', 'K-Bio', 'K-Take It Veggie', 'K-Favourites',
        'K-Free From', 'K-Budget', 'K-Purland', 'Exquisit',
        'Bevola', 'Sun Snacks', 'Gut Langenhof'
    ],
    'Billa': [
        'Clever', 'Billa Bio', 'Billa Premium', 'Chef Select',
        'Spar', 'S-Budget', 'Spar Natur Pur', 'Spar Premium',
        'Billa Corso', 'Da Pronto', 'Billa Extra'
    ]
}

# Known brand variations (OCR often captures these differently)
BRAND_ALIASES = {
    'MILBONA': 'Milbona',
    'PARKSIDE': 'Parkside',
    'PILOS': 'Pilos',
    'KANIA': 'Kania',
    'FRESHONA': 'Freshona',
    'CIEN': 'Cien',
    'CROWNFIELD': 'Crownfield',
    'РОДНА СТРЯХА': 'Родна Стряха',
    'МЕСКО': 'Меско',
    'ТАНДЕМ': 'Тандем',
    'РАФТИС': 'Рафтис',
}


@dataclass
class BrandResult:
    brand: Optional[str]
    method: str  # 'name_pattern', 'house_brand', 'image_cache', 'ocr', 'unknown'
    confidence: float
    raw_match: Optional[str] = None


class BrandResolver:
    def __init__(self, db_path: str = 'data/promobg.db'):
        self.db_path = db_path
        self.brand_patterns: List[Tuple[re.Pattern, str]] = []
        self._init_db()
        self._load_patterns()
    
    def _init_db(self):
        """Initialize brand resolution tables."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Brand patterns table
        c.execute("""
            CREATE TABLE IF NOT EXISTS brand_patterns (
                id INTEGER PRIMARY KEY,
                pattern TEXT NOT NULL,
                brand TEXT NOT NULL,
                store_id INTEGER,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pattern, brand)
            )
        """)
        
        # Image hash cache
        c.execute("""
            CREATE TABLE IF NOT EXISTS brand_image_cache (
                id INTEGER PRIMARY KEY,
                image_url TEXT NOT NULL UNIQUE,
                image_hash TEXT,
                brand TEXT,
                ocr_text TEXT,
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # OCR queue
        c.execute("""
            CREATE TABLE IF NOT EXISTS brand_ocr_queue (
                id INTEGER PRIMARY KEY,
                product_id INTEGER,
                image_url TEXT NOT NULL,
                store TEXT,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _load_patterns(self):
        """Load brand patterns from database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT pattern, brand FROM brand_patterns ORDER BY confidence DESC")
        for row in c.fetchall():
            try:
                pattern = re.compile(row[0], re.IGNORECASE)
                self.brand_patterns.append((pattern, row[1]))
            except re.error:
                pass
        
        conn.close()
        
        # Add house brand patterns
        for store, brands in HOUSE_BRANDS.items():
            for brand in brands:
                # Match brand name as word boundary
                pattern = re.compile(rf'\b{re.escape(brand)}\b', re.IGNORECASE)
                self.brand_patterns.append((pattern, brand))
    
    def resolve(self, name: str, store: str = None, image_url: str = None) -> BrandResult:
        """
        Resolve brand for a product using multiple strategies.
        
        Args:
            name: Product name
            store: Store name (Lidl, Kaufland, Billa)
            image_url: Product image URL (for cache lookup)
        
        Returns:
            BrandResult with brand, method, and confidence
        """
        # Strategy 1: Name pattern match
        result = self._match_name_pattern(name)
        if result.brand:
            return result
        
        # Strategy 2: House brand detection
        if store:
            result = self._detect_house_brand(name, store)
            if result.brand:
                return result
        
        # Strategy 3: Image hash cache lookup
        if image_url:
            result = self._lookup_image_cache(image_url)
            if result.brand:
                return result
        
        # No match found
        return BrandResult(brand=None, method='unknown', confidence=0.0)
    
    def _match_name_pattern(self, name: str) -> BrandResult:
        """Match product name against known brand patterns."""
        # Check direct aliases first
        for alias, normalized in BRAND_ALIASES.items():
            if alias.lower() in name.lower():
                return BrandResult(
                    brand=normalized,
                    method='name_pattern',
                    confidence=0.95,
                    raw_match=alias
                )
        
        # Check regex patterns
        for pattern, brand in self.brand_patterns:
            match = pattern.search(name)
            if match:
                return BrandResult(
                    brand=brand,
                    method='name_pattern',
                    confidence=0.90,
                    raw_match=match.group()
                )
        
        return BrandResult(brand=None, method='name_pattern', confidence=0.0)
    
    def _detect_house_brand(self, name: str, store: str) -> BrandResult:
        """Detect house brand based on store."""
        if store not in HOUSE_BRANDS:
            return BrandResult(brand=None, method='house_brand', confidence=0.0)
        
        name_lower = name.lower()
        for brand in HOUSE_BRANDS[store]:
            if brand.lower() in name_lower:
                return BrandResult(
                    brand=brand,
                    method='house_brand',
                    confidence=0.85,
                    raw_match=brand
                )
        
        return BrandResult(brand=None, method='house_brand', confidence=0.0)
    
    def _lookup_image_cache(self, image_url: str) -> BrandResult:
        """Look up brand from image cache."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            SELECT brand, confidence FROM brand_image_cache 
            WHERE image_url = ? AND brand IS NOT NULL
        """, (image_url,))
        
        row = c.fetchone()
        conn.close()
        
        if row:
            return BrandResult(
                brand=row[0],
                method='image_cache',
                confidence=row[1] or 0.80
            )
        
        return BrandResult(brand=None, method='image_cache', confidence=0.0)
    
    def queue_for_ocr(self, product_id: int, image_url: str, store: str = None, priority: int = 0):
        """Add product to OCR queue."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR IGNORE INTO brand_ocr_queue (product_id, image_url, store, priority)
            VALUES (?, ?, ?, ?)
        """, (product_id, image_url, store, priority))
        
        conn.commit()
        conn.close()
    
    def add_pattern(self, pattern: str, brand: str, source: str = 'manual', confidence: float = 1.0):
        """Add a brand pattern to the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR REPLACE INTO brand_patterns (pattern, brand, source, confidence)
            VALUES (?, ?, ?, ?)
        """, (pattern, brand, source, confidence))
        
        conn.commit()
        conn.close()
        
        # Add to in-memory patterns
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self.brand_patterns.append((compiled, brand))
        except re.error:
            pass
    
    def add_image_cache(self, image_url: str, brand: str, ocr_text: str = None, confidence: float = 0.80):
        """Add image to brand cache."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            INSERT OR REPLACE INTO brand_image_cache (image_url, brand, ocr_text, confidence)
            VALUES (?, ?, ?, ?)
        """, (image_url, brand, ocr_text, confidence))
        
        conn.commit()
        conn.close()
    
    def resolve_batch(self, products: List[Dict]) -> List[Dict]:
        """
        Resolve brands for multiple products.
        
        Args:
            products: List of dicts with 'name', 'store', 'image_url', 'id'
        
        Returns:
            List of products with added 'brand' and 'brand_method' fields
        """
        results = []
        for p in products:
            result = self.resolve(
                name=p.get('name', ''),
                store=p.get('store'),
                image_url=p.get('image_url')
            )
            p['brand'] = result.brand
            p['brand_method'] = result.method
            p['brand_confidence'] = result.confidence
            results.append(p)
        
        return results
    
    def get_stats(self) -> Dict:
        """Get resolution statistics."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM brand_patterns")
        pattern_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM brand_image_cache WHERE brand IS NOT NULL")
        cache_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM brand_ocr_queue WHERE status = 'pending'")
        queue_count = c.fetchone()[0]
        
        conn.close()
        
        return {
            'patterns': pattern_count,
            'cached_images': cache_count,
            'pending_ocr': queue_count,
            'house_brands': sum(len(brands) for brands in HOUSE_BRANDS.values())
        }


def build_patterns_from_ocr(ocr_results_path: str, resolver: BrandResolver):
    """Build brand patterns from OCR results."""
    with open(ocr_results_path, 'r') as f:
        results = json.load(f)
    
    added = 0
    for item in results:
        brand = item.get('brand')
        if not brand:
            continue
        
        # Create pattern from brand name
        pattern = rf'\b{re.escape(brand)}\b'
        resolver.add_pattern(pattern, brand, source='ocr', confidence=0.90)
        
        # Add image to cache
        image_url = item.get('image_url')
        if image_url:
            resolver.add_image_cache(
                image_url=image_url,
                brand=brand,
                ocr_text=item.get('ocr_text'),
                confidence=0.85
            )
        
        added += 1
    
    return added


if __name__ == '__main__':
    # Test the resolver
    resolver = BrandResolver('data/promobg.db')
    
    test_cases = [
        ("Милбона Кашкавал от краве мляко", "Lidl"),
        ("Parkside® Акумулаторна батерия", "Lidl"),
        ("K-Classic Прясно мляко 3.5%", "Kaufland"),
        ("Clever Кисело мляко", "Billa"),
        ("Саяна Кашкавал", None),  # National brand
    ]
    
    print("Brand Resolution Test")
    print("=" * 60)
    
    for name, store in test_cases:
        result = resolver.resolve(name, store)
        print(f"\n{name[:40]}")
        print(f"  → Brand: {result.brand or 'UNKNOWN'}")
        print(f"  → Method: {result.method}")
        print(f"  → Confidence: {result.confidence:.2f}")
    
    print("\n" + "=" * 60)
    stats = resolver.get_stats()
    print(f"Stats: {stats}")
