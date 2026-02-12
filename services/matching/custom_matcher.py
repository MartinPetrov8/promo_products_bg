#!/usr/bin/env python3
"""
Custom Product Matching Algorithm for Bulgarian Grocery Products

Matches the SAME product across different stores by extracting:
- Brand, Product Type, Variant (fat %, flavor), Size

Usage:
    python3 -u custom_matcher.py [--test] [--stats]
"""

import re
import sqlite3
import sys
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Tuple, Dict, Optional
from collections import defaultdict

sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "promobg.db"

# =============================================================================
# BRAND DATABASE - Bulgarian + International brands
# =============================================================================

BRANDS = {
    # Dairy
    'верея': 'vereia', 'vereia': 'vereia', 'vereya': 'vereia',
    'олимпус': 'olympus', 'olympus': 'olympus',
    'данон': 'danone', 'danone': 'danone',
    'активиа': 'activia', 'activia': 'activia',
    'президент': 'president', 'president': 'president',
    'маджаров': 'madjarov', 'madjarov': 'madjarov',
    'саяна': 'sayana', 'елена': 'elena', 'боженци': 'bozhentsi',
    
    # Beverages
    'кока-кола': 'coca-cola', 'coca-cola': 'coca-cola', 'coca cola': 'coca-cola',
    'пепси': 'pepsi', 'pepsi': 'pepsi',
    'фанта': 'fanta', 'fanta': 'fanta',
    'спрайт': 'sprite', 'sprite': 'sprite',
    'швепс': 'schweppes', 'schweppes': 'schweppes',
    'ред бул': 'red-bull', 'red bull': 'red-bull',
    
    # Water
    'девин': 'devin', 'devin': 'devin',
    'банкя': 'bankya', 'bankya': 'bankya',
    'горна баня': 'gorna-banya', 'gorna banya': 'gorna-banya',
    'хисар': 'hisar', 'hisar': 'hisar',
    
    # Sweets
    'милка': 'milka', 'milka': 'milka',
    'орео': 'oreo', 'oreo': 'oreo',
    'нутела': 'nutella', 'nutella': 'nutella',
    'фереро': 'ferrero', 'ferrero': 'ferrero',
    'рафаело': 'raffaello', 'raffaello': 'raffaello',
    'линдт': 'lindt', 'lindt': 'lindt',
    'тоблерон': 'toblerone', 'toblerone': 'toblerone',
    'сникърс': 'snickers', 'snickers': 'snickers',
    'марс': 'mars', 'mars': 'mars',
    'твикс': 'twix', 'twix': 'twix',
    'баунти': 'bounty', 'bounty': 'bounty',
    'kit kat': 'kitkat', 'kitkat': 'kitkat', 'кит кат': 'kitkat',
    'lion': 'lion', 'лион': 'lion',
    'харибо': 'haribo', 'haribo': 'haribo',
    
    # Coffee
    'нескафе': 'nescafe', 'nescafe': 'nescafe',
    'якобс': 'jacobs', 'jacobs': 'jacobs',
    'лаваца': 'lavazza', 'lavazza': 'lavazza',
    'давидоф': 'davidoff', 'davidoff': 'davidoff',
    'tchibo': 'tchibo', 'чибо': 'tchibo',
    
    # Baby/Nestle
    'нестле': 'nestle', 'nestle': 'nestle', 'nestlé': 'nestle',
    
    # Alcohol
    'загорка': 'zagorka', 'zagorka': 'zagorka',
    'каменица': 'kamenitza', 'kamenitza': 'kamenitza',
    'пиринско': 'pirinsko', 'pirinsko': 'pirinsko',
    'шуменско': 'shumensko', 'shumensko': 'shumensko',
    'heineken': 'heineken', 'хайнекен': 'heineken',
    'tuborg': 'tuborg', 'туборг': 'tuborg',
    'carlsberg': 'carlsberg', 'карлсберг': 'carlsberg',
    
    # Cleaning
    'ариел': 'ariel', 'ariel': 'ariel',
    'персил': 'persil', 'persil': 'persil',
    'ленор': 'lenor', 'lenor': 'lenor',
    'финиш': 'finish', 'finish': 'finish',
    'калгон': 'calgon', 'calgon': 'calgon',
    'доместос': 'domestos', 'domestos': 'domestos',
    
    # Care
    'нивеа': 'nivea', 'nivea': 'nivea',
    'гарние': 'garnier', 'garnier': 'garnier',
    'колгейт': 'colgate', 'colgate': 'colgate',
    'палмолив': 'palmolive', 'palmolive': 'palmolive',
    'dove': 'dove', 'дав': 'dove',
    'head & shoulders': 'head-shoulders', 'хед енд шолдърс': 'head-shoulders',
    
    # Store brands
    'k-classic': 'k-classic', 'к-класик': 'k-classic',
    'clever': 'clever', 'клевър': 'clever',
    'chef select': 'chef-select',
    'pilos': 'pilos', 'пилос': 'pilos',
    'milbona': 'milbona',
}

