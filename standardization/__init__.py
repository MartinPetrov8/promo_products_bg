"""
PromoBG Standardization Module

Provides consistent data extraction and normalization across all store scrapers.
Ensures products from Kaufland, Lidl, and Billa can be meaningfully compared.

Key Components:
- StandardProduct: Unified product schema
- BrandExtractor: Extract brands from product names
- QuantityParser: Parse Bulgarian quantities (мл, г, кг)
- NameNormalizer: Clean promo prefixes, normalize for matching
"""

from .schema import StandardProduct
from .brand_extractor import extract_brand, is_house_brand, KNOWN_BRANDS
from .quantity_parser import parse_quantity, normalize_unit
from .name_normalizer import clean_name, normalize_name

__all__ = [
    'StandardProduct',
    'extract_brand',
    'is_house_brand',
    'KNOWN_BRANDS',
    'parse_quantity',
    'normalize_unit',
    'clean_name',
    'normalize_name',
]
