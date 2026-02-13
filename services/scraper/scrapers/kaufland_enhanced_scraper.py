#!/usr/bin/env python3
"""
Kaufland Enhanced Scraper - Extracts detailed product data

Key improvements:
1. Extracts detailDescription field for more size/spec info
2. Extracts detailTitle for cleaner product names
3. Parses descriptions for sizes, brands, and attributes
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
    kl_nr: str
    title: str
    detail_title: Optional[str]
    subtitle: Optional[str]
    description: Optional[str]
    price: Optional[float]
    old_price: Optional[float]
    discount_pct: Optional[int]
    size_value: Optional[float] = None
    size_unit: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None


def extract_size(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract size from text like '400 г', '1.5 л', '2x500 мл', '10 бр.'"""
    if not text:
        return None, None
    
    text_lower = text.lower()
    
    # Pack format: 2x500 ml, 6 x 1.5 л
    pack_patterns = [
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
        (r'(\d+)\s*[xх×]\s*(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
    ]
    
    for pattern, unit in pack_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                count = int(match.group(1))
                value = float(match.group(2).replace(',', '.'))
                total = count * value
                if unit in ['kg', 'l']:
                    return total * 1000, 'g' if unit == 'kg' else 'ml'
                return total, 'g' if unit == 'g' else 'ml'
            except ValueError:
                continue
    
    # Single size patterns - weight/volume
    patterns = [
        (r'(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
        (r'(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
        (r'(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
        (r'(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
        (r'[Øø](\d+[.,]?\d*)\s*(см|cm)\b', 'cm'),  # Diameter
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
    
    # Piece count patterns - "10 бр.", "32+8 бр.", "42 -- 70 бр."
    # Take the first number for range patterns
    piece_match = re.search(r'(\d+)\s*(?:\+\s*\d+)?\s*(?:--\s*\d+)?\s*бр\.?', text_lower)
    if piece_match:
        try:
            value = float(piece_match.group(1))
            return value, 'бр'
        except ValueError:
            pass
    
    return None, None


def extract_brand(text: str) -> Optional[str]:
    """Extract brand from product name or description"""
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Sorted by specificity - longer/more specific first
    brands = [
        ('coca-cola', 'Coca-Cola'), ('coca cola', 'Coca-Cola'),
        ('k-classic', 'K-Classic'), ('k classic', 'K-Classic'),
        ('red bull', 'Red Bull'),
        ('lay\'s', "Lay's"), ('lays', "Lay's"),
        ('milka', 'Milka'), ('nescafe', 'Nescafe'), ('jacobs', 'Jacobs'),
        ('lavazza', 'Lavazza'), ('tchibo', 'Tchibo'),
        ('pepsi', 'Pepsi'), ('fanta', 'Fanta'), ('sprite', 'Sprite'),
        ('nestle', 'Nestle'), ('nestlé', 'Nestle'),
        ('ferrero', 'Ferrero'), ('kinder', 'Kinder'),
        ('lindt', 'Lindt'), ('haribo', 'Haribo'), ('nutella', 'Nutella'),
        ('pringles', 'Pringles'), ('doritos', 'Doritos'),
        ('heineken', 'Heineken'), ('stella artois', 'Stella Artois'),
        ('pampers', 'Pampers'), ('huggies', 'Huggies'),
        ('ariel', 'Ariel'), ('lenor', 'Lenor'), ('persil', 'Persil'),
        ('finish', 'Finish'), ('fairy', 'Fairy'),
        ('emeka', 'Emeka'), ('zewa', 'Zewa'),
        ('верея', 'Верея'), ('olympus', 'Olympus'), ('олимпус', 'Olympus'),
        ('danone', 'Danone'), ('данон', 'Danone'),
        ('president', 'President'), ('президент', 'President'),
        ('hochland', 'Hochland'), ('хохланд', 'Hochland'),
        ('dr. oetker', 'Dr. Oetker'), ('knorr', 'Knorr'),
        ('maggi', 'Maggi'), ('hellmann\'s', "Hellmann's"),
        ('bonduelle', 'Bonduelle'), ('бондюел', 'Bonduelle'),
        ('barilla', 'Barilla'), ('де чеко', 'De Cecco'),
        ('aquaphor', 'Aquaphor'), ('аквафор', 'Aquaphor'),
        ('oral-b', 'Oral-B'), ('colgate', 'Colgate'),
        ('nivea', 'Nivea'), ('dove', 'Dove'), ('rexona', 'Rexona'),
        ('калиакра', 'Калиакра'), ('девин', 'Devin'),
        ('банкя', 'Bankya'), ('горна баня', 'Горна Баня'),
    ]
    
    for pattern, brand_name in brands:
        if pattern in text_lower:
            return brand_name
    
    return None


def scrape_kaufland_enhanced() -> List[KauflandProduct]:
    """Scrape Kaufland offers page with enhanced data extraction"""
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
    
    # Extract all klNr entries
    kl_matches = list(re.finditer(r'"klNr":"([0-9]+)"', html))
    logger.info(f"Found {len(kl_matches)} klNr entries")
    
    products = []
    seen = set()
    
    for m in kl_matches:
        kl = m.group(1)
        if kl in seen:
            continue
        seen.add(kl)
        
        # Look backwards and forwards for associated data
        # Go back up to 1000 chars to find title, forward 2000 for description
        start = max(0, m.start() - 1000)
        end = min(len(html), m.start() + 2500)
        context = html[start:end]
        
        # Extract all available fields
        title_m = re.search(r'"title":"([^"]+)"', context)
        subtitle_m = re.search(r'"subtitle":"([^"]*)"', context)
        detail_title_m = re.search(r'"detailTitle":"([^"]*)"', context)
        desc_m = re.search(r'"detailDescription":"([^"]*)"', context)
        price_m = re.search(r'"price":([\d.]+)', context)
        old_price_m = re.search(r'"oldPrice":([\d.]+)', context)
        image_m = re.search(r'"listImage":"([^"]+)"', context)
        
        if not title_m:
            continue
        
        title = title_m.group(1)
        subtitle = subtitle_m.group(1) if subtitle_m else None
        detail_title = detail_title_m.group(1) if detail_title_m else None
        description = desc_m.group(1).replace('\\n', ' | ') if desc_m else None
        price = float(price_m.group(1)) if price_m else None
        old_price = float(old_price_m.group(1)) if old_price_m else None
        image_url = image_m.group(1) if image_m else None
        
        # Calculate discount
        discount_pct = None
        if price and old_price and old_price > price:
            discount_pct = int(100 * (old_price - price) / old_price)
        
        # Extract size - try multiple sources
        size_val, size_unit = None, None
        
        # 1. Try subtitle (often has size like "400 г")
        if subtitle:
            size_val, size_unit = extract_size(subtitle)
        
        # 2. Try description
        if not size_val and description:
            size_val, size_unit = extract_size(description)
        
        # 3. Try title
        if not size_val:
            size_val, size_unit = extract_size(title)
        
        # Extract brand - try multiple sources
        brand = extract_brand(title)
        if not brand and description:
            brand = extract_brand(description)
        if not brand and detail_title:
            brand = extract_brand(detail_title)
        
        products.append(KauflandProduct(
            kl_nr=kl,
            title=title,
            detail_title=detail_title,
            subtitle=subtitle,
            description=description,
            price=price,
            old_price=old_price,
            discount_pct=discount_pct,
            size_value=size_val,
            size_unit=size_unit,
            brand=brand,
            image_url=image_url,
        ))
    
    logger.info(f"Extracted {len(products)} unique products")
    return products


def main():
    products = scrape_kaufland_enhanced()
    
    print(f"\n{'='*60}")
    print("KAUFLAND ENHANCED SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Total products: {len(products)}")
    
    with_size = sum(1 for p in products if p.size_value)
    with_brand = sum(1 for p in products if p.brand)
    with_price = sum(1 for p in products if p.price)
    with_desc = sum(1 for p in products if p.description)
    
    print(f"With size: {with_size} ({100*with_size/max(1,len(products)):.1f}%)")
    print(f"With brand: {with_brand} ({100*with_brand/max(1,len(products)):.1f}%)")
    print(f"With price: {with_price} ({100*with_price/max(1,len(products)):.1f}%)")
    print(f"With description: {with_desc} ({100*with_desc/max(1,len(products)):.1f}%)")
    
    print(f"\n{'='*60}")
    print("SAMPLE PRODUCTS")
    print(f"{'='*60}")
    
    # Show products WITH descriptions
    sample = [p for p in products if p.description][:10]
    for p in sample:
        print(f"\nTitle: {p.title}")
        print(f"  Detail: {p.detail_title}")
        print(f"  Subtitle: {p.subtitle}")
        print(f"  Description: {p.description[:80] if p.description else None}...")
        print(f"  Brand: {p.brand} | Size: {p.size_value} {p.size_unit} | Price: {p.price}")
    
    # Save
    output = Path(__file__).parent.parent / "data" / "kaufland_enhanced.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Saved to {output}")


if __name__ == '__main__':
    main()
