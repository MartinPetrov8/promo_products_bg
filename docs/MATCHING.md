# Cross-Store Matching Algorithm

## Overview

Finds same/similar products across Kaufland, Lidl, and Billa to compare prices.

## Matching Pipeline

```
products_clean.json → group by category → compare pairs → filter → matches
```

## Matching Hierarchy

### 1. Brand + Name (if both have brand)
- Brand similarity ≥ 85%
- Name similarity ≥ 55%
- Score = 0.3 × brand_sim + 0.7 × name_sim

### 2. Name Only (fallback)
- Name similarity ≥ 65%
- Score = name_sim

## Comparability Rules

### Size Indicators (XXL, семейна, etc.)
- **CANNOT compare** if one has size indicator, other doesn't
- **Can compare** if both have same indicator(s)
- Reason: "Портокали XXL" might be 3kg bag vs "Портокали" at 1kg price

```python
SIZE_INDICATORS = ['xxl', 'xl', 'семейна', 'семеен', 'голям', 
                   'малък', 'мини', 'макси', 'джъмбо', 'jumbo', 'фамилия']
```

### Quantity Rules

| Scenario | "Други" category | Categorized products |
|----------|------------------|----------------------|
| Both have qty, match (±20%) | ✅ Compare | ✅ Compare |
| Both have qty, mismatch | ❌ Reject | ❌ Reject |
| Both have no qty | ✅ Compare | ✅ Compare |
| One has qty, one doesn't | ❌ Reject | ✅ Compare* |

*Categorized products: category confirms product type, so we allow comparison even with missing quantity data.

### Per-kg Products
- Products priced per kg (fruits, vegetables, meat) are always comparable
- Detection: "за 1 кг", "на кг", unit="kg" with value=1

### Price Sanity Check
- Max 150% price difference
- Filters obvious mismatches (e.g., single item vs bulk pack)

## Known Limitations

1. **Lidl missing quantities**: JSON-LD doesn't include size/weight
   - Matches "Кисело мляко БДС" (Lidl, no qty) vs Billa (400g)
   - Price comparison not perfectly fair

2. **Brand matching rarely triggers**: Different stores carry different brands
   - Dairy: Верея (Billa) vs Ида (Lidl) vs different private labels
   - Result: Most matches are "name_only"

3. **Category fragmentation**: Some products miscategorized
   - "Други" category has flowers, fish, vegetables mixed

## Output Format

```json
{
  "product": "Кисело мляко БДС",
  "category": "Млечни продукти",
  "stores": {
    "Lidl": {"price": 0.69, "sku": "...", "quantity": ""},
    "Billa": {"price": 1.55, "sku": "...", "quantity": "400g"}
  },
  "cheaper_store": "Lidl",
  "savings_pct": 56,
  "similarity": 0.78,
  "match_method": "name_only"
}
```

## Statistics (2026-02-16)

| Metric | Value |
|--------|-------|
| Comparisons made | 30,591 |
| Matches found | 45 |
| Match rate | 0.15% |

### Rejections
| Reason | Count |
|--------|-------|
| altri_missing_qty | 3,920 |
| size_indicator_mismatch | 1,875 |
| different_units | 468 |
| qty_mismatch | 215 |

### Store Wins
| Store | Wins | % |
|-------|------|---|
| Lidl | 29 | 64.4% |
| Kaufland | 10 | 22.2% |
| Billa | 6 | 13.3% |

## Future Improvements

1. **EAN/barcode matching**: Would be definitive but requires scraping barcodes
2. **Unit price normalization**: Calculate price/kg or price/L for fair comparison
3. **Fuzzy brand matching**: "Верея" ≈ "Vereia" 
4. **Category cleanup**: Better classification to reduce "Други" size