# =============================================================================
# PRODUCT TYPES
# =============================================================================

PRODUCT_TYPES = {
    # Dairy
    'мляко': 'milk', 'прясно мляко': 'milk', 'кисело мляко': 'yogurt',
    'сирене': 'cheese', 'кашкавал': 'kashkaval', 'извара': 'cottage-cheese',
    'масло': 'butter', 'сметана': 'cream', 'йогурт': 'yogurt',
    
    # Meat
    'кайма': 'minced-meat', 'кебапче': 'kebapche', 'кюфте': 'kyufte',
    'пиле': 'chicken', 'пилешко': 'chicken', 'свинско': 'pork', 'телешко': 'beef',
    'филе': 'fillet', 'каре': 'loin', 'бут': 'leg',
    
    # Produce
    'банани': 'bananas', 'банан': 'bananas',
    'ябълки': 'apples', 'ябълка': 'apples',
    'портокали': 'oranges', 'портокал': 'oranges',
    'домати': 'tomatoes', 'домат': 'tomatoes',
    'краставици': 'cucumbers', 'краставица': 'cucumbers',
    'картофи': 'potatoes', 'картоф': 'potatoes',
    'моркови': 'carrots', 'морков': 'carrots',
    'лук': 'onions',
    
    # Bakery
    'хляб': 'bread', 'питка': 'flatbread', 'пърленка': 'parlenka',
    'баничка': 'banitsa', 'козунак': 'kozunak',
    
    # Beverages
    'сок': 'juice', 'нектар': 'nectar',
    'газирана': 'soda', 'напитка': 'drink',
    'вода': 'water', 'минерална': 'mineral-water',
    'бира': 'beer', 'вино': 'wine',
    
    # Sweets
    'шоколад': 'chocolate', 'бонбони': 'candy', 'бисквити': 'biscuits',
    'вафли': 'wafers', 'сладолед': 'ice-cream',
    
    # Snacks
    'чипс': 'chips', 'пуканки': 'popcorn', 'солети': 'pretzels',
    
    # Frozen
    'пица': 'pizza', 'замразени': 'frozen',
    
    # Other
    'яйца': 'eggs', 'олио': 'oil', 'зехтин': 'olive-oil',
    'ориз': 'rice', 'паста': 'pasta', 'спагети': 'spaghetti',
    'кафе': 'coffee', 'чай': 'tea',
}

# =============================================================================
# PROMO TEXT PATTERNS TO STRIP
# =============================================================================

PROMO_PATTERNS = [
    r'king\s+оферта\s*-?\s*',
    r'супер\s+цена\s*-?\s*',
    r'само\s+с\s+billa\s+card\s*-?\s*',
    r'сега\s+в\s+billa\s*-?\s*',
    r'продукт[,\s]+маркиран.*$',
    r'от\s+деликатесната\s+витрина',
    r'от\s+нашата\s+пекарна',
    r'различни\s+видове',
    r'различни\s+вкусове',
]


