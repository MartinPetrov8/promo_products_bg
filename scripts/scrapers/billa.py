"""Billa.bg scraper - TODO: implement"""

from .base import BaseScraper
import logging

log = logging.getLogger(__name__)


class BillaScraper(BaseScraper):
    """Billa Bulgaria scraper - placeholder"""
    
    STORE_NAME = "billa"
    
    def scrape(self, limit=None):
        log.warning("Billa scraper not implemented - using existing data")
        return []
