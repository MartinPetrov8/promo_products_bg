"""
PromoBG Standardization Module

Provides consistent data extraction and normalization across all store scrapers.
Ensures products from Kaufland, Lidl, and Billa can be meaningfully compared.

Key Components:
- StandardProduct: Unified product schema
- BrandExtractor: Extract brands from product names
- QuantityParser: Parse Bulgarian quantities (мл, г, кг)
- NameNormalizer: Clean promo prefixes, normalize for matching
- CategoryClassifier: Classify products into GS1 GPC categories
- ProductProcessor: Main orchestrator
"""

from .schema import StandardProduct
from .brand_extractor import extract_brand, is_house_brand, KNOWN_BRANDS
from .quantity_parser import parse_quantity, normalize_unit, quantities_compatible
from .name_normalizer import clean_name, normalize_name
from .category_classifier import CategoryClassifier, classify_product
from .processor import ProductProcessor, standardize_product

__all__ = [
    # Schema
    'StandardProduct',
    
    # Brand extraction
    'extract_brand',
    'is_house_brand',
    'KNOWN_BRANDS',
    
    # Quantity parsing
    'parse_quantity',
    'normalize_unit',
    'quantities_compatible',
    
    # Name normalization
    'clean_name',
    'normalize_name',
    
    # Category classification
    'CategoryClassifier',
    'classify_product',
    
    # Processor
    'ProductProcessor',
    'standardize_product',
]
