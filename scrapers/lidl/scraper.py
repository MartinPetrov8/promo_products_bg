import json
import gzip
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Set
from scrapers.base import BaseScraper, Store, RawProduct

class LidlScraper(BaseScraper):
    
    DATA_DIR = Path(__file__).parent.parent.parent / "data"
    SITEMAP_URL = "https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz"
    
    @property
    def store(self) -> Store:
        return Store.LIDL
    
    def health_check(self) -> bool:
        try:
            resp = requests.head("https://www.lidl.bg", timeout=10)
            return resp.status_code < 500
        except:
            return False
    
    def scrape(self) -> List[RawProduct]:
        products = []
        seen: Set[str] = set()
        
        # Load from JSON-LD batch files
        for batch_file in sorted(self.DATA_DIR.glob("lidl_jsonld_batch*.json")):
            with open(batch_file) as f:
                data = json.load(f)
            
            for item in data:
                pid = item.get('product_id')
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                
                products.append(RawProduct(
                    store=self.store.value,
                    sku=pid,
                    raw_name=item.get('name', ''),
                    raw_description=item.get('description', ''),
                    brand=item.get('brand'),
                    price_bgn=item.get('price'),
                    old_price_bgn=item.get('old_price'),
                    discount_pct=item.get('discount_pct'),
                    image_url=item.get('image_url'),
                    product_url=item.get('product_url'),
                ))
        
        # Merge lidl_fresh.json (has more brands)
        fresh_file = self.DATA_DIR / "lidl_fresh.json"
        if fresh_file.exists():
            with open(fresh_file) as f:
                fresh_data = json.load(f)
            
            for item in fresh_data:
                pid = item.get('product_id')
                if not pid:
                    continue
                
                if pid in seen:
                    # Update existing with brand if missing
                    for p in products:
                        if p.sku == pid and not p.brand and item.get('brand'):
                            p.brand = item['brand']
                    continue
                
                seen.add(pid)
                products.append(RawProduct(
                    store=self.store.value,
                    sku=pid,
                    raw_name=item.get('name', ''),
                    raw_description=item.get('description', ''),
                    brand=item.get('brand'),
                    price_bgn=item.get('price'),
                    old_price_bgn=item.get('old_price'),
                    image_url=item.get('image_url'),
                    product_url=item.get('product_url'),
                ))
        
        return products
