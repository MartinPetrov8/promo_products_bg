"""
Quantity Parser

Parses product quantities from text, handling Bulgarian units and formats.
Normalizes to base units (ml for liquids, g for solids) for comparison.

Handles:
- Simple quantities: "500 мл", "1.5 л", "250 g"
- Multipacks: "2 x 250 мл", "6х330ml"
- Bulgarian units: мл, л, г, кг
- Ranges and approximations

Example:
    >>> parse_quantity("2 x 500 мл")
    (1000.0, 'ml')
    >>> parse_quantity("1.5 кг")
    (1500.0, 'g')
"""

import re
from typing import Optional, Tuple


# === Unit Normalization ===

UNIT_MAPPING = {
    # Milliliters (base unit for liquids)
    'ml': 'ml',
    'мл': 'ml',
    'milliliter': 'ml',
    'millilitre': 'ml',
    
    # Liters → convert to ml
    'l': 'l',
    'л': 'l',
    'liter': 'l',
    'litre': 'l',
    'литра': 'l',
    'литър': 'l',
    
    # Grams (base unit for solids)
    'g': 'g',
    'г': 'g',
    'gram': 'g',
    'грам': 'g',
    'грама': 'g',
    
    # Kilograms → convert to g
    'kg': 'kg',
    'кг': 'kg',
    'kilogram': 'kg',
    'килограм': 'kg',
    'килограма': 'kg',
    
    # Pieces
    'pcs': 'pcs',
    'бр': 'pcs',
    'броя': 'pcs',
    'брой': 'pcs',
    'шт': 'pcs',
    'pc': 'pcs',
    'piece': 'pcs',
    'pieces': 'pcs',
}


def normalize_unit(unit: str) -> str:
    """
    Normalize unit string to standard format.
    
    Args:
        unit: Raw unit string (may be Bulgarian)
        
    Returns:
        Normalized unit: 'ml', 'l', 'g', 'kg', 'pcs'
        
    Example:
        >>> normalize_unit("мл")
        'ml'
        >>> normalize_unit("кг")
        'kg'
    """
    if not unit:
        return ''
    
    unit_lower = unit.lower().strip()
    return UNIT_MAPPING.get(unit_lower, unit_lower)


def convert_to_base_unit(value: float, unit: str) -> Tuple[float, str]:
    """
    Convert quantity to base unit (ml or g).
    
    Args:
        value: Numeric quantity
        unit: Normalized unit
        
    Returns:
        Tuple of (value_in_base_unit, base_unit)
        
    Example:
        >>> convert_to_base_unit(1.5, 'l')
        (1500.0, 'ml')
        >>> convert_to_base_unit(2, 'kg')
        (2000.0, 'g')
    """
    unit = normalize_unit(unit)
    
    if unit == 'l':
        return (value * 1000, 'ml')
    elif unit == 'kg':
        return (value * 1000, 'g')
    else:
        return (value, unit)


# === Quantity Patterns ===
# Ordered by specificity (most specific first)

QUANTITY_PATTERNS = [
    # Multipack with unit: "2 x 250 мл", "6х330ml", "3 × 1.5 л"
    (
        r'(\d+)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*(ml|мл|l|л|g|г|kg|кг)',
        'multipack_unit'
    ),
    
    # Multipack without unit after: "2 x 500" (unit may follow separately)
    (
        r'(\d+)\s*[xх×]\s*(\d+(?:[.,]\d+)?)',
        'multipack_value'
    ),
    
    # Simple with decimal: "1.5 л", "500.5 g", "0,75 л"
    (
        r'(\d+[.,]\d+)\s*(ml|мл|l|л|g|г|kg|кг|бр|pcs)',
        'decimal'
    ),
    
    # Simple integer: "500 мл", "250 g", "10 бр"
    (
        r'(\d+)\s*(ml|мл|l|л|g|г|kg|кг|бр|pcs)',
        'simple'
    ),
    
    # Weight in grams (Bulgarian style): "400 г", "150г"
    (
        r'(\d{2,5})\s*г\b',
        'grams_bg'
    ),
    
    # Volume in ml (Bulgarian style): "500 мл", "250мл"
    (
        r'(\d{2,5})\s*мл\b',
        'ml_bg'
    ),
    
    # Liters: "1л", "0.75л", "1,5 л"
    (
        r'(\d+[.,]?\d*)\s*л\b',
        'liters_bg'
    ),
    
    # Kilograms: "1кг", "0.5 кг", "2,5кг"
    (
        r'(\d+[.,]?\d*)\s*кг\b',
        'kg_bg'
    ),
    
    # Pieces (Bulgarian): "10 бр", "6бр"
    (
        r'(\d+)\s*бр\.?\b',
        'pieces_bg'
    ),
]


