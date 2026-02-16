# Billa Scraper Documentation

## Source
- **URL:** https://ssbbilla.site
- **Type:** Accessibility version of Billa Bulgaria website
- **Catalog pages:** Weekly brochure, upcoming brochure

## Scraper Location
`scrapers/billa/scraper.py`

## Data Quality
| Metric | Value |
|--------|-------|
| Total products | ~500 |
| With brand | 80.9% |
| With old_price | 43.4% |
| Price coverage | 100% |

## How It Works

### 1. Page Structure
ssbbilla.site displays promotional brochure pages with structured HTML:

```html
<div class="product">
  <span class="actualProduct">Product Name</span>
  <span class="price">3.99</span>
  <span class="currency">€</span>
  <span class="price">2.49</span>  <!-- promo price -->
  <span class="currency">€</span>
  <span class="discount">-38%</span>
</div>
```

### 2. Price Extraction
- Collects all `.price` elements with corresponding `.currency`
- Separates EUR (€) and BGN (лв) prices
- **Sorts prices to ensure old > current** (higher = old price)
- Converts EUR to BGN using fixed rate (1.95583)

### 3. Name Cleaning
Removes promotional prefixes:
- `King оферта - Само с Billa Card -`
- `King оферта - Супер цена -`
- `Супер цена -`

### 4. Deduplication
- Products appear on multiple catalog pages
- Uses `seen_names` set to prevent duplicates

## Catalog URLs
```python
CATALOG_URLS = [
    "https://ssbbilla.site/catalog/sedmichna-broshura",     # Weekly
    "https://ssbbilla.site/catalog/predstoyashta-broshura", # Upcoming
]
```

## Output Schema
```python
RawProduct(
    store='Billa',
    sku='billa_abc123',           # Deterministic hash of cleaned name
    raw_name='Краве сирене 600 г',
    price_bgn=4.89,
    old_price_bgn=6.99,           # Promo: ~43% have this
    image_url='https://...',
)
```

## Known Limitations

1. **No direct product URLs** - Products link to brochure pages, not individual product pages
2. **Seasonal catalogs** - Special catalogs (e.g., "protein selection") may appear/disappear
3. **EUR/BGN dual pricing** - Site shows both, we normalize to BGN

## Validation
- Minimum 50 products threshold
- Must have >50% price coverage
- Discount range validated (1-70%)

## Sample Output
```
Свински врат без кост               | 6.98лв (was 16.00) | -56%
Портокали                           | 1.55лв (was 2.99)  | -48%
Lavazza Мляно кафе Crema e Gusto    | 18.17лв (was 0.00) | -
```

## Last Updated
2026-02-16
