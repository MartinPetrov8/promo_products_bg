# PromoBG Pipeline Audit
**Date:** 2026-02-17
**Auditor:** Cookie

---

## Executive Summary

**Critical bugs found in the data pipeline:**
1. Products appearing in multiple matches get overwritten (83 products affected)
2. Groups claim stores where products aren't present in export
3. No deduplication when product matches multiple groups

**Result:** Frontend shows 217 groups, but only 88 are valid (59% broken)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SCRAPE                                                                     │
│  scripts/scrapers/{store}.py → raw_scrapes/{store}_{date}.json              │
│  Status: ✅ Working (Lidl has scraper, Kaufland/Billa use OCR or manual)   │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SYNC (daily_sync.py)                                                       │
│  Raw JSON → DB (products, store_products, prices, price_history)            │
│  Status: ✅ Working                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  MATCH (pipeline.py run_matching)                                           │
│  Tokenize → Categorize → Pairwise similarity → cross_store_matches DB       │
│  Status: ⚠️ CREATES DUPLICATE MATCHES (same product in multiple groups)    │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  EXPORT (pipeline.py export_frontend)                                       │
│  DB → docs/data/products.json                                               │
│  Status: 🔴 BUG: Later matches overwrite earlier group_id assignments       │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (docs/index.html)                                                 │
│  JavaScript renders products.json                                           │
│  Status: ✅ FIXED (now validates actual product count)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

```
stores (id, name)
  ├── Kaufland (1)
  ├── Lidl (2)
  └── Billa (3)

products (id, name, normalized_name, brand, category)
  └── 1618 total products

store_products (id, store_id, product_id, external_id, status, image_url)
  └── Links products to stores with metadata

prices (id, store_product_id, current_price, old_price, discount_pct)
  └── Current pricing data

cross_store_matches (id, kaufland_product_id, lidl_product_id, billa_product_id, 
                     canonical_name, canonical_brand, confidence, store_count)
  └── 217 matches (many invalid due to duplicates)
```

---

## 🔴 BUG 1: Products in Multiple Matches

**Problem:** 83 products appear in 2+ different matches. When exporting, the `product_to_group` dict gets overwritten:

```python
# Current code in export_frontend():
for i, m in enumerate(matches):
    group_id = f"g{i+1}"
    for store, col in [...]:
        if m[col]:
            product_to_group[m[col]] = group_id  # ← OVERWRITE BUG
```

**Example:**
- Match 450: Kaufland=587, Lidl=1045 → g1
- Match 474: Kaufland=588, Lidl=1045 → g25 ← OVERWRITES product 1045's group!

**Result:** Product 1045 ends up in g25, so g1 only has 1 product.

**Data:**
```
Products appearing in multiple matches: 83
  Product 1045: appears in 2 matches (Плюшена играчка)
  Product 256: appears in 3 matches
  Product 262: appears in 3 matches
  ...
```

---

## 🔴 BUG 2: Match Groups Aren't Transitive

**Problem:** The matching creates separate match records for each pair, not groups.

**Example:**
```
Match 450: K=587 ↔ L=1045  (confidence 1.0)
Match 474: K=588 ↔ L=1045  (confidence 0.67)
```

These should be **one group** containing K:587, K:588, L:1045. Instead, they're two separate matches that fight over L:1045.

---

## 🔴 BUG 3: Orphan Groups in Export

