#!/usr/bin/env python3
"""
Robust Product Standardization Pipeline

Extracts and normalizes:
- Brand
- Product description (clean)
- Quantity (value + unit)
- Category
- Price validation
"""
import re
import json
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List
from pathlib import Path

@dataclass
class StandardizedProduct:
    """Standardized product with all extracted attributes."""
    id: int
    store: str
    raw_name: str
    clean_name: str
    brand: Optional[str]
    description: str
    quantity_value: Optional[float]
    quantity_unit: Optional[str]
    category: str
    price: float
    old_price: Optional[float]
    discount_pct: Optional[int]
    unit_price: Optional[float]
    unit_price_base: Optional[str]
    image_url: Optional[str]
    validation_errors: List[str]
    
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============= NAME CLEANING =============

# Store-specific patterns to remove
LIDL_PATTERNS = [
    r'\s*\|\s*LIDL\s*$',
    r'\s*\|\s*Lidl\s*$',
]

KAUFLAND_PATTERNS = [
    r'\s+от\s+нашата\s+пекарна\s*$',
    r'\s+от\s+нашата\s+витрина\s*$',
    r'\s+от\s+свежата\s+витрина\s*$',
    r'\s+от\s+свежата\s+витр\s*$',
    r'\s+от\s+деликатеснат\s*$',
]

BILLA_PATTERNS = [
    r'^King\s+оферта\s*-\s*Супер\s+цена\s*-\s*',
    r'^King\s+оферта\s*-\s*Само\s+с\s+BILLA\s+CARD\s*-\s*',
    r'^King\s+оферта\s*-\s*Сега\s+в\s+Billa\s*-\s*',
    r'^King\s+оферта\s*-\s*Ново\s+в\s+Billa\s*-\s*',
    r'^King\s+оферта\s*-\s*',
    r'^Супер\s+цена\s*-\s*',
]

GENERIC_PATTERNS = [
    r'\s+различни\s+видове\s*$',
    r'\s+избрани\s+видове\s*$',
    r'\s+различни\s+вкусове\s*$',
    r'\s+различни\s+размери\s*$',
    r'\n+',  # Newlines to spaces
]

def clean_name(name: str, store: str) -> str:
    """Remove store-specific and generic noise from product name."""
    if not name:
        return ""
    
    original = name
    
    # Apply store-specific patterns
    if store == 'Lidl':
        for pattern in LIDL_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    elif store == 'Kaufland':
        for pattern in KAUFLAND_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    elif store == 'Billa':
        for pattern in BILLA_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Apply generic patterns
    for pattern in GENERIC_PATTERNS:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
    
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


# ============= BRAND EXTRACTION =============

