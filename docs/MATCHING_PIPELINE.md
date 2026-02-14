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
│  (5,113 items)  │    │   (3 phases)     │    │ (14,853 items)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    [Phase 1a]          [Phase 1b]          [Phase 2]
    Token Match      Transliteration       Embeddings
    Barcode/Fuzzy    Cyrillic→Latin        LaBSE
```

## Matching Phases

### Phase 1a: Token & Barcode Matching
- **Barcode Match** (100% confidence): Exact EAN lookup
- **Token Match** (~60-95%): Weighted Jaccard similarity on tokenized names
- **Fuzzy Match** (~40-60%): SequenceMatcher fallback

### Phase 1b: Transliteration Matching
- **Method:** Cyrillic→Latin transliteration of unmatched products
- **Confidence tiers:**
  - `translit_confident` (≥0.85): High confidence
  - `translit_likely` (0.75-0.84): Likely match
  - `translit_low` (0.60-0.74): Lower confidence
- **Result:** +505 additional matches

### Phase 2: Embedding-Based Semantic Matching
- **Model:** LaBSE (Language-agnostic BERT Sentence Embeddings)
- **Method:** Cosine similarity on product name embeddings
- **Threshold:** 0.75 minimum
- **Confidence tiers:**
  - `embedding_confident` (≥0.85): High confidence
  - `embedding_likely` (0.75-0.84): Likely match
- **Result:** +14 additional matches

## Current Performance

| Metric | Value |
|--------|-------|
| Total store products | 5,113 |
| **Matched** | **3,235 (63.3%)** |
| Unmatched | 1,878 |

### Match Breakdown
| Match Type | Count | Confidence Range |
|------------|-------|------------------|
| token | 2,415 | 60-95% |
| translit_low | 433 | 60-74% |
| barcode | 288 | 100% |
| translit_likely | 61 | 75-84% |
| fuzzy | 13 | 40-60% |
| embedding_likely | 13 | 75-84% |
| translit_confident | 11 | ≥85% |
| embedding_confident | 1 | ≥85% |

## Database Schema

### product_off_matches
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| product_id | INTEGER | FK to products |
| off_product_id | INTEGER | FK to off_products |
| match_type | TEXT | 'barcode', 'token', 'fuzzy', 'translit_*', 'embedding_*' |
| match_confidence | REAL | 0.0 to 1.0 |
| is_verified | INTEGER | Manual verification flag |
| created_at | TEXT | Timestamp |

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
# Run full matching pipeline (Phase 1)
python3 scripts/matching_pipeline.py

# Run embedding matching (Phase 2)
python3 scripts/phase2_embeddings_fixed.py

# Results saved to data/promobg.db (product_off_matches table)
```

## Known Limitations

1. **Bulgarian local brands** often not in OFF
   - Шеф Месар, Vernada, etc.
   - Cannot be matched without OFF contribution

2. **Category mismatches** possible
   - No category-aware filtering yet
   - Wine could match non-wine, etc.

3. **Size variations** not normalized
   - 500г ≠ 500g in matching (treated as different tokens)

## Future Improvements

- [ ] Category-aware matching (wine→wine, dairy→dairy)
- [ ] Size normalization (500г = 500g = 0.5kg)
- [ ] Contribute Bulgarian products to OFF
- [ ] Manual verification UI for low-confidence matches
