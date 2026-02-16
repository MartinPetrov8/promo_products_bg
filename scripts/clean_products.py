#!/usr/bin/env python3
"""
Clean and standardize ALL products
Extract: brand, size, quantity, category, description
Output: unified CSV
"""
import json
import re
import csv
from pathlib import Path
from collections import defaultdict

INPUT_FILE = Path(__file__).parent.parent / "output" / "raw_products.json"
OUTPUT_CSV = Path(__file__).parent.parent / "output" / "products_clean.csv"
OUTPUT_JSON = Path(__file__).parent.parent / "output" / "products_clean.json"

# ============================================================================
# BRAND EXTRACTION
# ============================================================================

KNOWN_BRANDS = [
    # International food brands
    'coca-cola', 'coca cola', 'pepsi', 'fanta', 'sprite', '7up', '7 up', 'mirinda',
    'nestle', 'nescafe', 'nespresso', 'jacobs', 'lavazza', 'tchibo', 'melitta', 'illy',
    'milka', 'oreo', 'lindt', 'toblerone', 'ferrero', 'raffaello', 'kinder', 'nutella',
    'haribo', 'snickers', 'mars', 'twix', 'bounty', 'kitkat', 'kit kat', 'm&m',
    'heinz', 'hellmann', 'bonduelle', 'barilla', 'de cecco', 'knorr', 'maggi',
    'danone', 'activia', 'president', 'philadelphia', 'hochland', 'exquisa',
    'whiskas', 'pedigree', 'felix', 'friskies', 'gourmet',
    'lipton', 'ahmad', 'twinings',
    'red bull', 'monster', 'hell',
    'lay\'s', 'lays', 'pringles', 'doritos', 'cheetos',
    'bacardi', 'smirnoff', 'absolut', 'johnnie walker', 'jack daniels', 'jim beam',
    'heineken', 'carlsberg', 'stella artois', 'budweiser', 'corona',
    'nivea', 'dove', 'garnier', 'loreal', 'colgate', 'oral-b', 'gillette',
    'ariel', 'persil', 'lenor', 'fairy', 'domestos', 'ajax',
    
    # Bulgarian brands
    'верея', 'олимпус', 'olympus', 'данон', 'activia', 'активиа',
    'загорка', 'каменица', 'пиринско', 'шуменско', 'ариана',
    'девин', 'devin', 'банкя', 'горна баня', 'хисар', 'велинград',
    'тракия', 'trakia', 'домейн бояр',
    'тандем', 'кенар', 'bulgaricus',
    'златна добруджа', 'добруджа', 'родина',
    'саяна', 'саяна', 'рафтис', 'дестан', 'елена', 'меггле', 'meggle',
    'bella bulgaria', 'бела българия',
    
    # Lidl brands
    'parkside', 'silvercrest', 'livarno', 'crivit', 'esmara', 'livergy',
    'w5', 'cien', 'freeway', 'solevita', 'milbona', 'pikok', 'pilos',
    'chef select', 'deluxe', 'italiamo', 'alpenfest',
    
    # Kaufland brands  
    'k-classic', 'k-bio', 'k-favourites', 'k-purland', 'bevola',
    
    # Billa brands
    'billa', 'clever', 'ja! natürlich',
    
    # Other
    'dr. oetker', 'dr oetker', 'iglo', 'findus',
    'casa rinaldi', 'de cecco', 'rummo',
    'nucrema', 'nutella', 'lotus', 'biscoff',
]

def extract_brand(name, subtitle='', description=''):
    """Extract brand from product text"""
    text = f"{name} {subtitle} {description}".lower()
    
    for brand in KNOWN_BRANDS:
        if brand in text:
            return brand.title().replace('-', ' ')
    
    # Try first word if capitalized and >= 3 chars
    words = name.split()
    if words and len(words[0]) >= 3:
        first = words[0].strip('®™©')
        if first[0].isupper() or first.isupper():
            return first
    
    return None

# ============================================================================
# SIZE/QUANTITY EXTRACTION
# ============================================================================

def extract_quantity(name, subtitle='', unit=''):
    """Extract quantity info: value, unit, pack_size"""
    text = f"{name} {subtitle} {unit}".lower()
    
    result = {
        'quantity_value': None,
        'quantity_unit': None,
        'pack_size': None,
        'quantity_raw': None,
    }
    
    # Pack patterns: 6x330ml, 4 x 1.5л
    pack_match = re.search(r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|гр?|g|кг|kg)', text)
    if pack_match:
        pack_size = int(pack_match.group(1))
        value = float(pack_match.group(2).replace(',', '.'))
        unit = pack_match.group(3).lower()
        
        # Normalize units
        unit_map = {'мл': 'ml', 'л': 'l', 'гр': 'g', 'г': 'g', 'кг': 'kg'}
        unit = unit_map.get(unit, unit)
        
        result['quantity_value'] = value
        result['quantity_unit'] = unit
        result['pack_size'] = pack_size
        result['quantity_raw'] = pack_match.group(0)
        return result
    
    # Single quantity patterns
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', 'ml'),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l|L)(?:\s|$|[^a-z])', 'l'),
        (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)(?:\s|$|[^a-z])', 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 'kg'),
        (r'(\d+)\s*(бр|броя|pcs)', 'pcs'),
        (r'(\d+(?:[.,]\d+)?)\s*(см|cm)', 'cm'),
    ]
    
    for pattern, unit_name in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(',', '.'))
            result['quantity_value'] = value
            result['quantity_unit'] = unit_name
            result['quantity_raw'] = match.group(0)
            return result
    
    return result

