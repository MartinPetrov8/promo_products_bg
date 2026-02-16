# QA Cleanup Report - Cross-Store Matching

**Date:** 2026-02-16  
**Status:** ✅ COMPLETE

## Executive Summary

Cross-store matching was **94% garbage**. After QA cleanup:

| Metric | Before | After |
|--------|--------|-------|
| Total Groups | 133 | **4** |
| Valid % | ~6% | **100%** |

## Root Causes

### 1. Lidl Scraper Data Corrupted (CRITICAL)
- 43 groups had prices like **€117-155** for bread/pastries
- This is clearly wrong (should be <€5)
- Likely cause: BGN↔EUR conversion bug OR wrong field parsed
- **Action needed:** Fix Lidl scraper

### 2. Matching Confidence Too Low
- 124 groups had products matched with <70% confidence
- Many at 40-60% confidence - essentially random
- **Action needed:** Raise minimum threshold to 0.75-0.80

### 3. No Product Type Validation
- Pork grouped with lamb
- Whisky grouped with rum
- Chocolate bars grouped with donuts
- **Action needed:** Add product type detection + blocking

### 4. No Brand Validation
- Different brands (Merci, Pergale, Roshen) grouped together
- **Action needed:** Require brand match when detectable

### 5. No Price Sanity Check
- 20x price differences within same "group"
- **Action needed:** Reject groups with >4-5x price ratio

## Valid Groups (4 remaining)

1. **Spinach leaves** - Billa €1.19, Kaufland €2.99
2. **Carrots** - Lidl €0.44, Kaufland €0.45  
3. **Orange juice** - Kaufland €0.84, Lidl €1.53
4. **Горна Баня water** - Kaufland €0.43, Lidl €1.02

## Files Changed

- `docs/data/products.json` - Clean data deployed
- `apps/web/data/products.json` - Same
- `scripts/validate_groups.py` - V1 validator
- `scripts/validate_groups_v2.py` - Strict validator
- `scripts/validate_groups_v3.py` - Final cleanup

## What "Similar Products" Was

The original concept was to group products by shared OpenFoodFacts barcode (same EAN = same product). The problem:
- Matching algorithm had no quality gate
- Any match (even 40% confidence) formed a group
- No validation of product type, brand, or price reasonableness

## Recommendations

### Immediate
1. Keep cross-store groups OFF until matching is fixed
2. The individual store prices are still useful
3. Don't show "compare" feature with bad data

### Short-term (fix matching)
1. Fix Lidl scraper prices
2. Raise confidence threshold to 0.80
3. Add product type blocking
4. Add price ratio check (max 4x)

### Long-term
1. Manual verification UI for matches
2. User feedback ("this is wrong") mechanism
3. Better OFF matching using category filters
