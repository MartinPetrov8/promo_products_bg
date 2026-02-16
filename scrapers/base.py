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
