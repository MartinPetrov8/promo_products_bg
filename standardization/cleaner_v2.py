#!/usr/bin/env python3
"""
Robust Product Standardization Pipeline v2

Expanded category keywords based on actual data analysis.
"""
import re
import json
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List

@dataclass
class StandardizedProduct:
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
    r'\s+от\s+деликатесната\s+витрина\s*$',
]

BILLA_PATTERNS = [
    r'^King\s+оферта\s*-\s*Супер\s+цена\s*-\s*',
    r'^King\s+оферта\s*-\s*Само\s+с\s+BILLA\s+CARD\s*-\s*',
    r'^King\s+оферта\s*-\s*Сега\s+в\s+Billa\s*-\s*',
    r'^King\s+оферта\s*-\s*Ново\s+в\s+Billa\s*-\s*',
    r'^King\s+оферта\s*-\s*',
    r'^Супер\s+цена\s*-\s*',
    r'^\s*продукт,\s+маркиран\s+със\s+синя\s+звезда\s*',
]

GENERIC_PATTERNS = [
    r'\s+различни\s+видове\s*$',
    r'\s+избрани\s+видове\s*$',
    r'\s+различни\s+вкусове\s*$',
    r'\s+различни\s+размери\s*$',
    r'\s+различни\s+цветове\s*$',
    r'\s+до\s+\d+\s*кг\s+на\s+покупка\s*$',
    r'\s+Произход[^,]*$',
    r'\n+',
]

def clean_name(name: str, store: str) -> str:
    if not name:
        return ""
    
    if store == 'Lidl':
        for pattern in LIDL_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    elif store == 'Kaufland':
        for pattern in KAUFLAND_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    elif store == 'Billa':
        for pattern in BILLA_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    for pattern in GENERIC_PATTERNS:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
    
    name = re.sub(r'\s+', ' ', name).strip()
    return name

# ============= BRAND EXTRACTION =============

KNOWN_BRANDS = {
    # Dairy
    'верея': 'Верея', 'олимпус': 'Олимпус', 'данон': 'Danone', 'danone': 'Danone',
    'активиа': 'Activia', 'activia': 'Activia', 'президент': 'President',
    'елена': 'Елена', 'маджаров': 'Маджаров', 'саяна': 'Саяна', 'lacrima': 'Lacrima',
    'philadelphia': 'Philadelphia', 'kiri': 'Kiri', 'kri kri': 'Kri Kri',
    
    # Beverages
    'coca-cola': 'Coca-Cola', 'кока-кола': 'Coca-Cola', 'pepsi': 'Pepsi', 
    'fanta': 'Fanta', 'sprite': 'Sprite', 'schweppes': 'Schweppes',
    'девин': 'Devin', 'банкя': 'Банкя', 'горна баня': 'Горна Баня',
    'prisun': 'Prisun', 'cappy': 'Cappy', 'red bull': 'Red Bull',
    
    # Coffee
    'nescafe': 'Nescafe', 'jacobs': 'Jacobs', 'lavazza': 'Lavazza', 
    'tchibo': 'Tchibo', 'melitta': 'Melitta', 'kimbo': 'Kimbo',
    'davidoff': 'Davidoff', 'eduscho': 'Eduscho', 'illy': 'Illy',
    
    # Chocolate/Snacks
    'milka': 'Milka', 'oreo': 'Oreo', 'lindt': 'Lindt', 'toblerone': 'Toblerone',
    'haribo': 'Haribo', 'snickers': 'Snickers', 'mars': 'Mars', 'twix': 'Twix',
    'kinder': 'Kinder', 'ferrero': 'Ferrero', 'raffaello': 'Raffaello',
    'nutella': 'Nutella', 'nestle': 'Nestle', 'lacmi': 'Lacmi',
    
    # Condiments
    'heinz': 'Heinz', 'hellmann': 'Hellmann\'s', 'bonduelle': 'Bonduelle',
    'олинеза': 'Олинеза', 'кенар': 'Кенар',
    
    # Oil/Pantry
    'златно добруджанско': 'Златно Добруджанско', 'biser': 'Biser',
    
    # Beer
    'загорка': 'Загорка', 'каменица': 'Каменица', 'heineken': 'Heineken',
    'carlsberg': 'Carlsberg', 'stella artois': 'Stella Artois',
    'ариана': 'Ариана', 'пиринско': 'Пиринско',
    
    # Alcohol
    'absolut': 'Absolut', 'smirnoff': 'Smirnoff', 'william peel': 'William Peel',
    'bacardi': 'Bacardi', 'johnnie walker': 'Johnnie Walker',
    
    # Household
    'ariel': 'Ariel', 'persil': 'Persil', 'lenor': 'Lenor', 'fairy': 'Fairy',
    'somat': 'Somat', 'finish': 'Finish', 'vanish': 'Vanish', 'bref': 'Bref',
    
    # Personal care
    'nivea': 'Nivea', 'dove': 'Dove', 'garnier': 'Garnier', 'colgate': 'Colgate',
    'gillette': 'Gillette', 'oral-b': 'Oral-B', 'palmolive': 'Palmolive',
    'head & shoulders': 'Head & Shoulders', 'pantene': 'Pantene',
    
    # Store brands
    'k-classic': 'K-Classic', 'pilos': 'Pilos', 'milbona': 'Milbona',
    'chef select': 'Chef Select', 'balkan': 'Balkan', 'kingshill': 'Kingshill',
    
    # Kitchen/Tools
    'muhler': 'Muhler', 'brio': 'BRIO', 'tefal': 'Tefal', 'philips': 'Philips',
    'parkside': 'Parkside', 'luminarc': 'Luminarc', 'pyrex': 'Pyrex',
    'liv&bo': 'Liv&Bo', 'top pot': 'Top Pot',
    
    # Pet
    'whiskas': 'Whiskas', 'pedigree': 'Pedigree', 'felix': 'Felix',
    
    # Pizza/Frozen
    'buitoni': 'Buitoni', 'dr. oetker': 'Dr. Oetker', 'galileo': 'Galileo',
}

