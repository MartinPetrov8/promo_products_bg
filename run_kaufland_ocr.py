#!/usr/bin/env python3
"""
Run OCR on Kaufland product images to extract brands.
Uses Google Cloud Vision API (~$0.002/image).

Usage:
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
    python run_kaufland_ocr.py
"""

import os
import json
import sqlite3
import requests
from time import sleep
from typing import Optional
import re

KNOWN_BRANDS = {
    'MILBONA', 'PILOS', 'PARKSIDE', 'CRIVIT', 'SILVERCREST', 
    'KANIA', 'FRESHONA', 'DULANO', 'CIEN', 'W5', 'TRONIC',
    'K-CLASSIC', 'K-BIO', 'EXQUISIT', 'BEVOLA',
    'NESTLE', 'DANONE', 'COCA-COLA', 'PEPSI', 'ORBIT',
    'HEINZ', 'KNORR', 'MAGGI', 'BARILLA', 'PRINGLES',
    'JACOBS', 'NESCAFE', 'LAVAZZA', 'TCHIBO',
    'NIVEA', 'DOVE', 'GILLETTE', 'COLGATE', 'ORAL-B',
    'FAIRY', 'ARIEL', 'PERSIL', 'TIDE', 'LENOR',
    'РОДНА СТРЯХА', 'МЕСКО', 'ТАНДЕМ', 'ПИЛКО', 'GRADUS',
    'CHIPITA', 'SAVEX', 'JOHNNIE WALKER', 'JAMESON',
}


def get_access_token(creds: dict) -> str:
    """Get OAuth2 access token from service account credentials."""
    import jwt
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    payload = {
        'iss': creds['client_email'],
        'scope': 'https://www.googleapis.com/auth/cloud-vision',
        'aud': 'https://oauth2.googleapis.com/token',
        'iat': now,
        'exp': now + timedelta(hours=1)
    }
    
    signed_jwt = jwt.encode(payload, creds['private_key'], algorithm='RS256')
    
    resp = requests.post('https://oauth2.googleapis.com/token', data={
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': signed_jwt
    })
    resp.raise_for_status()
    return resp.json()['access_token']


def ocr_image_url(image_url: str, access_token: str) -> Optional[str]:
    """Run OCR on image URL using Google Cloud Vision API."""
    endpoint = 'https://vision.googleapis.com/v1/images:annotate'
    
    payload = {
        'requests': [{
            'image': {'source': {'imageUri': image_url}},
            'features': [{'type': 'TEXT_DETECTION', 'maxResults': 1}]
        }]
    }
    
    resp = requests.post(
        endpoint,
        json=payload,
        headers={'Authorization': f'Bearer {access_token}'}
    )
    
    if resp.status_code != 200:
        print(f"  Error {resp.status_code}: {resp.text[:200]}")
        return None
    
    result = resp.json()
    annotations = result.get('responses', [{}])[0].get('textAnnotations', [])
    
    if annotations:
        return annotations[0].get('description', '')
    return None


def extract_brand_from_ocr(ocr_text: str) -> Optional[str]:
    """Extract brand name from OCR text."""
    if not ocr_text:
        return None
    
    # First check for known brands
    ocr_upper = ocr_text.upper()
    for brand in KNOWN_BRANDS:
        if brand in ocr_upper:
            return brand.title() if brand.isupper() else brand
    
    # Try first capitalized word
    match = re.search(r'^([A-ZА-Я][A-Za-zА-Яа-я&\'-]{2,20})', ocr_text)
    if match:
        return match.group(1)
    
    return None


def main():
    # Load products needing OCR
    with open('/tmp/needs_ocr.json') as f:
        products = json.load(f)
    
    kaufland_products = [p for p in products if p['store'] == 'Kaufland']
    print(f"Kaufland products to OCR: {len(kaufland_products)}")
    print(f"Estimated cost: ${len(kaufland_products) * 0.002:.2f}")
    
    # Get credentials
    creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path or not os.path.exists(creds_path):
        print("\nNo credentials found. Set GOOGLE_APPLICATION_CREDENTIALS")
        return
    
    with open(creds_path) as f:
        creds = json.load(f)
    
    access_token = get_access_token(creds)
    print("Access token obtained")
    
    conn = sqlite3.connect('data/promobg.db')
    cur = conn.cursor()
    
    results = []
    brands_found = 0
    
    for i, product in enumerate(kaufland_products):
        print(f"[{i+1}/{len(kaufland_products)}] {product['name'][:40]}...")
        
        ocr_text = ocr_image_url(product['image_url'], access_token)
        brand = extract_brand_from_ocr(ocr_text) if ocr_text else None
        
        if brand:
            brands_found += 1
            print(f"  → Brand: {brand}")
        
        cur.execute('''
            INSERT OR REPLACE INTO brand_image_cache 
            (image_url, brand, ocr_text, confidence, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', (product['image_url'], brand, ocr_text, 0.8 if brand else 0.0))
        
        results.append({
            'name': product['name'],
            'image_url': product['image_url'],
            'ocr_text': ocr_text,
            'brand': brand
        })
        
        if (i + 1) % 10 == 0:
            conn.commit()
            sleep(0.5)
    
    conn.commit()
    conn.close()
    
    with open('/tmp/kaufland_ocr_results.json', 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nDone! {brands_found}/{len(kaufland_products)} brands extracted")


if __name__ == '__main__':
    main()
