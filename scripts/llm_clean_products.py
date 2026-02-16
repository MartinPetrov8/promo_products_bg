#!/usr/bin/env python3
"""
LLM-powered product data cleaning pipeline.
Processes each product through an LLM to extract structured data.
"""

import json
import os
import time
import requests
from pathlib import Path

# Kimi API config
KIMI_API_KEY = os.environ.get('KIMI_API_KEY')
KIMI_ENDPOINT = "https://api.moonshot.ai/v1/chat/completions"

CATEGORIES = [
    "Млечни продукти",
    "Месо и колбаси", 
    "Риба и морски дарове",
    "Плодове и зеленчуци",
    "Хляб и печива",
    "Сладкарски изделия",
    "Напитки безалкохолни",
    "Напитки алкохолни",
    "Кафе и чай",
    "Снаксове",
    "Консерви",
    "Зърнени храни",
    "Паста и тестени изделия",
    "Подправки и сосове",
    "Замразени храни",
    "Храна за животни",
    "Почистващи препарати",
    "Хигиена",
    "Козметика",
    "Инструменти",
    "Градина",
    "Дом и бит",
    "Други"
]

SYSTEM_PROMPT = f"""You are a Bulgarian grocery product data parser. Extract structured data from product names.

CATEGORIES (pick exactly one):
{chr(10).join(f'- {c}' for c in CATEGORIES)}

RULES:
1. brand: The manufacturer/brand name (e.g., "Milka", "Верея", "Billa"). Return null if unknown.
2. product_name: Clean product name WITHOUT brand, quantity, or promo text.
3. quantity_value: Numeric value (e.g., 500, 1.5). Return null if not specified.
4. quantity_unit: One of: ml, l, g, kg, pcs. Return null if not specified.
5. pack_size: Number of items in pack (e.g., "6x330ml" -> 6). Also include special notes like "промопакет", "от свежата витрина". Return null if single item.
6. category: Pick from the list above.

EXAMPLES:
Input: "Milka Млечен шоколад различни видове 100 г"
Output: {{"brand": "Milka", "product_name": "Млечен шоколад различни видове", "quantity_value": 100, "quantity_unit": "g", "pack_size": null, "category": "Сладкарски изделия"}}

Input: "Верея Кисело мляко 3.6% 400 г"
Output: {{"brand": "Верея", "product_name": "Кисело мляко 3.6%", "quantity_value": 400, "quantity_unit": "g", "pack_size": null, "category": "Млечни продукти"}}

Input: "Загорка Бира 6x500 мл"
Output: {{"brand": "Загорка", "product_name": "Бира", "quantity_value": 3000, "quantity_unit": "ml", "pack_size": "6x", "category": "Напитки алкохолни"}}

Input: "Свински гърди от свежата витрина"
Output: {{"brand": null, "product_name": "Свински гърди", "quantity_value": null, "quantity_unit": null, "pack_size": "от свежата витрина", "category": "Месо и колбаси"}}

Respond with ONLY valid JSON, no markdown, no explanation."""

def call_kimi(products_batch):
    """Call Kimi API to parse a batch of products."""
    if not KIMI_API_KEY:
        raise ValueError("KIMI_API_KEY not set")
    
    # Format batch
    batch_text = "\n".join([f"{i+1}. {p}" for i, p in enumerate(products_batch)])
    
    response = requests.post(
        KIMI_ENDPOINT,
        headers={
            "Authorization": f"Bearer {KIMI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "moonshot-v1-8k",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Parse these {len(products_batch)} products and return a JSON array:\n\n{batch_text}"}
            ],
            "temperature": 0.1
        },
        timeout=60
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def parse_batch(products_batch, max_retries=3):
    """Parse a batch with retries."""
    for attempt in range(max_retries):
        try:
            result = call_kimi(products_batch)
            # Clean up response
            result = result.strip()
            if result.startswith('```'):
                result = result.split('\n', 1)[1].rsplit('```', 1)[0]
            return json.loads(result)
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None

def main():
    # Load raw products
    with open('output/raw_products.json') as f:
        raw_products = json.load(f)
    
    print(f"Loaded {len(raw_products)} raw products")
    
    # Prepare product names
    products_to_clean = []
    for raw in raw_products:
        name = (raw.get('raw_name', '') + ' ' + raw.get('raw_subtitle', '')).strip()
        name = ' '.join(name.split())  # normalize whitespace
        if name:
            products_to_clean.append({
                'store': raw['store'],
                'sku': raw.get('sku'),
                'raw_name': name,
                'price_eur': raw.get('price_eur'),
                'price_bgn': raw.get('price_bgn')
            })
    
    print(f"Processing {len(products_to_clean)} products with LLM...")
    
    # Process in batches
    BATCH_SIZE = 20
    cleaned = []
    
    for i in range(0, len(products_to_clean), BATCH_SIZE):
        batch = products_to_clean[i:i+BATCH_SIZE]
        batch_names = [p['raw_name'] for p in batch]
        
        print(f"Processing batch {i//BATCH_SIZE + 1}/{(len(products_to_clean) + BATCH_SIZE - 1)//BATCH_SIZE}...")
        
        parsed = parse_batch(batch_names)
        
        if parsed and len(parsed) == len(batch):
            for j, p in enumerate(parsed):
                cleaned.append({
                    'store': batch[j]['store'],
                    'sku': batch[j]['sku'],
                    'name': p.get('product_name', batch[j]['raw_name']),
                    'brand': p.get('brand'),
                    'category': p.get('category', 'Други'),
                    'quantity_value': p.get('quantity_value'),
                    'quantity_unit': p.get('quantity_unit'),
                    'pack_size': p.get('pack_size'),
                    'price_eur': batch[j]['price_eur'],
                    'price_bgn': batch[j]['price_bgn'],
                })
        else:
            print(f"  Batch failed, using fallback")
            for p in batch:
                cleaned.append({
                    'store': p['store'],
                    'sku': p['sku'],
                    'name': p['raw_name'],
                    'brand': None,
                    'category': 'Други',
                    'quantity_value': None,
                    'quantity_unit': None,
                    'pack_size': None,
                    'price_eur': p['price_eur'],
                    'price_bgn': p['price_bgn'],
                })
        
        # Rate limit
        time.sleep(0.5)
    
    # Save results
    with open('output/products_llm_cleaned.json', 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    # Stats
    with_brand = sum(1 for p in cleaned if p['brand'])
    with_qty = sum(1 for p in cleaned if p['quantity_value'])
    print(f"\nResults:")
    print(f"  Total: {len(cleaned)}")
    print(f"  With brand: {with_brand} ({with_brand/len(cleaned)*100:.1f}%)")
    print(f"  With quantity: {with_qty} ({with_qty/len(cleaned)*100:.1f}%)")

if __name__ == '__main__':
    main()
