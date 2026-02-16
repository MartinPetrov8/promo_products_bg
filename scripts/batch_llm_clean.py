#!/usr/bin/env python3
"""
Batch LLM cleaning via OpenAI GPT-4.
"""

import json
import os
import time
import requests

API_KEY = os.environ.get('OPENAI_API_KEY')
ENDPOINT = "https://api.openai.com/v1/chat/completions"

CATEGORIES = ["Млечни продукти", "Месо и колбаси", "Риба", "Плодове и зеленчуци", 
              "Хляб и печива", "Сладкарски изделия", "Напитки безалкохолни", 
              "Напитки алкохолни", "Кафе и чай", "Снаксове", "Консерви", 
              "Зърнени храни", "Паста", "Подправки и сосове", "Замразени", 
              "Храна за животни", "Почистващи", "Хигиена", "Козметика", 
              "Инструменти", "Градина", "Дом", "Други"]

SYSTEM_PROMPT = f"""Parse Bulgarian grocery products and return a JSON array.
For each product extract:
- brand: manufacturer name or null
- product_name: clean name without brand/quantity
- quantity_value: number or null (total, e.g. 6x500ml = 3000)
- quantity_unit: ml/l/g/kg/pcs or null
- pack_size: pack info like "6x", "промопакет", "от свежата витрина" or null
- category: one of {CATEGORIES}

Return ONLY valid JSON array, no markdown."""

def call_api(products):
    prompt = "Parse these products:\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(products))
    
    resp = requests.post(ENDPOINT, headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }, json={
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }, timeout=120)
    resp.raise_for_status()
    
    result = resp.json()['choices'][0]['message']['content']
    # Extract JSON
    if '```' in result:
        result = result.split('```')[1]
        if result.startswith('json'):
            result = result[4:]
    return json.loads(result.strip())

def main():
    with open('output/raw_products.json') as f:
        raw = json.load(f)
    
    # Prepare names
    products = []
    for r in raw:
        name = (r.get('raw_name', '') + ' ' + r.get('raw_subtitle', '')).strip()
        if name:
            products.append({
                'store': r['store'],
                'sku': r.get('sku'),
                'raw_name': ' '.join(name.split()),
                'price_eur': r.get('price_eur'),
                'price_bgn': r.get('price_bgn')
            })
    
    print(f"Processing {len(products)} products...")
    
    BATCH = 30
    cleaned = []
    
    for i in range(0, len(products), BATCH):
        batch = products[i:i+BATCH]
        names = [p['raw_name'] for p in batch]
        
        print(f"Batch {i//BATCH+1}/{(len(products)+BATCH-1)//BATCH}...", end=" ", flush=True)
        
        try:
            parsed = call_api(names)
            if len(parsed) == len(batch):
                for j, p in enumerate(parsed):
                    cleaned.append({
                        'store': batch[j]['store'],
                        'sku': batch[j]['sku'],
                        'name': p.get('product_name', batch[j]['raw_name']),
                        'brand': p.get('brand'),
                        'category': p.get('category', 'Други'),
                        'quantity_value': p.get('quantity_value'),
                        'quantity_unit': p.get('quantity_unit'),
                        'pack_size': str(p['pack_size']) if p.get('pack_size') else None,
                        'price_eur': batch[j]['price_eur'],
                        'price_bgn': batch[j]['price_bgn'],
                    })
                print("✓")
            else:
                raise ValueError(f"Got {len(parsed)}, expected {len(batch)}")
        except Exception as e:
            print(f"✗ {e}")
            for p in batch:
                cleaned.append({
                    'store': p['store'], 'sku': p['sku'],
                    'name': p['raw_name'], 'brand': None,
                    'category': 'Други', 'quantity_value': None,
                    'quantity_unit': None, 'pack_size': None,
                    'price_eur': p['price_eur'], 'price_bgn': p['price_bgn']
                })
        
        time.sleep(0.5)  # Rate limit
    
    # Save
    with open('output/products_llm_cleaned.json', 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    # Stats
    with_brand = sum(1 for p in cleaned if p['brand'])
    with_qty = sum(1 for p in cleaned if p['quantity_value'])
    print(f"\nDone! {len(cleaned)} products")
    print(f"  Brands: {with_brand} ({with_brand/len(cleaned)*100:.1f}%)")
    print(f"  Quantities: {with_qty} ({with_qty/len(cleaned)*100:.1f}%)")

if __name__ == '__main__':
    main()