**Problem:** Groups reference product IDs that aren't assigned to them:
- 39 groups have 0 products (group_id wasn't assigned to any product)
- 90 groups have 1 product (the other product was overwritten)

---

## Data Integrity Stats (Current)

| Metric | Value |
|--------|-------|
| Total products in DB | 1,618 |
| Exportable products | 1,506 |
| Cross-store matches | 217 |
| Products in 2+ matches | 83 |
| Valid groups (2+ products) | 88 |
| Broken groups | 129 |

---

## 🛠️ RECOMMENDED FIXES

### Fix 1: Deduplicate Matches Before Export (Quick Fix)

```python
def export_frontend():
    # ... load products and matches ...
    
    # Build product_to_group with BEST match wins
    product_to_group = {}
    product_to_confidence = {}
    
    for i, m in enumerate(matches):
        group_id = f"g{i+1}"
        
        for store, col in [('Kaufland', 'kaufland_product_id'), 
                           ('Lidl', 'lidl_product_id'), 
                           ('Billa', 'billa_product_id')]:
            pid = m[col]
            if pid:
                # Only assign if better confidence or not yet assigned
                current_conf = product_to_confidence.get(pid, 0)
                if m['confidence'] > current_conf:
                    product_to_group[pid] = group_id
                    product_to_confidence[pid] = m['confidence']
```

### Fix 2: Recalculate Group Stores from Actual Products (Required)

```python
def export_frontend():
    # ... assign group_ids to products ...
    
    # Recalculate stores from actual assigned products
    for gid in groups:
        actual_products = [p for p in products if p['group_id'] == gid]
        actual_stores = list(set(p['store'] for p in actual_products))
        groups[gid]['stores'] = actual_stores
        groups[gid]['product_count'] = len(actual_products)
    
    # Remove invalid groups (< 2 products or < 2 stores)
    groups = {gid: g for gid, g in groups.items() 
              if g['product_count'] >= 2 and len(g['stores']) >= 2}
```

### Fix 3: Union-Find for Transitive Grouping (Best Long-Term)

Instead of pairwise matches, use Union-Find to merge all connected products into one group:

```python
class UnionFind:
    def __init__(self):
        self.parent = {}
    
    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py

def run_matching():
    # ... find matches ...
    
    uf = UnionFind()
    for m in matches:
        pids = [m[col] for col in ['kaufland_product_id', 'lidl_product_id', 'billa_product_id'] if m[col]]
        for i in range(1, len(pids)):
            uf.union(pids[0], pids[i])
    
    # Build groups from union-find
    groups = defaultdict(list)
    for pid in all_product_ids:
        groups[uf.find(pid)].append(pid)
```

### Fix 4: Clean Store Suffixes in Cleaner (Pipeline Level)

Add to `config/cleaning.json`:
```json
{
  "strip_suffixes": [
    "от свежата витрина",
    "от нашата пекарна",
    "от деликатесната витрина",
    "За 1 кг"
  ]
}
```

Apply in `daily_sync.py` before saving to DB.

---

## Implementation Priority

1. **[DONE] Frontend fix** - Validates actual product count (pushed to GitHub)
2. **[NEXT] Export recalculation** - Recalculate stores from actual products
3. **[NEXT] Deduplication** - Best-confidence-wins when assigning group_ids
4. **[LATER] Union-Find** - Proper transitive grouping
5. **[LATER] Cleaner integration** - Strip store suffixes at pipeline level

---

## Files to Modify

| File | Change |
|------|--------|
| `scripts/pipeline.py` | Fix `export_frontend()` - recalculate stores, deduplicate |
| `scripts/daily_sync.py` | Add suffix stripping during import |
| `config/cleaning.json` | Add `strip_suffixes` config |
| `scripts/qa_cleanup.py` | Run after export to validate data |

---

## Validation Queries

After fixing, run these checks:

```python
# 1. No product should appear in multiple groups
assert len(product_to_group) == len(set(product_to_group.values()))

# 2. All groups should have 2+ products
for gid, g in groups.items():
    products_in_group = [p for p in products if p['group_id'] == gid]
    assert len(products_in_group) >= 2, f"Group {gid} has {len(products_in_group)} products"

# 3. All groups should have 2+ stores
for gid, g in groups.items():
    products_in_group = [p for p in products if p['group_id'] == gid]
    stores = set(p['store'] for p in products_in_group)
    assert len(stores) >= 2, f"Group {gid} has only {stores}"
```

---

## Next Steps

1. ⏳ Apply Fix 2 (recalculate stores) to `pipeline.py`
2. ⏳ Apply Fix 1 (deduplication) to `pipeline.py`  
3. ⏳ Run `python pipeline.py --export` to regenerate data
4. ⏳ Verify frontend shows only valid groups
5. ⏳ Document changes in CHANGELOG

---

*Audit complete. Ready for implementation.*