# Known brands (Bulgarian + international)
KNOWN_BRANDS = {
    # Dairy
    'верея': 'Верея', 'олимпус': 'Олимпус', 'данон': 'Danone', 'danone': 'Danone',
    'активиа': 'Activia', 'activia': 'Activia', 'президент': 'President',
    'елена': 'Елена', 'маджаров': 'Маджаров', 'бор-чвор': 'Бор-Чвор',
    'саяна': 'Саяна', 'милкер': 'Milker', 'мleкара': 'Млекара',
    
    # Beverages
    'coca-cola': 'Coca-Cola', 'кока-кола': 'Coca-Cola', 'кока кола': 'Coca-Cola',
    'pepsi': 'Pepsi', 'пепси': 'Pepsi', 'fanta': 'Fanta', 'фанта': 'Fanta',
    'sprite': 'Sprite', 'спрайт': 'Sprite', 'schweppes': 'Schweppes',
    'девин': 'Devin', 'devin': 'Devin', 'банкя': 'Банкя', 'горна баня': 'Горна Баня',
    'хисаря': 'Хисаря', 'велинград': 'Велинград',
    
    # Coffee
    'nescafe': 'Nescafe', 'нескафе': 'Nescafe', 'jacobs': 'Jacobs', 'якобс': 'Jacobs',
    'lavazza': 'Lavazza', 'лаваца': 'Lavazza', 'tchibo': 'Tchibo', 'чибо': 'Tchibo',
    'melitta': 'Melitta', 'мелита': 'Melitta', 'kimbo': 'Kimbo', 'кимбо': 'Kimbo',
    'davidoff': 'Davidoff', 'давидоф': 'Davidoff',
    
    # Chocolate/Snacks
    'milka': 'Milka', 'милка': 'Milka', 'oreo': 'Oreo', 'орео': 'Oreo',
    'lindt': 'Lindt', 'линдт': 'Lindt', 'toblerone': 'Toblerone', 'тоблерон': 'Toblerone',
    'haribo': 'Haribo', 'харибо': 'Haribo', 'snickers': 'Snickers', 'сникърс': 'Snickers',
    'mars': 'Mars', 'марс': 'Mars', 'twix': 'Twix', 'твикс': 'Twix',
    'bounty': 'Bounty', 'баунти': 'Bounty', 'kinder': 'Kinder', 'киндер': 'Kinder',
    'ferrero': 'Ferrero', 'фереро': 'Ferrero', 'raffaello': 'Raffaello',
    'nutella': 'Nutella', 'нутела': 'Nutella', 'nestle': 'Nestle', 'нестле': 'Nestle',
    
    # Condiments
    'heinz': 'Heinz', 'хайнц': 'Heinz', 'hellmann': 'Hellmann\'s',
    'bonduelle': 'Bonduelle', 'бондюел': 'Bonduelle', 'олинеза': 'Олинеза',
    
    # Beer
    'загорка': 'Загорка', 'каменица': 'Каменица', 'heineken': 'Heineken',
    'хайнекен': 'Heineken', 'carlsberg': 'Carlsberg', 'карлсберг': 'Carlsberg',
    'stella artois': 'Stella Artois', 'budweiser': 'Budweiser',
    
    # Alcohol
    'absolut': 'Absolut', 'smirnoff': 'Smirnoff', 'johnnie walker': 'Johnnie Walker',
    'jack daniels': 'Jack Daniel\'s', 'jameson': 'Jameson', 'william peel': 'William Peel',
    'bacardi': 'Bacardi', 'бакарди': 'Bacardi',
    
    # Household
    'ariel': 'Ariel', 'ариел': 'Ariel', 'persil': 'Persil', 'персил': 'Persil',
    'lenor': 'Lenor', 'ленор': 'Lenor', 'fairy': 'Fairy', 'фейри': 'Fairy',
    
    # Personal care
    'nivea': 'Nivea', 'нивеа': 'Nivea', 'dove': 'Dove', 'дав': 'Dove',
    'garnier': 'Garnier', 'гарние': 'Garnier', 'colgate': 'Colgate', 'колгейт': 'Colgate',
    'gillette': 'Gillette', 'жилет': 'Gillette', 'oral-b': 'Oral-B',
    
    # Store brands
    'k-classic': 'K-Classic', 'k classic': 'K-Classic',
    'pilos': 'Pilos', 'milbona': 'Milbona', 'chef select': 'Chef Select',
    'balkan': 'Balkan',
    
    # Appliances
    'muhler': 'Muhler', 'мюлер': 'Muhler', 'brio': 'BRIO', 'брио': 'BRIO',
    'tefal': 'Tefal', 'тефал': 'Tefal', 'philips': 'Philips', 'филипс': 'Philips',
}

def extract_brand(name: str, existing_brand: str = None) -> Optional[str]:
    """Extract brand from product name."""
    if existing_brand and existing_brand not in ['NO_BRAND', 'Unknown', '']:
        # Normalize existing brand
        for key, canonical in KNOWN_BRANDS.items():
            if existing_brand.lower() == key or existing_brand == canonical:
                return canonical
        return existing_brand
    
    name_lower = name.lower()
    
    # Check known brands
    for key, canonical in KNOWN_BRANDS.items():
        if key in name_lower:
            return canonical
    
    return None


# ============= QUANTITY PARSING =============

