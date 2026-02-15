"""
StandardProduct Schema

Unified product format that ALL scrapers must output.
This ensures consistent data for cross-store matching.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, Any
from decimal import Decimal
import hashlib
import json


@dataclass
class StandardProduct:
    """
    Standardized product format for cross-store comparison.
    
    All scrapers must transform their raw data to this format.
    The matching pipeline relies on these fields being consistently populated.
    
    Required fields for matching:
    - store, name, normalized_name
    - brand (highly recommended for quality matches)
    - quantity_value + quantity_unit (for size compatibility)
    
    Example:
        product = StandardProduct(
            store="Kaufland",
            store_product_id="12345",
            name="Coca-Cola 2L",
            normalized_name="coca cola 2l",
            brand="Coca-Cola",
            quantity_value=2000.0,
            quantity_unit="ml",
            price=Decimal("3.49"),
        )
    """
    
    # === Identity (required) ===
    store: str  # "Kaufland" | "Lidl" | "Billa"
    store_product_id: str  # Store's native product ID
    
    # === Core Attributes (required for matching) ===
    name: str  # Clean display name (no promo prefixes)
    normalized_name: str  # Lowercase, no special chars, for matching
    
    # === Brand (highly recommended) ===
    brand: Optional[str] = None  # Extracted brand name
    is_house_brand: bool = False  # K-Classic, Pilos, Clever, etc.
    
    # === Quantity (normalized to base units) ===
    quantity_value: Optional[float] = None  # e.g., 500, 2000
    quantity_unit: Optional[str] = None  # "ml" | "g" | "pcs" | "kg" | "l"
    
    # === Category (for blocking - Phase 2) ===
    category_code: Optional[str] = None  # GS1 GPC code
    category_name: Optional[str] = None  # Human-readable
    
    # === Price ===
    price: Optional[Decimal] = None  # Current/promo price (BGN)
    old_price: Optional[Decimal] = None  # Regular/strikethrough price
    currency: str = "BGN"
    
    # Calculated fields
    price_per_100ml: Optional[float] = None
    price_per_100g: Optional[float] = None
    
    # === Availability ===
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_available: bool = True
    
    # === Metadata ===
    image_url: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    barcode: Optional[str] = None  # EAN/UPC if available
    
    # === Tracking ===
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    
    # === Raw data (for debugging) ===
    raw_data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate and compute derived fields."""
        # Ensure store is valid
        valid_stores = {"Kaufland", "Lidl", "Billa", "Fantastico"}
        if self.store not in valid_stores:
            raise ValueError(f"Invalid store: {self.store}. Must be one of {valid_stores}")
        
        # Compute price per unit if possible
        if self.price and self.quantity_value and self.quantity_unit:
            self._compute_price_per_unit()
    
    def _compute_price_per_unit(self):
        """Calculate price per 100ml or 100g."""
        if not self.quantity_value or self.quantity_value <= 0:
            return
        
        unit = (self.quantity_unit or "").lower()
        price_float = float(self.price)
        
        # Normalize to base unit (ml or g)
        if unit in ('ml', 'мл'):
            base_qty = self.quantity_value
            self.price_per_100ml = (price_float / base_qty) * 100
        elif unit in ('l', 'л'):
            base_qty = self.quantity_value * 1000  # Convert to ml
            self.price_per_100ml = (price_float / base_qty) * 100
        elif unit in ('g', 'г'):
            base_qty = self.quantity_value
            self.price_per_100g = (price_float / base_qty) * 100
        elif unit in ('kg', 'кг'):
            base_qty = self.quantity_value * 1000  # Convert to g
            self.price_per_100g = (price_float / base_qty) * 100
    
    @property
    def content_hash(self) -> str:
        """
        Generate hash for change detection.
        Used to detect if product data has changed between scrapes.
        """
        content = {
            "store": self.store,
            "store_product_id": self.store_product_id,
            "name": self.name,
            "brand": self.brand,
            "price": str(self.price) if self.price else None,
            "quantity_value": self.quantity_value,
            "quantity_unit": self.quantity_unit,
        }
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.md5(content_str.encode()).hexdigest()
    
    @property
    def display_quantity(self) -> str:
        """Human-readable quantity string."""
        if not self.quantity_value or not self.quantity_unit:
            return ""
        
        # Format nicely
        if self.quantity_value == int(self.quantity_value):
            qty = int(self.quantity_value)
        else:
            qty = self.quantity_value
        
        return f"{qty} {self.quantity_unit}"
    
    @property
    def discount_percent(self) -> Optional[float]:
        """Calculate discount percentage if old_price is available."""
        if not self.old_price or not self.price:
            return None
        if self.old_price <= 0:
            return None
        
        discount = (float(self.old_price) - float(self.price)) / float(self.old_price) * 100
        return round(discount, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "store": self.store,
            "store_product_id": self.store_product_id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "brand": self.brand,
            "is_house_brand": self.is_house_brand,
            "quantity": self.quantity_value,
            "unit": self.quantity_unit,
            "category_code": self.category_code,
            "category_name": self.category_name,
            "price": float(self.price) if self.price else None,
            "old_price": float(self.old_price) if self.old_price else None,
            "price_per_100ml": self.price_per_100ml,
            "price_per_100g": self.price_per_100g,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "image_url": self.image_url,
            "barcode": self.barcode,
            "scraped_at": self.scraped_at.isoformat(),
            "content_hash": self.content_hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StandardProduct":
        """Create StandardProduct from dictionary."""
        return cls(
            store=data["store"],
            store_product_id=data["store_product_id"],
            name=data["name"],
            normalized_name=data.get("normalized_name", ""),
            brand=data.get("brand"),
            is_house_brand=data.get("is_house_brand", False),
            quantity_value=data.get("quantity"),
            quantity_unit=data.get("unit"),
            category_code=data.get("category_code"),
            category_name=data.get("category_name"),
            price=Decimal(str(data["price"])) if data.get("price") else None,
            old_price=Decimal(str(data["old_price"])) if data.get("old_price") else None,
            valid_from=date.fromisoformat(data["valid_from"]) if data.get("valid_from") else None,
            valid_to=date.fromisoformat(data["valid_to"]) if data.get("valid_to") else None,
            image_url=data.get("image_url"),
            barcode=data.get("barcode"),
        )
