# PromoBG Scrapers

Python scrapers for Bulgarian supermarket websites.

## Overview

| Scraper | Store | Source URL | Method |
|---------|-------|------------|--------|
| `kaufland_scraper.py` | Kaufland | kaufland.bg | HTML/CSS parsing |
| `lidl_scraper.py` | Lidl | lidl.bg | Embedded JSON |
| `billa_scraper.py` | Billa | ssbbilla.site | HTML tables |

## Requirements

```bash
pip install requests beautifulsoup4 lxml
```

Or use existing Python environment (these are typically pre-installed).

## Usage

### Run Individual Scraper

```bash
cd services/scraper

# Kaufland
python3 scrapers/kaufland_scraper.py
# → Output: kaufland_products.json

# Lidl  
python3 scrapers/lidl_scraper.py
# → Output: lidl_products.json

# Billa
python3 scrapers/billa_scraper.py
# → Output: billa_products.json
```

### Run All Scrapers (Combined)

```bash
python3 combined_scraper.py
# → Output: data/all_products.json
```

## Output Format

Each scraper produces a list of products:

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "name": "Краставици кг",
    "store": "Kaufland",
    "price_eur": 0.89,
    "price_bgn": 1.74,
    "old_price_eur": 1.29,
    "old_price_bgn": 2.52,
    "discount_pct": 31,
    "quantity": "1 кг",
    "category": "Зеленчуци",
    "image_url": "https://...",
    "scraped_at": "2026-02-12T05:30:00Z"
  }
]
```

## Scraper Details

### Kaufland (`kaufland_scraper.py`)

**Source:** `https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html`

**Method:**
1. Fetch HTML page (~4MB, contains all products)
2. Find elements with class `k-product-tile`
3. Extract:
   - Title: `.k-product-tile__title`
   - Subtitle: `.k-product-tile__subtitle`
   - Price: `.k-price-tag__price`
   - Old price: `.k-price-tag__old-price`
   - Discount: `.k-price-tag__discount`

**Notes:**
- Largest product count (~1,200)
- Prices in both EUR and BGN
- Updates weekly (Monday)

---

### Lidl (`lidl_scraper.py`)

**Source:** `https://www.lidl.bg/c/lidl-plus-promotsii/a10039565`

**Method:**
1. Fetch HTML page
2. Decode HTML entities (data is escaped)
3. Split by `"canonicalUrl"` to find product blocks
4. Extract using regex:
   - `"title":"([^"]+)"`
   - `"price":([\d.]+)`
   - `"oldPrice":([\d.]+)`
   - `"priceSecond":([\d.]+)` (BGN)

**Notes:**
- Smaller catalog (~50 weekly promos)
- Data embedded as JSON in HTML
- Lidl Plus exclusive offers

---

### Billa (`billa_scraper.py`)

**Source:** `https://ssbbilla.site/catalog/sedmichna-broshura`

**Method:**
1. Fetch HTML from accessibility site (structured data)
2. Find elements with class `product`
3. Extract:
   - Name: `.actualProduct`
   - Prices: `span.price` + `span.currency`
   - Discount: `.discount`

**Notes:**
- Uses accessibility version (better structured)
- ~280 products
- Some products have multi-buy offers

---

## Adding a New Scraper

### 1. Create scraper file

```python
# services/scraper/scrapers/newstore_scraper.py

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Product:
    name: str
    quantity: Optional[str]
    price_eur: float
    price_bgn: float
    old_price_eur: Optional[float]
    old_price_bgn: Optional[float]
    discount_pct: Optional[int]
    image_url: Optional[str]
    category: str = "NewStore"

def scrape_newstore() -> List[Product]:
    url = "https://newstore.bg/offers"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    resp = requests.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    products = []
    # ... parsing logic ...
    
    return products

if __name__ == "__main__":
    products = scrape_newstore()
    print(f"Found {len(products)} products")
```

### 2. Add to combined scraper

```python
# In combined_scraper.py

from scrapers.newstore_scraper import scrape_newstore

def scrape_all():
    # ... existing code ...
    
    print("Scraping NewStore...")
    try:
        all_products.extend(scrape_newstore())
        print(f"  ✓ NewStore: {len([p for p in all_products if p.store == 'NewStore'])} products")
    except Exception as e:
        print(f"  ✗ NewStore failed: {e}")
```

### 3. Test and verify

```bash
python3 scrapers/newstore_scraper.py
python3 combined_scraper.py
```

## Troubleshooting

### "No products found"
- Check if website structure changed
- Verify CSS selectors are correct
- Check for JavaScript-only content (may need Selenium)

### "Connection timeout"
- Add retry logic
- Check if IP is blocked
- Try with different User-Agent

### "Encoding issues"
- Use `html.unescape()` for HTML entities
- Specify encoding: `resp.encoding = 'utf-8'`

## Scheduling

For automatic updates, add to cron:

```bash
# Update daily at 6 AM
0 6 * * * cd /path/to/promo_products_bg && python3 services/scraper/combined_scraper.py
```

Or use OpenClaw cron job for automated scraping + deployment.
