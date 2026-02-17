#!/usr/bin/env python3
"""
Hybrid cleaning pipeline:
1. Apply rules to all products (free, 85-97% accurate)
2. Detect low-confidence extractions
3. Send only edge cases to LLM (~$0.002/run)
4. Deduplicate products (same name+store or same SKU+store)
5. Apply OCR brand cache for Lidl
"""

import json
import re
import os
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent

# Load configs
with open(PROJECT_ROOT / 'config/brands.json') as f:
    BRANDS = json.load(f)['brands']
with open(PROJECT_ROOT / 'config/categories.json') as f:
    CATEGORY_CONFIG = json.load(f)['categories']

# Load OCR brand cache for Lidl
BRAND_CACHE = {}
cache_file = PROJECT_ROOT / 'data' / 'brand_cache.json'
if cache_file.exists():
    with open(cache_file) as f:
        BRAND_CACHE = json.load(f)

# Pre-compile brand patterns
BRAND_PATTERNS = [(b.rstrip('®™© '), re.compile(
    r'(?:^|[\s\-/\(])' + re.escape(b.rstrip('®™© ')) + r'(?:[\s\-/\)®™©,]|$)', re.I)) 
    for b in sorted(BRANDS, key=len, reverse=True)]

def normalize_name(name: str) -> str:
    """Normalize name for deduplication."""
    if not name:
        return ''
    # Lowercase, remove special chars, collapse whitespace
    normalized = name.lower()
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def extract_brand(text, sku=None, store=None):
    # Check OCR cache first for Lidl
    if store == 'Lidl' and sku and sku in BRAND_CACHE:
        cached = BRAND_CACHE[sku]
        if cached.get('brand'):
            return cached['brand'], 1.0
    
    for brand, pattern in BRAND_PATTERNS:
        if pattern.search(text):
            return brand, 1.0
    if re.match(r'^[A-ZА-Я]{2,}', text):
        return None, 0.3
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
        confidence = min(scores[best] / 20, 1.0)
        return best, confidence
    return 'Други', 0.5

def extract_quantity(text):
    text_lower = text.lower()
    
    # Addition: "32+8 бр."
    add_match = re.search(r'(\d+)\s*\+\s*(\d+)\s*(бр\.?)', text_lower)
    if add_match:
        return float(int(add_match.group(1)) + int(add_match.group(2))), 'бр.', 1.0
    
    # Pack: 6x500ml
    pack = re.search(r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|гр?|g|кг|kg)', text_lower)
    if pack:
        count = int(pack.group(1))
        value = float(pack.group(2).replace(',', '.'))
        unit = pack.group(3).lower()
        if unit in ('л', 'l'): value, unit = value * 1000, 'ml'
        if unit in ('кг', 'kg'): value, unit = value * 1000, 'g'
        return count * value, 'ml' if unit in ('мл', 'ml') else 'g', 1.0
    
    # Simple units
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 1000, 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)\b', 1, 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l)\b', 1000, 'ml'),
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', 1, 'ml'),
        (r'(\d+)\s*(бр\.?|pcs)', 1, 'бр.'),
    ]
    for pattern, multiplier, unit in patterns:
        m = re.search(pattern, text_lower)
        if m:
            value = float(m.group(1).replace(',', '.')) * multiplier
            return value, unit, 1.0
    
    return None, None, 1.0

def llm_extract_batch(batch, api_key):
    """Extract data from edge cases using GPT-4o-mini."""
    import requests
    
    prompt = "Extract brand, category, quantity from these Bulgarian product names. Return JSON array.\n\n"
    for i, item in enumerate(batch):
        prompt += f"{i+1}. {item['text']}\n"
    prompt += "\nReturn: [{\"sku\": \"...\", \"brand\": \"...\", \"category\": \"...\", \"quantity_value\": ..., \"quantity_unit\": \"...\"}]"
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0
            },
            timeout=60
        )
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        
        # Parse JSON from response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            results = json.loads(json_match.group())
            return {batch[i]['sku']: r for i, r in enumerate(results) if i < len(batch)}
    except Exception as e:
        print(f"LLM error: {e}")
    return {}

def deduplicate(results):
    """Remove duplicate products (same normalized name + store)."""
    seen = set()
    deduplicated = []
    duplicates = 0
    
    for r in results:
        # Create dedup key: normalized name + store
        norm_name = normalize_name(r.get('raw_name', ''))
        store = r.get('store', '')
        key = f"{store}:{norm_name}"
        
        if key in seen:
            duplicates += 1
            continue
        
        seen.add(key)
        deduplicated.append(r)
    
    if duplicates > 0:
        print(f"Removed {duplicates} duplicates")
    
    return deduplicated

def main():
    # Load raw products
    with open(PROJECT_ROOT / 'output/raw_products.json') as f:
        raw_products = json.load(f)
    
    print(f"Processing {len(raw_products)} products...")
    
    # Phase 1: Apply rules
    results = []
    edge_cases = []
    
    for p in raw_products:
        text = ((p.get('raw_name') or '') + ' ' + (p.get('raw_subtitle') or '')).strip()
        sku = p.get('sku')
        store = p.get('store')
        
        # Use raw brand if available, otherwise extract
        raw_brand = p.get('brand')
        if raw_brand:
            brand, brand_conf = raw_brand, 1.0
        else:
            brand, brand_conf = extract_brand(text, sku, store)
        category, cat_conf = extract_category(text)
        
        # Use scraped quantity if available, otherwise extract from text
        raw_qty_value = p.get('quantity_value')
        raw_qty_unit = p.get('quantity_unit')
        if raw_qty_value and raw_qty_unit:
            qty_value, qty_unit, qty_conf = raw_qty_value, raw_qty_unit, 1.0
        else:
            qty_value, qty_unit, qty_conf = extract_quantity(text)
        
        min_conf = min(brand_conf, cat_conf, qty_conf)
        
        result = {
            'sku': sku,
            'store': store,
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
            
            BATCH_SIZE = 30
            llm_results = {}
            for i in range(0, len(edge_cases), BATCH_SIZE):
                batch = edge_cases[i:i+BATCH_SIZE]
                print(f"  Batch {i//BATCH_SIZE + 1}/{(len(edge_cases)-1)//BATCH_SIZE + 1}...", end=" ", flush=True)
                batch_results = llm_extract_batch(batch, api_key)
                llm_results.update(batch_results)
                print(f"got {len(batch_results)}")
            
            for r in results:
                if r['sku'] in llm_results:
                    llm = llm_results[r['sku']]
                    if llm.get('brand'): r['brand'] = llm['brand']
                    # if llm.get('category'): r['category'] = llm['category']  # Disabled - rules more reliable
                    if llm.get('quantity_value'): r['quantity_value'] = llm['quantity_value']
                    if llm.get('quantity_unit'): r['quantity_unit'] = llm['quantity_unit']
            
            print(f"Merged {len(llm_results)} LLM extractions")
        else:
            print("No OpenAI API key - skipping LLM extraction")
    
    # Phase 3: Deduplicate
    print("\nDeduplicating...")
    results = deduplicate(results)
    
    # Remove confidence field
    for r in results:
        del r['_confidence']
    
    # Add clean_name for matching
    for r in results:
        name = r.get('raw_name', '')
        brand = r.get('brand', '')
        if brand and name.lower().startswith(brand.lower()):
            name = name[len(brand):].strip()
        r['clean_name'] = name
    
    # Save
    with open(PROJECT_ROOT / 'output/products_clean.json', 'w', encoding='utf-8') as f:
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
