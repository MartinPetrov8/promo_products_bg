#!/usr/bin/env python3
"""
Hybrid cleaning pipeline:
1. Apply rules to all products (free, 85-97% accurate)
2. Detect low-confidence extractions
3. Send only edge cases to LLM (~$0.002/run)
"""

import json
import re
import subprocess
import os
from collections import defaultdict

# Load configs
with open('config/brands.json') as f:
    BRANDS = json.load(f)['brands']
with open('config/categories.json') as f:
    CATEGORY_CONFIG = json.load(f)['categories']

# Pre-compile brand patterns
BRAND_PATTERNS = [(b.rstrip('®™© '), re.compile(
    r'(?:^|[\s\-/\(])' + re.escape(b.rstrip('®™© ')) + r'(?:[\s\-/\)®™©,]|$)', re.I)) 
    for b in sorted(BRANDS, key=len, reverse=True)]

def extract_brand(text):
    for brand, pattern in BRAND_PATTERNS:
        if pattern.search(text):
            return brand, 1.0  # confidence
    # Check if text has potential brand (capitalized word at start)
    if re.match(r'^[A-ZА-Я]{2,}', text):
        return None, 0.3  # low confidence - might have brand
    return None, 1.0

def extract_category(text):
    text_lower = text.lower()
    scores = defaultdict(int)
    for cat, keywords in CATEGORY_CONFIG.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                scores[cat] += len(kw) * 2 if len(kw) > 4 else len(kw)
    if scores:
        best = max(scores, key=scores.get)
        confidence = min(scores[best] / 20, 1.0)  # Higher score = more confident
        return best, confidence
    return 'Други', 0.5

def extract_quantity(text):
    text_lower = text.lower()
    
    # Check if has quantity pattern
    has_pattern = bool(re.search(r'\d+(?:[.,]\d+)?\s*(мл|ml|л|l|гр|g|кг|kg|бр|w|см)', text_lower, re.I))
    
    # Addition: "32+8 бр."
    add_match = re.search(r'(\d+)\s*\+\s*(\d+)\s*(бр\.?)', text_lower)
    if add_match:
        return float(int(add_match.group(1)) + int(add_match.group(2))), 'бр.', 1.0
    
    # Dimensions
    dim = re.search(r'(\d+)\s*[xх]\s*(\d+)\s*см', text_lower)
    if dim:
        return float(int(dim.group(1)) * int(dim.group(2))), 'см', 0.9
    
    # Diameter
    diam = re.search(r'[øо](\d+)\s*см', text_lower)
    if diam:
        return float(diam.group(1)), 'см', 0.9
    
    # Wattage
    watt = re.search(r'(\d+(?:[.,]\d+)?)\s*w', text_lower)
    if watt:
        return float(watt.group(1).replace(',', '.')), 'W', 1.0
    
    # Pack: 6x500ml
    pack = re.search(r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|гр?|g|кг|kg)', text_lower)
    if pack:
        count = int(pack.group(1))
        value = float(pack.group(2).replace(',', '.'))
        unit = pack.group(3).lower()
        if unit in ('л', 'l'): value, unit = value * 1000, 'ml'
        elif unit in ('кг', 'kg'): value, unit = value * 1000, 'g'
        elif unit in ('мл', 'ml'): unit = 'ml'
        elif unit in ('гр', 'г', 'g'): unit = 'g'
        return value * count, unit, 1.0
    
    # Single quantity
    for pattern, base_unit, mult in [
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', 'ml', 1),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l)(?:\s|$|,|=)', 'ml', 1000),
        (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)(?:\s|$|,)', 'g', 1),
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 'g', 1000),
        (r'(\d+)\s*(бр\.?|pcs)', 'бр.', 1),
    ]:
        m = re.search(pattern, text_lower)
        if m:
            return float(m.group(1).replace(',', '.')) * mult, base_unit, 1.0
    
    # Has pattern but couldn't extract = low confidence
    if has_pattern:
        return None, None, 0.3
    return None, None, 1.0