def extract_brand(name: str, existing_brand: str = None) -> Optional[str]:
    if existing_brand and existing_brand not in ['NO_BRAND', 'Unknown', '']:
        for key, canonical in KNOWN_BRANDS.items():
            if existing_brand.lower() == key or existing_brand == canonical:
                return canonical
        return existing_brand
    
    name_lower = name.lower()
    for key, canonical in KNOWN_BRANDS.items():
        if key in name_lower:
            return canonical
    
    return None

# ============= QUANTITY PARSING =============

QUANTITY_PATTERNS = [
    (r'(\d+(?:[.,]\d+)?)\s*кг\b', 'kg'),
    (r'(\d+(?:[.,]\d+)?)\s*kg\b', 'kg'),
    (r'(\d+(?:[.,]\d+)?)\s*(?:г|гр)\b', 'g'),
    (r'(\d+(?:[.,]\d+)?)\s*g\b', 'g'),
    (r'(\d+(?:[.,]\d+)?)\s*л\b', 'L'),
    (r'(\d+(?:[.,]\d+)?)\s*l\b', 'L'),
    (r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b', 'ml'),
    (r'(\d+)\s*(?:бр|броя)\b', 'pcs'),
    (r'(\d+)\s*x\s*\d+', 'pcs'),  # Multi-packs like 6x500ml
]

def parse_quantity(text: str) -> Tuple[Optional[float], Optional[str]]:
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

# ============= EXPANDED CATEGORY CLASSIFICATION =============

CATEGORY_KEYWORDS = {
    'dairy': ['мляко', 'сирене', 'кашкавал', 'йогурт', 'кисело', 'масло', 'сметана', 
              'извара', 'крема сирене', 'бри', 'моцарела', 'пармезан', 'ементал'],
    'meat': ['месо', 'свинско', 'пилешко', 'телешко', 'агнешко', 'кайма', 'бекон', 
             'шунка', 'салам', 'кренвирш', 'наденица', 'луканка', 'филе', 'бут', 
             'врат', 'плешка', 'котлет', 'карначе', 'кюфте', 'бабек'],
    'fish': ['риба', 'сьомга', 'скумрия', 'пъстърва', 'сельодка', 'скариди', 'сурими',
             'херинга', 'тон', 'туна', 'филе от', 'морски'],
    'produce': ['ябълки', 'портокали', 'банани', 'домати', 'краставици', 'картофи', 
                'моркови', 'лук', 'чесън', 'салата', 'зеле', 'броколи', 'авокадо', 
                'манго', 'ягоди', 'ананас', 'грозде', 'круши', 'лимони', 'мандарини',
                'диня', 'пъпеш', 'череши', 'праскови', 'кайсии', 'нектарини',
                'тиквички', 'патладжан', 'пипер', 'чушки', 'спанак'],
    'bakery': ['хляб', 'питка', 'кифла', 'кроасан', 'баничка', 'земел', 'франзела', 
               'козунак', 'мъфин', 'донат', 'бейгъл', 'брецел', 'пура', 'точени кори',
               'лаваш', 'тортила', 'пърленка', 'симид', 'погача'],
    'beverages': ['вода', 'сок', 'газирана', 'напитка', 'енергийна', 'чай', 
                  'минерална', 'безалкохолн'],
    'coffee': ['кафе', 'еспресо', 'капучино', 'капсули', 'зърна'],
    'alcohol': ['бира', 'вино', 'водка', 'уиски', 'ром', 'ракия', 'джин', 'ликьор',
                'шампанско', 'пенливо', 'мастика', 'текила', 'бренди', 'коняк'],
    'snacks': ['чипс', 'бисквити', 'шоколад', 'вафла', 'бонбони', 'дъвки', 'ядки',
               'крекери', 'пуканки', 'солети', 'крокан', 'локум', 'десерт'],
    'frozen': ['замразен', 'замразена', 'сладолед', 'пица', 'минипици'],
    'canned': ['консерва', 'буркан', 'царевица', 'грах', 'фасул', 'боб', 'маслини',
               'корнишон', 'туршия'],
    'pantry': ['ориз', 'паста', 'макарони', 'спагети', 'олио', 'оцет', 'брашно',
               'захар', 'сол', 'подправки', 'кетчуп', 'майонеза', 'горчица', 'сос'],
    'household': ['препарат', 'почистващ', 'перилен', 'омекотител', 'освежител', 
                  'кърпи', 'тоалетна хартия', 'салфетки', 'гъба', 'ръкавици',
                  'торби', 'фолио', 'пране'],
    'personal_care': ['шампоан', 'душ гел', 'сапун', 'паста за зъби', 'дезодорант', 
                      'крем', 'лосион', 'четка за зъби', 'самобръсначка', 'пяна за бръснене'],
    'baby': ['бебешк', 'памперс', 'пелени', 'бебе'],
    'pet': ['храна за кучета', 'храна за котки', 'суха храна', 'консерва за'],
    'kitchenware': ['тава', 'тиган', 'кана', 'чаша', 'чиния', 'прибори', 'нож', 'ножове',
                    'комплект', 'части', 'ренде', 'миксер', 'блендер', 'чопър'],
    'nonfood': ['бормашина', 'прахосмукачка', 'фурна', 'телевизор', 'играчка', 
                'орхидея', 'цвете', 'одеяло', 'възглавница', 'спален', 'чаршаф',
                'гедоре', 'инструмент', 'чистачки', 'автомобилн', 'течност'],
}

def classify_category(name: str, brand: str = None) -> str:
    name_lower = name.lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return category
    
    return 'other'

# ============= PRICE VALIDATION =============

PRICE_RANGES = {
    'dairy': (0.30, 30.00),
    'meat': (0.80, 60.00),
    'fish': (1.50, 80.00),
    'produce': (0.15, 15.00),
    'bakery': (0.08, 12.00),  # Lowered min for пърленка
    'beverages': (0.20, 25.00),
    'coffee': (1.00, 50.00),  # Coffee can be expensive
    'alcohol': (0.80, 100.00),  # Beer can be cheap
    'snacks': (0.30, 25.00),
    'frozen': (1.00, 30.00),
    'canned': (0.50, 15.00),
    'pantry': (0.30, 20.00),
    'household': (0.50, 50.00),
    'personal_care': (0.50, 30.00),
    'baby': (1.00, 50.00),
    'pet': (0.50, 50.00),
    'kitchenware': (1.00, 100.00),
    'nonfood': (1.00, 500.00),
    'other': (0.05, 200.00),
}

def validate_price(price: float, category: str, store: str) -> List[str]:
    errors = []
    
    if not price or price <= 0:
        errors.append("Invalid price: zero or negative")
        return errors
    
    min_p, max_p = PRICE_RANGES.get(category, (0.05, 200.00))
    
    # Lidl price bug check
    if store == 'Lidl' and category in ['bakery', 'dairy', 'produce', 'snacks', 'beverages', 'meat']:
        if price > 50:
            errors.append(f"Lidl_price_bug: €{price} for {category}")
    
    if price < min_p:
        errors.append(f"Price_too_low: €{price} < €{min_p} for {category}")
    
    if price > max_p:
        errors.append(f"Price_too_high: €{price} > €{max_p} for {category}")
    
    return errors

# ============= UNIT PRICE =============

def calculate_unit_price(price: float, qty_value: float, qty_unit: str) -> Tuple[Optional[float], Optional[str]]:
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

# ============= MAIN =============

def standardize_product(
    id: int,
    name: str,
    store: str,
    price: float,
    old_price: float = None,
    existing_brand: str = None,
    image_url: str = None
) -> StandardizedProduct:
    errors = []
    
    clean = clean_name(name, store)
    brand = extract_brand(name, existing_brand)
    
    description = clean
    if brand:
        description = re.sub(re.escape(brand), '', description, flags=re.IGNORECASE).strip()
        description = re.sub(r'^\s*[-–]\s*', '', description).strip()
    
    qty_value, qty_unit = parse_quantity(name)
    category = classify_category(name, brand)
    price_errors = validate_price(price, category, store)
    errors.extend(price_errors)
    
    discount_pct = None
    if old_price and old_price > price:
        discount_pct = int((1 - price / old_price) * 100)
        if discount_pct > 85:
            errors.append(f"Suspicious_discount: {discount_pct}%")
    
    unit_price, unit_base = calculate_unit_price(price, qty_value, qty_unit)
    
    return StandardizedProduct(
        id=id, store=store, raw_name=name, clean_name=clean,
        brand=brand, description=description,
        quantity_value=qty_value, quantity_unit=qty_unit,
        category=category, price=price, old_price=old_price,
        discount_pct=discount_pct, unit_price=unit_price,
        unit_price_base=unit_base, image_url=image_url,
        validation_errors=errors
    )

if __name__ == '__main__':
    import sqlite3
    
    conn = sqlite3.connect('/host-workspace/projects/promo_products/repo/data/promobg.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.id, p.name, p.brand, s.name as store, pr.current_price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        JOIN prices pr ON sp.id = pr.store_product_id
        WHERE pr.current_price IS NOT NULL
    """)
    
    products = []
    errors_by_type = {}
    categories = {}
    valid_count = 0
    
    for row in cur.fetchall():
        result = standardize_product(
            id=row['id'], name=row['name'], store=row['store'],
            price=row['current_price'], existing_brand=row['brand']
        )
        products.append(result.to_dict())
        
        cat = result.category
        categories[cat] = categories.get(cat, 0) + 1
        
        if result.is_valid():
            valid_count += 1
        else:
            for err in result.validation_errors:
                err_type = err.split(':')[0]
                if err_type not in errors_by_type:
                    errors_by_type[err_type] = []
                errors_by_type[err_type].append({
                    'name': result.raw_name[:50], 'store': result.store,
                    'price': result.price, 'category': result.category
                })
    
    conn.close()
    
    print(f"=== STANDARDIZATION v2 ===")
    print(f"Total: {len(products)}, Valid: {valid_count} ({100*valid_count/len(products):.1f}%)")
    
    print(f"\n=== CATEGORY DISTRIBUTION ===")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    
    print(f"\n=== ERRORS ===")
    for err_type, items in sorted(errors_by_type.items(), key=lambda x: -len(x[1])):
        print(f"{err_type}: {len(items)}")
    
    # Save
    with open('/host-workspace/promo_products_bg/standardized_v2.json', 'w') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to standardized_v2.json")
