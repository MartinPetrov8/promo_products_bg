#!/usr/bin/env python3
"""
Open Food Facts API Client

Fetches product images, descriptions, and metadata from OFF
for matching with our scraped products.

API Docs: https://openfoodfacts.github.io/openfoodfacts-server/api/
"""

import json
import logging
import time
import random
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

# API Configuration
BASE_URL = "https://world.openfoodfacts.org/api/v2"
SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
USER_AGENT = "PromoBG/1.0 (https://github.com/MartinPetrov8/promo_products_bg; contact@promobg.com)"

# Rate limiting
MIN_DELAY = 1.0  # OFF asks for 1 request per second
MAX_DELAY = 2.0


@dataclass
class OFFProduct:
    """Product data from Open Food Facts"""
    barcode: str
    name: str
    generic_name: Optional[str]
    brands: Optional[str]
    categories: Optional[str]
    image_url: Optional[str]
    image_small_url: Optional[str]
    image_ingredients_url: Optional[str]
    image_nutrition_url: Optional[str]
    quantity: Optional[str]
    packaging: Optional[str]
    ingredients_text: Optional[str]
    nutriscore_grade: Optional[str]
    countries: Optional[str]
    
    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> 'OFFProduct':
        """Create from API response"""
        return cls(
            barcode=data.get('code', ''),
            name=data.get('product_name', ''),
            generic_name=data.get('generic_name'),
            brands=data.get('brands'),
            categories=data.get('categories'),
            image_url=data.get('image_url'),
            image_small_url=data.get('image_small_url'),
            image_ingredients_url=data.get('image_ingredients_url'),
            image_nutrition_url=data.get('image_nutrition_url'),
            quantity=data.get('quantity'),
            packaging=data.get('packaging'),
            ingredients_text=data.get('ingredients_text'),
            nutriscore_grade=data.get('nutriscore_grade'),
            countries=data.get('countries'),
        )


class OpenFoodFactsClient:
    """
    Client for Open Food Facts API.
    
    Rate limited to 1 request/second as per OFF guidelines.
    """
    
    # Fields to request (minimize response size)
    DEFAULT_FIELDS = [
        'code', 'product_name', 'generic_name', 'brands', 'categories',
        'image_url', 'image_small_url', 'image_ingredients_url', 'image_nutrition_url',
        'quantity', 'packaging', 'ingredients_text', 'nutriscore_grade', 'countries'
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json',
        })
        self.last_request_time = 0
        self.stats = {
            'requests': 0,
            'products_found': 0,
            'errors': 0,
        }
    
    def _rate_limit(self):
        """Enforce rate limiting"""
        elapsed = time.time() - self.last_request_time
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        
        if elapsed < delay:
            time.sleep(delay - elapsed)
        
        self.last_request_time = time.time()
    
    def get_product_by_barcode(self, barcode: str) -> Optional[OFFProduct]:
        """
        Get product by EAN/UPC barcode.
        
        Args:
            barcode: EAN-13, EAN-8, or UPC code
            
        Returns:
            OFFProduct if found, None otherwise
        """
        self._rate_limit()
        self.stats['requests'] += 1
        
        url = f"{BASE_URL}/product/{barcode}"
        params = {'fields': ','.join(self.DEFAULT_FIELDS)}
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 1:
                    self.stats['products_found'] += 1
                    return OFFProduct.from_api(data['product'])
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching barcode {barcode}: {e}")
            self.stats['errors'] += 1
            return None
    
    def search_products(
        self,
        query: Optional[str] = None,
        country: str = 'bulgaria',
        brand: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> List[OFFProduct]:
        """
        Search for products.
        
        Args:
            query: Search terms
            country: Country filter (default: bulgaria)
            brand: Brand filter
            category: Category filter
            page: Page number (1-indexed)
            page_size: Results per page (max 100)
            
        Returns:
            List of OFFProduct objects
        """
        self._rate_limit()
        self.stats['requests'] += 1
        
        params = {
            'json': '1',
            'page': page,
            'page_size': min(page_size, 100),
            'fields': ','.join(self.DEFAULT_FIELDS),
        }
        
        if query:
            params['search_terms'] = query
        if country:
            params['countries_tags_en'] = country
        if brand:
            params['brands_tags'] = brand
        if category:
            params['categories_tags'] = category
        
        try:
            response = self.session.get(SEARCH_URL, params=params, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                products = [OFFProduct.from_api(p) for p in data.get('products', [])]
                self.stats['products_found'] += len(products)
                return products
            
            return []
            
        except Exception as e:
            logger.error(f"Error searching OFF: {e}")
            self.stats['errors'] += 1
            return []
    
    def get_bulgarian_products(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[List[OFFProduct], int]:
        """
        Get Bulgarian products.
        
        Returns:
            Tuple of (products, total_count)
        """
        self._rate_limit()
        self.stats['requests'] += 1
        
        url = f"{BASE_URL}/search"
        params = {
            'countries_tags_en': 'bulgaria',
            'page': page,
            'page_size': min(page_size, 100),
            'fields': ','.join(self.DEFAULT_FIELDS),
        }
        
        try:
            response = self.session.get(url, params=params, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                products = [OFFProduct.from_api(p) for p in data.get('products', [])]
                total = data.get('count', 0)
                self.stats['products_found'] += len(products)
                return products, total
            
            return [], 0
            
        except Exception as e:
            logger.error(f"Error fetching Bulgarian products: {e}")
            self.stats['errors'] += 1
            return [], 0
    
    def get_stats(self) -> Dict:
        """Get client statistics"""
        return self.stats.copy()


def main():
    """Test the client"""
    logging.basicConfig(level=logging.INFO)
    
    client = OpenFoodFactsClient()
    
    print("=" * 60)
    print("Open Food Facts Client Test")
    print("=" * 60)
    
    # Test 1: Get Bulgarian products
    print("\n1. Fetching Bulgarian products...")
    products, total = client.get_bulgarian_products(page=1, page_size=5)
    print(f"   Total Bulgarian products: {total:,}")
    print(f"   Fetched: {len(products)}")
    
    for p in products:
        print(f"   - {p.name} ({p.brands})")
        print(f"     Barcode: {p.barcode}")
        print(f"     Image: {'Yes' if p.image_url else 'No'}")
    
    # Test 2: Search by name
    print("\n2. Searching for 'мляко'...")
    products = client.search_products(query='мляко', country='bulgaria', page_size=3)
    print(f"   Found: {len(products)}")
    
    for p in products:
        print(f"   - {p.name} ({p.brands})")
    
    # Test 3: Get by barcode
    print("\n3. Getting product by barcode (3800748001317)...")
    product = client.get_product_by_barcode('3800748001317')
    if product:
        print(f"   Found: {product.name}")
        print(f"   Brand: {product.brands}")
        print(f"   Image: {product.image_url}")
    else:
        print("   Not found")
    
    print(f"\nStats: {client.get_stats()}")


if __name__ == "__main__":
    main()
