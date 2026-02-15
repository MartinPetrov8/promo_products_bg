# PromoBG Implementation Roadmap

**Last Updated:** 2026-02-15  
**Current Status:** Phase 1 in progress

---

## Phase 0: COMPLETED ✓

### What We Did
- Analyzed barcode coverage (only 4 products match via barcode)
- Built initial cross-store matching pipeline (3-phase)
- Ran end-to-end matching: 90 → 2,346 matched products (26x improvement)
- Applied standardization fixes: 802 products updated
- Identified data quality issues per store

### Key Findings
| Store | Products | Brand Coverage | Critical Issues |
|-------|----------|----------------|-----------------|
| Kaufland | 3,293 | 68% | Unit field has descriptions |
| Lidl | 1,540 | 37% | HTML in unit field |
| Billa | 831 | 35% (was 9%) | "King оферта -" prefixes |

---

## Phase 1: Standardize Scrapers (IN PROGRESS)

**Goal:** Every scraper outputs consistent StandardProduct schema

### Deliverables
- [x] Apply standardization fixes to existing database (802 products)
- [ ] standardization/schema.py - StandardProduct dataclass
- [ ] standardization/brand_extractor.py - Brand extraction
- [ ] standardization/quantity_parser.py - Bulgarian quantity parsing
- [ ] standardization/name_normalizer.py - Promo prefix stripping
- [ ] scrapers/base.py - Base scraper class
- [ ] Update Lidl scraper (strip HTML)
- [ ] Update Billa scraper (strip prefixes)

---

## Phase 2: Category Classification

**Goal:** Categorize all products using GS1 GPC taxonomy

### Deliverables
- [ ] data/gs1_gpc_taxonomy.json - Category mapping
- [ ] standardization/category_classifier.py - Bulgarian-aware classifier
- [ ] scripts/assign_categories.py - Batch categorization

---

## Phase 3: Improved Matching Pipeline

**Goal:** Increase high-quality matches from 68 to 500+

### Deliverables
- [ ] matching/pipeline.py - Category-based blocking
- [ ] matching/house_brands.py - House brand mapping
- [ ] matching/confidence.py - Confidence tier calculation

---

## Phase 4: Price Normalization & API

**Goal:** Enable meaningful price comparison

### Deliverables
- [ ] standardization/price_normalizer.py
- [ ] api/main.py - FastAPI endpoints
- [ ] Price history tracking

---

## Phase 5: Frontend MVP

**Goal:** Simple, functional UI

### Deliverables
- [ ] "Exact matches" → "Similar products" → "Other sizes" UX
- [ ] Product search with category filtering
- [ ] Price per unit comparison

---

## File Structure

```
repo/
├── standardization/
│   ├── __init__.py
│   ├── schema.py
│   ├── brand_extractor.py
│   ├── quantity_parser.py
│   ├── name_normalizer.py
│   ├── category_classifier.py
│   └── price_normalizer.py
├── matching/
│   ├── __init__.py
│   ├── pipeline.py
│   ├── confidence.py
│   └── house_brands.py
├── scrapers/
│   ├── base.py
│   ├── kaufland.py
│   ├── lidl.py
│   └── billa.py
├── api/
│   ├── main.py
│   └── models.py
└── data/
    ├── promobg.db
    └── gs1_gpc_taxonomy.json
```
