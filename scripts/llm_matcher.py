#!/usr/bin/env python3
"""Helper for LLM-based product matching"""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / 'data'
DB_PATH = DATA_DIR / 'promobg.db'
OFF_DB_PATH = DATA_DIR / 'off_bulgaria.db'

def get_unmatched_food_products(limit=50):
    """Get unmatched products that are likely food"""
    food_keywords = ['мляко', 'сирене', 'кисело', 'масло', 'хляб', 'месо', 'пиле', 'риба', 
                     'бисквити', 'шоколад', 'бонбони', 'сок', 'вода', 'бира', 'вино',
                     'кафе', 'чай', 'захар', 'сол', 'брашно', 'ориз', 'паста', 'зърнена',
                     'плод', 'зеленчук', 'салам', 'кренвирш', 'луканка', 'кашкавал',
                     'кисело', 'айран', 'йогурт', 'извара', 'урда', 'сметана',
                     'майонеза', 'кетчуп', 'горчица', 'оцет', 'олио', 'зехтин',
                     'консерв', 'туна', 'сардин', 'пастет', 'бекон', 'шунка',
                     'наденица', 'кайма', 'суджук', 'филе', 'пържола',
                     'яйца', 'яйце', 'яица', 'боб', 'леща', 'нахут',
                     'орех', 'бадем', 'фъстък', 'лешник', 'стафид',
                     'чипс', 'крекер', 'гофрет', 'вафл', 'кроасан',
                     'торта', 'кекс', 'баница', 'питка', 'кифл',
                     'спагети', 'макарон', 'нудъл', 'лазаня',
                     'пица', 'замразен', 'сладолед', 'крем']
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.name, p.brand, p.description
        FROM products p
        LEFT JOIN product_off_matches m ON p.id = m.product_id
        WHERE m.id IS NULL
        ORDER BY p.name
    ''')
    
    results = []
    for pid, name, brand, desc in cursor.fetchall():
        name_lower = (name or '').lower()
        desc_lower = (desc or '').lower()
        if any(kw in name_lower or kw in desc_lower for kw in food_keywords):
            results.append({
                'id': pid,
                'name': name.replace('\n', ' '),
                'brand': brand,
                'description': (desc or '').replace('\n', ' ')[:100]
            })
            if len(results) >= limit:
                break
    
    conn.close()
    return results

def search_off(query, limit=10):
    """Search OFF products by name"""
    conn = sqlite3.connect(OFF_DB_PATH)
    cursor = conn.cursor()
    
    # Search in both name fields
    cursor.execute('''
        SELECT id, product_name, product_name_bg, brands
        FROM off_products
        WHERE product_name_bg LIKE ? OR product_name LIKE ? OR brands LIKE ?
        LIMIT ?
    ''', (f'%{query}%', f'%{query}%', f'%{query}%', limit))
    
    results = []
    for oid, name, name_bg, brands in cursor.fetchall():
        results.append({
            'id': oid,
            'name': name,
            'name_bg': name_bg,
            'brands': brands
        })
    
    conn.close()
    return results

def save_match(product_id, off_id, confidence=0.9):
    """Save a match to the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO product_off_matches (product_id, off_product_id, match_type, match_confidence)
            VALUES (?, ?, 'llm_match', ?)
        ''', (product_id, off_id, confidence))
        conn.commit()
        print(f"✓ Saved match: product {product_id} → OFF {off_id}")
        return True
    except sqlite3.IntegrityError:
        print(f"! Already matched: product {product_id}")
        return False
    finally:
        conn.close()

def mark_no_match(product_id):
    """Mark a product as having no OFF match (non-food or not in database)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO product_off_matches (product_id, off_product_id, match_type, match_confidence)
            VALUES (?, NULL, 'no_match', 0)
        ''', (product_id,))
        conn.commit()
        print(f"✓ Marked as no match: product {product_id}")
        return True
    except sqlite3.IntegrityError:
        print(f"! Already processed: product {product_id}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    print("=== Unmatched Food Products (first 20) ===\n")
    products = get_unmatched_food_products(20)
    for p in products:
        print(f"ID {p['id']}: [{p['brand'] or 'N/A'}] {p['name']}")
        if p['description']:
            print(f"    Desc: {p['description']}")
        print()
