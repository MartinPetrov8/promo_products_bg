# PromoBG Architecture

**Last Updated:** 2026-02-15

## System Overview

PromoBG is a Bulgarian grocery price comparison platform that aggregates promotional offers from Kaufland, Lidl, and Billa, normalizes product data, and enables cross-store price comparison.

**Current Metrics:**
- 6,425 total products across 3 stores
- 162 cross-store matches (high quality, 0.92+ confidence)
- 82 matches with valid price comparison data
- 29 product categories

---

## Data Flow

```
┌─────────────┐    ┌────────────────┐    ┌──────────────────┐    ┌─────────────┐
│   Scrapers  │───▶│ Standardization│───▶│ Category Classify│───▶│  Matching   │
│ K/L/B sites │    │ brand/qty/name │    │ 29 GS1 categories│    │ Pipeline v2.4│
└─────────────┘    └────────────────┘    └──────────────────┘    └─────────────┘
                                                                        │
                                                                        ▼
                   ┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐
                   │    API/UI       │◀───│  Price Compare   │◀───│ cross_store │
                   │  compare.html   │    │  82 products     │    │  _matches   │
                   └─────────────────┘    └──────────────────┘    └─────────────┘
```

---

## Core Components

### 1. Standardization Module (`standardization/`)

Normalizes raw scraped data into consistent format:

```python
# Key fields normalized:
- normalized_name: Lowercase, promo prefixes stripped
- brand: Extracted from name or dedicated field
- quantity: Parsed to numeric value
- unit: Normalized (л→l, кг→kg, мл→ml, г→g, бр→pcs)
- category_code: GS1 GPC code
```

**Files:**
- `schema.py` - StandardProduct dataclass
- `brand_extractor.py` - Brand detection
- `quantity_parser.py` - Bulgarian quantity parsing
- `category_classifier.py` - Keyword-based categorization

### 2. Category Taxonomy (`data/categories.json`)

29 simplified GS1 GPC categories for Bulgarian groceries:

| Category | Code | Products |
|----------|------|----------|
| dairy | 10300000 | Milk, cheese, yogurt |
| meat | 10200000 | Fresh meat |
| produce_fruit | 10101500 | Fruits |
| produce_veg | 10101600 | Vegetables |
| beverages_soft | 10504900 | Soft drinks |
| ... | ... | ... |

### 3. Matching Pipeline v2.4 (`matching/pipeline.py`)

Four-phase matching with quality controls:

| Phase | Method | Threshold | Matches |
|-------|--------|-----------|---------|
| 1a | Exact branded | brand + name + qty | 0 |
| 1b | Exact generic | name + qty | 8 |
| 2 | Brand fuzzy (bidirectional) | 0.80 | 52 |
| 3 | Embedding (bidirectional + category) | 0.92 | 102 |

**Key Features:**
- Bidirectional confirmation (both products must be each other's best match)
- Category-mismatch rejection (requires 0.98 if categories differ)
- Quantity/unit validation in exact matching

### 4. Database Schema

```sql
-- Products table
products (
    id, name, normalized_name, brand,
    quantity, unit, category_code, category_name,
    barcode_ean, image_url, ...
)

-- Store-specific data
store_products (
    id, product_id, store_id,
    store_product_code, store_product_url, ...
)

-- Prices (separate table)
prices (
    id, store_product_id,
    current_price, old_price, discount_percent,
    price_per_unit, price_per_unit_base, ...
)

-- Cross-store matches
cross_store_matches (
    id, kaufland_product_id, lidl_product_id, billa_product_id,
    canonical_name, canonical_brand, category_code,
    match_type, confidence, store_count
)
```

---

## Store Data Quality

| Store | Products | Brand Coverage | Quantity Coverage | Issues |
|-------|----------|----------------|-------------------|--------|
| Kaufland | 3,293 | 68% | 39% | Unit field has descriptions |
| Lidl | 1,540 | 37% | 33% | Price scraper bug (10-100x too high) |
| Billa | 831 | 35% | 53% | "King оферта" prefixes |

---

## API & Frontend

### Static UI (`api/compare.html`)
- 82 products with price comparison
- Best value highlighting (🏆)
- Savings percentage calculation
- Store-colored branding

### API Endpoints (future)
- `GET /matches` - Cross-store matches with prices
- `GET /categories` - Category list with counts
- `GET /stats` - Overall statistics

---

## Known Issues

1. **Lidl price scraper** - Returns prices 10-100x actual value for some products
2. **Quantity parsing** - Only 39% of Kaufland products have quantity extracted
3. **Category coverage** - 53% of products fall into "other" (non-food items, flowers, etc.)

---

## Future Improvements

1. Fix Lidl price scraper
2. Add more stores (T-Market, Fantastico)
3. Daily scraping cron
4. Mobile PWA version
5. User accounts + shopping lists
