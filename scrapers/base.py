from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timezone
import hashlib

class Store(Enum):
    KAUFLAND = "Kaufland"
    LIDL = "Lidl"
    BILLA = "Billa"

@dataclass
class RawProduct:
    store: str
    sku: str
    raw_name: str
    raw_subtitle: Optional[str] = None
    raw_description: Optional[str] = None
    brand: Optional[str] = None
    price_bgn: Optional[float] = None
    old_price_bgn: Optional[float] = None
    discount_pct: Optional[float] = None
    quantity_value: Optional[float] = None  # e.g., 500
    quantity_unit: Optional[str] = None     # e.g., "g", "ml", "kg"
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    scraped_at: str = None
    
    def __post_init__(self):
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self):
        return asdict(self)
    
    @staticmethod
    def generate_sku(text: str) -> str:
        """Generate deterministic SKU from text (fixes hash randomization issue)"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

class BaseScraper(ABC):
    @property
    @abstractmethod
    def store(self) -> Store:
        pass
    
    @abstractmethod
    def scrape(self) -> List[RawProduct]:
        pass
    
    def health_check(self) -> bool:
        return True


# === Utility Functions ===

def parse_quantity_from_name(name: str) -> tuple:
    """
    Extract quantity from product name.
    
    Patterns handled:
    - "2 x 250 г" → (500, 'g')
    - "125 г" → (125, 'g')
    - "1.5 кг" → (1500, 'g')
    - "0.5 л" → (500, 'ml')
    - "500 мл" → (500, 'ml')
    - "3 бр." → (3, 'count')
    
    Returns: (value, unit) or (None, None)
    """
    if not name:
        return None, None
    
    import re
    name_lower = name.lower()
    
    # Pattern 1: "X x Y unit" (multiply)
    match = re.search(r'(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(г|g|кг|kg|мл|ml|л|l)\b', name_lower)
    if match:
        count = int(match.group(1))
        value = float(match.group(2).replace(',', '.'))
        unit = match.group(3)
        total = count * value
        
        # Normalize units
        if unit in ('г', 'g'):
            return total, 'g'
        elif unit in ('кг', 'kg'):
            return total * 1000, 'g'
        elif unit in ('мл', 'ml'):
            return total, 'ml'
        elif unit in ('л', 'l'):
            return total * 1000, 'ml'
    
    # Pattern 2: "Y unit" (single quantity)
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(г|g|кг|kg|мл|ml|л|l)\b', name_lower)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2)
        
        # Normalize units
        if unit in ('г', 'g'):
            return value, 'g'
        elif unit in ('кг', 'kg'):
            return value * 1000, 'g'
        elif unit in ('мл', 'ml'):
            return value, 'ml'
        elif unit in ('л', 'l'):
            return value * 1000, 'ml'
    
    # Pattern 2b: No space before unit ("1,2кг", "500мл")
    match = re.search(r'(\d+(?:[.,]\d+)?)(г|g|кг|kg|мл|ml|л|l)\b', name_lower)
    if match:
        value = float(match.group(1).replace(',', '.'))
        unit = match.group(2)
        if unit in ('г', 'g'):
            return value, 'g'
        elif unit in ('кг', 'kg'):
            return value * 1000, 'g'
        elif unit in ('мл', 'ml'):
            return value, 'ml'
        elif unit in ('л', 'l'):
            return value * 1000, 'ml'
    
    # Pattern 2c: Range ("250-300 г") — take first value
    match = re.search(r'(\d+)\s*[-–]\s*\d+\s*(г|g|кг|kg|мл|ml|л|l)\b', name_lower)
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        if unit in ('г', 'g'):
            return value, 'g'
        elif unit in ('кг', 'kg'):
            return value * 1000, 'g'
        elif unit in ('мл', 'ml'):
            return value, 'ml'
        elif unit in ('л', 'l'):
            return value * 1000, 'ml'
    
    # Pattern 3: "X бр" (count)
    match = re.search(r'(\d+)\s*бр\.?', name_lower)
    if match:
        return int(match.group(1)), 'count'
    
    return None, None


def extract_brand_from_name(name: str, known_brands: set = None) -> Optional[str]:
    """
    Extract brand from product name.
    
    Strategy (in priority order):
    1. Match against known brands list (longest match wins) — handles Cyrillic + Latin
    2. Extract Latin brand from start of name (heuristic fallback)
    
    Returns: brand name or None
    """
    if not name:
        return None
    
    import re
    name = name.strip()
    
    # Strategy 1: Known brands list (most reliable, handles Cyrillic)
    if known_brands:
        name_lower = name.lower()
        for brand in sorted(known_brands, key=len, reverse=True):
            if brand.lower() in name_lower:
                # Word boundary check to prevent substring matches
                pattern = re.compile(
                    r'(?:^|[\s,\-\(])' + re.escape(brand) + r'(?:[\s,\-\)\.:]|$)',
                    re.IGNORECASE
                )
                if pattern.search(name):
                    return brand
    
    # Strategy 2: Latin text at start of name = likely brand
    words = name.split()
    if not words:
        return None
    
    first_word = words[0]
    
    # Remove common prefixes
    if first_word.lower() in ('king', 'супер', 'mega', 'промо'):
        if len(words) > 1:
            first_word = words[1]
        else:
            return None
    
    has_latin = bool(re.search(r'[a-zA-Z]', first_word))
    has_cyrillic = bool(re.search(r'[а-яА-Я]', first_word))
    
    if has_latin and not has_cyrillic:
        brand_parts = [first_word]
        
        for i, word in enumerate(words[1:], 1):
            if re.search(r'[а-яА-Я]', word):
                break
            if word.lower() in ('-', 'с', 'от', 'за'):
                break
            if re.search(r'[a-zA-Z]', word) or word in ('&', '+'):
                brand_parts.append(word)
            else:
                break
            if i >= 2:
                break
        
        brand = ' '.join(brand_parts).strip()
        brand = re.sub(r'[,\-:]+$', '', brand).strip()
        
        if brand and len(brand) >= 2 and len(brand) <= 50:
            return brand
    
    return None
