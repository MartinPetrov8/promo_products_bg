"""Kaufland.bg scraper - TODO: implement"""

from .base import BaseScraper
import logging

log = logging.getLogger(__name__)


class KauflandScraper(BaseScraper):
    """Kaufland Bulgaria scraper - placeholder"""
    
    STORE_NAME = "kaufland"
    
    def scrape(self, limit=None):
        log.warning("Kaufland scraper not implemented - using existing data")
        return []
