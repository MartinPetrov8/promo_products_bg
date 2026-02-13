# Scraper Refinement Plan

**Date:** 2026-02-13
**Goal:** Extract maximum product attributes from each store for OFF matching

---

## Current Data Quality Issues

| Store | Products | Price | Brand | Size | Description | Category | Barcode |
|-------|----------|-------|-------|------|-------------|----------|---------|
| Billa | 554 | 100% ✅ | 14% | 80% | 0% ❌ | 0% ❌ | 5% |
| Lidl | 876 | 8% ⚠️ | 32% | 36% | 0% ❌ | 82% | 0% |
| Kaufland | 2214 | 51% | 11% | 24% | 0% ❌ | 0% ❌ | 7% |

---

## Phase 1: Deep Website Research (Kimi 2.5)

### 1.1 Kaufland Research
- **Target URL:** https://www.kaufland.bg/aktualni-predlozheniya/oferti.html
- **Modal view:** `?kloffer-articleID={id}` parameter
- **Research tasks:**
  - Inspect modal/overlay HTML structure
  - Find hidden product attributes (EAN, full description, ingredients, origin)
  - Check if there's an API endpoint
  - Document CSS selectors for all data fields

### 1.2 Lidl Research  
- **Target URL:** https://www.lidl.bg/
- **Research tasks:**
  - Find price data source (currently only 8% have prices)
  - Check sitemap vs API vs category pages
  - Inspect product detail modals
  - Find size/quantity in structured format (not HTML)

### 1.3 Billa Research
- **Target URL:** https://ssbbilla.site/ (accessibility version)
- **Research tasks:**
  - Find product descriptions
  - Check for category structure
  - Find any hidden data attributes
  - Verify price accuracy

---

## Phase 2: Scraper Implementation (Minimax 2.5)

For each store (sequential):
1. Implement findings from Kimi research
2. Run scraper with new extraction logic
3. Validate data quality improvement
4. Commit changes

---

## Execution Order

1. ⏳ Spawn Kimi agents for website research (parallel)
2. ⏳ Wait for research reports
3. ⏳ Implement scrapers sequentially with Minimax
4. ⏳ Validate and commit after each

