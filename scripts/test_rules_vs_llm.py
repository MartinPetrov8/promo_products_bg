#!/usr/bin/env python3
"""Test Python rules against LLM output - v4 with W and cm."""

import json
import re
from collections import defaultdict

with open('output/products_llm_cleaned.json') as f:
    llm_data = json.load(f)
with open('output/raw_products.json') as f:
    raw_data = json.load(f)
with open('config/brands.json') as f:
    BRANDS = json.load(f)['brands']
with open('config/categories.json') as f:
    CATEGORY_CONFIG = json.load(f)['categories']

raw_lookup = {}
for r in raw_data:
    if r.get('sku'):
        text = (r.get('raw_name', '') + ' ' + r.get('raw_subtitle', '')).strip()
        raw_lookup[r['sku']] = text

BRAND_PATTERNS = [(b.rstrip('®™© '), re.compile(r'(?:^|[\s\-/\(])' + re.escape(b.rstrip('®™© ')) + r'(?:[\s\-/\)®™©,]|$)', re.I)) 
                  for b in sorted(BRANDS, key=len, reverse=True)]

def extract_brand_rules(text):
    for brand, pattern in BRAND_PATTERNS:
        if pattern.search(text): return brand
    return None

def extract_category_rules(text):
    text_lower = text.lower()
    scores = defaultdict(int)
    for cat, keywords in CATEGORY_CONFIG.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                scores[cat] += len(kw) * 2 if len(kw) > 4 else len(kw)
    return max(scores, key=scores.get) if scores else 'Други'

def extract_quantity_rules(text):
    text_lower = text.lower()
    
    # Addition: "32+8 бр."
    add_match = re.search(r'(\d+)\s*\+\s*(\d+)\s*(бр\.?)', text_lower)
    if add_match:
        return float(int(add_match.group(1)) + int(add_match.group(2))), 'бр.', None
    
    # Dimensions: "150 x 200 см" → area
    dim = re.search(r'(\d+)\s*[xх]\s*(\d+)\s*см', text_lower)
    if dim:
        return float(int(dim.group(1)) * int(dim.group(2))), 'см', None
    
    # Diameter: "Ø22 см"
    diam = re.search(r'[øо](\d+)\s*см', text_lower)
    if diam:
        return float(diam.group(1)), 'см', None
    
    # Single dimension: "32 х 7 см" → take first
    single_dim = re.search(r'(\d+)\s*[хx]\s*\d+\s*см', text_lower)
    if single_dim:
        return float(single_dim.group(1)), 'см', None
    
    # Wattage: "4,9 W" or "10 W"
    watt = re.search(r'(\d+(?:[.,]\d+)?)\s*w', text_lower)
    if watt:
        return float(watt.group(1).replace(',', '.')), 'W', None
    
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
        return value * count, unit, f"{count}x"
    
    # Single quantity (prefer ml/l/g/kg over бр/пр)
    for pattern, base_unit, mult in [
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', 'ml', 1),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l)(?:\s|$|,|=)', 'ml', 1000),
        (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)(?:\s|$|,)', 'g', 1),
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 'g', 1000),
        (r'(\d+)\s*(бр\.?|pcs)', 'бр.', 1),
        (r'(\d+)\s*(пранета|пр\.?)', 'пранета', 1),
        (r'(\d+)\s*(части)', 'части', 1),
    ]:
        m = re.search(pattern, text_lower)
        if m:
            return float(m.group(1).replace(',', '.')) * mult, base_unit, None
    return None, None, None

def normalize_unit(unit):
    if not unit: return None
    unit = str(unit).lower().strip()
    return {'мл': 'ml', 'л': 'ml', 'l': 'ml', 'гр': 'g', 'г': 'g', 
            'кг': 'g', 'kg': 'g', 'бр': 'бр.', 'бр.': 'бр.', 'pcs': 'бр.',
            'w': 'W', 'см': 'см'}.get(unit, unit)

print("=== TESTING RULES VS LLM (v4) ===\n")
results = {'brand': [0, 0], 'category': [0, 0], 'quantity': [0, 0]}

for p in llm_data:
    sku = p.get('sku')
    if sku not in raw_lookup: continue
    text = raw_lookup[sku]
    
    llm_brand = (p.get('brand') or '').rstrip('®™© ').lower()
    rule_brand = (extract_brand_rules(text) or '').lower()
    results['brand'][0 if llm_brand == rule_brand else 1] += 1
    
    if p.get('category', 'Други') == extract_category_rules(text):
        results['category'][0] += 1
    else:
        results['category'][1] += 1
    
    if p.get('quantity_value') and p.get('quantity_unit'):
        llm_qty = float(p['quantity_value'])
        llm_unit = normalize_unit(p['quantity_unit'])
        if p['quantity_unit'].lower() in ('л', 'l'): llm_qty *= 1000
        elif p['quantity_unit'].lower() in ('кг', 'kg'): llm_qty *= 1000
        
        rule_qty, rule_unit, _ = extract_quantity_rules(text)
        rule_unit = normalize_unit(rule_unit)
        
        if rule_qty and abs(rule_qty - llm_qty) < 1 and rule_unit == llm_unit:
            results['quantity'][0] += 1
        else:
            results['quantity'][1] += 1

for key in ['brand', 'category', 'quantity']:
    match, miss = results[key]
    total = match + miss
    print(f"{key.upper():10} {match}/{total} ({match*100/total:.1f}%)")
