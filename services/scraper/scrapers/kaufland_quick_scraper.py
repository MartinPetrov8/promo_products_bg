#!/usr/bin/env python3
"""
Kaufland Quick Scraper - Uses klNr regex extraction

Simple and robust - extracts product data from Kaufland offers page.
"""

import re
import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class KauflandProduct:
    name: str
    kl_nr: str
    subtitle: Optional[str]
    price: Optional[float]
    size_value: Optional[float] = None
    size_unit: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None


def extract_size(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract size from text like '400 г', '1.5 л', 'Ø9 см'"""
    if not text:
        return None, None
    
    text_lower = text.lower()
    
    patterns = [
        (r'(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
        (r'(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
        (r'(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
        (r'(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
        (r'[Øø](\d+[.,]?\d*)\s*(см|cm)\b', 'cm'),
        (r'(\d+[.,]?\d*)\s*(бр|br)\b', 'pc'),
    ]
    
    for pattern, unit in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                if unit == 'kg':
                    return value * 1000, 'g'
                elif unit == 'l':
                    return value * 1000, 'ml'
                return value, unit
            except ValueError:
                continue
    
    return None, None


def extract_brand(text: str) -> Optional[str]:
    """Extract brand from product name"""
    if not text:
        return None
    
    text_lower = text.lower()
    brands = [
        ('k-classic', 'K-Classic'), ('k classic', 'K-Classic'), ('clever', 'Clever'),
        ('milka', 'Milka'), ('nescafe', 'Nescafe'), ('jacobs', 'Jacobs'),
        ('lavazza', 'Lavazza'), ('coca-cola', 'Coca-Cola'), ('coca cola', 'Coca-Cola'),
        ('pepsi', 'Pepsi'), ('nestle', 'Nestle'), ('ferrero', 'Ferrero'),
        ('kinder', 'Kinder'), ('lindt', 'Lindt'), ('haribo', 'Haribo'),
        ('nutella', 'Nutella'), ('pringles', 'Pringles'), ('lays', "Lay's"),
        ('doritos', 'Doritos'), ('red bull', 'Red Bull'), ('heineken', 'Heineken'),
        ('pampers', 'Pampers'), ('ariel', 'Ariel'), ('lenor', 'Lenor'),
        ('persil', 'Persil'), ('finish', 'Finish'), ('emeka', 'Emeka'),
    ]
    
    for pattern, brand_name in brands:
        if pattern in text_lower:
            return brand_name
    
    return None


def scrape_kaufland_offers() -> List[KauflandProduct]:
    """Scrape Kaufland offers page"""
    url = "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "bg-BG,bg;q=0.9",
    }
    
    logger.info(f"Fetching {url}")
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    
    html = resp.text
    logger.info(f"Page size: {len(html)} bytes")
    
    # Extract product data - look for klNr, then find title/subtitle in surrounding context
    kl_matches = list(re.finditer(r'"klNr":"([0-9]+)"', html))
    logger.info(f"Found {len(kl_matches)} klNr entries")
    
    # Process each klNr entry and find associated data
    products = []
    seen = set()
    
    for m in kl_matches:
        kl = m.group(1)
        if kl in seen:
            continue
        seen.add(kl)
        
        # Look in surrounding 2000 chars for title/subtitle/price
        context = html[m.start():m.start()+2000]
        
        title_match = re.search(r'"title":"([^"]+)"', context)
        subtitle_match = re.search(r'"subtitle":"([^"]*)"', context)
        price_match = re.search(r'"price":([\d.]+)', context)
        
        if title_match:
            title = title_match.group(1)
            subtitle = subtitle_match.group(1) if subtitle_match else None
            price = float(price_match.group(1)) if price_match else None
            
            # Extract size
            size_val, size_unit = extract_size(subtitle)
            if not size_val:
                size_val, size_unit = extract_size(title)
            
            # Extract brand
            brand = extract_brand(title)
            
            products.append(KauflandProduct(
                name=title,
                kl_nr=kl,
                subtitle=subtitle,
                price=price,
                size_value=size_val,
                size_unit=size_unit,
                brand=brand,
            ))
    
    logger.info(f"Extracted {len(products)} unique products")
    return products


def main():
    products = scrape_kaufland_offers()
    
    print(f"\n{'='*60}")
    print(f"KAUFLAND SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Total products: {len(products)}")
    
    with_size = sum(1 for p in products if p.size_value)
    with_brand = sum(1 for p in products if p.brand)
    with_price = sum(1 for p in products if p.price)
    
    print(f"With size: {with_size} ({100*with_size/max(1,len(products)):.1f}%)")
    print(f"With brand: {with_brand} ({100*with_brand/max(1,len(products)):.1f}%)")
    print(f"With price: {with_price} ({100*with_price/max(1,len(products)):.1f}%)")
    
    print(f"\n{'='*60}")
    print("SAMPLE PRODUCTS")
    print(f"{'='*60}")
    
    for p in products[:10]:
        print(f"\n{p.name}")
        print(f"  klNr: {p.kl_nr}")
        print(f"  Subtitle: {p.subtitle}")
        print(f"  Brand: {p.brand}")
        print(f"  Size: {p.size_value} {p.size_unit}")
        print(f"  Price: {p.price} BGN")
    
    # Save
    output = Path(__file__).parent.parent / "data" / "kaufland_quick.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved to {output}")


if __name__ == '__main__':
    main()
