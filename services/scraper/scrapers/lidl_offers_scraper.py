"""
Lidl.bg Offers Scraper - Uses category pages (not sitemap)
Updated Feb 2026 after Lidl removed sitemap.xml
"""
import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class LidlProduct:
    name: str
    price_eur: Optional[float]
    price_bgn: Optional[float]
    old_price_eur: Optional[float] = None
    old_price_bgn: Optional[float] = None
    discount_pct: Optional[int] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None

class LidlOffersScraper:
    BASE_URL = "https://www.lidl.bg"
    EUR_BGN = 1.9558
    
    # Categories with offers
    CATEGORY_URLS = [
        "/c/aktualni-predlozheniya/s10019920",  # Current offers
        "/c/khrani-i-napitki/s10068374",
        "/c/dom-i-obzavezhdane/s10068371",
        "/c/instrumenti-i-gradina/s10068222",
        "/c/bebe-dete-i-igrachki/s10068225",
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8',
        })
        self.products = []
        self.seen_names = set()
    
    def _delay(self):
        """Gaussian delay for human-like behavior"""
        delay = max(2.0, random.gauss(4.0, 1.5))
        time.sleep(delay)
    
    def _parse_price(self, text: str) -> Optional[float]:
        if not text:
            return None
        match = re.search(r'([\d]+[,.][\d]+)', text.replace(' ', ''))
        if match:
            return float(match.group(1).replace(',', '.'))
        return None
    
    def _extract_from_jsonld(self, soup: BeautifulSoup) -> List[dict]:
        """Extract products from JSON-LD data"""
        products = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'ItemList':
                    for item in data.get('itemListElement', []):
                        if 'item' in item:
                            products.append(item['item'])
                elif data.get('@type') == 'Product':
                    products.append(data)
            except:
                pass
        return products
    
    def _scrape_category(self, url: str, category_name: str = None) -> int:
        """Scrape a single category page"""
        full_url = self.BASE_URL + url if url.startswith('/') else url
        
        try:
            self._delay()
            resp = self.session.get(full_url, timeout=20)
            if resp.status_code != 200:
                print(f"  {url}: Status {resp.status_code}")
                return 0
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            count = 0
            
            # Try JSON-LD first
            jsonld_products = self._extract_from_jsonld(soup)
            for p in jsonld_products:
                name = p.get('name', '')
                if not name or name.lower() in self.seen_names:
                    continue
                
                offers = p.get('offers', {})
                price = self._parse_price(str(offers.get('price', '')))
                
                self.products.append(LidlProduct(
                    name=name,
                    price_eur=price,
                    price_bgn=price * self.EUR_BGN if price else None,
                    image_url=p.get('image'),
                    product_url=p.get('url'),
                    category=category_name,
                    brand=p.get('brand', {}).get('name') if isinstance(p.get('brand'), dict) else p.get('brand'),
                ))
                self.seen_names.add(name.lower())
                count += 1
            
            # Also look for product tiles in HTML
            for tile in soup.select('[class*="product-tile"], [class*="product-item"]'):
                name_el = tile.select_one('[class*="title"], [class*="name"], h3, h4')
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or name.lower() in self.seen_names:
                    continue
                
                price_el = tile.select_one('[class*="price"]')
                price = self._parse_price(price_el.get_text() if price_el else '')
                
                img = tile.select_one('img')
                link = tile.select_one('a[href*="/p/"]')
                
                self.products.append(LidlProduct(
                    name=name,
                    price_eur=price,
                    price_bgn=price * self.EUR_BGN if price else None,
                    image_url=img.get('src') if img else None,
                    product_url=link.get('href') if link else None,
                    category=category_name,
                ))
                self.seen_names.add(name.lower())
                count += 1
            
            return count
            
        except Exception as e:
            print(f"  Error: {e}")
            return 0
    
    def scrape(self) -> List[LidlProduct]:
        """Main scraping method"""
        print("Lidl Offers Scraper (Category-based)")
        print("=" * 50)
        
        # First get all category links from homepage
        try:
            resp = self.session.get(self.BASE_URL, timeout=20)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find offer links (a10... are usually offers)
            offer_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/c/a10' in href:  # Offer pages
                    if href not in offer_links:
                        offer_links.append(href)
            
            print(f"Found {len(offer_links)} offer category links")
            self._delay()
        except Exception as e:
            print(f"Homepage error: {e}")
            offer_links = []
        
        # Scrape offer categories first
        for url in offer_links[:10]:  # Limit to 10 categories
            count = self._scrape_category(url, "offers")
            print(f"  {url}: {count} products")
        
        # Then scrape main categories
        for url in self.CATEGORY_URLS:
            count = self._scrape_category(url, url.split('/')[-2])
            print(f"  {url}: {count} products")
        
        print(f"\nTotal: {len(self.products)} unique products")
        return self.products
    
    def save(self, filepath: str = None):
        if filepath is None:
            filepath = Path(__file__).parent.parent / "data" / "lidl_products.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([asdict(p) for p in self.products], f, ensure_ascii=False, indent=2)
        print(f"Saved to {filepath}")

if __name__ == "__main__":
    scraper = LidlOffersScraper()
    scraper.scrape()
    scraper.save()
