# Product Matching Pipeline

## Overview

The matching pipeline connects Bulgarian store products (Kaufland, Lidl, Billa) to OpenFoodFacts (OFF) entries, enabling:
- Nutritional data enrichment
- Cross-store price comparison via shared barcodes
- Product standardization

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Store Products │───▶│ Matching Pipeline │───▶│ OFF Products    │
│  (Cyrillic)     │    │                  │    │ (14,853 items)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼         ▼         ▼
              [Barcode]  [Token]   [Fuzzy]
               100%      ~0.6      ~0.5
             confidence  conf      conf
```

## Matching Strategies

### 1. Barcode Match (Highest Priority)
- **Confidence:** 100%
- **Method:** Exact EAN barcode lookup
- **Coverage:** ~7% of products (limited barcode availability)

### 2. Token Match (Primary Strategy)
- **Confidence:** 40-95%
- **Method:** 
  - Tokenize product names
  - Weighted Jaccard similarity (longer tokens = more weight)
  - Brand index lookup for candidate narrowing
  - Token hit bonus from inverted index
- **Coverage:** ~70% of matches

### 3. Fuzzy Match (Fallback)
- **Confidence:** 38-70%
- **Method:** SequenceMatcher ratio on normalized names
- **Coverage:** <1% (last resort)

## Non-Food Filtering

Products are filtered before matching if they contain keywords for:
- Electronics (Philips, Rowenta, TEFAL, etc.)
- Cosmetics (Nivea, Vaseline, Palmolive, etc.)
- Household (cleaning products, detergents)
- Pet food (Friskies, Whiskas, etc.)
- Clothing (CRIVIT, sportswear)
- Garden/Plants
- Tobacco

See `scripts/fast_matching_v2.py` for full keyword list.

## Database Schema

### product_off_matches
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| product_id | INTEGER | FK to products |
| off_product_id | INTEGER | FK to off_products |
| match_type | TEXT | 'barcode', 'token', or 'fuzzy' |
| match_confidence | REAL | 0.0 to 1.0 |
| is_verified | INTEGER | Manual verification flag |
| created_at | TEXT | Timestamp |

### Indices Used
- `off_brand_index.json` - Brand → [barcodes]
- `off_token_index.json` - Token → [barcodes]

## Current Performance

| Metric | Value |
|--------|-------|
| Total store products | 4,356 |
| Non-food filtered | 912 (21%) |
| Food products | 3,444 |
| Matched | 2,728 (79.4%) |
| Cross-store links | 179 OFF products |

### Match Breakdown
- Barcode: 288 (100% confidence)
- Token: 2,428 (~60-95% confidence)
- Fuzzy: 19 (~40-60% confidence)

## Cross-Store Matching

Products from different stores can be linked via shared OFF barcode:

```sql
-- Find same products across stores
SELECT off_product_id, GROUP_CONCAT(DISTINCT store_name)
FROM product_off_matches pom
JOIN products p ON pom.product_id = p.id
JOIN store_products sp ON sp.product_id = p.id
JOIN stores s ON sp.store_id = s.id
GROUP BY off_product_id
HAVING COUNT(DISTINCT s.id) > 1;
```

## Usage

```bash
# Run matching pipeline
cd repo
python3 scripts/fast_matching_v2.py

# Results saved to:
# - data/promobg.db (product_off_matches table)
# - data/pipeline_results.json (statistics)
```

## Known Limitations

1. **Cyrillic→Latin transliteration** not yet implemented
   - Wine names (Пино Гриджо → Pinot Grigio) don't match
   - ~5% potential improvement

2. **Bulgarian local brands** often not in OFF
   - Шеф Месар, Vernada, etc.
   - Cannot be matched without OFF contribution

3. **Low-confidence matches** need manual verification
   - 1,400+ matches at <60% confidence

## Future Improvements

- [ ] Add transliteration layer (P0)
- [ ] Implement embedding-based semantic matching (P1)
- [ ] Category-aware matching (wine→wine, dairy→dairy)
- [ ] Size normalization (500г = 500g = 0.5kg)
- [ ] Contribute Bulgarian products to OFF
