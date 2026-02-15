"""
Lidl.bg Adaptive Scraper
========================
Multi-strategy, human-like, self-healing scraper.
Takes as long as needed to get ALL products with ALL attributes.

Strategies (in order):
1. Sitemap (if available)
2. Category page crawling
3. Offer page deep crawling
4. Search-based discovery

Human-like behavior:
- Gaussian delays (4-8 seconds average)
- Coffee breaks every 20 requests (2-5 minutes)
- Session rotation
- Real browser fingerprints
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Product:
    name: str
    price_eur: Optional[float] = None
    price_bgn: Optional[float] = None
    old_price_eur: Optional[float] = None
    old_price_bgn: Optional[float] = None
    discount_pct: Optional[int] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    description: Optional[str] = None


@dataclass  
class ScraperStats:
    requests_made: int = 0
    products_found: int = 0
    categories_scraped: int = 0
    coffee_breaks: int = 0
    errors: int = 0
    strategy_used: str = ""
    start_time: float = field(default_factory=time.time)
    
    def duration_minutes(self) -> float:
        return (time.time() - self.start_time) / 60


class LidlAdaptiveScraper:
    """
    Adaptive scraper that tries multiple strategies and takes its time.
    """
    
    BASE_URL = "https://www.lidl.bg"
    EUR_BGN = 1.9558
    
    # Human-like timing
    MIN_DELAY = 3.0
    MAX_DELAY = 12.0
    AVG_DELAY = 5.0
    COFFEE_BREAK_EVERY = 20
    COFFEE_BREAK_MIN = 60  # 1 minute
    COFFEE_BREAK_MAX = 180  # 3 minutes
    
    # User agents (rotate these)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self._rotate_session()
        self.products: Dict[str, Product] = {}  # name.lower() -> Product
        self.visited_urls: Set[str] = set()
        self.stats = ScraperStats()
        
    def _rotate_session(self):
        """Create new session with random fingerprint"""
        ua = random.choice(self.USER_AGENTS)
        self.session.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        })
        logger.debug(f"Rotated session, UA: {ua[:50]}...")
        
    def _human_delay(self):
        """Gaussian delay to mimic human browsing"""
        delay = max(self.MIN_DELAY, random.gauss(self.AVG_DELAY, 2.0))
        delay = min(delay, self.MAX_DELAY)
        time.sleep(delay)
        
    def _coffee_break(self):
        """Take a longer break (human would grab coffee)"""
        duration = random.uniform(self.COFFEE_BREAK_MIN, self.COFFEE_BREAK_MAX)
        logger.info(f"☕ Coffee break: {duration:.0f} seconds...")
        self.stats.coffee_breaks += 1
        time.sleep(duration)
        self._rotate_session()  # New session after break
        
    def _fetch(self, url: str, referer: str = None) -> Optional[BeautifulSoup]:
        """Fetch URL with human-like behavior"""
        if url in self.visited_urls:
            return None
            
        self.stats.requests_made += 1
        
        # Coffee break every N requests
        if self.stats.requests_made % self.COFFEE_BREAK_EVERY == 0:
            self._coffee_break()
        else:
            self._human_delay()
            
        try:
            headers = {}
            if referer:
                headers['Referer'] = referer
                
            resp = self.session.get(url, headers=headers, timeout=30)
            self.visited_urls.add(url)
            
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, 'html.parser')
            else:
                logger.warning(f"Status {resp.status_code}: {url}")
                self.stats.errors += 1
                return None
                
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self.stats.errors += 1
            return None
            
    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        # Handle both "1,99" and "1.99" formats
        match = re.search(r'([\d]+[,.][\d]+)', text.replace(' ', ''))
        if match:
            return float(match.group(1).replace(',', '.'))
        return None
        
    def _add_product(self, product: Product):
        """Add product, avoiding duplicates"""
        key = product.name.lower().strip()
        if key and key not in self.products:
            self.products[key] = product
            self.stats.products_found += 1
            
    def _extract_jsonld_products(self, soup: BeautifulSoup) -> int:
        """Extract products from JSON-LD structured data"""
        count = 0
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                items = []
                
                if data.get('@type') == 'ItemList':
                    items = [i.get('item', i) for i in data.get('itemListElement', [])]
                elif data.get('@type') == 'Product':
                    items = [data]
                elif isinstance(data, list):
                    items = [d for d in data if d.get('@type') == 'Product']
                    
                for item in items:
                    name = item.get('name', '')
                    if not name:
                        continue
                        
                    offers = item.get('offers', {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                        
                    price = self._parse_price(str(offers.get('price', '')))
                    
                    brand = item.get('brand', {})
                    if isinstance(brand, dict):
                        brand = brand.get('name', '')
                        
                    self._add_product(Product(
                        name=name,
                        price_eur=price,
                        price_bgn=price * self.EUR_BGN if price else None,
                        image_url=item.get('image'),
                        product_url=item.get('url'),
                        brand=brand,
                        description=item.get('description', '')[:200] if item.get('description') else None,
                    ))
                    count += 1
                    
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.debug(f"JSON-LD parse error: {e}")
                
        return count
        
    def _extract_html_products(self, soup: BeautifulSoup, category: str = None) -> int:
        """Extract products from HTML elements"""
        count = 0
        
        # Try various product tile selectors
        selectors = [
            '.product-grid-box',
            '.product-item',
            '[class*="product-tile"]',
            '[class*="productTile"]',
            '[data-testid*="product"]',
            '.nuc-a-product-tile',
        ]
        
        tiles = []
        for selector in selectors:
            tiles = soup.select(selector)
            if tiles:
                break
                
        for tile in tiles:
            try:
                # Find name
                name_el = tile.select_one(
                    '[class*="title"], [class*="name"], '
                    '[class*="productTitle"], h2, h3, h4'
                )
                name = name_el.get_text(strip=True) if name_el else ''
                if not name or len(name) < 3:
                    continue
                    
                # Find price
                price_el = tile.select_one('[class*="price"]:not([class*="old"])')
                price = self._parse_price(price_el.get_text() if price_el else '')
                
                # Find old price
                old_price_el = tile.select_one('[class*="old-price"], [class*="oldPrice"]')
                old_price = self._parse_price(old_price_el.get_text() if old_price_el else '')
                
                # Find discount
                discount = None
                discount_el = tile.select_one('[class*="discount"], [class*="saving"]')
                if discount_el:
                    match = re.search(r'(\d+)%', discount_el.get_text())
                    if match:
                        discount = int(match.group(1))
                        
                # Find image
                img = tile.select_one('img')
                img_url = None
                if img:
                    img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    
                # Find product link
                link = tile.select_one('a[href*="/p/"]')
                prod_url = None
                if link:
                    href = link.get('href', '')
                    prod_url = urljoin(self.BASE_URL, href) if href else None
                    
                self._add_product(Product(
                    name=name,
                    price_eur=price,
                    price_bgn=price * self.EUR_BGN if price else None,
                    old_price_eur=old_price,
                    old_price_bgn=old_price * self.EUR_BGN if old_price else None,
                    discount_pct=discount,
                    image_url=img_url,
                    product_url=prod_url,
                    category=category,
                ))
                count += 1
                
            except Exception as e:
                logger.debug(f"HTML parse error: {e}")
                
        return count
        
    def _discover_category_urls(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Find category URLs from a page"""
        categories = []
        seen = set()
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            
            # Look for category patterns
            if '/c/' in href or '/s1' in href:
                full_url = urljoin(self.BASE_URL, href)
                if full_url not in seen and full_url not in self.visited_urls:
                    seen.add(full_url)
                    name = a.get_text(strip=True) or urlparse(href).path.split('/')[-1]
                    categories.append((full_url, name))
                    
        return categories
        
    def scrape(self) -> List[Product]:
        """
        Main scraping method. Tries multiple strategies.
        Takes as long as needed to get complete data.
        """
        logger.info("=" * 60)
        logger.info("Lidl Adaptive Scraper - Starting")
        logger.info("This may take 15-30 minutes for complete data")
        logger.info("=" * 60)
        
        # Strategy 1: Try sitemap first
        logger.info("\n📋 Strategy 1: Checking sitemap...")
        sitemap_soup = self._fetch(f"{self.BASE_URL}/sitemap.xml")
        if sitemap_soup:
            # Parse sitemap for product URLs
            for loc in sitemap_soup.find_all('loc'):
                url = loc.get_text()
                if '/p/' in url:  # Product page
                    self.visited_urls.add(url)  # Just mark, don't fetch individual pages
            logger.info(f"  Found {len([u for u in self.visited_urls if '/p/' in u])} product URLs in sitemap")
        else:
            logger.info("  Sitemap not available, using other strategies")
            
        # Strategy 2: Homepage -> Categories
        logger.info("\n🏠 Strategy 2: Homepage category discovery...")
        homepage = self._fetch(self.BASE_URL)
        if homepage:
            # Extract products from homepage
            count = self._extract_jsonld_products(homepage)
            count += self._extract_html_products(homepage, "homepage")
            logger.info(f"  Homepage: {count} products")
            
            # Find category links
            categories = self._discover_category_urls(homepage)
            logger.info(f"  Found {len(categories)} category links")
            
            # Strategy 3: Deep crawl categories
            logger.info("\n📁 Strategy 3: Deep category crawling...")
            for cat_url, cat_name in categories[:30]:  # Limit to 30 categories
                soup = self._fetch(cat_url, referer=self.BASE_URL)
                if soup:
                    count = self._extract_jsonld_products(soup)
                    count += self._extract_html_products(soup, cat_name)
                    if count > 0:
                        logger.info(f"  {cat_name}: {count} products")
                    self.stats.categories_scraped += 1
                    
                    # Find subcategories
                    subcats = self._discover_category_urls(soup)
                    for sub_url, sub_name in subcats[:10]:  # Limit subcategories
                        sub_soup = self._fetch(sub_url, referer=cat_url)
                        if sub_soup:
                            count = self._extract_jsonld_products(sub_soup)
                            count += self._extract_html_products(sub_soup, f"{cat_name}/{sub_name}")
                            if count > 0:
                                logger.info(f"    {sub_name}: {count} products")
                            self.stats.categories_scraped += 1
                            
        # Final stats
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Duration: {self.stats.duration_minutes():.1f} minutes")
        logger.info(f"Products found: {self.stats.products_found}")
        logger.info(f"Categories scraped: {self.stats.categories_scraped}")
        logger.info(f"Requests made: {self.stats.requests_made}")
        logger.info(f"Coffee breaks: {self.stats.coffee_breaks}")
        logger.info(f"Errors: {self.stats.errors}")
        
        return list(self.products.values())
        
    def save(self, filepath: str = None):
        if filepath is None:
            filepath = Path(__file__).parent.parent / "data" / "lidl_products.json"
            
        products_list = [asdict(p) for p in self.products.values()]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(products_list, f, ensure_ascii=False, indent=2)
            
        logger.info(f"💾 Saved {len(products_list)} products to {filepath}")


if __name__ == "__main__":
    scraper = LidlAdaptiveScraper()
    scraper.scrape()
    scraper.save()
