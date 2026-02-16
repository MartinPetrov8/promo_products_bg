#!/usr/bin/env python3
"""
Ollama-powered product data cleaning - uses local LLM, no API cost.
"""

import json
import time
import requests
from pathlib import Path

OLLAMA_ENDPOINT = "http://172.17.0.1:11434/api/generate"
MODEL = "llama3.1:8b-instruct-q4_K_M"

CATEGORIES = [
    "Млечни продукти", "Месо и колбаси", "Риба и морски дарове",
    "Плодове и зеленчуци", "Хляб и печива", "Сладкарски изделия",
    "Напитки безалкохолни", "Напитки алкохолни", "Кафе и чай",
    "Снаксове", "Консерви", "Зърнени храни", "Паста и тестени изделия",
    "Подправки и сосове", "Замразени храни", "Храна за животни",
    "Почистващи препарати", "Хигиена", "Козметика", "Инструменти",
    "Градина", "Дом и бит", "Други"
]

PROMPT_TEMPLATE = '''Parse this Bulgarian grocery product and extract structured data.
Return ONLY valid JSON with these fields:
- brand: manufacturer name or null
- product_name: clean name without brand/quantity
- quantity_value: number or null
- quantity_unit: ml/l/g/kg/pcs or null
- pack_size: pack info like "6x" or "от свежата витрина" or null
- category: one of {categories}

Product: {product}

JSON:'''

def call_ollama(product_name):
    """Call local Ollama to parse a single product."""
    prompt = PROMPT_TEMPLATE.format(
        categories=", ".join(CATEGORIES),
        product=product_name
    )
    
    try:
        response = requests.post(
            OLLAMA_ENDPOINT,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=30
        )
        response.raise_for_status()
        result = response.json().get('response', '').strip()
        
        # Extract JSON from response
        if '{' in result:
            start = result.index('{')
            end = result.rindex('}') + 1
            return json.loads(result[start:end])
    except Exception as e:
        pass
    return None

def main():
    # Load raw products
    with open('output/raw_products.json') as f:
        raw_products = json.load(f)
    
    print(f"Processing {len(raw_products)} products with Ollama...")
    
    cleaned = []
    success = 0
    
    for i, raw in enumerate(raw_products):
        name = (raw.get('raw_name', '') + ' ' + raw.get('raw_subtitle', '')).strip()
        name = ' '.join(name.split())
        
        if not name:
            continue
            
        # Progress
        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(raw_products)} ({success} parsed)")
        
        parsed = call_ollama(name)
        
        if parsed:
            success += 1
            cleaned.append({
                'store': raw['store'],
                'sku': raw.get('sku'),
                'name': parsed.get('product_name', name),
                'brand': parsed.get('brand'),
                'category': parsed.get('category', 'Други'),
                'quantity_value': parsed.get('quantity_value'),
                'quantity_unit': parsed.get('quantity_unit'),
                'pack_size': parsed.get('pack_size'),
                'price_eur': raw.get('price_eur'),
                'price_bgn': raw.get('price_bgn'),
            })
        else:
            cleaned.append({
                'store': raw['store'],
                'sku': raw.get('sku'),
                'name': name,
                'brand': None,
                'category': 'Други',
                'quantity_value': None,
                'quantity_unit': None,
                'pack_size': None,
                'price_eur': raw.get('price_eur'),
                'price_bgn': raw.get('price_bgn'),
            })
    
    # Save
    with open('output/products_llm_cleaned.json', 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    # Stats
    with_brand = sum(1 for p in cleaned if p['brand'])
    with_qty = sum(1 for p in cleaned if p['quantity_value'])
    print(f"\nDone! Parsed {success}/{len(cleaned)} products")
    print(f"  With brand: {with_brand} ({with_brand/len(cleaned)*100:.1f}%)")
    print(f"  With quantity: {with_qty} ({with_qty/len(cleaned)*100:.1f}%)")

if __name__ == '__main__':
    main()