# ============================================================================
# CATEGORY ASSIGNMENT
# ============================================================================

CATEGORIES = {
    'Млечни продукти': ['мляко', 'сирене', 'кашкавал', 'йогурт', 'кисело', 'масло', 'извара', 'скир', 'крем сирене', 'топено', 'моцарела', 'пармезан', 'бри', 'камамбер', 'фета'],
    'Месо и колбаси': ['месо', 'пилешко', 'свинско', 'говеждо', 'агнешко', 'телешко', 'кайма', 'филе', 'бут', 'врат', 'каре', 'ребра', 'шунка', 'салам', 'луканка', 'наденица', 'кренвирш', 'бекон', 'пастет'],
    'Риба и морски дарове': ['риба', 'сьомга', 'скумрия', 'пъстърва', 'херинга', 'тон', 'скариди', 'миди', 'калмари', 'филе риба'],
    'Плодове и зеленчуци': ['ябълки', 'портокали', 'банани', 'ягоди', 'круши', 'грозде', 'лимони', 'мандарини', 'киви', 'авокадо', 'домати', 'краставици', 'пипер', 'лук', 'картофи', 'моркови', 'зеле', 'салата', 'спанак', 'броколи', 'тиквички', 'патладжан', 'гъби'],
    'Хляб и печива': ['хляб', 'питка', 'земел', 'кифла', 'баница', 'бутер', 'кроасан', 'багета', 'франзела', 'тост', 'пита', 'лаваш', 'донат', 'мъфин', 'кекс'],
    'Напитки безалкохолни': ['сок', 'вода', 'газирана', 'кола', 'фанта', 'спрайт', 'пепси', 'енергийна', 'айрян', 'чай', 'студен чай'],
    'Напитки алкохолни': ['бира', 'вино', 'уиски', 'водка', 'ракия', 'ром', 'джин', 'ликьор', 'коняк', 'бренди', 'шампанско', 'просеко'],
    'Кафе и чай': ['кафе', 'еспресо', 'капсули', 'чай', 'мляно кафе', 'разтворимо кафе', 'кафе на зърна'],
    'Сладкарски изделия': ['шоколад', 'бонбони', 'бисквити', 'вафли', 'торта', 'сладолед', 'десерт', 'крем', 'пудинг', 'желе'],
    'Снаксове': ['чипс', 'крекери', 'пуканки', 'солети', 'ядки', 'сушени плодове', 'бадеми', 'фъстъци', 'кашу'],
    'Консерви и буркани': ['консерва', 'буркан', 'маслини', 'кисели', 'туршия', 'лютеница', 'компот', 'конфитюр', 'мармалад'],
    'Зърнени и бобови': ['ориз', 'леща', 'боб', 'грах', 'нахут', 'киноа', 'булгур', 'кускус', 'овесени'],
    'Паста и тестени': ['паста', 'макарони', 'спагети', 'лазаня', 'нудълс', 'кори', 'тесто'],
    'Подправки и сосове': ['подправка', 'сос', 'кетчуп', 'майонеза', 'горчица', 'оцет', 'олио', 'зехтин'],
    'Замразени': ['замразен', 'замразена', 'замразени', 'пица замразена', 'зеленчуци замразени'],
    'Храна за домашни любимци': ['храна за котки', 'храна за кучета', 'котешка', 'кучешка', 'whiskas', 'pedigree', 'felix'],
    'Почистващи препарати': ['препарат', 'почистващ', 'перилен', 'омекотител', 'белина', 'обезмаслител', 'препарат за съдове', 'спрей'],
    'Хартиени изделия': ['тоалетна хартия', 'кърпи', 'салфетки', 'кухненска ролка'],
    'Козметика и хигиена': ['шампоан', 'сапун', 'душ гел', 'крем', 'дезодорант', 'паста за зъби', 'четка', 'самобръсначка', 'пяна за бръснене'],
    'Бебешки продукти': ['пелени', 'памперс', 'бебешко', 'кърмачета'],
    'Инструменти': ['бормашина', 'шлайф', 'циркуляр', 'лобзик', 'гайковерт', 'битове', 'инструмент', 'комплект инструменти'],
    'Градина': ['градина', 'саксия', 'растение', 'цвете', 'орхидея', 'тор', 'семена'],
    'Дом и бит': ['чаша', 'чиния', 'тенджера', 'тиган', 'прибор', 'кърпа', 'възглавница', 'завивка'],
}

