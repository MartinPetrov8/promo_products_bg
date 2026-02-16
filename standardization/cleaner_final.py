#!/usr/bin/env python3
"""
Product Standardization v3 - Comprehensive cleanup

Target: <100 products in 'other' category
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

def clean_name(name: str, store: str) -> str:
    if not name:
        return ""
    
    # Lidl
    name = re.sub(r'\s*\|\s*LIDL\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\|\s*Lidl\s*$', '', name, flags=re.IGNORECASE)
    
    # Kaufland
    name = re.sub(r'\s+от\s+нашата\s+(?:пекарна|витрина)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+от\s+свежата\s+витр(?:ина)?\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+от\s+деликатес(?:ната\s+витрина|нат)?\s*$', '', name, flags=re.IGNORECASE)
    
    # Billa - comprehensive cleanup
    name = re.sub(r'^King\s+оферта\s*-\s*[^-]+-\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^King\s+оферта\s*-\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^\s*продукт,\s+маркиран\s+(?:с|със)\s+синя\s+звезда[^А-Яа-яA-Za-z]*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^Супер\s+цена\s*-\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\*+\s*валидно[^*]+\*+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\d{2}\.\d{2}\.\d{4}', '', name)  # Dates
    name = re.sub(r'\s+От\s+Billa\s+пекарна', '', name, flags=re.IGNORECASE)
    
    # Generic cleanup
    name = re.sub(r'\s+различни\s+(?:видове|вкусове|размери|цветове)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+избрани\s+видове\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+до\s+\d+\s*кг\s+на\s+покупка\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+Произход[^,]*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\n+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

# ============= BRAND EXTRACTION =============

KNOWN_BRANDS = {
    # Dairy
    'верея': 'Верея', 'олимпус': 'Олимпус', 'данон': 'Danone', 'danone': 'Danone',
    'активиа': 'Activia', 'президент': 'President', 'саяна': 'Саяна',
    'lacrima': 'Lacrima', 'philadelphia': 'Philadelphia', 'kri kri': 'Kri Kri',
    'маскарпоне': 'Mascarpone', 'fivepi': 'FivePi', 'bettine': 'Bettine',
    
    # Beverages
    'coca-cola': 'Coca-Cola', 'pepsi': 'Pepsi', 'fanta': 'Fanta', 'sprite': 'Sprite',
    'девин': 'Devin', 'банкя': 'Банкя', 'горна баня': 'Горна Баня',
    'prisun': 'Prisun', 'cappy': 'Cappy', 'red bull': 'Red Bull',
    
    # Coffee
    'nescafe': 'Nescafe', 'jacobs': 'Jacobs', 'lavazza': 'Lavazza', 
    'tchibo': 'Tchibo', 'melitta': 'Melitta', 'kimbo': 'Kimbo',
    'eduscho': 'Eduscho', 'illy': 'Illy', 'davidoff': 'Davidoff',
    
    # Chocolate/Snacks
    'milka': 'Milka', 'oreo': 'Oreo', 'lindt': 'Lindt', 'toblerone': 'Toblerone',
    'haribo': 'Haribo', 'snickers': 'Snickers', 'mars': 'Mars', 'twix': 'Twix',
    'kinder': 'Kinder', 'ferrero': 'Ferrero', 'raffaello': 'Raffaello',
    'nutella': 'Nutella', 'nestle': 'Nestle', 'lacmi': 'Lacmi',
    'heidi': 'Heidi', 'linea': 'Linea', 'heli': 'Хели',
    
    # Condiments/Pantry
    'heinz': 'Heinz', 'hellmann': 'Hellmann\'s', 'bonduelle': 'Bonduelle',
    'олинеза': 'Олинеза', 'кенар': 'Кенар', 'deroni': 'Deroni',
    'златно добруджанско': 'Златно Добруджанско', 'biser': 'Biser',
    'flora': 'Flora', 'krina': 'Krina', 'булгар': 'Булгар',
    
    # Beer/Alcohol
    'загорка': 'Загорка', 'каменица': 'Каменица', 'heineken': 'Heineken',
    'carlsberg': 'Carlsberg', 'stella artois': 'Stella Artois',
    'ариана': 'Ариана', 'пиринско': 'Пиринско', 'шуменско': 'Шуменско',
    'absolut': 'Absolut', 'smirnoff': 'Smirnoff', 'william peel': 'William Peel',
    'bacardi': 'Bacardi', 'flirt': 'Flirt',
    
    # Meat/Deli
    'тандем': 'Тандем', 'родопски': 'Родопски', 'наша': 'Наша',
    'житница': 'Житница', 'градус': 'Градус', 'пилко': 'Пилко',
    
    # Household
    'ariel': 'Ariel', 'persil': 'Persil', 'lenor': 'Lenor', 'fairy': 'Fairy',
    'somat': 'Somat', 'finish': 'Finish', 'vanish': 'Vanish', 'bref': 'Bref',
    'domestos': 'Domestos', 'cif': 'Cif', 'pronto': 'Pronto',
    
    # Personal care
    'nivea': 'Nivea', 'dove': 'Dove', 'garnier': 'Garnier', 'colgate': 'Colgate',
    'gillette': 'Gillette', 'oral-b': 'Oral-B', 'palmolive': 'Palmolive',
    'gliss': 'Gliss', 'schauma': 'Schauma', 'taft': 'Taft', 'fa': 'FA',
    'durex': 'Durex', 'always': 'Always', 'tampax': 'Tampax',
    
    # Store brands
    'k-classic': 'K-Classic', 'pilos': 'Pilos', 'milbona': 'Milbona',
    'chef select': 'Chef Select', 'balkan': 'Balkan', 'kingshill': 'Kingshill',
    'clever': 'Clever', 'simply': 'Simply',
    
    # Kitchen/Home
    'muhler': 'Muhler', 'brio': 'BRIO', 'tefal': 'Tefal', 'philips': 'Philips',
    'parkside': 'Parkside', 'luminarc': 'Luminarc', 'pyrex': 'Pyrex',
    'liv&bo': 'Liv&Bo', 'top pot': 'Top Pot', 'home practic': 'Home Practic',
    'osram': 'Osram', 'duracell': 'Duracell',
    
    # Pet
    'whiskas': 'Whiskas', 'pedigree': 'Pedigree', 'felix': 'Felix',
    'purina': 'Purina', 'friskies': 'Friskies',
    
    # Sports/Clothing
    'adidas': 'Adidas', 'nike': 'Nike', 'puma': 'Puma',
    'oyanda': 'Oyanda', 'crivit': 'Crivit',
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

def parse_quantity(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None
    
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*кг\b', 'kg'),
        (r'(\d+(?:[.,]\d+)?)\s*kg\b', 'kg'),
        (r'(\d+(?:[.,]\d+)?)\s*(?:г|гр)\b', 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*g\b', 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*л\b', 'L'),
        (r'(\d+(?:[.,]\d+)?)\s*l\b', 'L'),
        (r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b', 'ml'),
        (r'(\d+)\s*(?:бр|броя)\b', 'pcs'),
    ]
    
    text_lower = text.lower()
    for pattern, unit in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value, unit
            except ValueError:
                continue
    
    return None, None

# ============= COMPREHENSIVE CATEGORY CLASSIFICATION =============

CATEGORY_KEYWORDS = {
    'dairy': ['мляко', 'сирене', 'кашкавал', 'йогурт', 'кисело', 'масло сладкосолено',
              'сметана', 'извара', 'бри', 'моцарела', 'пармезан', 'ементал',
              'маскарпоне', 'рикота', 'фета', 'крема сирене'],
    'meat': ['месо', 'свинско', 'пилешко', 'телешко', 'агнешко', 'кайма', 'бекон', 
             'шунка', 'салам', 'кренвирш', 'наденица', 'луканка', 'филе', 'бут', 
             'врат', 'плешка', 'котлет', 'карначе', 'кюфте', 'бабек', 'колбас',
             'пуешко', 'заешко', 'патешко', 'пастърма', 'суджук', 'роле'],
    'fish': ['риба', 'сьомга', 'скумрия', 'пъстърва', 'сельодка', 'скариди', 'сурими',
             'херинга', 'тон', 'туна', 'филе от риба', 'морски дар'],
    'produce': ['ябълки', 'портокали', 'банани', 'домати', 'краставици', 'картофи', 
                'моркови', 'лук', 'чесън', 'салата', 'зеле', 'броколи', 'авокадо', 
                'манго', 'ягоди', 'ананас', 'грозде', 'круши', 'лимони', 'мандарини',
                'диня', 'пъпеш', 'череши', 'праскови', 'кайсии', 'нектарини',
                'тиквички', 'патладжан', 'пипер', 'чушки', 'спанак', 'гъби'],
    'bakery': ['хляб', 'питка', 'кифла', 'кроасан', 'баничка', 'земел', 'франзела', 
               'козунак', 'мъфин', 'донат', 'бейгъл', 'брецел', 'пура', 'точени кори',
               'лаваш', 'тортила', 'пърленка', 'симид', 'погача', 'рогче'],
    'beverages': ['вода минерална', 'сок', 'газирана напитка', 'енергийна напитка',
                  'безалкохолн', 'минерална вода', 'студен чай'],
    'coffee': ['кафе', 'еспресо', 'капучино', 'капсули за кафе', 'зърна кафе', 'разтворимо кафе'],
    'tea': ['чай', 'билков', 'зелен чай', 'черен чай'],
    'alcohol': ['бира', 'вино', 'водка', 'уиски', 'ром', 'ракия', 'джин', 'ликьор',
                'шампанско', 'пенливо', 'мастика', 'текила', 'бренди', 'коняк', 'вермут'],
    'snacks': ['чипс', 'бисквити', 'шоколад', 'вафла', 'вафли', 'бонбони', 'дъвки', 'ядки',
               'крекери', 'пуканки', 'солети', 'крокан', 'локум', 'десерт', 'торта', 'кейк'],
    'frozen': ['замразен', 'замразена', 'сладолед', 'пица', 'минипици', 'замразени'],
    'canned': ['консерва', 'буркан', 'царевица консерва', 'грах консерва', 'фасул', 'боб', 
               'маслини', 'корнишон', 'туршия', 'лютеница', 'кьопоолу', 'айвар'],
    'pantry': ['ориз', 'паста', 'макарони', 'спагети', 'олио', 'оцет', 'брашно',
               'захар', 'сол', 'подправки', 'кетчуп', 'майонеза', 'горчица', 'сос',
               'мед', 'конфитюр', 'тахан', 'халва'],
    'household': ['препарат', 'почистващ', 'перилен', 'омекотител', 'освежител', 
                  'кърпи', 'тоалетна хартия', 'салфетки', 'гъба', 'ръкавици',
                  'торби', 'фолио', 'пране', 'миене', 'препарат за'],
    'personal_care': ['шампоан', 'душ гел', 'сапун', 'паста за зъби', 'дезодорант', 
                      'крем', 'лосион', 'четка за зъби', 'самобръсначка', 
                      'пяна за бръснене', 'маска за коса', 'балсам за коса'],
    'baby': ['бебешк', 'памперс', 'пелени', 'бебе', 'кърмачет'],
    'pet': ['храна за кучета', 'храна за котки', 'суха храна за', 'консерва за кучета',
            'консерва за котки'],
    'kitchenware': ['тава', 'тиган', 'тенджера', 'кана', 'чаша', 'чиния', 'прибори', 
                    'нож', 'ножове', 'ренде', 'дъска за рязане', 'купа', 'съд за'],
    'electronics': ['батерии', 'зарядно', 'крушка', 'лампа', 'удължител', 'разклонител'],
    'tools': ['бормашина', 'прахосмукачка', 'трион', 'гедоре', 'инструмент', 
              'ключ', 'клещи', 'отвертка'],
    'appliances': ['миксер', 'блендер', 'чопър', 'кафемашина', 'тостер', 'фритюрник',
                   'прахосмукачка', 'ютия', 'сешоар'],
    'home_textiles': ['одеяло', 'възглавница', 'спален', 'чаршаф', 'кърпа за баня',
                      'хавлия', 'завеса', 'килим'],
    'clothing': ['чорапи', 'тениска', 'панталон', 'яке', 'пижама', 'бельо',
                 'боксерки', 'чехли', 'обувки', 'ботуши'],
    'garden': ['саксия', 'цвете', 'орхидея', 'растение', 'пръст', 'семена', 'тор'],
    'automotive': ['чистачки', 'автомобилн', 'течност за чистачки', 'антифриз',
                   'масло за двигател'],
    'toys': ['играчка', 'плюшен', 'пъзел', 'конструктор', 'кукла', 'топка'],
}

def classify_category(name: str, brand: str = None) -> str:
    name_lower = name.lower()
    
    # Check each category's keywords
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return category
    
    # Brand-based fallbacks
    if brand:
        brand_lower = brand.lower()
        if brand_lower in ['parkside', 'home practic']:
            return 'tools'
        if brand_lower in ['brio', 'muhler', 'pyrex', 'luminarc', 'top pot']:
            return 'kitchenware'
        if brand_lower in ['osram', 'duracell']:
            return 'electronics'
        if brand_lower in ['adidas', 'nike', 'puma', 'crivit', 'oyanda']:
            return 'clothing'
    
    return 'other'

# ============= PRICE VALIDATION =============

PRICE_RANGES = {
    'dairy': (0.30, 35.00),
    'meat': (0.80, 70.00),
    'fish': (1.50, 80.00),
    'produce': (0.15, 20.00),
    'bakery': (0.08, 15.00),
    'beverages': (0.20, 30.00),
    'coffee': (1.00, 60.00),
    'tea': (0.50, 20.00),
    'alcohol': (0.80, 150.00),
    'snacks': (0.30, 30.00),
    'frozen': (1.00, 40.00),
    'canned': (0.50, 20.00),
    'pantry': (0.30, 25.00),
    'household': (0.50, 60.00),
    'personal_care': (0.50, 40.00),
    'baby': (1.00, 60.00),
    'pet': (0.50, 60.00),
    'kitchenware': (1.00, 150.00),
    'electronics': (0.50, 100.00),
    'tools': (1.00, 300.00),
    'appliances': (5.00, 500.00),
    'home_textiles': (2.00, 200.00),
    'clothing': (1.00, 150.00),
    'garden': (0.50, 100.00),
    'automotive': (1.00, 100.00),
    'toys': (1.00, 150.00),
    'other': (0.05, 300.00),
}

def validate_price(price: float, category: str, store: str) -> List[str]:
    errors = []
    
    if not price or price <= 0:
        errors.append("Invalid_price: zero or negative")
        return errors
    
    min_p, max_p = PRICE_RANGES.get(category, (0.05, 300.00))
    
    # Lidl price bug check - only for food categories
    food_cats = ['bakery', 'dairy', 'produce', 'snacks', 'beverages', 'meat', 'fish', 'frozen', 'canned']
    if store == 'Lidl' and category in food_cats:
        if price > 50:
            errors.append(f"Lidl_price_bug: €{price} for {category}")
    
    if price < min_p:
        errors.append(f"Price_too_low: €{price} < €{min_p} for {category}")
    
    if price > max_p:
        errors.append(f"Price_too_high: €{price} > €{max_p} for {category}")
    
    return errors

# ============= MAIN =============

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

def standardize_product(
    id: int, name: str, store: str, price: float,
    old_price: float = None, existing_brand: str = None, image_url: str = None
) -> StandardizedProduct:
    errors = []
    
    clean = clean_name(name, store)
    brand = extract_brand(name, existing_brand)
    
    description = clean
    if brand:
        description = re.sub(re.escape(brand), '', description, flags=re.IGNORECASE).strip()
        description = re.sub(r'^\s*[-–]\s*', '', description).strip()
    
    qty_value, qty_unit = parse_quantity(name)
    category = classify_category(clean, brand)
    price_errors = validate_price(price, category, store)
    errors.extend(price_errors)
    
    discount_pct = None
    if old_price and old_price > price:
        discount_pct = int((1 - price / old_price) * 100)
        if discount_pct > 90:
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
                    'name': result.raw_name[:60], 'store': result.store,
                    'price': result.price, 'category': result.category
                })
    
    conn.close()
    
    print(f"=== STANDARDIZATION v3 ===")
    print(f"Total: {len(products)}")
    print(f"Valid: {valid_count} ({100*valid_count/len(products):.1f}%)")
    print(f"Invalid: {len(products)-valid_count}")
    
    print(f"\n=== CATEGORY DISTRIBUTION ===")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    
    if errors_by_type:
        print(f"\n=== ERRORS ===")
        for err_type, items in sorted(errors_by_type.items(), key=lambda x: -len(x[1])):
            print(f"{err_type}: {len(items)}")
            for item in items[:3]:
                print(f"  [{item['store']}] {item['name']} | €{item['price']} ({item['category']})")
    
    # Save
    with open('/host-workspace/promo_products_bg/standardized_v3.json', 'w') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to standardized_v3.json")
