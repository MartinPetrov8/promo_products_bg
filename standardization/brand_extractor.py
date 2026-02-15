"""
Brand Extractor

Extracts brand names from product names using a dictionary of known brands.
Critical for cross-store matching since brands are often embedded in product names.

Example:
    "Hochland крема сирене 200 г" → brand="Hochland"
    "K-Classic Прясно мляко 3.5%" → brand="K-Classic", is_house_brand=True
"""

import re
from typing import Optional, Set, Tuple


# === Known Brand Dictionary ===
# Sorted by length (longest first) for greedy matching

INTERNATIONAL_BRANDS: Set[str] = {
    # Beverages
    'Coca-Cola', 'Pepsi', 'Fanta', 'Sprite', '7Up', 'Schweppes', 'Red Bull',
    'Nescafé', 'Lavazza', 'Jacobs', 'Tchibo', 'Illy',
    
    # Dairy
    'Danone', 'Activia', 'Actimel', 'Nestlé', 'Müller',
    
    # Chocolate/Confectionery
    'Milka', 'Oreo', 'Ferrero', 'Nutella', 'Kinder', 'Lindt', 'Toblerone',
    'Haribo', 'Mars', 'Snickers', 'Twix', 'Bounty', 'M&M\'s',
    
    # Snacks
    'Pringles', 'Lay\'s', 'Doritos', 'Cheetos',
    
    # Food
    'Heinz', 'Barilla', 'Knorr', 'Maggi', 'Hellmann\'s', 'Bonduelle',
    
    # Personal Care
    'Palmolive', 'Colgate', 'Nivea', 'Dove', 'Head & Shoulders',
    'Garnier', "L'Oreal", 'Oral-B', 'Sensodyne', 'Rexona', 'Axe',
    
    # Household
    'Ariel', 'Persil', 'Finish', 'Fairy', 'Mr. Proper', 'Domestos',
    
    # Beer
    'Heineken', 'Carlsberg', 'Paulaner', 'Budweiser', 'Corona', 'Stella Artois',
    
    # Cheese
    'Hochland', 'Philadelphia', 'Président', 'Galbani',
}

BULGARIAN_BRANDS: Set[str] = {
    # Dairy
    'Верея', 'Елена', 'Olympus', 'Калиакра', 'Родопско', 'Мандра', 'БДС',
    'Добруджа', 'Родопи', 'Бор Чвор', 'Млечни продукти',
    
    # Meat
    'Престиж', 'Тандем', 'Перелик', 'КФМ', 'ЕКО МЕС', 'Родопи',
    'Деликатес Житница', 'Българска Ферма', 'Мираж', 'Роден край',
    'Тракия', 'Карнобат', 'Леки', 'Маджаров',
    
    # Beverages
    'Девин', 'Горна Баня', 'Банкя', 'Хисар', 'Михалково',
    
    # Beer
    'Каменица', 'Загорка', 'Пиринско', 'Шуменско', 'Ариана',
    
    # Bakery
    'Боровец', 'Закуска',
    
    # Confectionery
    'Своге', 'Шоколадова фабрика',
    
    # Other
    'Jogobella', 'Born Winner', 'Nucrema', 'Prima',
}

# House brands (store-exclusive private labels)
HOUSE_BRANDS: dict = {
    'Kaufland': {
        'K-Classic', 'K-Bio', 'Exquisit', 'BRIO', 'LIV&BO', "Liv&Bo",
        'OYANDA', 'Livarno', 'LIVARNO', 'ERNESTO', 'MERADISO', 'CROFTON',
    },
    'Lidl': {
        'Pilos', 'Milbona', 'Solevita', 'Cien', 'Silvercrest', 'Parkside',
        'Esmara', 'Clever', 'S-Budget', 'Lupilu', 'CRIVIT', 'Livergy',
        'Preferred Selection', 'Deluxe', 'Freeway', 'Sondey', 'Bellarom',
        'Dulano', 'Combino', 'Italiamo', 'Chef Select', 'Vemondo',
    },
    'Billa': {
        'BILLA', 'Billa', 'La Provincia', "Cammino D'oro", 'Clever',
        'S-Budget', 'BILLA Bio', 'BILLA Premium',
    },
}

# Flatten house brands for quick lookup
ALL_HOUSE_BRANDS: Set[str] = set()
for store_brands in HOUSE_BRANDS.values():
    ALL_HOUSE_BRANDS.update(store_brands)

# Combine all known brands
KNOWN_BRANDS: Set[str] = INTERNATIONAL_BRANDS | BULGARIAN_BRANDS | ALL_HOUSE_BRANDS

