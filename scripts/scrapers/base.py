"""Base scraper class - all store scrapers inherit from this"""

from abc import ABC, abstractmethod
import random
import time
import requests
import logging

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]


class BaseScraper(ABC):
    """
    Base class for all store scrapers.
    
    All scrapers MUST return products in this format:
    {
        "name": str,           # Product name (required)
        "brand": str | None,   # Brand name
        "price": float | None, # Current price
        "currency": str,       # "EUR" or "BGN"
        "old_price": float | None,
        "image_url": str | None,
        "product_url": str | None,
        "sku": str | None,     # Store's product ID
    }
    """
    
    STORE_NAME = "base"  # Override in subclass
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.7',
        })
        self.stats = {
            'urls_processed': 0,
            'products_found': 0,
            'errors': 0
        }
    
    @abstractmethod
    def scrape(self) -> list:
        """
        Scrape all products from the store.
        Returns list of product dicts in standard format.
        """
        pass
    
    def delay(self, min_sec=1.0, max_sec=3.0):
        """Human-like delay between requests"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def coffee_break(self):
        """Longer pause every N requests to avoid rate limiting"""
        pause = random.uniform(10, 20)
        log.info(f"Coffee break: {pause:.1f}s")
        time.sleep(pause)
    
    def rotate_user_agent(self):
        """Rotate user agent randomly"""
        self.session.headers['User-Agent'] = random.choice(USER_AGENTS)
    
    def fetch(self, url, **kwargs):
        """Fetch URL with error handling"""
        try:
            self.stats['urls_processed'] += 1
            response = self.session.get(url, timeout=20, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            log.warning(f"Error fetching {url}: {e}")
            self.stats['errors'] += 1
            return None
