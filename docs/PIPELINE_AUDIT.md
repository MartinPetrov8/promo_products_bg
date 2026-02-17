# PromoBG Pipeline Audit
**Date:** 2026-02-17

## Summary

**Bugs found and fixed:**
1. Products appearing in multiple matches got overwritten (83 products affected)
2. Groups claimed stores where products weren't present in export
3. No deduplication when product matches multiple groups

**Before:** 217 groups (129 broken - 59%)
**After:** 91 valid groups (100% have 2+ products in 2+ stores)

## Root Cause

The matching creates pairwise matches, so one product can match multiple products from another store:
- Match 450: K=587 ↔ L=1045 (confidence 1.0)
- Match 474: K=588 ↔ L=1045 (confidence 0.67)

The export code was:
```python
product_to_group[pid] = group_id  # ← OVERWRITE BUG
```

So product 1045 ended up in the later match's group, leaving the earlier group empty.

## Fixes Applied

### Frontend (index.html)
- Changed comparison check from `group.stores.length >= 2` to actual product count
- Added `hasValidComparison()` function
- Clean product names (strip store suffixes)

### Pipeline (pipeline.py)
- Best-confidence-wins deduplication
- Recalculate stores from actual exported products
- Filter invalid groups (< 2 products or < 2 stores)

## Validation

Run after each pipeline execution:
```python
# All groups should have 2+ products in 2+ stores
for gid, g in groups.items():
    products = [p for p in all_products if p['group_id'] == gid]
    stores = set(p['store'] for p in products)
    assert len(products) >= 2
    assert len(stores) >= 2
```
