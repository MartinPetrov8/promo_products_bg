#!/usr/bin/env python3
"""
Kaufland.bg Enhanced Scraper - With Product Detail Extraction

Extracts detailed product data by:
1. Scraping main offers page for product list + articleIDs
2. Fetching detail modal for each product via kloffer-articleID parameter
3. Parsing deep divs for name, brand, size, full description

Uses hardened scraper infrastructure.
"""

import re
import json
import time
import logging
import random
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Set, Tuple
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

# Infrastructure imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.scraper.core.session_manager import SessionManager, SessionConfig
from services.scraper.core.rate_limiter import DomainRateLimiter
from services.scraper.core.circuit_breaker import CircuitBreaker
from services.scraper.core.retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)


@dataclass
class KauflandProduct:
    """Enhanced product data from Kaufland with detailed attributes"""
    # Basic info
    name: str
    subtitle: Optional[str]          # Short description from tile
    detail_description: Optional[str] # Full description from modal
    
    # Attributes extracted from descriptions
    brand: Optional[str] = None
    size_value: Optional[float] = None
    size_unit: Optional[str] = None
    fat_content: Optional[str] = None
    
    # Pricing
    price_eur: Optional[float] = None
    price_bgn: Optional[float] = None
    old_price_eur: Optional[float] = None
    old_price_bgn: Optional[float] = None
    discount_pct: Optional[int] = None
    
    # Media & IDs
    image_url: Optional[str] = None
    article_id: Optional[str] = None    # kloffer-articleID
    kl_nr: Optional[str] = None         # Internal Kaufland number
    category: Optional[str] = None
    product_url: Optional[str] = None
    
    # Metadata
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class KauflandEnhancedScraper:
    """
    Enhanced Kaufland scraper with detail modal fetching.
    """
    
    DOMAIN = "kaufland.bg"
    BASE_URL = "https://www.kaufland.bg"
    
    def __init__(self):
        # Infrastructure
        self.session_manager = SessionManager(
            config=SessionConfig(
                max_requests=25,
                max_age_seconds=600,
            )
        )
        self.rate_limiter = DomainRateLimiter()
        self.circuit_breaker = CircuitBreaker(
            name=self.DOMAIN,
            failure_threshold=5,
            recovery_timeout=120,
        )
        self.retry_handler = RetryHandler(
            config=RetryConfig(
                max_attempts=3,
                base_delay=4.0,
                max_delay=60.0,
            )
        )
        
        self.stats = {
            'tiles_scraped': 0,
            'details_fetched': 0,
            'products_enhanced': 0,
            'failures': 0,
        }
    
    def _extract_article_id(self, tile_html: str) -> Optional[str]:
        """Extract kloffer-articleID from product tile HTML"""
        # Look for data attributes or URL patterns
        # Pattern 1: data-kloffer-id or similar
        match = re.search(r'data-[\w-]*(?:article|offer)["\']?[=:]\s*["\']?(\d+)', tile_html, re.I)
        if match:
            return match.group(1)
        
        # Pattern 2: in onclick handlers
        match = re.search(r'articleID[=:](\d+)', tile_html, re.I)
        if match:
            return match.group(1)
        
        # Pattern 3: klNr in JSON data
        match = re.search(r'"klNr":"(\d+)"', tile_html)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_category_from_url(self, url: str) -> Optional[str]:
        """Extract category name from offer page URL"""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'kloffer-category' in params:
                cat = params['kloffer-category'][0]
                # Decode URL encoding and clean
                return cat.split('_')[-1] if '_' in cat else cat
        except:
            pass
        return None
    
    def _parse_size(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract size value and unit from text"""
        if not text:
            return None, None
        
        text_lower = text.lower()
        
        # Pattern: "X г", "X кг", "X мл", "X л"
        # Also handle "Ø9 см" for plants
        patterns = [
            (r'(\d+[.,]?\d*)\s*(кг|kg)\b', 'kg'),
            (r'(\d+[.,]?\d*)\s*(г|гр|g)\b', 'g'),
            (r'(\d+[.,]?\d*)\s*(л|l)\b', 'l'),
            (r'(\d+[.,]?\d*)\s*(мл|ml)\b', 'ml'),
            (r'[Øø](\d+[.,]?\d*)\s*(см|cm)\b', 'cm'),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    value = float(match.group(1).replace(',', '.'))
                    # Convert kg to g, l to ml for consistency
                    if unit == 'kg':
                        return value * 1000, 'g'
                    elif unit == 'l':
                        return value * 1000, 'ml'
                    return value, unit
                except ValueError:
                    continue
        
        return None, None
    
    def _extract_brand(self, text: str) -> Optional[str]:
        """Extract brand from product name or description"""
        if not text:
            return None
        
        text_lower = text.lower()
        
        brands = [
            ('k-classic', 'K-Classic'),
            ('k classic', 'K-Classic'),
            ('clever', 'Clever'),
            ('milka', 'Milka'),
            ('nescafe', 'Nescafe'),
            ('jacobs', 'Jacobs'),
            ('lavazza', 'Lavazza'),
            ('coca-cola', 'Coca-Cola'),
            ('coca cola', 'Coca-Cola'),
            ('pepsi', 'Pepsi'),
            ('nestle', 'Nestle'),
            ('ferrero', 'Ferrero'),
            ('kinder', 'Kinder'),
            ('lindt', 'Lindt'),
            ('milka', 'Milka'),
            ('haribo', 'Haribo'),
            ('nutella', 'Nutella'),
            ('pringles', 'Pringles'),
            ('lays', 'Lay\'s'),
            ('doritos', 'Doritos'),
            ('red bull', 'Red Bull'),
            ('heineken', 'Heineken'),
            ('pampers', 'Pampers'),
            ('ariel', 'Ariel'),
            ('lenor', 'Lenor'),
            ('persil', 'Persil'),
            ('finish', 'Finish'),
        ]
        
        for pattern, brand_name in brands:
            if pattern in text_lower:
                return brand_name
        
        return None
    
    def _fetch_product_detail(self, article_id: str, category: Optional[str] = None) -> Optional[Dict]:
        """Fetch detailed product info via kloffer-articleID parameter"""
        if not article_id:
            return None
        
        # Build detail URL
        params = {
            'kloffer-week': 'current',
            'kloffer-articleID': article_id,
        }
        if category:
            params['kloffer-category'] = category
        
        url = f"{self.BASE_URL}/aktualni-predlozheniya/oferti.html?{urlencode(params)}"
        
        # Rate limit
        self.rate_limiter.wait(url)
        
        if self.circuit_breaker.is_open:
            logger.warning(f"Circuit breaker OPEN")
            return None
        
        session = self.session_manager.get_session(self.DOMAIN)
        
        try:
            response = session.get(url, timeout=30)
            
            if response.status_code == 200:
                self.circuit_breaker._on_success()
                self.rate_limiter.report_success(url)
                self.stats['details_fetched'] += 1
                
                # Parse detail data from HTML
                return self._parse_detail_html(response.text)
            else:
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                return None
                
        except Exception as e:
            logger.error(f"Detail fetch failed: {e}")
            self.circuit_breaker._on_failure()
            return None
    
    def _parse_detail_html(self, html: str) -> Dict:
        """Extract detailed product info from HTML"""
        result = {
            'title': None,
            'subtitle': None,
            'detail_description': None,
            'brand': None,
            'kl_nr': None,
        }
        
        # Look for embedded JSON data
        # Pattern 1: Direct JSON in script tags
        json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                # Navigate to offer data
                offers = data.get('offer', {}).get('offers', [])
                if offers:
                    offer = offers[0]
                    result['title'] = offer.get('title')
                    result['subtitle'] = offer.get('subtitle')
                    result['detail_description'] = offer.get('detailDescription')
                    result['kl_nr'] = offer.get('klNr')
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Pattern 2: Individual data attributes
        if not result['title']:
            title_match = re.search(r'"title":"([^"]+)"', html)
            if title_match:
                result['title'] = title_match.group(1)
        
        if not result['subtitle']:
            subtitle_match = re.search(r'"subtitle":"([^"]+)"', html)
            if subtitle_match:
                result['subtitle'] = subtitle_match.group(1)
        
        if not result['detail_description']:
            desc_match = re.search(r'"detailDescription":"([^"]+)"', html)
            if desc_match:
                result['detail_description'] = desc_match.group(1).replace('\\n', '\n')
        
        # Extract brand from title
        if result['title']:
            result['brand'] = self._extract_brand(result['title'])
        
        return result
    
    def _parse_offers_page(self, html: str, source_url: str) -> List[KauflandProduct]:
        """Parse products from main offers page with detail fetching"""
        products = []
        category = self._extract_category_from_url(source_url)
        
        # Extract all product data from embedded JSON
        # Look for offer arrays in the page
        json_patterns = [
            r'"offers":\s*(\[.*?\])',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        ]
        
        offers_data = []
        for pattern in json_patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, list):
                        offers_data.extend(data)
                    elif isinstance(data, dict) and 'offer' in data:
                        offers = data.get('offer', {}).get('offers', [])
                        offers_data.extend(offers)
                except json.JSONDecodeError:
                    continue
        
        logger.info(f"Found {len(offers_data)} offers in page data")
        
        # Process each offer
        seen_ids: Set[str] = set()
        
        for offer in offers_data:
            try:
                article_id = offer.get('articleId') or offer.get('klNr')
                if not article_id or article_id in seen_ids:
                    continue
                seen_ids.add(article_id)
                
                # Basic product data
                name = offer.get('title', '')
                if not name:
                    continue
                
                subtitle = offer.get('subtitle')
                detail_desc = offer.get('detailDescription')
                kl_nr = offer.get('klNr')
                
                # Pricing
                price = offer.get('price')
                old_price = offer.get('oldPrice')
                discount = offer.get('discount')
                
                # Alternative price format
                prices = offer.get('prices', {})
                if not price and 'alternative' in prices:
                    price_str = prices['alternative'].get('formatted', {}).get('standard', '')
                    # Parse BGN price from formatted string
                    price_match = re.search(r'([\d.,]+)', price_str.replace(' ', ''))
                    if price_match:
                        price = float(price_match.group(1).replace(',', '.'))
                
                # Image
                image_url = offer.get('listImage') or offer.get('detailImages', [None])[0]
                
                # Size extraction
                size_value, size_unit = None, None
                if subtitle:
                    size_value, size_unit = self._parse_size(subtitle)
                if not size_value and detail_desc:
                    size_value, size_unit = self._parse_size(detail_desc)
                
                # Brand extraction
                brand = self._extract_brand(name)
                if not brand and detail_desc:
                    brand = self._extract_brand(detail_desc)
                
                # Create product
                product = KauflandProduct(
                    name=name,
                    subtitle=subtitle,
                    detail_description=detail_desc,
                    brand=brand,
                    size_value=size_value,
                    size_unit=size_unit,
                    price_eur=None,  # Will calculate from BGN
                    price_bgn=price,
                    old_price_bgn=old_price,
                    discount_pct=discount,
                    image_url=image_url,
                    article_id=str(article_id),
                    kl_nr=kl_nr,
                    category=category,
                )
                
                products.append(product)
                self.stats['products_enhanced'] += 1
                
            except Exception as e:
                logger.warning(f"Failed to parse offer: {e}")
                continue
        
        return products
    
    def scrape_offers_page(self, url: str) -> List[KauflandProduct]:
        """Scrape a single offers page with full details"""
        logger.info(f"Scraping: {url}")
        
        # Rate limit
        self.rate_limiter.wait(url)
        
        if self.circuit_breaker.is_open:
            logger.warning(f"Circuit breaker OPEN for {self.DOMAIN}")
            return []
        
        session = self.session_manager.get_session(self.DOMAIN)
        
        try:
            response = session.get(url, timeout=30)
            
            if response.status_code == 200:
                self.circuit_breaker._on_success()
                self.rate_limiter.report_success(url)
                
                products = self._parse_offers_page(response.text, url)
                logger.info(f"Scraped {len(products)} products from {url}")
                return products
            else:
                self.circuit_breaker._on_failure()
                self.rate_limiter.report_failure(url, response.status_code)
                return []
                
        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            self.circuit_breaker._on_failure()
            return []
    
    def scrape_all(self) -> List[KauflandProduct]:
        """Scrape all offer pages"""
        all_products = []
        
        offer_urls = [
            f"{self.BASE_URL}/aktualni-predlozheniya/oferti.html",
            f"{self.BASE_URL}/aktualni-predlozheniya/ot-ponedelnik.html",
            f"{self.BASE_URL}/aktualni-predlozheniya/ot-sryada.html",
        ]
        
        for url in offer_urls:
            products = self.scrape_offers_page(url)
            all_products.extend(products)
            
            # Delay between pages
            time.sleep(random.uniform(3, 6))
        
        logger.info(f"Total products scraped: {len(all_products)}")
        return all_products
    
    def save_to_json(self, products: List[KauflandProduct], output_path: Optional[Path] = None):
        """Save products to JSON"""
        if output_path is None:
            output_path = Path(__file__).parent.parent / "data" / "kaufland_enhanced.json"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = [asdict(p) for p in products]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(products)} products to {output_path}")
        return output_path


def main():
    """Run the enhanced scraper"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    scraper = KauflandEnhancedScraper()
    products = scraper.scrape_all()
    
    # Save
    scraper.save_to_json(products)
    
    # Stats
    with_size = sum(1 for p in products if p.size_value)
    with_brand = sum(1 for p in products if p.brand)
    with_detail = sum(1 for p in products if p.detail_description)
    
    print(f"\n{'='*60}")
    print(f"KAUFLAND ENHANCED SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Total products: {len(products)}")
    print(f"With size: {with_size} ({100*with_size/max(1,len(products)):.1f}%)")
    print(f"With brand: {with_brand} ({100*with_brand/max(1,len(products)):.1f}%)")
    print(f"With detail description: {with_detail} ({100*with_detail/max(1,len(products)):.1f}%)")


if __name__ == '__main__':
    main()
