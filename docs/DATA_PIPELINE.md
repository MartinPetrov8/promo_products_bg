# PromoBG Data Pipeline Documentation

**Last Updated:** 2026-02-17

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                              │
│  │  Lidl    │    │ Kaufland │    │  Billa   │                              │
│  │ Website  │    │  Brochure│    │ Website  │                              │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘                              │
│       │               │               │                                     │
│       ▼               ▼               ▼                                     │
│  ┌──────────────────────────────────────────┐                              │
│  │           SCRAPERS                        │                              │
│  │  • Lidl: JSON-LD from product pages      │                              │
│  │  • Kaufland: OCR from brochure images    │                              │
│  │  • Billa: Website scraping               │                              │
│  └────────────────────┬─────────────────────┘                              │
│                       │                                                     │
│                       ▼                                                     │
│  ┌──────────────────────────────────────────┐                              │
│  │         raw_scrapes/ (JSON files)         │                              │
│  │  • lidl_20260217.json                    │                              │
│  │  • kaufland_20260217.json                │                              │
│  │  • billa_20260217.json                   │                              │
│  └────────────────────┬─────────────────────┘                              │
│                       │                                                     │
│       ┌───────────────┼───────────────┐                                    │
│       │               │               │                                     │
│       ▼               ▼               ▼                                     │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐                              │
│  │  OCR    │    │ daily_   │    │  Brand    │                              │
│  │ Brand   │───▶│ sync.py  │◀───│  Cache    │                              │
│  │ Extract │    │          │    │ .json     │                              │
│  └─────────┘    └────┬─────┘    └───────────┘                              │
│                      │                                                      │
│                      ▼                                                      │
│  ┌──────────────────────────────────────────┐                              │
│  │         promobg.db (SQLite)               │                              │
│  │  • products (name, brand, quantity)       │                              │
│  │  • store_products (per-store links)       │                              │
│  │  • prices (current_price, old_price)      │                              │
│  │  • cross_store_matches (comparisons)      │                              │
│  └────────────────────┬─────────────────────┘                              │
│                       │                                                     │
│                       ▼                                                     │
│  ┌──────────────────────────────────────────┐                              │
│  │        pipeline.py --export               │                              │
│  │  • Validates groups (2+ products/stores)  │                              │
│  │  • Deduplicates (best confidence wins)    │                              │
│  └────────────────────┬─────────────────────┘                              │
│                       │                                                     │
│                       ▼                                                     │
│  ┌──────────────────────────────────────────┐                              │
│  │      docs/data/products.json              │                              │
│  │  → GitHub Pages → promobg.github.io       │                              │
│  └──────────────────────────────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Database Schema

### products
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| name | TEXT | Product name |
| normalized_name | TEXT | Lowercase, cleaned name |
| brand | TEXT | Brand name |
| quantity | REAL | Quantity in base units (g or ml) |
| quantity_unit | TEXT | Unit type: 'g', 'ml', 'pcs' |
| category | TEXT | Product category |

### store_products
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| store_id | INTEGER | FK to stores |
| product_id | INTEGER | FK to products |
| external_id | TEXT | Store's SKU |
| status | TEXT | 'active' or 'delisted' |
| image_url | TEXT | Product image URL |

### prices
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| store_product_id | INTEGER | FK to store_products |
| current_price | REAL | Current price in EUR |
| old_price | REAL | Previous price |
| discount_pct | REAL | Discount percentage |

### cross_store_matches
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| kaufland_product_id | INTEGER | FK to products |
| lidl_product_id | INTEGER | FK to products |
| billa_product_id | INTEGER | FK to products |
| canonical_name | TEXT | Matched product name |
| canonical_brand | TEXT | Matched brand |
| confidence | REAL | Match confidence 0-1 |

## Key Scripts

### pipeline.py
Main orchestrator. Commands:
- `--full` - Scrape + sync + match + export
- `--daily` - Sync + match + export (no scrape)
- `--export` - Export to JSON only
- `--match` - Run matching only

### daily_sync.py
Imports scraped products into database:
- Detects new products
- Tracks price changes
- Updates existing products
- Applies brand cache (OCR-extracted brands)
- Applies quantity extraction

### lidl_ocr_brands.py
Extracts brands from Lidl product images:
- Uses Google Cloud Vision API
- Caches results in `data/brand_cache.json`
- Also extracts quantities from OCR text

### quantity_extractor.py
Parses quantities from text:
- Weight: 100g, 1.5kg → grams
- Volume: 500ml, 1L → milliliters
- Multipacks: 4x100g → 400g

## Data Files

### data/brand_cache.json
```json
{
  "10051120": {
    "brand": "Alesto",
    "ocr_text": "NUTRI-SCORE\nAlesto\nФъстъци\n100 g",
    "source": "ocr",
    "quantity": 100.0,
    "quantity_unit": "g"
  }
}
```

### docs/data/products.json
Frontend data export:
```json
{
  "meta": {"total_products": 1506, "cross_store_groups": 91},
  "products": [...],
  "groups": {...}
}
```

## Matching Logic

### Token Similarity
1. Tokenize product names (remove stopwords, quantities)
2. Calculate Jaccard similarity: `|A ∩ B| / |A ∪ B|`
3. Require minimum common tokens
4. Group by category first (reduce comparisons)

### Validation Rules
1. Groups must have 2+ products
2. Groups must have 2+ different stores
3. Best-confidence-wins when product matches multiple groups

### Known Issues
1. **Different brands can match** - "Верея мляко" vs generic "мляко"
2. **Missing quantities** - Can't compare 1L vs 500ml
3. **Price ratio not checked** - 3x price diff should flag as suspicious

## Running the Pipeline

```bash
# Full pipeline (with scraping)
python scripts/pipeline.py --full

# Daily update (no scraping)
python scripts/pipeline.py --daily

# Export only
python scripts/pipeline.py --export

# Run OCR for Lidl brands
python scripts/lidl_ocr_brands.py --limit 100
```

## Cron Schedule

```cron
# Daily at 6 AM
0 6 * * * /host-workspace/promo_products_bg/scripts/daily_scrape.sh
```

## Product Images

### Source: znamcenite.bg
81 generic grocery product images (no brand logos).

**Pipeline:**
1. Scraped from `https://znamcenite.bg/images/products/`
2. Background removed using `rembg` (u2net model)
3. Resized to max 512px, saved as transparent PNG
4. Stored in `docs/images/products/`

**Mapping:** `data/image_mapping.json`
- `keyword_to_image` — Maps Bulgarian product keywords to image files
- `category_images` — Maps product categories to representative images

**Usage in Frontend:**
The frontend can match product names to images using keyword search:
```javascript
function getProductImage(name) {
    const nameLower = name.toLowerCase();
    for (const [keyword, image] of Object.entries(imageMapping)) {
        if (nameLower.includes(keyword)) {
            return 'images/products/' + image;
        }
    }
    return null; // No match - use store emoji
}
```

### Image Stats
- 81 transparent PNGs
- Total size: ~14MB
- Avg size: ~170KB per image
- Categories: 22 (fruits, vegetables, meat, dairy, beverages, etc.)