def assign_category(name, subtitle='', description=''):
    """Assign product category"""
    text = f"{name} {subtitle} {description}".lower()
    
    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                return category
    
    return 'Други'

# ============================================================================
# MAIN CLEANING PIPELINE
# ============================================================================

def clean_name(name):
    """Clean product name"""
    if not name:
        return ''
    # Remove newlines
    name = re.sub(r'\s*\n\s*', ' ', name)
    # Remove multiple spaces
    name = re.sub(r'\s+', ' ', name)
    # Remove trademark symbols
    name = re.sub(r'[®™©]', '', name)
    # Strip
    return name.strip()


def clean_product(raw):
    """Clean single product, extract all attributes"""
    name = clean_name(raw.get('raw_name', ''))
    subtitle = clean_name(raw.get('raw_subtitle', ''))
    description = clean_name(raw.get('raw_description', ''))
    
    # Full name combines name + subtitle
    full_name = name
    if subtitle and subtitle.lower() not in name.lower():
        full_name = f"{name} {subtitle}"
    
    # Extract attributes
    brand = extract_brand(name, subtitle, description)
    quantity = extract_quantity(name, subtitle, raw.get('raw_unit', ''))
    category = assign_category(name, subtitle, description)
    
    # Price handling
    price_eur = raw.get('price_eur')
    price_bgn = raw.get('price_bgn')
    
    if price_eur is None and price_bgn:
        price_eur = round(price_bgn / 1.9558, 2)
    if price_bgn is None and price_eur:
        price_bgn = round(price_eur * 1.9558, 2)
    
    return {
        'store': raw.get('store'),
        'sku': raw.get('sku'),
        'name': full_name,
        'brand': brand,
        'category': category,
        'quantity_value': quantity['quantity_value'],
        'quantity_unit': quantity['quantity_unit'],
        'pack_size': quantity['pack_size'],
        'quantity_raw': quantity['quantity_raw'],
        'price_eur': price_eur,
        'price_bgn': price_bgn,
        'old_price_bgn': raw.get('old_price_bgn'),
        'image_url': raw.get('image_url'),
        'description': description[:200] if description else None,
    }


def main():
    print("="*60, flush=True)
    print("CLEANING PRODUCTS", flush=True)
    print("="*60, flush=True)
    
    # Load raw
    with open(INPUT_FILE) as f:
        raw_products = json.load(f)
    
    print(f"Loaded {len(raw_products)} raw products", flush=True)
    
    # Clean all
    cleaned = []
    for raw in raw_products:
        clean = clean_product(raw)
        if clean['name'] and clean['price_eur']:  # Must have name and price
            cleaned.append(clean)
    
    print(f"Cleaned {len(cleaned)} products (with name and price)", flush=True)
    
    # Stats
    by_store = defaultdict(int)
    by_category = defaultdict(int)
    with_brand = 0
    with_quantity = 0
    
    for p in cleaned:
        by_store[p['store']] += 1
        by_category[p['category']] += 1
        if p['brand']:
            with_brand += 1
        if p['quantity_value']:
            with_quantity += 1
    
    print(f"\nBy store:", flush=True)
    for store, count in sorted(by_store.items()):
        print(f"  {store}: {count}", flush=True)
    
    print(f"\nWith brand: {with_brand} ({with_brand/len(cleaned)*100:.1f}%)", flush=True)
    print(f"With quantity: {with_quantity} ({with_quantity/len(cleaned)*100:.1f}%)", flush=True)
    
    print(f"\nBy category:", flush=True)
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1])[:15]:
        print(f"  {cat}: {count}", flush=True)
    
    # Save CSV
    csv_fields = ['store', 'sku', 'name', 'brand', 'category', 'quantity_value', 'quantity_unit', 'pack_size', 'price_eur', 'price_bgn', 'old_price_bgn', 'image_url', 'description']
    
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(cleaned)
    
    print(f"\nSaved CSV: {OUTPUT_CSV}", flush=True)
    
    # Save JSON
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    print(f"Saved JSON: {OUTPUT_JSON}", flush=True)
    
    # Show samples
    print(f"\n{'='*60}", flush=True)
    print("SAMPLE CLEANED PRODUCTS", flush=True)
    print("="*60, flush=True)
    
    for store in ['Kaufland', 'Lidl', 'Billa']:
        print(f"\n{store}:", flush=True)
        samples = [p for p in cleaned if p['store'] == store][:5]
        for p in samples:
            qty = f"{p['quantity_value']}{p['quantity_unit']}" if p['quantity_value'] else '-'
            brand = p['brand'] or '-'
            print(f"  [{p['category'][:15]}] {p['name'][:40]} | Brand: {brand} | Qty: {qty} | €{p['price_eur']}", flush=True)


if __name__ == '__main__':
    main()
