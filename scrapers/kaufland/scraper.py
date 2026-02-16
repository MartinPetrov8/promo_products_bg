import json
import requests
import logging
from pathlib import Path
from typing import List
from scrapers.base import BaseScraper, Store, RawProduct

logger = logging.getLogger(__name__)

class KauflandScraper(BaseScraper):
    
    DATA_FILE = Path(__file__).parent.parent.parent / "data" / "kaufland_enhanced.json"
    API_URL = "https://www.kaufland.bg"
    
    @property
    def store(self) -> Store:
        return Store.KAUFLAND
    
    def health_check(self) -> bool:
        try:
            resp = requests.head(self.API_URL, timeout=10)
            return resp.status_code < 500
        except Exception as e:
            logger.error(f"Kaufland health check failed: {e}")
            return False
    
    def scrape(self) -> List[RawProduct]:
        products = []
        
        if not self.DATA_FILE.exists():
            logger.warning(f"Data file not found: {self.DATA_FILE}")
            return products
        
        with open(self.DATA_FILE) as f:
            data = json.load(f)
        
        for item in data:
            # Use deterministic SKU
            sku = item.get('kl_nr')
            if not sku:
                sku = RawProduct.generate_sku(item.get('title', ''))
            
            products.append(RawProduct(
                store=self.store.value,
                sku=str(sku),
                raw_name=item.get('title', ''),
                raw_subtitle=item.get('subtitle', ''),
                raw_description=item.get('description', ''),
                brand=item.get('brand'),
                price_bgn=item.get('price_bgn'),
                old_price_bgn=item.get('old_price_bgn'),
                image_url=item.get('image_url'),
                product_url=item.get('url'),
            ))
        
        return products
