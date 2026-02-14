"""
Unit price normalization for Bulgarian grocery products.
Parses quantities from product names and calculates price per kg/L.
"""
import re
from typing import Optional, Tuple, Dict

# Regex patterns for Bulgarian/Latin units
WEIGHT_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*([гgкkКK][гgрr]?|[гgГG][рr]?)',
    re.IGNORECASE
)
VOLUME_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*([мmМM][лlЛL]|[лlЛL])',
    re.IGNORECASE
)
SINGLE_WEIGHT = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*([кkКK][гgГG]|[гgГG][рr]?)',
    re.IGNORECASE
)
SINGLE_VOLUME = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*([мmМM][лlЛL]|[лlЛL])',
    re.IGNORECASE
)


def _parse_number(s: str) -> float:
    """Parse number, handling comma as decimal separator."""
    return float(s.replace(',', '.'))


def _normalize_unit(unit: str) -> Tuple[str, float]:
    """
    Normalize unit to base (g or ml) with multiplier.
    Returns (base_unit, multiplier)
    """
    unit = unit.lower()
    # Kilograms
    if unit in ('кг', 'kg', 'кг', 'kг'):
        return ('g', 1000)
    # Grams
    if unit in ('г', 'g', 'гр', 'gr', 'г'):
        return ('g', 1)
    # Liters
    if unit in ('л', 'l', 'л'):
        return ('ml', 1000)
    # Milliliters
    if unit in ('мл', 'ml', 'мл'):
        return ('ml', 1)
    return ('unknown', 1)


def parse_quantity(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse quantity from product name/description.
    Returns (amount_in_base_unit, base_unit) or (None, None).
    
    Examples:
        "Мляко 1л" → (1000.0, "ml")
        "Сирене 400г" → (400.0, "g")
        "Бира 6x500мл" → (3000.0, "ml")
    """
    if not text:
        return None, None
    
    # Try multi-pack weight first (6x500г)
    match = WEIGHT_PATTERN.search(text)
    if match:
        count = _parse_number(match.group(1))
        amount = _parse_number(match.group(2))
        unit = match.group(3)
        base_unit, multiplier = _normalize_unit(unit)
        return count * amount * multiplier, base_unit
    
    # Try multi-pack volume (6x500мл)
    match = VOLUME_PATTERN.search(text)
    if match:
        count = _parse_number(match.group(1))
        amount = _parse_number(match.group(2))
        unit = match.group(3)
        base_unit, multiplier = _normalize_unit(unit)
        return count * amount * multiplier, base_unit
    
    # Try single weight (500г, 1.5кг)
    match = SINGLE_WEIGHT.search(text)
    if match:
        amount = _parse_number(match.group(1))
        unit = match.group(2)
        base_unit, multiplier = _normalize_unit(unit)
        return amount * multiplier, base_unit
    
    # Try single volume (1л, 500мл)
    match = SINGLE_VOLUME.search(text)
    if match:
        amount = _parse_number(match.group(1))
        unit = match.group(2)
        base_unit, multiplier = _normalize_unit(unit)
        return amount * multiplier, base_unit
    
    return None, None


def calculate_unit_price(price: float, quantity: float, unit: str) -> Dict[str, Optional[float]]:
    """
    Calculate normalized unit prices.
    Returns {"price_per_kg": float | None, "price_per_liter": float | None}
    """
    result = {"price_per_kg": None, "price_per_liter": None}
    
    if quantity <= 0:
        return result
    
    if unit == 'g':
        # Convert to price per kg
        result["price_per_kg"] = round((price / quantity) * 1000, 2)
    elif unit == 'ml':
        # Convert to price per liter
        result["price_per_liter"] = round((price / quantity) * 1000, 2)
    
    return result


def get_unit_prices(name: str, price: float) -> Dict[str, Optional[float]]:
    """
    Convenience function: parse quantity and calculate unit prices.
    """
    quantity, unit = parse_quantity(name)
    if quantity is None:
        return {"price_per_kg": None, "price_per_liter": None}
    return calculate_unit_price(price, quantity, unit)


if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("Прясно мляко 1л", 2.49),           # → price_per_liter: 2.49
        ("Кашкавал 400г", 5.99),              # → price_per_kg: 14.975
        ("Бира Загорка 6x500мл", 7.99),       # → price_per_liter: 2.66
        ("Кисело мляко 4x400г", 3.99),        # → price_per_kg: 2.49
        ("Олио 1.5 L", 4.49),                 # → price_per_liter: 2.99
        ("Захар 1 кг", 2.19),                 # → price_per_kg: 2.19
        ("Сирене краве 200 гр", 3.49),        # → price_per_kg: 17.45
        ("Вода минерална 1,5л", 0.89),        # → price_per_liter: 0.59
        ("Бисквити без количество", 1.99),   # → None, None
    ]
    
    print("=== Unit Price Tests ===\n")
    for name, price in test_cases:
        qty, unit = parse_quantity(name)
        prices = get_unit_prices(name, price)
        print(f"'{name}' @ {price}€")
        print(f"  Parsed: {qty} {unit}")
        print(f"  Unit prices: {prices}\n")