# Sort by length (longest first) for greedy matching
_BRANDS_SORTED = sorted(KNOWN_BRANDS, key=len, reverse=True)


def extract_brand(name: str, store: Optional[str] = None) -> Optional[str]:
    """
    Extract brand from product name using known brands dictionary.
    
    Args:
        name: Product name to search
        store: Optional store name for context-aware matching
        
    Returns:
        Brand name if found, None otherwise
        
    Example:
        >>> extract_brand("Hochland крема сирене 200 г")
        'Hochland'
        >>> extract_brand("K-Classic Прясно мляко 3.5%")
        'K-Classic'
    """
    if not name:
        return None
    
    name_lower = name.lower()
    
    # Check store house brands first (higher priority)
    if store and store in HOUSE_BRANDS:
        for brand in HOUSE_BRANDS[store]:
            if brand.lower() in name_lower:
                return brand
    
    # Search all known brands (longest first for greedy match)
    for brand in _BRANDS_SORTED:
        brand_lower = brand.lower()
        # Use word boundary matching for accuracy
        pattern = r'\b' + re.escape(brand_lower) + r'\b'
        if re.search(pattern, name_lower):
            return brand
        # Fallback: simple contains check for brands with special chars
        if brand_lower in name_lower:
            return brand
    
    return None


def is_house_brand(brand: Optional[str], store: Optional[str] = None) -> bool:
    """
    Check if a brand is a store house brand.
    
    Args:
        brand: Brand name to check
        store: Optional store name for specific check
        
    Returns:
        True if brand is a house brand
        
    Example:
        >>> is_house_brand("K-Classic")
        True
        >>> is_house_brand("Coca-Cola")
        False
    """
    if not brand:
        return False
    
    brand_lower = brand.lower()
    
    # Check specific store
    if store and store in HOUSE_BRANDS:
        for hb in HOUSE_BRANDS[store]:
            if hb.lower() == brand_lower:
                return True
    
    # Check all house brands
    for hb in ALL_HOUSE_BRANDS:
        if hb.lower() == brand_lower:
            return True
    
    return False


def get_brand_store(brand: str) -> Optional[str]:
    """
    Get the store that owns a house brand.
    
    Args:
        brand: Brand name to check
        
    Returns:
        Store name if house brand, None otherwise
        
    Example:
        >>> get_brand_store("K-Classic")
        'Kaufland'
        >>> get_brand_store("Pilos")
        'Lidl'
    """
    if not brand:
        return None
    
    brand_lower = brand.lower()
    
    for store, brands in HOUSE_BRANDS.items():
        for hb in brands:
            if hb.lower() == brand_lower:
                return store
    
    return None


def extract_brand_and_type(name: str, store: Optional[str] = None) -> Tuple[Optional[str], bool]:
    """
    Extract brand and determine if it's a house brand in one call.
    
    Args:
        name: Product name to search
        store: Optional store name for context
        
    Returns:
        Tuple of (brand_name, is_house_brand)
        
    Example:
        >>> extract_brand_and_type("K-Classic Прясно мляко", "Kaufland")
        ('K-Classic', True)
        >>> extract_brand_and_type("Coca-Cola 500ml")
        ('Coca-Cola', False)
    """
    brand = extract_brand(name, store)
    if brand:
        return (brand, is_house_brand(brand, store))
    return (None, False)


# === Testing ===
if __name__ == "__main__":
    test_cases = [
        ("Hochland крема сирене 200 г", None, "Hochland"),
        ("K-Classic Прясно мляко 3.5% 1L", "Kaufland", "K-Classic"),
        ("Pilos кисело мляко 400г", "Lidl", "Pilos"),
        ("BILLA Био яйца 10 бр", "Billa", "BILLA"),
        ("Coca-Cola 2L", None, "Coca-Cola"),
        ("Верея Прясно мляко 3%", None, "Верея"),
        ("Престиж Луканка 200г", None, "Престиж"),
        ("Обикновен продукт без марка", None, None),
    ]
    
    print("Brand Extraction Tests:")
    print("-" * 60)
    for name, store, expected in test_cases:
        result = extract_brand(name, store)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name[:40]}...' → {result} (expected: {expected})")
    
    print("\nHouse Brand Tests:")
    print("-" * 60)
    for brand in ["K-Classic", "Pilos", "Coca-Cola", "Верея"]:
        result = is_house_brand(brand)
        store = get_brand_store(brand)
        print(f"  {brand}: house_brand={result}, store={store}")
