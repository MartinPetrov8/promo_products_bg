#!/usr/bin/env python3
"""
Lidl OCR Brand Extraction - ONE-TIME PROCESS

Uses Google Cloud Vision API with service account authentication.
Results cached in data/brand_cache.json for daily scrapes.

Usage:
    python scripts/lidl_ocr_brands.py           # Process all missing brands
    python scripts/lidl_ocr_brands.py --limit 10  # Test with 10 products
"""

import json
import re
import sys
import time
import base64
import logging
import argparse
import requests
from pathlib import Path
from datetime import datetime, timezone

# For JWT signing
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SECRETS_DIR = PROJECT_ROOT / '.secrets'
SA_FILE = SECRETS_DIR / 'google_vision_sa.json'
CACHE_FILE = PROJECT_ROOT / 'data' / 'brand_cache.json'
PRODUCTS_FILE = PROJECT_ROOT / 'output' / 'raw_products.json'

KNOWN_BRANDS = None
_access_token = None
_token_expiry = 0

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def create_jwt(sa_info: dict) -> str:
    """Create a signed JWT for Google OAuth."""
    now = int(time.time())
    
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa_info["client_email"],
        "scope": "https://www.googleapis.com/auth/cloud-vision",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600
    }
    
    header_b64 = base64url_encode(json.dumps(header).encode())
    payload_b64 = base64url_encode(json.dumps(payload).encode())
    unsigned = f"{header_b64}.{payload_b64}"
    
    # Sign with private key
    private_key = serialization.load_pem_private_key(
        sa_info["private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    
    signature = private_key.sign(
        unsigned.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    
    signature_b64 = base64url_encode(signature)
    return f"{unsigned}.{signature_b64}"

def get_access_token() -> str:
    """Get OAuth access token using service account."""
    global _access_token, _token_expiry
    
    if _access_token and time.time() < _token_expiry - 60:
        return _access_token
    
    with open(SA_FILE) as f:
        sa_info = json.load(f)
    
    jwt_token = create_jwt(sa_info)
    
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token
        },
        timeout=30
    )
    response.raise_for_status()
    
    token_data = response.json()
    _access_token = token_data["access_token"]
    _token_expiry = time.time() + token_data.get("expires_in", 3600)
    
    return _access_token

def load_known_brands():
    global KNOWN_BRANDS
    brands_file = PROJECT_ROOT / 'config' / 'brands.json'
    if brands_file.exists():
        with open(brands_file) as f:
            KNOWN_BRANDS = set(json.load(f).get('brands', []))
    else:
        KNOWN_BRANDS = set()
    return KNOWN_BRANDS

def load_brand_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}

def save_brand_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def ocr_image(image_url: str) -> str:
    """Call Google Vision API to OCR an image."""
    access_token = get_access_token()
    
    endpoint = "https://vision.googleapis.com/v1/images:annotate"
    
    payload = {
        "requests": [{
            "image": {"source": {"imageUri": image_url}},
            "features": [{"type": "TEXT_DETECTION", "maxResults": 1}]
        }]
    }
    
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        annotations = result.get('responses', [{}])[0].get('textAnnotations', [])
        if annotations:
            return annotations[0].get('description', '')
        return ''
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ''

def extract_brand_from_ocr(ocr_text: str, product_name: str) -> str:
    """Extract brand from OCR text."""
    if not ocr_text:
        return None
    
    ocr_upper = ocr_text.upper()
    name_upper = product_name.upper()
    
    # Match known brands
    for brand in KNOWN_BRANDS:
        brand_clean = brand.upper().rstrip('®™© ')
        if brand_clean in ocr_upper and brand_clean not in name_upper:
            return brand.rstrip('®™© ')
    
    # Try first lines for brand-like text
    lines = ocr_text.strip().split('\n')
    for line in lines[:3]:
        match = re.match(r'^([A-ZА-Я][A-Za-zА-Яа-я®™]+)(?:\s|$)', line.strip())
        if match:
            potential = match.group(1).rstrip('®™')
            if len(potential) >= 3 and potential.upper() not in name_upper:
                return potential
    
    return None

def get_products_needing_ocr(cache: dict) -> list:
    """Get Lidl products without brand and not in cache."""
    if not PRODUCTS_FILE.exists():
        logger.error(f"Products file not found: {PRODUCTS_FILE}")
        return []
    
    with open(PRODUCTS_FILE) as f:
        products = json.load(f)
    
    needs_ocr = []
    for p in products:
        if p.get('store') != 'Lidl':
            continue
        if p.get('brand'):
            continue
        sku = p.get('sku')
        if sku in cache:
            continue
        if not p.get('image_url'):
            continue
        needs_ocr.append(p)
    
    return needs_ocr

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit products to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    args = parser.parse_args()
    
    load_known_brands()
    cache = load_brand_cache()
    
    logger.info(f"Known brands: {len(KNOWN_BRANDS)}")
    logger.info(f"Cached brands: {len(cache)}")
    
    products = get_products_needing_ocr(cache)
    logger.info(f"Products needing OCR: {len(products)}")
    
    if args.limit:
        products = products[:args.limit]
        logger.info(f"Limited to: {len(products)}")
    
    if args.dry_run:
        for p in products[:10]:
            logger.info(f"  Would OCR: {p.get('sku')} - {p.get('raw_name', '')[:40]}")
        return
    
    success = 0
    failed = 0
    
    for i, p in enumerate(products):
        sku = p.get('sku')
        name = p.get('raw_name', '')
        image_url = p.get('image_url')
        
        logger.info(f"[{i+1}/{len(products)}] {sku}: {name[:30]}...")
        
        ocr_text = ocr_image(image_url)
        
        if ocr_text:
            brand = extract_brand_from_ocr(ocr_text, name)
            cache[sku] = {
                'brand': brand,
                'ocr_text': ocr_text[:200],
                'source': 'ocr'
            }
            if brand:
                logger.info(f"  → Brand: {brand}")
                success += 1
            else:
                logger.info(f"  → No brand found")
                failed += 1
        else:
            cache[sku] = {'brand': None, 'ocr_text': None, 'source': 'ocr_failed'}
            logger.info(f"  → OCR failed")
            failed += 1
        
        if (i + 1) % 10 == 0:
            save_brand_cache(cache)
        
        time.sleep(0.5)
    
    save_brand_cache(cache)
    
    logger.info(f"\n=== RESULTS ===")
    logger.info(f"Processed: {len(products)}")
    logger.info(f"Brands found: {success}")
    logger.info(f"No brand: {failed}")
    logger.info(f"Cache size: {len(cache)}")

if __name__ == '__main__':
    main()
