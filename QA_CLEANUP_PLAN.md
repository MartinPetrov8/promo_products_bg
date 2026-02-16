# QA Cleanup Plan - Product Matching

**Created:** 2026-02-16
**Goal:** 100% clean matches - no false positives

## Root Causes Identified

1. **Lidl Price Bug:** 37% of products show €100+ prices (scraper parsing error)
2. **Embedding Threshold 0.65:** Creates matches at 0.68-0.73 confidence (MUHLER→Пура)
3. **No Category Validation:** Kitchen appliances grouped with food
4. **No Price Sanity Check:** €0.04 bread passes validation

## Fix Strategy

1. Delete all matches with confidence < 0.85
2. Filter unrealistic prices (€0.05 < price < €100 for food)
3. Validate category compatibility
4. Rebuild frontend data

## Success Criteria

- Zero groups with >3x price variance
- All matches ≥0.85 confidence  
- Manual review passes 100%
