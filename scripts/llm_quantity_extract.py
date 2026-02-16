#!/usr/bin/env python3
"""Strict LLM quantity extraction using curl."""

import json
import subprocess
import os

# Get API key from env
api_key = os.environ.get('OPENAI_API_KEY')
if not api_key:
    # Try reading from file
    try:
        with open(os.path.expanduser('~/.config/openai/api_key')) as f:
            api_key = f.read().strip()
    except:
        print("No OpenAI API key found")
        exit(1)

with open('output/need_quantity_extraction.json') as f:
    products = json.load(f)

print(f"Processing {len(products)} products...")

PROMPT = """Extract quantity from these Bulgarian products. Return JSON: {"products": [{"sku": "...", "quantity_value": NUMBER, "quantity_unit": "..."}]}

Rules:
- Packs "6x500ml" → total: 3000ml
- Addition "32+8 бр." → 40 бр.
- Dimensions "150x200" → area (30000)
- Wattage "4.9 W" → 4.9 W
- Convert: л→ml (*1000), кг→g (*1000)

Products:
"""

BATCH_SIZE = 30
results = []

for i in range(0, len(products), BATCH_SIZE):
    batch = products[i:i+BATCH_SIZE]
    batch_text = "\n".join([f"SKU:{p['sku']}|{p['text']}" for p in batch])
    
    print(f"Batch {i//BATCH_SIZE + 1}/{(len(products)-1)//BATCH_SIZE + 1}...", end=" ", flush=True)
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Extract quantities. Return only JSON."},
            {"role": "user", "content": PROMPT + batch_text}
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"}
    }
    
    cmd = ['curl', '-s', 'https://api.openai.com/v1/chat/completions',
           '-H', 'Content-Type: application/json',
           '-H', f'Authorization: Bearer {api_key}',
           '-d', json.dumps(payload)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    try:
        resp = json.loads(result.stdout)
        content = resp['choices'][0]['message']['content']
        batch_result = json.loads(content)
        prods = batch_result.get('products', batch_result if isinstance(batch_result, list) else [])
        results.extend(prods)
        print(f"got {len(prods)}")
    except Exception as e:
        print(f"error: {e}")

print(f"\nExtracted {len(results)} quantities")

# Build lookup
qty_lookup = {str(r.get('sku')): r for r in results if r.get('sku')}
print(f"Valid extractions: {len(qty_lookup)}")

# Merge back
with open('output/products_llm_cleaned.json') as f:
    llm_data = json.load(f)

updated = 0
for p in llm_data:
    sku = str(p.get('sku', ''))
    if sku in qty_lookup:
        q = qty_lookup[sku]
        if q.get('quantity_value') is not None and q.get('quantity_unit'):
            p['quantity_value'] = q['quantity_value']
            p['quantity_unit'] = q['quantity_unit']
            updated += 1

print(f"Updated {updated} products")

with open('output/products_llm_cleaned.json', 'w', encoding='utf-8') as f:
    json.dump(llm_data, f, ensure_ascii=False, indent=2)
