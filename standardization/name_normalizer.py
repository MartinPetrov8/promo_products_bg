"""
Name Normalizer

Cleans and normalizes product names for matching.

Key functions:
1. clean_name: Remove HTML, promo prefixes, normalize whitespace
2. normalize_name: Create matching-friendly version (lowercase, no special chars)

Example:
    >>> clean_name("King оферта - Hochland крема сирене 200 г", "Billa")
    'Hochland крема сирене 200 г'
    >>> normalize_name("Coca-Cola 2L")
    'coca cola 2l'
"""

import re
from typing import Optional


# === Promo Prefix Patterns ===
# Store-specific prefixes that pollute product names

PROMO_PREFIXES = {
    'Billa': [
        r'^King оферта\s*[-–—]\s*',
        r'^Само с Billa (?:Card|App)\s*[-–—]\s*',
        r'^Супер цена\s*[-–—]\s*',
        r'^Сега в Billa\s*[-–—]\s*',
        r'^Онлайн оферта\s*[-–—]\s*',
        r'^Само онлайн\s*[-–—]\s*',
        r'^Нова цена\s*[-–—]\s*',
        r'^Специална цена\s*[-–—]\s*',
    ],
    'Lidl': [
        r'^Само тази седмица\s*[-–—]\s*',
        r'^Лидл плюс\s*[-–—]\s*',
        r'^Lidl Plus\s*[-–—]\s*',
        r'^Супер оферта\s*[-–—]\s*',
    ],
    'Kaufland': [
        r'^K-Classic\s+',  # Note: K-Classic is a brand, not prefix
        r'^Kaufland Card\s*[-–—]\s*',
        r'^Само с карта\s*[-–—]\s*',
    ],
}

# Generic prefixes that apply to all stores
GENERIC_PREFIXES = [
    r'^Промоция\s*[-–—:]\s*',
    r'^Акция\s*[-–—:]\s*',
    r'^Оферта\s*[-–—:]\s*',
    r'^Специална оферта\s*[-–—:]\s*',
    r'^Ексклузивно\s*[-–—:]\s*',
    r'^НОВО\s*[-–—:]\s*',
    r'^Ново\s*[-–—:]\s*',
]

# Suffixes to remove
SUFFIXES_TO_REMOVE = [
    r'\s*\|\s*LIDL$',  # "Product | LIDL" → "Product"
    r'\s*\|\s*Kaufland$',
    r'\s*\|\s*Billa$',
    r'\s*-\s*\d+%\s*$',  # "Product -30%" → "Product"
]


def clean_name(name: str, store: Optional[str] = None) -> str:
    """
    Clean product name by removing HTML, prefixes, and normalizing whitespace.
    
    Args:
        name: Raw product name
        store: Store name for store-specific prefix removal
        
    Returns:
        Cleaned product name
        
    Example:
        >>> clean_name("King оферта - Hochland крема сирене", "Billa")
        'Hochland крема сирене'
        >>> clean_name("<b>Product</b> Name", None)
        'Product Name'
    """
    if not name:
        return ""
    
    cleaned = name.strip()
    
    # Step 1: Remove HTML tags
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    
    # Step 2: Remove HTML entities
    cleaned = re.sub(r'&[a-z]+;', ' ', cleaned)
    cleaned = re.sub(r'&#\d+;', ' ', cleaned)
    
    # Step 3: Remove store-specific promo prefixes
    if store and store in PROMO_PREFIXES:
        for pattern in PROMO_PREFIXES[store]:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Step 4: Remove generic prefixes
    for pattern in GENERIC_PREFIXES:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Step 5: Remove suffixes
    for pattern in SUFFIXES_TO_REMOVE:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Step 6: Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Step 7: Strip leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned


def normalize_name(name: str) -> str:
    """
    Create normalized version for matching.
    
    - Lowercase
    - Remove special characters (keep Cyrillic and Latin letters, digits, spaces)
    - Normalize whitespace
    - Remove common filler words
    
    Args:
        name: Product name (ideally already cleaned)
        
    Returns:
        Normalized name for matching
        
    Example:
        >>> normalize_name("Coca-Cola 2L")
        'coca cola 2l'
        >>> normalize_name("Прясно мляко 3.5%")
        'прясно мляко 3 5'
    """
    if not name:
        return ""
    
    normalized = name.lower()
    
    # Keep only letters (Cyrillic + Latin), digits, and spaces
    # Remove punctuation and special characters
    normalized = re.sub(r'[^\w\sа-яА-Яa-zA-Z0-9]', ' ', normalized)
    
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove common filler words that don't help matching
    filler_words = [
        r'\bразлични видове\b',
        r'\bразлични вкусове\b',
        r'\bпо избор\b',
        r'\bот нашата пекарна\b',
        r'\bот топла витрина\b',
        r'\bот свежата витрина\b',
        r'\bвалидно от\b',
        r'\bдо изчерпване\b',
    ]
    for pattern in filler_words:
        normalized = re.sub(pattern, '', normalized)
    
    # Normalize whitespace again after removals
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized.strip()


