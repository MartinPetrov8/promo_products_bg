import sqlite3
from pathlib import Path
from typing import List
from scrapers.base import BaseScraper, Store, RawProduct

class BillaScraper(BaseScraper):
    
    DB_PATH = Path(__file__).parent.parent.parent / "data" / "promobg.db"
    
    @property
    def store(self) -> Store:
        return Store.BILLA
    
    def health_check(self) -> bool:
        return self.DB_PATH.exists()
    
    def scrape(self) -> List[RawProduct]:
        products = []
        
        if not self.DB_PATH.exists():
            return products
        
        conn = sqlite3.connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("""
            SELECT p.id, p.name, p.brand, sp.image_url, sp.product_url, pr.current_price
            FROM products p
            JOIN store_products sp ON p.id = sp.product_id
            JOIN stores s ON sp.store_id = s.id
            LEFT JOIN prices pr ON pr.store_product_id = sp.id
            WHERE s.name = 'Billa'
        """)
        
        for row in cur.fetchall():
            products.append(RawProduct(
                store=self.store.value,
                sku=str(row['id']),
                raw_name=row['name'] or '',
                brand=row['brand'],
                price_bgn=round(row['current_price'] * 1.9558, 2) if row['current_price'] else None,
                image_url=row['image_url'],
                product_url=row['product_url'],
            ))
        
        conn.close()
        return products