class AttributeExtractor:
    """Extracts structured attributes from Bulgarian product names."""
    
    def __init__(self):
        self.promo_patterns = [re.compile(p, re.IGNORECASE) for p in PROMO_PATTERNS]
    
    def clean_name(self, name: str) -> str:
        """Remove promotional text."""
        cleaned = name.lower().strip()
        for pattern in self.promo_patterns:
            cleaned = pattern.sub('', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def extract_brand(self, name: str) -> Optional[str]:
        """Extract and normalize brand."""
        name_lower = name.lower()
        
        # Check longest matches first
        for brand in sorted(BRANDS.keys(), key=len, reverse=True):
            if brand in name_lower:
                return BRANDS[brand]
        return None
    
    def extract_type(self, name: str) -> Optional[str]:
        """Extract product type."""
        name_lower = name.lower()
        
        for ptype in sorted(PRODUCT_TYPES.keys(), key=len, reverse=True):
            if ptype in name_lower:
                return PRODUCT_TYPES[ptype]
        return None
    
    def extract_size(self, name: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Extract and normalize size.
        Returns (quantity_normalized, unit) where unit is 'ml' or 'g'
        """
        name_lower = name.lower()
        
        # Multiplier pattern: 6x330мл
        mult_match = re.search(r'(\d+)\s*[xх]\s*(\d+[.,]?\d*)\s*(мл|ml|л|l|г|g|кг|kg)', name_lower)
        if mult_match:
            mult = int(mult_match.group(1))
            qty = float(mult_match.group(2).replace(',', '.'))
            unit_raw = mult_match.group(3)
            
            if unit_raw in ['л', 'l']:
                return (mult * qty * 1000, 'ml')
            elif unit_raw in ['мл', 'ml']:
                return (mult * qty, 'ml')
            elif unit_raw in ['кг', 'kg']:
                return (mult * qty * 1000, 'g')
            else:
                return (mult * qty, 'g')
        
        # Single size patterns
        patterns = [
            (r'(\d+[.,]?\d*)\s*(литър|литра|л)\b', 'ml', 1000),
            (r'(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml', 1),
            (r'(\d+[.,]?\d*)\s*(килограм|кг|kg)\b', 'g', 1000),
            (r'(\d+[.,]?\d*)\s*(грама|гр|г|g)\b', 'g', 1),
        ]
        
        for pattern, unit, factor in patterns:
            match = re.search(pattern, name_lower)
            if match:
                qty = float(match.group(1).replace(',', '.'))
                return (qty * factor, unit)
        
        return (None, None)
    
    def extract_variant(self, name: str) -> List[str]:
        """Extract variants (fat %, flavor, etc.)"""
        name_lower = name.lower()
        variants = []
        
        # Fat percentage
        pct_match = re.search(r'(\d+[.,]?\d*)\s*%', name_lower)
        if pct_match:
            pct = pct_match.group(1).replace(',', '.')
            variants.append(f'{pct}%')
        
        # Milk type
        for v in ['краве', 'козе', 'овче', 'прясно', 'кисело', 'пълномаслено', 'обезмаслено']:
            if v in name_lower:
                variants.append(v)
        
        return variants
    
    def extract(self, name: str) -> Dict:
        """Extract all attributes."""
        cleaned = self.clean_name(name)
        size_qty, size_unit = self.extract_size(cleaned)
        
        return {
            'original': name,
            'cleaned': cleaned,
            'brand': self.extract_brand(cleaned),
            'type': self.extract_type(cleaned),
            'size_qty': size_qty,
            'size_unit': size_unit,
            'variants': self.extract_variant(cleaned),
        }


class ProductMatcher:
    """Matches products across stores using tiered confidence."""
    
    TIERS = {
        1: ('exact', 0.95, 'brand + type + size'),
        2: ('strong', 0.80, 'brand + type'),
        3: ('fuzzy', 0.65, 'type + size'),
        4: ('generic', 0.50, 'type only'),
    }
    
    def __init__(self):
        self.extractor = AttributeExtractor()
    
    def size_matches(self, s1: Tuple, s2: Tuple, tolerance: float = 0.15) -> bool:
        """Check if sizes match within tolerance."""
        qty1, unit1 = s1
        qty2, unit2 = s2
        
        if not qty1 or not qty2:
            return False
        if unit1 != unit2:
            return False
        
        diff = abs(qty1 - qty2) / max(qty1, qty2)
        return diff <= tolerance
    
    def calculate_match(self, p1: Dict, p2: Dict) -> Tuple[float, int]:
        """
        Calculate match confidence and tier.
        Returns (confidence, tier) where tier=0 means no match.
        """
        ext1, ext2 = p1['extracted'], p2['extracted']
        
        brand1, brand2 = ext1.get('brand'), ext2.get('brand')
        type1, type2 = ext1.get('type'), ext2.get('type')
        size1 = (ext1.get('size_qty'), ext1.get('size_unit'))
        size2 = (ext2.get('size_qty'), ext2.get('size_unit'))
        
        brand_match = brand1 and brand2 and brand1 == brand2
        type_match = type1 and type2 and type1 == type2
        size_match = self.size_matches(size1, size2)
        
        # Tier 1: brand + type + size
        if brand_match and type_match and size_match:
            return (0.95, 1)
        
        # Tier 2: brand + type
        if brand_match and type_match:
            return (0.80, 2)
        
        # Tier 3: type + size (no brand or different brand)
        if type_match and size_match:
            return (0.65, 3)
        
        # Tier 4: type only
        if type_match:
            return (0.50, 4)
        
        return (0.0, 0)
    
    def find_matches(self, product: Dict, all_products: List[Dict], 
                     min_confidence: float = 0.65) -> List[Tuple[Dict, float, int]]:
        """Find cross-store matches for a product."""
        matches = []
        
        for other in all_products:
            if other['id'] == product['id']:
                continue
            if other['store'] == product['store']:
                continue
            
            conf, tier = self.calculate_match(product, other)
            if conf >= min_confidence:
                matches.append((other, conf, tier))
        
        return sorted(matches, key=lambda x: -x[1])
    
    def generate_match_key(self, product: Dict) -> str:
        """Generate grouping key for identical products."""
        ext = product['extracted']
        brand = ext.get('brand') or '_'
        ptype = ext.get('type') or '_'
        size = ext.get('size_qty') or 0
        unit = ext.get('size_unit') or '_'
        variants = '|'.join(sorted(ext.get('variants', [])))
        
        return f"{brand}:{ptype}:{size:.0f}{unit}:{variants}"


def load_products(db_path: str = None) -> List[Dict]:
    """Load products from database."""
    db_path = db_path or str(DB_PATH)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.name, p.normalized_name, p.brand, s.name as store
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        WHERE p.deleted_at IS NULL
    ''')
    
    extractor = AttributeExtractor()
    products = []
    seen = set()
    
    for row in cursor.fetchall():
        pid = row[0]
        if pid in seen:
            continue
        seen.add(pid)
        
        product = {
            'id': pid,
            'name': row[1],
            'normalized_name': row[2],
            'brand_db': row[3],
            'store': row[4],
            'extracted': extractor.extract(row[1])
        }
        products.append(product)
    
    conn.close()
    return products


def run_matching(min_confidence: float = 0.65):
    """Run cross-store matching and print results."""
    print("=" * 60)
    print("🔍 Custom Product Matcher - Bulgarian Groceries")
    print("=" * 60)
    
    products = load_products()
    print(f"📦 Loaded {len(products)} products\n")
    
    matcher = ProductMatcher()
    
    # Group products by match key
    groups = defaultdict(list)
    for p in products:
        key = matcher.generate_match_key(p)
        groups[key].append(p)
    
    # Find cross-store matches
    cross_store_groups = []
    for key, group in groups.items():
        stores = set(p['store'] for p in group)
        if len(stores) >= 2:
            cross_store_groups.append((key, group, stores))
    
    # Stats
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    
    print(f"🎯 Found {len(cross_store_groups)} potential cross-store product groups\n")
    print("-" * 60)
    
    # Show top matches
    for key, group, stores in sorted(cross_store_groups, key=lambda x: -len(x[2]))[:30]:
        ext = group[0]['extracted']
        brand = ext.get('brand') or '(generic)'
        ptype = ext.get('type') or '(unknown)'
        size = ext.get('size_qty')
        unit = ext.get('size_unit') or ''
        
        size_str = f"{size:.0f}{unit}" if size else "(no size)"
        
        print(f"\n✅ {brand.upper()} | {ptype} | {size_str}")
        print(f"   Stores: {', '.join(sorted(stores))}")
        
        for p in group[:4]:
            print(f"   • [{p['store'][:8]:8}] {p['name'][:50]}")
        
        # Determine tier
        if ext.get('brand') and ext.get('type') and ext.get('size_qty'):
            tier_counts[1] += 1
        elif ext.get('brand') and ext.get('type'):
            tier_counts[2] += 1
        elif ext.get('type') and ext.get('size_qty'):
            tier_counts[3] += 1
        else:
            tier_counts[4] += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 MATCHING SUMMARY")
    print("=" * 60)
    print(f"Total products:           {len(products)}")
    print(f"Unique match keys:        {len(groups)}")
    print(f"Cross-store groups:       {len(cross_store_groups)}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Tier 1 (brand+type+size): {tier_counts[1]}")
    print(f"Tier 2 (brand+type):      {tier_counts[2]}")
    print(f"Tier 3 (type+size):       {tier_counts[3]}")
    print(f"Tier 4 (type only):       {tier_counts[4]}")
    
    # Products per store in matches
    store_match_counts = defaultdict(int)
    for key, group, stores in cross_store_groups:
        for p in group:
            store_match_counts[p['store']] += 1
    
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("Products in cross-store matches by store:")
    for store, count in sorted(store_match_counts.items()):
        print(f"  {store}: {count}")


if __name__ == '__main__':
    run_matching()
