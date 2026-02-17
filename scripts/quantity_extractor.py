#!/usr/bin/env python3
"""
Quantity Extractor - Extract product quantities from OCR text and product names

Patterns supported:
- Weight: 100g, 500 г, 1.5 kg, 1,5 кг
- Volume: 500ml, 1l, 750 мл, 1 л
- Count: 10 бр, 12 pcs, 4x100g (multipacks)

Returns normalized quantity in base units:
- Weight → grams (g)
- Volume → milliliters (ml)
- Count → pieces (pcs)
"""

import re
from typing import Optional, Tuple, Dict

# Unit normalization mappings
WEIGHT_UNITS = {
    'g': 1, 'г': 1, 'гр': 1, 'gram': 1, 'grams': 1,
    'kg': 1000, 'кг': 1000, 'kilogram': 1000,
    'mg': 0.001, 'мг': 0.001,
}

VOLUME_UNITS = {
    'ml': 1, 'мл': 1, 'milliliter': 1,
    'l': 1000, 'л': 1000, 'liter': 1000, 'litre': 1000,
    'cl': 10, 'сл': 10,
    'dl': 100, 'дл': 100,
}

COUNT_UNITS = {
    'бр': 1, 'pcs': 1, 'шт': 1, 'pc': 1, 'x': 1, 'х': 1,
}

# Combined pattern for quantity extraction
QUANTITY_PATTERN = re.compile(
    r'(?:^|[\s\(\[])' +  # Start or whitespace
    r'(\d+(?:[.,]\d+)?)' +  # Number (with optional decimal)
    r'\s*' +  # Optional whitespace
    r'(г|g|гр|кг|kg|мл|ml|л|l|cl|бр|pcs|шт|x|х)' +  # Unit
    r'(?:\s|$|[\)\]\.,])',  # End or whitespace
    re.IGNORECASE
)

# Multipack pattern: 4x100g, 12 x 330ml
MULTIPACK_PATTERN = re.compile(
    r'(\d+)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*(г|g|гр|кг|kg|мл|ml|л|l)',
    re.IGNORECASE
)


def normalize_number(num_str: str) -> float:
    """Convert string number to float, handling comma decimals."""
    return float(num_str.replace(',', '.'))


def extract_quantity(text: str) -> Optional[Dict]:
    """
    Extract quantity from text (OCR or product name).
    
    Returns dict with:
        - value: normalized numeric value
        - unit: normalized unit (g, ml, pcs)
        - original: original string found
        - type: 'weight', 'volume', or 'count'
    """
    if not text:
        return None
    
    # Try multipack first (e.g., "4x100g" = 400g)
    multipack = MULTIPACK_PATTERN.search(text)
    if multipack:
        count = int(multipack.group(1))
        amount = normalize_number(multipack.group(2))
        unit = multipack.group(3).lower()
        
        # Normalize unit
        if unit in WEIGHT_UNITS or unit in ['г', 'g', 'гр', 'кг', 'kg']:
            multiplier = WEIGHT_UNITS.get(unit, 1)
            total = count * amount * multiplier
            return {
                'value': total,
                'unit': 'g',
                'original': multipack.group(0),
                'type': 'weight',
                'multipack': {'count': count, 'per_unit': amount * multiplier}
            }
        elif unit in VOLUME_UNITS or unit in ['мл', 'ml', 'л', 'l']:
            multiplier = VOLUME_UNITS.get(unit, 1)
            total = count * amount * multiplier
            return {
                'value': total,
                'unit': 'ml',
                'original': multipack.group(0),
                'type': 'volume',
                'multipack': {'count': count, 'per_unit': amount * multiplier}
            }
    
    # Find all quantity matches
    matches = QUANTITY_PATTERN.findall(text)
    
    if not matches:
        return None
    
    # Prefer the largest/most significant quantity
    best = None
    best_value = 0
    
    for num_str, unit in matches:
        amount = normalize_number(num_str)
        unit_lower = unit.lower()
        
        # Determine unit type and normalize
        if unit_lower in WEIGHT_UNITS or unit_lower in ['г', 'g', 'гр', 'кг', 'kg', 'mg', 'мг']:
            multiplier = WEIGHT_UNITS.get(unit_lower, 1)
            normalized_value = amount * multiplier
            unit_type = 'weight'
            norm_unit = 'g'
        elif unit_lower in VOLUME_UNITS or unit_lower in ['мл', 'ml', 'л', 'l', 'cl', 'сл']:
            multiplier = VOLUME_UNITS.get(unit_lower, 1)
            normalized_value = amount * multiplier
            unit_type = 'volume'
            norm_unit = 'ml'
        elif unit_lower in COUNT_UNITS or unit_lower in ['бр', 'pcs', 'шт', 'x', 'х']:
            normalized_value = amount
            unit_type = 'count'
            norm_unit = 'pcs'
        else:
            continue
        
        # Keep the largest value (usually the total, not per-100g)
        if normalized_value > best_value:
            best_value = normalized_value
            best = {
                'value': normalized_value,
                'unit': norm_unit,
                'original': f"{num_str} {unit}",
                'type': unit_type
            }
    
    return best


def extract_quantity_from_name(name: str) -> Optional[Dict]:
    """Extract quantity from product name."""
    return extract_quantity(name)


def extract_quantity_from_ocr(ocr_text: str) -> Optional[Dict]:
    """Extract quantity from OCR text."""
    return extract_quantity(ocr_text)


# Test
if __name__ == '__main__':
    test_cases = [
        "Alesto Фъстъци 100 g",
        "Мляко прясно 1 л",
        "Кашкавал 400г",
        "4x100g multipack",
        "12 x 330 ml",
        "Масло 250 гр",
        "Сирене 500 г",
        "Вода минерална 1,5 л",
        "Бисквити 150g",
    ]
    
    print("Quantity extraction tests:")
    for text in test_cases:
        result = extract_quantity(text)
        print(f"  '{text}' → {result}")
