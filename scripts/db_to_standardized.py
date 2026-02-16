#!/usr/bin/env python3
"""Export DB products to standardized_final.json for matching"""

import sqlite3
import json
import re

DB_PATH = 'data/promobg.db'
OUTPUT_PATH = 'standardized_final.json'

CATEGORY_KEYWORDS = {
    'dairy': ['мляко', 'сирене', 'кашкавал', 'кисело', 'йогурт', 'масло', 'извара', 'крема'],
    'meat': ['кайма', 'пиле', 'свинско', 'телешко', 'салам', 'кренвирш', 'бекон', 'шунка', 'филе', 'бут'],
    'produce': ['домат', 'краставиц', 'картоф', 'морков', 'лук', 'чесън', 'ябълк', 'банан', 'портокал', 'лимон'],
    'bakery': ['хляб', 'питка', 'кифла', 'сомун', 'багета', 'козунак'],
    'beverages': ['вода', 'сок', 'кола', 'бира', 'кафе', 'чай', 'напитка'],
    'alcohol': ['вино', 'водка', 'уиски', 'ракия', 'ром', 'джин'],
    'snacks': ['чипс', 'бисквит', 'вафла', 'шоколад', 'бонбон', 'крекер'],
    'canned': ['консерв', 'маслин', 'кисел', 'туршия'],
    'household': ['перилен', 'почист', 'сапун', 'препарат'],
    'personal_care': ['шампоан', 'душ гел', 'паста', 'дезодорант'],
    'pantry': ['ориз', 'макарон', 'брашно', 'захар', 'олио', 'оцет'],
    'frozen': ['замраз', 'сладолед']
}

def categorize(name):
    name_lower = name.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return cat
    return 'other'

def export():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            p.id, p.name, p.brand,
            s.name as store,
            pr.current_price as price
        FROM products p
        JOIN store_products sp ON p.id = sp.product_id
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN prices pr ON pr.store_product_id = sp.id
        WHERE pr.current_price IS NOT NULL AND pr.current_price > 0
    """)
    
    products = []
    for row in cur.fetchall():
        name = row['name']
        clean_name = re.sub(r'\n', ' ', name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        products.append({
            'id': row['id'],
            'store': row['store'],
            'raw_name': name,
            'clean_name': clean_name,
            'brand': row['brand'],
            'description': clean_name,
            'quantity_value': None,
            'quantity_unit': None,
            'category': categorize(name),
            'price': round(row['price'], 2),
            'old_price': None,
            'discount_pct': None,
            'unit_price': None,
            'unit_price_base': None,
            'image_url': None,
            'validation_errors': []
        })
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    print(f"Exported {len(products)} products to {OUTPUT_PATH}")
    
    by_store = {}
    for p in products:
        by_store[p['store']] = by_store.get(p['store'], 0) + 1
    print(f"By store: {by_store}")

if __name__ == '__main__':
    export()