QUANTITY_PATTERNS = [
    # Weight
    (r'(\d+(?:[.,]\d+)?)\s*кг\b', 'kg'),
    (r'(\d+(?:[.,]\d+)?)\s*kg\b', 'kg'),
    (r'(\d+(?:[.,]\d+)?)\s*(?:г|гр)\b', 'g'),
    (r'(\d+(?:[.,]\d+)?)\s*g\b', 'g'),
    
    # Volume
    (r'(\d+(?:[.,]\d+)?)\s*л\b', 'L'),
    (r'(\d+(?:[.,]\d+)?)\s*l\b', 'L'),
    (r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b', 'ml'),
    
    # Pieces
    (r'(\d+)\s*(?:бр|броя)\b', 'pcs'),
    (r'x\s*(\d+)\b', 'pcs'),
]

def parse_quantity(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Parse quantity value and unit from text."""
    if not text:
        return None, None
    
    text_lower = text.lower()
    
    for pattern, unit in QUANTITY_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value, unit
            except ValueError:
                continue
    
    return None, None


# ============= CATEGORY CLASSIFICATION =============

CATEGORY_KEYWORDS = {
    'dairy': ['мляко', 'сирене', 'кашкавал', 'йогурт', 'кисело', 'масло', 'сметана', 'извара'],
    'meat': ['месо', 'свинско', 'пилешко', 'телешко', 'агнешко', 'кайма', 'бекон', 'шунка', 'салам', 'кренвирш', 'наденица'],
    'fish': ['риба', 'сьомга', 'скумрия', 'пъстърва', 'сельодка', 'скариди', 'сурими'],
    'produce': ['ябълки', 'портокали', 'банани', 'домати', 'краставици', 'картофи', 'моркови', 'лук', 'чесън', 'салата', 'зеле', 'броколи', 'авокадо', 'манго', 'ягоди', 'ананас', 'грозде', 'круши', 'лимони'],
    'bakery': ['хляб', 'питка', 'кифла', 'кроасан', 'баничка', 'земел', 'франзела', 'козунак', 'мъфин', 'донат', 'бейгъл', 'брецел', 'пура', 'точени кори'],
    'beverages': ['вода', 'сок', 'газирана', 'напитка', 'енергийна', 'чай', 'кафе', 'капучино'],
    'alcohol': ['бира', 'вино', 'водка', 'уиски', 'ром', 'ракия', 'джин', 'ликьор'],
    'snacks': ['чипс', 'бисквити', 'шоколад', 'вафла', 'бонбони', 'дъвки', 'ядки', 'крекери'],
    'frozen': ['замразен', 'замразена', 'сладолед'],
    'canned': ['консерва', 'буркан', 'туна', 'царевица', 'грах', 'фасул', 'боб'],
    'household': ['препарат', 'почистващ', 'перилен', 'омекотител', 'освежител', 'кърпи', 'тоалетна'],
    'personal_care': ['шампоан', 'душ гел', 'сапун', 'паста за зъби', 'дезодорант', 'крем'],
    'pet': ['храна за кучета', 'храна за котки', 'суха храна'],
    'nonfood': ['бормашина', 'прахосмукачка', 'фурна', 'миксер', 'блендер', 'телевизор', 'играчка', 'орхидея', 'цвете', 'одеяло', 'възглавница'],
}

def classify_category(name: str, brand: str = None) -> str:
    """Classify product into category based on name and brand."""
    name_lower = name.lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return category
    
    return 'other'


# ============= PRICE VALIDATION =============

PRICE_RANGES = {
    'dairy': (0.30, 25.00),
    'meat': (1.00, 60.00),
    'fish': (2.00, 80.00),
    'produce': (0.20, 15.00),
    'bakery': (0.15, 12.00),
    'beverages': (0.20, 25.00),
    'alcohol': (1.00, 100.00),
    'snacks': (0.30, 20.00),
    'frozen': (1.00, 30.00),
    'canned': (0.50, 15.00),
    'household': (0.50, 50.00),
    'personal_care': (0.50, 30.00),
    'pet': (1.00, 50.00),
    'nonfood': (1.00, 500.00),
    'other': (0.10, 200.00),
}

def validate_price(price: float, category: str, store: str) -> List[str]:
    """Validate price and return list of errors."""
    errors = []
    
    if not price or price <= 0:
        errors.append("Invalid price: zero or negative")
        return errors
    
    min_p, max_p = PRICE_RANGES.get(category, (0.10, 200.00))
    
    # Lidl price bug check: if bakery/dairy/produce > €50, likely 100x bug
    if store == 'Lidl' and category in ['bakery', 'dairy', 'produce', 'snacks', 'beverages']:
        if price > 50:
            errors.append(f"Lidl price bug suspected: €{price} for {category} (should divide by 100)")
    
    if price < min_p:
        errors.append(f"Price too low: €{price} < €{min_p} for {category}")
    
    if price > max_p:
        errors.append(f"Price too high: €{price} > €{max_p} for {category}")
    
    return errors


# ============= UNIT PRICE CALCULATION =============

def calculate_unit_price(price: float, qty_value: float, qty_unit: str) -> Tuple[Optional[float], Optional[str]]:
    """Calculate price per kg or per liter."""
    if not price or not qty_value or not qty_unit:
        return None, None
    
    if qty_unit == 'kg':
        return round(price / qty_value, 2), 'kg'
    elif qty_unit == 'g':
        return round(price / qty_value * 1000, 2), 'kg'
    elif qty_unit == 'L':
        return round(price / qty_value, 2), 'L'
    elif qty_unit == 'ml':
        return round(price / qty_value * 1000, 2), 'L'
    
    return None, None


# ============= MAIN STANDARDIZATION =============

def standardize_product(
    id: int,
    name: str,
    store: str,
    price: float,
    old_price: float = None,
    existing_brand: str = None,
    image_url: str = None
) -> StandardizedProduct:
    """Standardize a single product."""
    errors = []
    
    # 1. Clean name
    clean = clean_name(name, store)
    
    # 2. Extract brand
    brand = extract_brand(name, existing_brand)
    
    # 3. Create description (name without brand)
    description = clean
    if brand:
        # Remove brand from description
        description = re.sub(re.escape(brand), '', description, flags=re.IGNORECASE).strip()
        description = re.sub(r'^\s*[-–]\s*', '', description).strip()
    
    # 4. Parse quantity
    qty_value, qty_unit = parse_quantity(name)
    
    # 5. Classify category
    category = classify_category(name, brand)
    
    # 6. Validate price
    price_errors = validate_price(price, category, store)
    errors.extend(price_errors)
    
    # 7. Calculate discount
    discount_pct = None
    if old_price and old_price > price:
        discount_pct = int((1 - price / old_price) * 100)
        if discount_pct > 80:
            errors.append(f"Suspicious discount: {discount_pct}%")
    
    # 8. Calculate unit price
    unit_price, unit_base = calculate_unit_price(price, qty_value, qty_unit)
    
    return StandardizedProduct(
        id=id,
        store=store,
        raw_name=name,
        clean_name=clean,
        brand=brand,
        description=description,
        quantity_value=qty_value,
        quantity_unit=qty_unit,
        category=category,
        price=price,
        old_price=old_price,
        discount_pct=discount_pct,
        unit_price=unit_price,
        unit_price_base=unit_base,
        image_url=image_url,
        validation_errors=errors
    )


if __name__ == '__main__':
    # Test
    test_cases = [
        ("Верея Прясно мляко 3% 1л | LIDL", "Lidl", 1.43),
        ("King оферта - Супер цена - Ягоди 250 г", "Billa", 1.69),
        ("Хляб със семена от нашата пекарна", "Kaufland", 1.47),
        ("Heinz Кетчуп различни видове", "Kaufland", 5.48),
        ("Бял хляб | LIDL", "Lidl", 119.30),  # Price bug
    ]
    
    print("=== STANDARDIZATION TEST ===\n")
    for name, store, price in test_cases:
        result = standardize_product(0, name, store, price)
        print(f"Input: {name}")
        print(f"  Clean: {result.clean_name}")
        print(f"  Brand: {result.brand}")
        print(f"  Category: {result.category}")
        print(f"  Quantity: {result.quantity_value} {result.quantity_unit}")
        print(f"  Errors: {result.validation_errors}")
        print()
