#!/usr/bin/env python3
"""
Fast rule-based product cleaner using LLM-cleaned data as lookup.
"""

import json
import csv
from pathlib import Path

def main():
    # Load LLM-cleaned data as lookup table
    print("Loading LLM-cleaned data...")
    with open('output/products_llm_cleaned.json') as f:
        llm_data = json.load(f)
    
    # Build lookup by SKU
    lookup = {}
    for p in llm_data:
        if p.get('sku'):
            lookup[p['sku']] = {
                'brand': p.get('brand'),
                'category': p.get('category', 'Други'),
                'clean_name': p.get('name'),
                'quantity': p.get('quantity'),
                'quantity_unit': p.get('quantity_unit'),
                'pack_size': p.get('pack_size'),
            }
    
    print(f"Loaded {len(lookup)} products in lookup")
    
    # Load raw products
    with open('output/raw_products.json') as f:
        raw = json.load(f)
    
    print(f"Processing {len(raw)} raw products...")
    
    # Enrich raw with LLM data
    output = []
    matched = 0
    for p in raw:
        sku = p.get('sku')
        enrichment = lookup.get(sku, {})
        
        if enrichment:
            matched += 1
        
        # Calculate discount
        price = p.get('price_bgn') or p.get('price_eur')
        old_price = p.get('old_price_bgn')
        discount_pct = None
        if price and old_price and old_price > price:
            discount_pct = round((1 - price / old_price) * 100, 1)
        
        output.append({
            'sku': sku,
            'store': p.get('store', ''),
            'raw_name': p.get('raw_name', ''),
            'raw_subtitle': p.get('raw_subtitle', ''),
            'brand': enrichment.get('brand') or '',
            'category': enrichment.get('category', 'Други'),
            'clean_name': enrichment.get('clean_name') or p.get('raw_name', ''),
            'quantity': enrichment.get('quantity') or '',
            'quantity_unit': enrichment.get('quantity_unit') or '',
            'pack_size': enrichment.get('pack_size') or '',
            'price_bgn': price or '',
            'old_price_bgn': old_price or '',
            'discount_pct': discount_pct or '',
            'image_url': p.get('image_url', ''),
            'url': p.get('product_url', ''),
        })
    
    # Save CSV
    Path('output').mkdir(exist_ok=True)
    fieldnames = ['sku', 'store', 'raw_name', 'raw_subtitle', 'brand', 'category', 
                  'clean_name', 'quantity', 'quantity_unit', 'pack_size',
                  'price_bgn', 'old_price_bgn', 'discount_pct',
                  'image_url', 'url']
    
    with open('output/products_clean.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output)
    
    # Also save JSON
    with open('output/products_clean.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n=== RESULTS ===")
    print(f"Total products: {len(output)}")
    print(f"Matched with LLM data: {matched} ({matched*100/len(output):.1f}%)")
    
    # Stats
    with_brand = sum(1 for p in output if p['brand'])
    with_category = sum(1 for p in output if p['category'] != 'Други')
    with_price = sum(1 for p in output if p['price_bgn'])
    with_discount = sum(1 for p in output if p['discount_pct'])
    
    print(f"With brand: {with_brand} ({with_brand*100/len(output):.1f}%)")
    print(f"With category (not Други): {with_category} ({with_category*100/len(output):.1f}%)")
    print(f"With price: {with_price} ({with_price*100/len(output):.1f}%)")
    print(f"With discount: {with_discount} ({with_discount*100/len(output):.1f}%)")
    print(f"\nSaved: output/products_clean.csv")
    print(f"Saved: output/products_clean.json")

if __name__ == '__main__':
    main()
