# Lidl.bg Scraping Strategy

## Data Sources

Lidl product pages contain data in **two locations**:

### 1. JSON-LD (schema.org)
```html
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Product",...}
</script>
```

**Available fields:**
- `sku` - Product ID (e.g., "10050882")
- `name` - Product name
- `description` - HTML description (needs cleaning)
- `image` - Product image URL
- `brand` - Brand object (often empty)
- `offers.price` - ⚠️ **EUR price, NOT BGN!**
- `offers.availability` - InStoreOnly, InStock, OutOfStock

### 2. HTML (rendered content)

**BGN Price** (the real local price):
```html
<div class="ods-price__value">9.00ЛВ.*</div>
```

**Size/Weight** (in keyfacts):
```html
<span>600 g/опаковка</span>
```

## ⚠️ Critical: EUR vs BGN Prices

**JSON-LD contains EUR prices, not BGN!**

| Source | Field | Example | Currency |
|--------|-------|---------|----------|
| JSON-LD | `offers.price` | 4.60 | EUR |
| HTML | `ods-price__value` + ЛВ | 9.00 | **BGN** |

Always extract BGN price from HTML, not JSON-LD!

## Extraction Patterns

### BGN Price (HTML)
```python
# Current price
re.search(r'ods-price__value[^>]*>(\d+[,\.]\d{2})\s*(?:лв|ЛВ)', html)

# Old/strikethrough price
re.search(r'ods-price--strikethrough[^>]*>(\d+[,\.]\d{2})\s*(?:лв|ЛВ)', html)
```

### Size/Weight (HTML)
```python
# Standard sizes: g, kg, ml, l
re.search(r'(\d+(?:[,\.]\d+)?)\s*(g|kg|ml|l|л)\s*/\s*опаковка', html)

# Piece counts
re.search(r'(\d+)\s*бр\.?\s*/\s*опаковка', html)
```

### JSON-LD
```python
pattern = r'<script type="application/ld\+json">(\{"@context":"http://schema\.org","@type":"Product"[^<]+)</script>'
match = re.search(pattern, html)
data = json.loads(match.group(1))
```

## Implementation

See: `services/scraper/scrapers/lidl_product_scraper.py`

### Usage
```python
from services.scraper.scrapers.lidl_product_scraper import LidlProductScraper

scraper = LidlProductScraper()
product = scraper.fetch_product('https://www.lidl.bg/p/.../p10050882')

print(product.price_bgn)  # 9.0 (BGN, correct!)
print(product.price_eur)  # 4.6 (EUR, for reference)
print(product.size_raw)   # "600 g/опаковка"
print(product.size_value) # 600.0
print(product.size_unit)  # "g"
```

### Batch Processing
```python
urls = scraper.get_existing_product_urls()  # From database
products = scraper.scrape_products(urls)
scraper.save_to_db()
```

## Rate Limiting

- Default: 10 requests/minute, 3s minimum delay
- Coffee breaks: 30-60s pause every 50 requests
- Jitter: Random 1-3s added to each request

## Data Quality Results

After running product page scraper on 876 Lidl products:

| Field | Before | After |
|-------|--------|-------|
| Price (BGN) | 8% | **100%** |
| Size | 36% | **~80%** |
| Description | 0% | **100%** |

## Research Notes

- Discovered: 2026-02-13
- JSON-LD price currency confirmed as EUR
- BGN price only available in rendered HTML
- Size in "keyfacts" section, pattern: `X unit/опаковка`
