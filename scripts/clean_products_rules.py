#!/usr/bin/env python3
"""
AUTO-GENERATED rule-based product cleaner.
Uses patterns extracted from LLM cleaning.
Run: python scripts/clean_products_rules.py
"""

import json
import csv
import re
from pathlib import Path

# Load config
with open('config/brands.json') as f:
    BRANDS = json.load(f)['brands']

with open('config/categories.json') as f:
    CATEGORY_KEYWORDS = json.load(f)['categories']

with open('config/pack_patterns.json') as f:
    PACK_PATTERNS = json.load(f)['patterns']

def extract_brand(text):
    """Extract brand from product name."""
    text_lower = text.lower()
    for brand in sorted(BRANDS, key=len, reverse=True):
        pattern = r'(?:^|[\s\-/])' + re.escape(brand.lower()) + r'(?:[\s\-/®™©]|$)'
        if re.search(pattern, text_lower):
            return brand
    return None

def extract_quantity(text):
    """Extract quantity value and unit."""
    text_lower = text.lower()
    
    # Pack pattern: 6x500ml
    pack = re.search(r'(\d+)\s*[xх]\s*(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|гр?|g|кг|kg)', text_lower)
    if pack:
        count = int(pack.group(1))
        value = float(pack.group(2).replace(',', '.'))
        unit = pack.group(3).replace('мл','ml').replace('л','l').replace('гр','g').replace('г','g').replace('кг','kg')
        return value * count, unit, f"{count}x"
    
    # Single quantity patterns
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', 'ml'),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l)(?:\s|$)', 'l'),
        (r'(\d+(?:[.,]\d+)?)\s*(гр?|g)(?:\s|$)', 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 'kg'),
        (r'(\d+)\s*(бр)', 'pcs'),
    ]
    
    for pattern, unit in patterns:
        m = re.search(pattern, text_lower)
        if m:
            return float(m.group(1).replace(',', '.')), unit, None
    
    return None, None, None

def extract_pack_info(text):
    """Extract pack info patterns."""
    text_lower = text.lower()
    found = []
    for pattern in PACK_PATTERNS:
        if pattern.lower() in text_lower:
            found.append(pattern)
    return ', '.join(found) if found else None

def clean_name(text):
    """Remove pack info from product name."""
    for pattern in PACK_PATTERNS:
        text = re.sub(re.escape(pattern), '', text, flags=re.I)
    return ' '.join(text.split()).strip()

def assign_category(text):
    """Assign category based on keywords."""
    text_lower = text.lower()
    
    # Score each category
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[cat] = score
    
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return 'Други'

def clean_products(input_file, output_file):
    """Main cleaning function."""
    with open(input_file) as f:
        raw_products = json.load(f)
    
    cleaned = []
    for raw in raw_products:
        raw_name = (raw.get('raw_name', '') + ' ' + raw.get('raw_subtitle', '')).strip()
        raw_name = ' '.join(raw_name.split())
        raw_name = re.sub(r'[®™©]', '', raw_name)
        
        if not raw_name:
            continue
        
        price_eur = raw.get('price_eur')
        price_bgn = raw.get('price_bgn')
        if not price_eur and price_bgn:
            price_eur = round(price_bgn / 1.9558, 2)
        if not price_bgn and price_eur:
            price_bgn = round(price_eur * 1.9558, 2)
        
        if not price_eur or price_eur <= 0:
            continue
        
        # Extract all fields
        brand = extract_brand(raw_name)
        qty_val, qty_unit, pack_from_qty = extract_quantity(raw_name)
        pack_info = extract_pack_info(raw_name)
        name = clean_name(raw_name)
        category = assign_category(raw_name)
        
        # Combine pack info
        pack_parts = []
        if pack_from_qty:
            pack_parts.append(pack_from_qty)
        if pack_info:
            pack_parts.append(pack_info)
        pack_size = ', '.join(pack_parts) if pack_parts else None
        
        cleaned.append({
            'store': raw['store'],
            'sku': raw.get('sku'),
            'name': name,
            'brand': brand,
            'category': category,
            'quantity_value': qty_val,
            'quantity_unit': qty_unit,
            'pack_size': pack_size,
            'price_eur': price_eur,
            'price_bgn': price_bgn,
        })
    
    # Save JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    # Save CSV
    csv_file = output_file.replace('.json', '.csv')
    fields = ['store','sku','name','brand','category','quantity_value','quantity_unit','pack_size','price_eur','price_bgn']
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(cleaned)
    
    # Stats
    with_brand = sum(1 for p in cleaned if p['brand'])
    with_qty = sum(1 for p in cleaned if p['quantity_value'])
    print(f"Cleaned {len(cleaned)} products")
    print(f"  With brand: {with_brand} ({with_brand/len(cleaned)*100:.1f}%)")
    print(f"  With quantity: {with_qty} ({with_qty/len(cleaned)*100:.1f}%)")
    
    return cleaned

if __name__ == '__main__':
    clean_products('output/raw_products.json', 'output/products_clean.json')
