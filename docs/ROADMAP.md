# PromoBG Implementation Roadmap

**Last Updated:** 2026-02-15  
**Current Status:** Phase 4/5 MVP Complete ✓

---

## Phase 0: Data Analysis ✓

- Analyzed barcode coverage (only 4 products match)
- Identified data quality issues per store
- Built initial matching baseline

---

## Phase 1: Standardization ✓

- standardization/schema.py - StandardProduct dataclass
- standardization/brand_extractor.py - Brand extraction
- standardization/quantity_parser.py - Bulgarian quantity parsing
- standardization/processor.py - Batch processing
- Updated 802 products with clean data

---

## Phase 2: Category Classification ✓

- data/categories.json - 29-category taxonomy (GS1 GPC simplified)
- standardization/category_classifier.py - Keyword-based classifier
- Categorized 6,425 products

---

## Phase 3: Matching Pipeline v2.4 ✓

- matching/pipeline.py with 4 phases:
  1. Exact branded (brand + name + quantity)
  2. Exact generic (name + quantity)
  3. Brand fuzzy (bidirectional)
  4. Embedding (bidirectional + category validation)
- 162 high-quality matches @ 0.92+ confidence
- Threshold raised to 0.92, category mismatch rejection

---

## Phase 4/5: Price Comparison MVP ✓

- api/compare.html - Static price comparison page
- api/main.py - FastAPI endpoints (future)
- 82 matches with valid price data
- Best value highlighting + savings %

---

## Known Issues

1. **Lidl price scraper bug** - Some prices are 10-100x too high (e.g., 200 лв for shower gel)
2. **Kaufland quantity parsing** - 39% coverage, needs improvement
3. **Billa "King оферта" prefixes** - Stripped in normalized_name but source data has issues

---

## Next Steps

1. **Fix Lidl scraper** - Price extraction is broken
2. **Improve quantity coverage** - Parse from product names
3. **Add more stores** - T-Market, Fantastico
4. **Daily scraping cron** - Keep prices fresh
5. **Mobile-friendly UI** - PWA version

---

## Current Results

| Metric | Value |
|--------|-------|
| Products | 6,425 |
| Cross-store matches | 162 |
| Matches with prices | 82 |
| Match quality | 0.92-1.00 confidence |
| Categories | 29 |

**Stores:**
- Kaufland: 3,293 products
- Lidl: 1,540 products (price issues)
- Billa: 831 products

## Future Scalability Work

### O(n²) Matching Algorithm
**Status:** Logged for future  
**Impact:** Low at current scale (1.4K products), critical at 10K+  
**Problem:** `cross_store_matcher.py` Phase 2 (brand+fuzzy) and Phase 3 (embedding) use nested loops  
**Solution:** When scaling past 10K products:
1. Use FAISS for approximate nearest neighbor search
2. Pre-compute and cache embeddings in DB
3. Batch processing with chunking
4. Consider async processing queue (Celery)

**Estimated effort:** 1-2 days when needed