def parse_quantity(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse quantity from text.
    
    Returns value normalized to base units:
    - Liters → milliliters
    - Kilograms → grams
    
    Args:
        text: Text containing quantity (product name, unit field, etc.)
        
    Returns:
        Tuple of (value_in_base_units, base_unit) or (None, None)
        
    Example:
        >>> parse_quantity("Coca-Cola 2 x 500 мл")
        (1000.0, 'ml')
        >>> parse_quantity("Прясно мляко 1.5 л")
        (1500.0, 'ml')
        >>> parse_quantity("Сирене 400 г")
        (400.0, 'g')
    """
    if not text:
        return (None, None)
    
    # Clean text: strip HTML, normalize whitespace
    text = re.sub(r'<[^>]+>', ' ', text)  # Remove HTML tags
    text = re.sub(r'&[a-z]+;', ' ', text)  # Remove HTML entities
    text = text.lower()
    
    for pattern, pattern_type in QUANTITY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if pattern_type == 'multipack_unit':
                    # "2 x 250 мл" → 500 ml
                    count = int(match.group(1))
                    value = float(match.group(2).replace(',', '.'))
                    unit = normalize_unit(match.group(3))
                    total = count * value
                    return convert_to_base_unit(total, unit)
                
                elif pattern_type == 'multipack_value':
                    # "2 x 500" → 1000, but no unit
                    count = int(match.group(1))
                    value = float(match.group(2).replace(',', '.'))
                    total = count * value
                    # Try to find unit elsewhere in text
                    unit_match = re.search(r'(ml|мл|l|л|g|г|kg|кг)', text)
                    if unit_match:
                        unit = normalize_unit(unit_match.group(1))
                        return convert_to_base_unit(total, unit)
                    return (total, None)
                
                elif pattern_type in ('decimal', 'simple'):
                    value = float(match.group(1).replace(',', '.'))
                    unit = normalize_unit(match.group(2))
                    return convert_to_base_unit(value, unit)
                
                elif pattern_type == 'grams_bg':
                    value = float(match.group(1))
                    return (value, 'g')
                
                elif pattern_type == 'ml_bg':
                    value = float(match.group(1))
                    return (value, 'ml')
                
                elif pattern_type == 'liters_bg':
                    value = float(match.group(1).replace(',', '.'))
                    return (value * 1000, 'ml')
                
                elif pattern_type == 'kg_bg':
                    value = float(match.group(1).replace(',', '.'))
                    return (value * 1000, 'g')
                
                elif pattern_type == 'pieces_bg':
                    value = float(match.group(1))
                    return (value, 'pcs')
                    
            except (ValueError, IndexError):
                continue
    
    return (None, None)


def quantities_compatible(
    q1: Optional[float], u1: Optional[str],
    q2: Optional[float], u2: Optional[str],
    tolerance: float = 0.25
) -> bool:
    """
    Check if two quantities are compatible for matching.
    
    Compatible means:
    - Same unit type (volume or weight)
    - Within tolerance of each other (default 25%)
    
    Args:
        q1, u1: First quantity value and unit
        q2, u2: Second quantity value and unit
        tolerance: Maximum ratio difference (0.25 = 25%)
        
    Returns:
        True if quantities are compatible
        
    Example:
        >>> quantities_compatible(500, 'ml', 500, 'ml')
        True
        >>> quantities_compatible(500, 'ml', 400, 'ml')  # 20% diff, OK
        True
        >>> quantities_compatible(500, 'ml', 250, 'ml')  # 50% diff, not OK
        False
        >>> quantities_compatible(500, 'ml', 500, 'g')  # Different types
        False
    """
    # If either is missing, allow match (can't compare)
    if not q1 or not q2:
        return True
    
    # Normalize units
    u1_norm = normalize_unit(u1 or '')
    u2_norm = normalize_unit(u2 or '')
    
    # Must be same unit type
    if u1_norm != u2_norm:
        # Check if both are volume or both are weight
        volume_units = {'ml', 'l'}
        weight_units = {'g', 'kg'}
        
        u1_vol = u1_norm in volume_units
        u2_vol = u2_norm in volume_units
        u1_wt = u1_norm in weight_units
        u2_wt = u2_norm in weight_units
        
        if not ((u1_vol and u2_vol) or (u1_wt and u2_wt)):
            return False
    
    # Check ratio
    if min(q1, q2) <= 0:
        return False
    
    ratio = max(q1, q2) / min(q1, q2)
    return ratio <= (1 + tolerance)


# === Testing ===
if __name__ == "__main__":
    test_cases = [
        ("Coca-Cola 2 x 500 мл", 1000.0, 'ml'),
        ("Прясно мляко 1.5 л", 1500.0, 'ml'),
        ("Сирене 400 г", 400.0, 'g'),
        ("Масло 250г", 250.0, 'g'),
        ("Бира 6х330ml", 1980.0, 'ml'),
        ("Яйца 10 бр", 10.0, 'pcs'),
        ("Олио 1л", 1000.0, 'ml'),
        ("Захар 2 кг", 2000.0, 'g'),
        ("Вода 0,5 л", 500.0, 'ml'),
        ("Продукт без количество", None, None),
    ]
    
    print("Quantity Parsing Tests:")
    print("-" * 60)
    for text, expected_qty, expected_unit in test_cases:
        qty, unit = parse_quantity(text)
        match = qty == expected_qty and unit == expected_unit
        status = "✓" if match else "✗"
        print(f"{status} '{text[:35]}...' → {qty} {unit} (expected: {expected_qty} {expected_unit})")
    
    print("\nQuantity Compatibility Tests:")
    print("-" * 60)
    compat_tests = [
        (500, 'ml', 500, 'ml', True),
        (500, 'ml', 400, 'ml', True),   # 20% diff, OK
        (500, 'ml', 250, 'ml', False),  # 50% diff, not OK
        (500, 'ml', 500, 'g', False),   # Different types
        (1000, 'ml', 1, 'l', True),     # Same after normalization
    ]
    for q1, u1, q2, u2, expected in compat_tests:
        result = quantities_compatible(q1, u1, q2, u2)
        status = "✓" if result == expected else "✗"
        print(f"{status} ({q1}{u1}, {q2}{u2}) → {result} (expected: {expected})")