def llm_extract_batch(products, api_key):
    """Send edge cases to GPT-4o-mini."""
    if not products:
        return {}
    
    prompt = """Extract from Bulgarian products. Return JSON: {"products": [{"sku": "...", "brand": "...", "category": "...", "quantity_value": N, "quantity_unit": "..."}]}

Categories: Месо и колбаси, Млечни продукти, Напитки, Плодове и зеленчуци, Хигиена, Дом, Сладкарски изделия, Други

Products:
"""
    batch_text = "\n".join([f"SKU:{p['sku']}|{p['text']}" for p in products])
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Extract product data. Return only valid JSON."},
            {"role": "user", "content": prompt + batch_text}
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"}
    }
    
    cmd = ['curl', '-s', 'https://api.openai.com/v1/chat/completions',
           '-H', 'Content-Type: application/json',
           '-H', f'Authorization: Bearer {api_key}',
           '-d', json.dumps(payload)]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    try:
        resp = json.loads(result.stdout)
        content = resp['choices'][0]['message']['content']
        data = json.loads(content)
        prods = data.get('products', data if isinstance(data, list) else [])
        return {str(p['sku']): p for p in prods if p.get('sku')}
    except:
        return {}

def main():
    # Load raw products
    with open('output/raw_products.json') as f:
        raw_products = json.load(f)
    
    print(f"Processing {len(raw_products)} products...")
    
    # Phase 1: Apply rules
    results = []
    edge_cases = []
    
    for p in raw_products:
        text = (p.get('raw_name', '') + ' ' + p.get('raw_subtitle', '')).strip()
        sku = p.get('sku')
        
        # Use raw brand if available, otherwise extract
        raw_brand = p.get('brand')
        if raw_brand:
            brand, brand_conf = raw_brand, 1.0
        else:
            brand, brand_conf = extract_brand(text)
        category, cat_conf = extract_category(text)
        qty_value, qty_unit, qty_conf = extract_quantity(text)
        
        # Determine overall confidence
        min_conf = min(brand_conf, cat_conf, qty_conf)
        
        result = {
            'sku': sku,
            'store': p.get('store'),
            'raw_name': p.get('raw_name'),
            'raw_subtitle': p.get('raw_subtitle'),
            'brand': brand,
            'category': category,
            'quantity_value': qty_value,
            'quantity_unit': qty_unit,
            'price_bgn': p.get('price_bgn'),
            'old_price_bgn': p.get('old_price_bgn'),
            'image_url': p.get('image_url'),
            'url': p.get('product_url'),
            '_confidence': min_conf
        }
        results.append(result)
        
        if min_conf < 0.5:
            edge_cases.append({'sku': sku, 'text': text})
    
    print(f"Rules applied: {len(results)} products")
    print(f"Edge cases: {len(edge_cases)} ({len(edge_cases)*100/len(results):.1f}%)")
    
    # Phase 2: LLM for edge cases
    if edge_cases:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            try:
                with open(os.path.expanduser('~/.config/openai/api_key')) as f:
                    api_key = f.read().strip()
            except:
                pass
        
        if api_key:
            print(f"\nSending {len(edge_cases)} edge cases to GPT-4o-mini...")
            
            # Process in batches
            BATCH_SIZE = 30
            llm_results = {}
            for i in range(0, len(edge_cases), BATCH_SIZE):
                batch = edge_cases[i:i+BATCH_SIZE]
                print(f"  Batch {i//BATCH_SIZE + 1}/{(len(edge_cases)-1)//BATCH_SIZE + 1}...", end=" ", flush=True)
                batch_results = llm_extract_batch(batch, api_key)
                llm_results.update(batch_results)
                print(f"got {len(batch_results)}")
            
            # Merge LLM results
            for r in results:
                if r['sku'] in llm_results:
                    llm = llm_results[r['sku']]
                    if llm.get('brand'): r['brand'] = llm['brand']
                    if llm.get('category'): r['category'] = llm['category']
                    if llm.get('quantity_value'): r['quantity_value'] = llm['quantity_value']
                    if llm.get('quantity_unit'): r['quantity_unit'] = llm['quantity_unit']
            
            print(f"Merged {len(llm_results)} LLM extractions")
        else:
            print("No OpenAI API key - skipping LLM extraction")
    
    # Remove confidence field
    for r in results:
        del r['_confidence']
    
    # Save
    with open('output/products_clean.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Stats
    with_brand = sum(1 for r in results if r['brand'])
    with_qty = sum(1 for r in results if r['quantity_value'])
    print(f"\n=== RESULTS ===")
    print(f"Total: {len(results)}")
    print(f"With brand: {with_brand} ({with_brand*100/len(results):.1f}%)")
    print(f"With quantity: {with_qty} ({with_qty*100/len(results):.1f}%)")
    print(f"Saved: output/products_clean.json")

if __name__ == '__main__':
    main()
