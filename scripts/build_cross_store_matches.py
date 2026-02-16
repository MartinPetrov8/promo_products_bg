#!/usr/bin/env python3
"""
Build cross-store product matches from scratch.
Uses name similarity + brand matching + QUANTITY VALIDATION.

v2.0: Added quantity extraction and validation to prevent false matches
      (e.g., 50ml whisky matched to 700ml bottle)
"""
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Tuple

REPO = Path(__file__).parent.parent
INPUT_FILE = REPO / "docs" / "data" / "products.json"
OUTPUT_FILE = REPO / "docs" / "data" / "products_matched.json"

# Thresholds
MIN_SIMILARITY = 0.55
MIN_PRICE = 0.05
MAX_PRICE_RATIO = 2.5  # Only used when quantities match
MAX_PRICE_RATIO_NO_QTY = 3.0  # Stricter when no quantity info

# Stopwords (quantity units removed - we handle them separately)
STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'различни', 'видове', 
             'избрани', 'нашата', 'пекарна', 'витрина', 'свежата', 'промопакет',
             'lidl', 'kaufland', 'billa'}

# Known brand list
BRANDS = {
    'верея', 'олимпус', 'президент', 'данон', 'активиа', 'мюзли',
    'coca-cola', 'кока-кола', 'пепси', 'pepsi', 'фанта', 'fanta', 'спрайт', 'sprite',
    'нестле', 'nestle', 'нескафе', 'nescafe', 'якобс', 'jacobs', 'лаваца', 'lavazza',
    'милка', 'milka', 'орео', 'oreo', 'линдт', 'lindt', 'тоблерон', 'toblerone',
    'харибо', 'haribo', 'сникърс', 'snickers', 'марс', 'mars', 'твикс', 'twix',
    'heinz', 'хайнц', 'hellmann', 'хелман', 'bonduelle', 'бондюел',
    'ariel', 'ариел', 'persil', 'персил', 'lenor', 'ленор',
    'nivea', 'нивеа', 'dove', 'дав', 'garnier', 'гарние', 'colgate', 'колгейт',
    'gillette', 'жилет', 'oral-b', 'oral b',
    'загорка', 'каменица', 'heineken', 'хайнекен', 'carlsberg', 'карлсберг',
    'девин', 'devin', 'банкя', 'горна баня', 'хисаря', 'велинград',
    'tchibo', 'чибо', 'melitta', 'мелита', 'kimbo', 'кимбо', 'lavazza',
    'nutella', 'нутела', 'kinder', 'киндер', 'ferrero', 'фереро',
    'stella artois', 'стела артоа', 'budweiser', 'будвайзер',
    'muhler', 'мюлер', 'brio', 'брио', 'tefal', 'тефал', 'philips', 'филипс',
    'bacardi', 'бакарди', 'johnnie walker', 'джони уокър', 'jack daniels',
    'smirnoff', 'смирноф', 'absolut', 'абсолют', 'jagermeister', 'йегермайстер'
}

# Food keywords for Lidl price fix
FOOD_KEYWORDS = [
    'хляб', 'донат', 'мъфин', 'кифла', 'баничка', 'кроасан', 'земел', 
    'брецел', 'бейгъл', 'брускета', 'пура', 'кит кат', 'орео', 'milka',
    'лаваш', 'питка', 'франзела', 'козунак', 'руло', 'торта', 'кекс',
    'бисквита', 'вафла', 'шоколад', 'бонбон', 'джинджифил', 'сладкиш'
]

NONFOOD_KEYWORDS = [
    'бормашина', 'прахосмукачка', 'фурна', 'фрайър', 'миксер', 'блендер',
    'уред', 'машина', 'станция', 'инструмент', 'акумулаторн', 'електрическ'
]

# ============================================================================
# QUANTITY EXTRACTION (NEW IN v2)
# ============================================================================

@dataclass
class QuantityInfo:
    """Extracted quantity from product name"""
    value: float
    unit: str  # normalized: 'ml', 'g', 'бр'
    original: str
    
    def to_base(self) -> Tuple[float, str]:
        """Convert to base unit (ml or g)"""
        if self.unit == 'l':
            return self.value * 1000, 'ml'
        if self.unit == 'kg':
            return self.value * 1000, 'g'
        return self.value, self.unit
    
    def is_compatible(self, other: 'QuantityInfo', tolerance: float = 0.25) -> bool:
        """Check if quantities are similar enough to be same product"""
        b1 = self.to_base()
        b2 = other.to_base()
        
        # Must be same unit type
        if b1[1] != b2[1]:
            return False
        
        if b1[0] == 0 or b2[0] == 0:
            return False
        
        ratio = b1[0] / b2[0]
        return (1 - tolerance) <= ratio <= (1 + tolerance)


