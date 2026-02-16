# Lidl Scraper Documentation

## Source
- **URL:** https://www.lidl.bg
- **Type:** Sitemap-based product scraping with JSON-LD extraction
- **OCR:** Google Vision for brand extraction from product images

## Scraper Location
`scrapers/lidl/scraper.py`

## Data Quality
| Metric | Value |
|--------|-------|
| Total products | ~388 |
| With brand | 42.5% (via JSON-LD) + OCR cache |
| With old_price | 0% (not in JSON-LD) |
| Price coverage | 100% |

## How It Works

### 1. Sitemap Crawl
Fetches product URLs from Lidl's XML sitemap:
```
https://www.lidl.bg/sitemap.xml
→ https://www.lidl.bg/p/[product-slug]/p[product-id]
```

### 2. Concurrent Fetching
- Uses `ThreadPoolExecutor` with 10 workers
- ~1104 URLs processed in ~2 minutes
- Rate limited to avoid blocks

### 3. JSON-LD Extraction
Each product page contains schema.org JSON-LD:
```html
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "Product Name",
  "brand": {"name": "Brand"},
  "offers": {
    "price": "2.99",
    "priceCurrency": "BGN"
  }
}
</script>
```

**Note:** JSON-LD says "BGN" but prices are actually EUR. We convert using fixed rate.

### 4. Filtering
- **404s:** ~40% of sitemap URLs return 404 (stale sitemap)
- **No price:** ~35% have no price (in-store only items)
- **Valid:** ~25% yield products with prices

### 5. OCR Brand Extraction (One-time)
For products without brand in JSON-LD:
- `scripts/lidl_ocr_brands.py` - Google Vision API
- Reads product images, extracts brand text
- Results cached in `data/brand_cache.json`

## Sitemap Analysis (2026-02-16)
```
Total URLs: 1104
├── 404 errors: 441 (40%)
├── No price: 386 (35%)
└── Valid products: 277 (25%)
```

## Output Schema
```python
RawProduct(
    store='Lidl',
    sku='lidl_abc123',
    raw_name='Масло за готвене 1л',
    price_bgn=3.99,
    old_price_bgn=None,      # Not available from JSON-LD
    brand='Олинеза',         # From JSON-LD or OCR cache
    image_url='https://...',
    product_url='https://...',
)
```

## OCR Pipeline

### Service Account
- Project: `gen-lang-client-0460333336`
- Service account: `vision@gen-lang-client-0460333336.iam.gserviceaccount.com`
- Credentials: `.secrets/google_vision_sa.json`

### Cache Format
`data/brand_cache.json`:
```json
{
  "lidl_abc123": {
    "brand": "Олинеза",
    "raw_ocr": "ОЛИНЕЗА масло за готвене",
    "confidence": 0.95
  }
}
```

### Running OCR
```bash
# One-time batch process (not run daily)
python3 scripts/lidl_ocr_brands.py
```

## Known Limitations

1. **No promo prices** - JSON-LD only has current price
2. **Stale sitemap** - 40% of URLs are 404
3. **EUR labeled as BGN** - Need currency conversion
4. **Brand coverage** - Only ~42% have brand in JSON-LD

## Validation
- Minimum 50 products threshold
- Skip products without price
- Filter in-store-only items

## Sample Output
```
Deluxe Пилешко филе                 | 9.99лв | brand: Deluxe
Масло за готвене 1л                 | 3.99лв | brand: Олинеза (OCR)
Хляб пълнозърнест                   | 1.49лв | brand: -
```

## Last Updated
2026-02-16
