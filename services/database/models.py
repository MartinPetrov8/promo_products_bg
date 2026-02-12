"""
Pydantic Models for Database Entities

These models are used for validation and serialization.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class UnitType(str, Enum):
    KILOGRAM = "kg"
    GRAM = "g"
    LITER = "L"
    MILLILITER = "ml"
    PIECE = "бр"
    PACKAGE = "пакет"


class StoreCode(str, Enum):
    KAUFLAND = "kaufland"
    LIDL = "lidl"
    BILLA = "billa"
    METRO = "metro"
    FANTASTICO = "fantastico"


# ============================================
# Store Models
# ============================================

class Store(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    code: str
    name: str
    display_name: str
    logo_url: Optional[str] = None
    website: Optional[str] = None
    has_api: bool = False
    api_url: Optional[str] = None
    api_format: Optional[str] = None
    currency: str = "EUR"
    is_active: bool = True


class StoreCreate(BaseModel):
    code: str
    name: str
    display_name: str
    logo_url: Optional[str] = None
    website: Optional[str] = None


# ============================================
# Category Models
# ============================================

class Category(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    normalized_name: str
    parent_id: Optional[int] = None
    level: int = 0
    path: Optional[str] = None
    is_active: bool = True


# ============================================
# Product Models
# ============================================

class ProductBase(BaseModel):
    name: str
    normalized_name: Optional[str] = None
    brand: Optional[str] = None
    category_id: Optional[int] = None
    unit: str = "бр"
    quantity: Optional[float] = None
    barcode_ean: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_verified: bool = False
    match_confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime


# ============================================
# Store Product Models
# ============================================

class StoreProductBase(BaseModel):
    store_product_code: str
    store_product_url: Optional[str] = None
    store_image_url: Optional[str] = None
    name_override: Optional[str] = None
    package_size: Optional[str] = None


class StoreProduct(StoreProductBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    product_id: int
    store_id: int
    is_available: bool = True
    first_seen_at: datetime
    last_seen_at: datetime


# ============================================
# Price Models
# ============================================

class PriceBase(BaseModel):
    current_price: float = Field(..., ge=0)
    old_price: Optional[float] = Field(None, ge=0)
    discount_percent: Optional[float] = Field(None, ge=0, le=100)
    price_per_unit: Optional[float] = None
    price_per_unit_base: Optional[str] = None
    currency: str = "EUR"
    is_promotional: bool = False
    promotion_label: Optional[str] = None


class Price(PriceBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    store_product_id: int
    valid_from: datetime
    valid_to: Optional[datetime] = None


class PriceHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    store_product_id: int
    price: float
    old_price: Optional[float] = None
    discount_percent: Optional[float] = None
    recorded_at: datetime
    is_promotional: bool = False


# ============================================
# Combined/View Models
# ============================================

class ProductWithPrice(BaseModel):
    """Product with current price from a specific store."""
    name: str
    brand: Optional[str] = None
    store: str
    store_code: str
    current_price: float
    old_price: Optional[float] = None
    discount_percent: Optional[float] = None
    promotion_label: Optional[str] = None
    store_product_url: Optional[str] = None
    store_image_url: Optional[str] = None


class ProductComparison(BaseModel):
    """Product with prices from multiple stores for comparison."""
    name: str
    brand: Optional[str] = None
    barcode_ean: Optional[str] = None
    prices: List[ProductWithPrice]
    cheapest_store: str
    cheapest_price: float
    savings_vs_highest: float
    savings_percent: float


class DealProduct(BaseModel):
    """Product that's currently on promotion."""
    name: str
    brand: Optional[str] = None
    store: str
    store_code: str
    current_price: float
    old_price: float
    discount_percent: float
    promotion_label: Optional[str] = None
    store_product_url: Optional[str] = None
    store_image_url: Optional[str] = None
    is_lowest_recorded: bool = False
