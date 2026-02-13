# Store Scrapers Architecture

Each store has a unique website structure requiring custom scraping logic.

## Overview

| Store | Data Source | Price Field | BGN Location | Unique Challenges |
|-------|------------|-------------|--------------|-------------------|
| Kaufland | Embedded JSON arrays | `price` (EUR!) | `prices.alternative.formatted.standard` | 44+ offers arrays, 5.8MB page |
| Lidl | JSON-LD + HTML | `price` (EUR!) | HTML `ods-price__value` class | Scheduled products, keyfacts for size |
| Billa | ssbbilla.site mirror | Direct BGN | Direct in HTML | Vue SPA on main site, mirror only option |

## Critical Discovery: EUR vs BGN Prices

**Both Kaufland and Lidl store EUR prices in their `price` JSON field, even though they claim `priceCurrency: "BGN"`!**

The actual BGN prices must be extracted from:
- **Kaufland**: `prices.alternative.formatted.standard` (e.g., "12,38 ЛВ.")
- **Lidl**: HTML element with class `ods-price__value` (e.g., "9.00лв")

## Kaufland Scraper

### Data Source
Single page `https://www.kaufland.bg/aktualni-predlozheniya/oferti.html` contains all offers as embedded JSON arrays.

### Parsing Strategy
```python
# Find all "offers":[] arrays (44+ per page)
for m in re.finditer(r'"offers":\[', html):
    # Parse each as JSON array
    offers = json.loads(array_str)
    for offer in offers:
        kl_nr = offer.get('klNr')  # Product code
        price_bgn = parse_bgn_price(
            offer['prices']['alternative']['formatted']['standard']
        )
```

### Key Fields
| JSON Field | Description |
|------------|-------------|
| `klNr` | Product code (unique identifier) |
| `title` | Usually brand name |
| `subtitle` | Product description |
| `unit` | Size (e.g., "400 г", "кг") |
| `price` | EUR price (DO NOT USE for BGN!) |
| `prices.alternative.formatted.standard` | BGN current price |
| `prices.alternative.formatted.old` | BGN old price |
| `dateFrom` / `dateTo` | Offer validity dates |
| `discount` | Discount percentage |
| `listImage` | Product image URL |

### Files
- `services/scraper/scrapers/kaufland_enhanced_scraper.py`

---

## Lidl Scraper

### Data Source
Individual product pages at `https://www.lidl.bg/p/{slug}/p{sku}`

### Parsing Strategy
1. Extract JSON-LD for structured data (name, description, brand, image)
2. Extract BGN price from HTML (NOT from JSON-LD!)
3. Extract size from keyfacts HTML section
4. Handle scheduled products (availability dates in HTML)

### Key Patterns
```python
# BGN price from HTML
re.search(r'ods-price__value[^>]*>(\d+[,\.]\d{2})\s*(?:лв|ЛВ)', html)

# Size from keyfacts
re.search(r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|l|л)\s*/\s*опаковка', html)

# Scheduled availability
re.search(r'в магазините от (\d{2}\.\d{2}\.?\s*-\s*\d{2}\.\d{2}\.?)', html)
```

### Availability Types
- `IN_STORE` - Currently available
- `SCHEDULED` - Future date range (e.g., "в магазините от 16.02. - 22.02.")
- `SOLD_OUT` - No longer available

### Files
- `services/scraper/scrapers/lidl_product_scraper.py`
- `docs/LIDL_SCRAPING.md`

---

## Billa Scraper

### Data Source
Mirror site `ssbbilla.site` (main billa.bg is Vue SPA, not scrapeable without browser)

### Status
- Basic scraper exists
- Cleaner implemented for name normalization
- ~80% size extraction, 100% price coverage

### Files
- `services/scraper/scrapers/billa_scraper.py`
- `services/matching/billa_cleaner.py`

---

## Common Infrastructure

All scrapers use shared infrastructure from `services/scraper/core/`:

| Module | Purpose |
|--------|---------|
| `session_manager.py` | Connection pooling, cookie persistence |
| `rate_limiter.py` | Per-domain request throttling |
| `circuit_breaker.py` | Failure detection, automatic backoff |
| `retry_handler.py` | Exponential backoff with jitter |

### Usage
```python
from services.scraper.core.session_manager import SessionManager
from services.scraper.core.rate_limiter import DomainRateLimiter

session_manager = SessionManager()
rate_limiter = DomainRateLimiter()

rate_limiter.wait(url)
session = session_manager.get_session(domain)
response = session.get(url, timeout=120)
```

---

## Database Schema

Normalized schema with three main tables:

```
products (canonical product info)
    ↓ 1:N
store_products (store-specific: code, image, package_size)
    ↓ 1:N
prices (price history: current_price, old_price, valid_from/to)
```

### Key Columns
- `prices.currency` - Always 'BGN' for scraped data
- `prices.valid_from` / `valid_to` - Offer duration dates
- `store_products.store_product_code` - Store's internal product ID (klNr, SKU)

---

## Adding a New Store

1. Research the site structure (JSON-LD, embedded JSON, HTML patterns)
2. Create scraper in `services/scraper/scrapers/{store}_scraper.py`
3. Identify where the REAL price is (check for EUR vs BGN!)
4. Create cleaner in `services/matching/{store}_cleaner.py`
5. Document patterns in `docs/{STORE}_SCRAPING.md`
6. Add store to `stores` table with correct ID

---

*Last updated: 2026-02-13*
