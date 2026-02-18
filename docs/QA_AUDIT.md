# PromoBG Frontend QA Audit
**Date:** 2026-02-17
**Auditor:** Cookie

---

## Executive Summary

Found **3 critical issues** that directly impact user experience, plus several medium/low priority improvements.

---

## 🚨 CRITICAL ISSUES

### 1. CRITICAL: "Сравни оферти" Shows Only 1 Product

**Problem:** Users click "Compare offers" button but modal shows only 1 product instead of price comparison across stores.

**Root Cause:** Data integrity issue in `products.json`:
- **217 total groups** defined
- **Only 88 groups** have 2+ products (actual comparisons)
- **90 groups** have only 1 product (show Compare button but nothing to compare)
- **39 groups** have 0 products (orphaned group references)

**Evidence:**
```json
// Group g1 claims 2 stores but only has 1 product in data
{
  "group_id": "g1",
  "product_count": 1,
  "stores": ["Kaufland", "Lidl"]  // Claims both, only Kaufland exists
}
```

**Fix Required:** In the export pipeline, only include groups where:
1. `products.filter(p => p.group_id === groupId).length >= 2`
2. Actual products exist in both claimed stores

**Files to Fix:** `scripts/export_products.py` or `scripts/pipeline.py`

---

### 2. CRITICAL: Product Names Contain Store-Specific Suffixes

**Problem:** Product names display store-specific marketing text instead of clean product names.

**Examples:**
- "Черни маслини Мамут **от свежата витрина**" (Kaufland deli)
- "Бял земел **от нашата пекарна**" (Kaufland bakery)
- "Черни маслини Мамут 101-110* **От деликатесната витрина За 1 кг**" (Billa)
- "Портокали **За 1 кг**" (Billa per-kg)
- "Ананас **1 бр.**" (Billa per-piece)

**Patterns to Strip:**
```javascript
const storePatterns = [
  /от свежата витрина$/i,
  /от нашата пекарна$/i,
  /от деликатесната витрина$/i,
  /За 1 кг$/i,
  /\d+ бр\.?$/i,
  /\d+ г$/i,
  /\d+\*?$/i,  // Billa sizing codes like "101-110*"
];
```

**Fix Options:**
1. Clean names in scraper/pipeline (best)
2. Clean names in frontend `renderProducts()` (quick fix)
3. Store both `name` (original) and `display_name` (cleaned)

---

### 3. HIGH: Cross-Store Filter Shows Wrong Products

**Problem:** "Само за сравнение" checkbox passes products with `group_id` even when group has only 1 product.

**Current Code (line ~250):**
```javascript
if (crossStoreOnly) {
    const group = data.groups[p.group_id];
    if (!group || group.stores.length < 2) return false;
}
```

**Issue:** `group.stores.length` checks the **claimed** stores, not **actual** products with that group_id.

**Fix:**
```javascript
if (crossStoreOnly) {
    const group = data.groups[p.group_id];
    const actualProducts = data.products.filter(x => x.group_id === p.group_id);
    const actualStores = [...new Set(actualProducts.map(x => x.store))];
    if (!group || actualStores.length < 2) return false;
}
```

---

## ⚠️ MEDIUM ISSUES

### 4. MEDIUM: Brand Extraction Errors

Some brands are product descriptors, not actual brands:

| Product | Extracted Brand | Correct Brand |
|---------|-----------------|---------------|
| "играчка плюшена" | "Плюшена" | NO_BRAND |
| "Ананас 1 бр." | "Ананас" | NO_BRAND |
| "Свински бут без кост" | "Свински" | NO_BRAND |
| "ФИЛЕ ОТ ХЕРИНГА" | "ФИЛЕ ОТ ХЕРИНГА" | NO_BRAND |

**Fix:** Improve brand extraction in matching pipeline. Skip single Bulgarian words that are product types.

---

### 5. MEDIUM: Store Filter Count Confusion

**User Report:** "When you select only one store, everything else disappears and the counts are somewhat strange."

**Current Behavior:**
- Clicking "Kaufland" updates ALL store button counts to show only Kaufland-filtered totals
- This is technically correct but confusing

**Expected Behavior:**
- Store button counts should always show total products per store
- Only update when OTHER filters (discount, cross-store) are applied

**Fix:** In `updateFilteredStoreCounts()`, exclude `currentStoreFilter` from recalculating individual store counts.

---

### 6. MEDIUM: Newlines in Product Names

Product names contain `\n` characters that break display:
```
"S POWER Зимна течност за чистачки\nдо -20° С"
"Браво Дебърцини\nот свежата витрина"
```

**Fix:** Replace `\n` with space in display: `p.name.replace(/\n/g, ' ')`

---

## 📋 LOW PRIORITY

### 7. LOW: Meta Stats Incorrect

`meta.cross_store_groups: 217` includes broken groups.

**Should be:** 88 (actual multi-store groups)

---

### 8. LOW: Generic Names Risk False Matches

Very generic canonical names:
- "гъби печурки" (mushrooms)
- "червено зеле" (red cabbage)
- "кори точени" (phyllo dough)

These could match unrelated products. Consider requiring brand match OR higher confidence threshold.

---

## 🛠️ RECOMMENDED FIX ORDER

1. **Fix export pipeline** - Only export groups with 2+ actual products
2. **Clean product names** - Strip store-specific suffixes
3. **Fix cross-store filter** - Check actual product count, not claimed stores
4. **Replace newlines** - `name.replace(/\n/g, ' ')`
5. **Fix brand extraction** - Skip single-word product descriptors

---

## 📊 Data Summary

| Metric | Count |
|--------|-------|
| Total Products | 1,506 |
| Kaufland | 890 |
| Lidl | 339 |
| Billa | 277 |
| Total Groups | 217 |
| **Valid Groups (2+ products)** | **88** |
| Broken Groups (1 product) | 90 |
| Orphan Groups (0 products) | 39 |
| Products with Store Suffixes | ~50+ |

---

*Audit complete. Spawning verification agent for frontend logic review.*
