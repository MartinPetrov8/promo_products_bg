import json
import requests
from pathlib import Path
from typing import List
from scrapers.base import BaseScraper, Store, RawProduct

class KauflandScraper(BaseScraper):
    
    DATA_FILE = Path(__file__).parent.parent.parent / "data" / "kaufland_enhanced.json"
    API_URL = "https://www.kaufland.bg/api/offers"
    
    @property
    def store(self) -> Store:
        return Store.KAUFLAND
    
    def health_check(self) -> bool:
        try:
            resp = requests.head("https://www.kaufland.bg", timeout=10)
            return resp.status_code < 500
        except:
            return False
    
    def scrape(self) -> List[RawProduct]:
        products = []
        
        # Load from existing data file for now
        # TODO: Implement live API scraping
        if self.DATA_FILE.exists():
            with open(self.DATA_FILE) as f:
                data = json.load(f)
            
            for item in data:
                products.append(RawProduct(
                    store=self.store.value,
                    sku=item.get('kl_nr') or str(hash(item.get('title', ''))),
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