def create_search_tokens(name: str) -> list:
    """
    Create search tokens from product name.
    
    Useful for token-based matching and search.
    
    Args:
        name: Product name
        
    Returns:
        List of lowercase tokens (words)
        
    Example:
        >>> create_search_tokens("Coca-Cola 2L Cherry")
        ['coca', 'cola', '2l', 'cherry']
    """
    normalized = normalize_name(name)
    tokens = normalized.split()
    
    # Filter out very short tokens (likely noise)
    tokens = [t for t in tokens if len(t) > 1]
    
    return tokens


def names_similar(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """
    Check if two names are similar using token overlap.
    
    Simple Jaccard similarity on tokens.
    
    Args:
        name1: First product name
        name2: Second product name
        threshold: Minimum similarity score (0-1)
        
    Returns:
        True if names are similar above threshold
    """
    tokens1 = set(create_search_tokens(name1))
    tokens2 = set(create_search_tokens(name2))
    
    if not tokens1 or not tokens2:
        return False
    
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    
    similarity = intersection / union if union > 0 else 0
    return similarity >= threshold


def extract_product_type(name: str) -> Optional[str]:
    """
    Extract the main product type from name.
    
    Useful for category hints.
    
    Args:
        name: Product name
        
    Returns:
        Product type if identifiable
        
    Example:
        >>> extract_product_type("Прясно мляко 3.5% 1L")
        'мляко'
        >>> extract_product_type("Пилешки филета 500г")
        'пилешки'
    """
    # Common product type patterns (Bulgarian)
    product_types = [
        r'\b(мляко|кисело мляко|прясно мляко)\b',
        r'\b(сирене|кашкавал|топено сирене)\b',
        r'\b(масло|маргарин)\b',
        r'\b(хляб|питка|кифла|баничка)\b',
        r'\b(месо|пилешко|свинско|телешко|агнешко)\b',
        r'\b(колбас|луканка|кренвирш|салам|шунка)\b',
        r'\b(бира|вино|ракия|водка)\b',
        r'\b(сок|нектар|вода|кола)\b',
        r'\b(шоколад|бисквити|вафла)\b',
        r'\b(кафе|чай)\b',
    ]
    
    name_lower = name.lower()
    for pattern in product_types:
        match = re.search(pattern, name_lower)
        if match:
            return match.group(1)
    
    return None


# === Testing ===
if __name__ == "__main__":
    print("Name Cleaning Tests:")
    print("-" * 60)
    test_cases = [
        ("King оферта - Hochland крема сирене 200 г", "Billa", "Hochland крема сирене 200 г"),
        ("Само с Billa Card - Nivea Душ гел 500 мл", "Billa", "Nivea Душ гел 500 мл"),
        ("<ul><li>Продукт</li></ul>", None, "Продукт"),
        ("Coca-Cola 2L | LIDL", "Lidl", "Coca-Cola 2L"),
        ("Промоция - Прясно мляко", None, "Прясно мляко"),
    ]
    
    for name, store, expected in test_cases:
        result = clean_name(name, store)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name[:40]}...'")
        print(f"   → '{result}'")
        if result != expected:
            print(f"   Expected: '{expected}'")
    
    print("\nNormalization Tests:")
    print("-" * 60)
    norm_tests = [
        ("Coca-Cola 2L", "coca cola 2l"),
        ("Прясно мляко 3.5%", "прясно мляко 3 5"),
        ("HOCHLAND Крема-сирене", "hochland крема сирене"),
    ]
    
    for name, expected in norm_tests:
        result = normalize_name(name)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name}' → '{result}'")
        if result != expected:
            print(f"   Expected: '{expected}'")
    
    print("\nSimilarity Tests:")
    print("-" * 60)
    sim_tests = [
        ("Coca-Cola 2L", "Coca Cola 2 L", True),
        ("Прясно мляко 3%", "Прясно мляко 3.5%", True),
        ("Мляко", "Сирене", False),
    ]
    
    for name1, name2, expected in sim_tests:
        result = names_similar(name1, name2)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name1}' ~ '{name2}' → {result}")
