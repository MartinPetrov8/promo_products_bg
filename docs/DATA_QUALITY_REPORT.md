# PromoBG Data Quality Report

**Generated:** 2026-02-17 07:58:37

## Summary


| Metric | Value |
|--------|-------|
| Total products in DB | 1,510 |
| Products with brand | 1,219 (80%) |
| Products with quantity | 0 (0%) |
| Cross-store matches | 217 |
| Valid comparison groups | 91 |

## Brand Cache (OCR)

| Metric | Value |
|--------|-------|
| Total cache entries | 526 |
| Brands extracted | 252 |
| Quantities extracted | 101 |
| OCR failed | 259 |

## Frontend Export

| Metric | Value |
|--------|-------|
| Exported products | 1,506 |
| Valid groups | 91 |

## Products by Store

| Store | Total | With Brand | With Quantity |
|-------|-------|------------|---------------|
| Billa | 277 | 223 (80%) | 0 (0%) |
| Kaufland | 891 | 763 (85%) | 0 (0%) |
| Lidl | 342 | 233 (68%) | 0 (0%) |


## Known Issues

1. **Lidl brands** - Many extracted via OCR, but ~50% OCR failed
2. **Quantities** - Only ~6% of products have quantity data
3. **Matching** - Some false positives (different brands/sizes matched)

## Recommendations

1. Re-run OCR for failed images (check image URL accessibility)
2. Parse quantities from product names (not just OCR)
3. Add brand/quantity requirements to matching
4. Add price ratio sanity check (flag >2x differences)


## Product Images (NEW)

| Metric | Value |
|--------|-------|
| Source | znamcenite.bg |
| Total images | 81 |
| Background removed | 81 (100%) |
| Format | PNG with transparency |
| Total size | ~14MB |
| Keyword mappings | 157 |
| Category mappings | 22 |