# Patterns ordered by specificity (pack patterns first)
QUANTITY_PATTERNS = [
    # Pack patterns: "6x330ml", "4х500мл"
    (r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(?:мл|ml)', 'ml', True),
    (r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(?:гр?|g)', 'g', True),
    (r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(?:л|l)', 'l', True),
    
    # Single unit patterns
    (r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)', 'ml', False),
    (r'(\d+(?:[.,]\d+)?)\s*(?:л|l|L)(?:\s|$|[^a-zA-Zа-яА-Я])', 'l', False),
    (r'(\d+(?:[.,]\d+)?)\s*(?:cl|сл)', 'cl', False),  # centiliters
    (r'(\d+(?:[.,]\d+)?)\s*(?:гр?|g)(?:\s|$|[^a-zA-Zа-яА-Я])', 'g', False),
    (r'(\d+(?:[.,]\d+)?)\s*(?:кг|kg)', 'kg', False),
    (r'(\d+)\s*(?:бр|бройки|pcs|шт)', 'бр', False),
]


def extract_quantity(name: str) -> Optional[QuantityInfo]:
    """Extract quantity from product name."""
    if not name:
        return None
    
    name_lower = name.lower()
    
    for pattern, unit, is_pack in QUANTITY_PATTERNS:
        match = re.search(pattern, name_lower)
        if match:
            groups = match.groups()
            
            if is_pack and len(groups) == 2:
                # Pack format: count x amount
                count = float(groups[0])
                amount = float(groups[1].replace(',', '.'))
                value = count * amount
            else:
                value = float(groups[0].replace(',', '.'))
            
            # Convert centiliters to ml
            if unit == 'cl':
                value *= 10
                unit = 'ml'
            
            return QuantityInfo(value=value, unit=unit, original=match.group(0))
    
    return None


def quantities_compatible(name1: str, name2: str) -> Tuple[bool, str]:
    """
    Check if two products have compatible quantities.
    Returns (is_compatible, reason)
    """
    qty1 = extract_quantity(name1)
    qty2 = extract_quantity(name2)
    
    # Both have quantities - must match
    if qty1 and qty2:
        if qty1.is_compatible(qty2):
            return True, f"quantities match ({qty1.original} ≈ {qty2.original})"
        else:
            return False, f"quantity mismatch ({qty1.original} vs {qty2.original})"
    
    # Only one has quantity - suspicious but allow with stricter price check
    if qty1 or qty2:
        return True, "partial quantity (needs price check)"
    
    # Neither has quantity - allow with price check
    return True, "no quantities"


# ============================================================================
# ORIGINAL FUNCTIONS (with quantity integration)
# ============================================================================

def normalize_name(name):
    """Normalize product name for matching."""
    name = name.lower()
    name = re.sub(r'\|\s*lidl\s*$', '', name)  # Remove "| LIDL"
    name = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', name)
    # DON'T remove quantity anymore - we need it for validation
    # name = re.sub(r'\d+\s*(г|гр|кг|мл|л|бр)\.?\s*$', '', name)  # REMOVED
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def extract_tokens(name):
    """Extract meaningful tokens."""
    name = normalize_name(name)
    words = name.split()
    return set(w for w in words if w not in STOPWORDS and len(w) >= 2)

def extract_brand(name):
    """Extract brand from product name."""
    name_lower = name.lower()
    for brand in BRANDS:
        if brand in name_lower:
            return brand
    words = normalize_name(name).split()
    if words and len(words[0]) >= 3:
        return words[0]
    return None

def is_food_item(name):
    name_lower = name.lower()
    for kw in NONFOOD_KEYWORDS:
        if kw in name_lower:
            return False
    for kw in FOOD_KEYWORDS:
        if kw in name_lower:
            return True
    return False

def fix_lidl_price(product):
    if product['store'] != 'Lidl':
        return
    price = product.get('price', 0)
    if price and price > 50 and is_food_item(product['name']):
        product['price'] = round(price / 100, 2)
        if product.get('old_price'):
            product['old_price'] = round(product['old_price'] / 100, 2)

def similarity(name1, name2):
    """Calculate similarity between two product names."""
    tokens1 = extract_tokens(name1)
    tokens2 = extract_tokens(name2)
    
    if not tokens1 or not tokens2:
        return 0
    
    # Jaccard similarity
    common = len(tokens1 & tokens2)
    total = len(tokens1 | tokens2)
    jaccard = common / total if total > 0 else 0
    
    # Sequence similarity
    seq = SequenceMatcher(None, normalize_name(name1), normalize_name(name2)).ratio()
    
    return jaccard * 0.6 + seq * 0.4

def find_matches(products):
    """Find cross-store matches using name similarity + quantity validation."""
    by_store = defaultdict(list)
    for p in products:
        by_store[p['store']].append(p)
    
    stores = list(by_store.keys())
    matches = []
    used = set()
    rejected_qty = 0  # Track quantity-based rejections
    
    print(f"\nProducts by store:")
    for store, prods in by_store.items():
        print(f"  {store}: {len(prods)}")
    
    for i, store1 in enumerate(stores):
        for store2 in stores[i+1:]:
            print(f"\nMatching {store1} vs {store2}...")
            
            prods1 = [p for p in by_store[store1] if p['id'] not in used]
            prods2 = [p for p in by_store[store2] if p['id'] not in used]
            
            match_count = 0
            for p1 in prods1:
                if p1['id'] in used:
                    continue
                
                brand1 = extract_brand(p1['name'])
                best_match = None
                best_sim = 0
                
                for p2 in prods2:
                    if p2['id'] in used:
                        continue
                    
                    # Brand check
                    brand2 = extract_brand(p2['name'])
                    if brand1 and brand2 and brand1 != brand2:
                        continue
                    
                    sim = similarity(p1['name'], p2['name'])
                    if sim < MIN_SIMILARITY:
                        continue
                    
                    # ===== QUANTITY VALIDATION (NEW) =====
                    qty_ok, qty_reason = quantities_compatible(p1['name'], p2['name'])
                    if not qty_ok:
                        rejected_qty += 1
                        continue  # REJECT: different sizes
                    
                    # Price check (stricter if no quantity info)
                    price1 = p1.get('price', 0)
                    price2 = p2.get('price', 0)
                    if price1 and price2 and min(price1, price2) > 0:
                        ratio = max(price1, price2) / min(price1, price2)
                        
                        # Use stricter ratio when quantities unknown
                        qty1 = extract_quantity(p1['name'])
                        qty2 = extract_quantity(p2['name'])
                        
                        if qty1 and qty2:
                            # Both have quantities and they matched - allow normal ratio
                            max_ratio = MAX_PRICE_RATIO
                        else:
                            # Missing quantity info - be stricter
                            max_ratio = MAX_PRICE_RATIO_NO_QTY
                        
                        if ratio > max_ratio:
                            continue
                    
                    if sim > best_sim:
                        best_sim = sim
                        best_match = p2
                
                if best_match:
                    matches.append({
                        'products': [p1, best_match],
                        'similarity': best_sim,
                        'brand': brand1
                    })
                    used.add(p1['id'])
                    used.add(best_match['id'])
                    match_count += 1
            
            print(f"  Found {match_count} matches")
    
    print(f"\n⚠️  Rejected {rejected_qty} matches due to quantity mismatch")
    return matches

def main():
    print("=" * 60)
    print("CROSS-STORE MATCHER v2.0 (with quantity validation)")
    print("=" * 60)
    
    print("\nLoading data...")
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    products = data['products']
    print(f"Total products: {len(products)}")
    
    # Fix Lidl prices
    print("\nFixing Lidl prices...")
    for p in products:
        fix_lidl_price(p)
    
    # Filter bad prices
    products = [p for p in products if p.get('price', 0) >= MIN_PRICE]
    print(f"After price filter: {len(products)}")
    
    # Clear old group_ids
    for p in products:
        p['group_id'] = None
        p['match_type'] = None
        p['match_confidence'] = None
        p['off_barcode'] = None
    
    # Find matches
    matches = find_matches(products)
    print(f"\nTotal matches found: {len(matches)}")
    
    # Assign group IDs
    groups = {}
    for i, match in enumerate(matches):
        gid = f"g_{hashlib.md5(str(i).encode()).hexdigest()[:8]}"
        
        for p in match['products']:
            for prod in products:
                if prod['id'] == p['id']:
                    prod['group_id'] = gid
                    prod['match_type'] = 'name_similarity'
                    prod['match_confidence'] = round(match['similarity'], 2)
        
        prices = [p['price'] for p in match['products'] if p.get('price')]
        groups[gid] = {
            'product_ids': [p['id'] for p in match['products']],
            'stores': list(set(p['store'] for p in match['products'])),
            'min_price': min(prices) if prices else None,
            'max_price': max(prices) if prices else None,
            'brand': match['brand']
        }
    
    # Build output
    output = {
        'meta': {
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'total_products': len(products),
            'cross_store_groups': len(groups),
            'stores': ['Kaufland', 'Lidl', 'Billa'],
            'matcher_version': '2.0.0'
        },
        'products': products,
        'groups': groups
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"Products: {len(products)}")
    print(f"Cross-store groups: {len(groups)}")
    print(f"Saved to: {OUTPUT_FILE}")
    
    # Show sample matches
    print(f"\n{'=' * 60}")
    print("SAMPLE MATCHES")
    print(f"{'=' * 60}")
    for gid in list(groups.keys())[:10]:
        group = groups[gid]
        print(f"\n{gid} (brand: {group['brand']}):")
        for pid in group['product_ids']:
            p = next((x for x in products if x['id'] == pid), None)
            if p:
                qty = extract_quantity(p['name'])
                qty_str = f" [{qty.original}]" if qty else ""
                print(f"  {p['store']}: {p['name'][:45]}{qty_str} | €{p['price']}")

if __name__ == '__main__':
    main()
