# Frontend Implementation Plan

## Current State
- Static JSON export (`apps/web/data/all_products.json`)
- Simple product cards with price/discount
- No OFF data integration
- No cross-store price comparison

## Goal
Enable cross-store price comparison with OFF nutritional data enrichment.

---

## Data Architecture Options

### Option A: Single Denormalized JSON (Recommended)
**Structure:**
```json
{
  "products": [...],           // 3,235 matched products
  "off_lookup": {...},         // OFF data by barcode
  "cross_store": {...},        // Price comparison groups
  "meta": { "updated_at": "..." }
}
```

**Pros:**
- Single HTTP request
- Works with GitHub Pages (static hosting)
- ~500KB gzipped (acceptable)
- Instant client-side search

**Cons:**
- Full reload on any data change
- Memory usage on mobile (~2-3MB parsed)

### Option B: Split JSON Files
- `products.json` (store products)
- `off_data.json` (OFF lookup)
- `price_groups.json` (cross-store)

**Pros:** Cacheable separately, smaller initial load
**Cons:** Multiple HTTP requests, complexity

### Option C: API Backend
**Pros:** Real-time, pagination, server-side search
**Cons:** Hosting cost, complexity, not needed for ~5K products

**Decision: Option A** — simplest, fits static hosting, data size is manageable.

---

## Data Export Schema

### products.json
```json
{
  "meta": {
    "updated_at": "2026-02-14T13:30:00Z",
    "total_products": 5113,
    "matched_products": 3235,
    "stores": ["Kaufland", "Lidl", "Billa"]
  },
  "products": [
    {
      "id": 123,
      "name": "Мляко прясно 3.6%",
      "store": "Kaufland",
      "price": 1.49,
      "old_price": 1.99,
      "discount_pct": 25,
      "image_url": "https://...",
      "category": "Млечни",
      "off_barcode": "3800123456789",  // Link to OFF
      "group_id": "g_abc123"           // Cross-store group
    }
  ],
  "off": {
    "3800123456789": {
      "name": "Fresh Milk 3.6%",
      "brand": "Млечен завод",
      "nutriscore": "A",
      "ingredients": "мляко, витамин D",
      "categories": "Dairy, Milk"
    }
  },
  "groups": {
    "g_abc123": {
      "off_barcode": "3800123456789",
      "products": [123, 456, 789],     // Product IDs
      "stores": ["Kaufland", "Lidl", "Billa"],
      "min_price": 1.29,
      "max_price": 1.79
    }
  }
}
```

---

## Export Script Design

### scripts/export_frontend_data.py
```python
# Phases:
# 1. Load matched products with OFF data
# 2. Group by OFF barcode for cross-store comparison
# 3. Build lookup structures
# 4. Export to apps/web/data/products.json
```

**Key queries:**
```sql
-- Products with OFF match
SELECT p.*, sp.store_id, pr.current_price, pr.old_price,
       pom.off_product_id, off.barcode as off_barcode
FROM products p
JOIN store_products sp ON p.id = sp.product_id
JOIN prices pr ON sp.id = pr.store_product_id
LEFT JOIN product_off_matches pom ON p.id = pom.product_id
LEFT JOIN off_products off ON pom.off_product_id = off.id

-- Cross-store groups (products in 2+ stores)
SELECT off_product_id, GROUP_CONCAT(product_id)
FROM product_off_matches
GROUP BY off_product_id
HAVING COUNT(DISTINCT product_id) > 1
```

---

## Frontend Features

### Phase 1: OFF Data Display
- Nutriscore badge (A-E colored)
- "View ingredients" expandable
- Brand normalization

### Phase 2: Cross-Store Comparison
- "Compare prices" button on grouped products
- Modal showing same product across stores
- Sort by: price, discount, store

### Phase 3: Enhanced Search
- Search by OFF name (English) + store name (Bulgarian)
- Filter by Nutriscore (A, B, C...)
- Filter by "Has cross-store comparison"

---

## UI Mockups

### Product Card (Updated)
```
┌─────────────────────────┐
│  [Nutriscore A] -25%    │
│  ┌─────────────────┐    │
│  │    [Image]      │    │
│  └─────────────────┘    │
│  Kaufland               │
│  Мляко прясно 3.6%      │
│  1.49€  ̶1̶.̶9̶9̶€̶            │
│  [Compare 3 stores]     │
└─────────────────────────┘
```

### Comparison Modal
```
┌─────────────────────────────────────┐
│  Мляко прясно 3.6%                  │
│  OFF: Fresh Milk • Nutriscore: A    │
├─────────────────────────────────────┤
│  🟡 Kaufland   1.49€  -25%  ⭐BEST  │
│  🔵 Lidl       1.59€  -20%          │
│  🟢 Billa      1.79€  -10%          │
├─────────────────────────────────────┤
│  Save up to 0.30€ (17%)             │
└─────────────────────────────────────┘
```

---

## Implementation Steps

1. **Export Script** (1 hour)
   - Create `scripts/export_frontend_data.py`
   - Generate `apps/web/data/products.json`
   - Add to git, document usage

2. **Frontend: OFF Integration** (1 hour)
   - Update `index.html` to load new schema
   - Add Nutriscore badges
   - Add ingredients tooltip/modal

3. **Frontend: Cross-Store Comparison** (1.5 hours)
   - Group products by `group_id`
   - Add "Compare" button
   - Build comparison modal

4. **Frontend: Enhanced Filters** (0.5 hours)
   - Nutriscore filter
   - "Cross-store only" toggle
   - Search improvements

---

## Performance Considerations

### Data Size Estimate
| Component | Size (uncompressed) | Size (gzip) |
|-----------|---------------------|-------------|
| products (5K) | ~800KB | ~150KB |
| off lookup (3K) | ~400KB | ~80KB |
| groups (10) | ~2KB | ~1KB |
| **Total** | **~1.2MB** | **~230KB** |

Acceptable for mobile — loads in <1s on 3G.

### Client-Side Optimizations
- Lazy render (show 20, load more on scroll)
- Index product names for fast search
- Debounce search input (300ms)

---

## File Changes

### New Files
- `scripts/export_frontend_data.py`
- `apps/web/data/products.json` (replaces `all_products.json`)

### Modified Files
- `apps/web/index.html` (major update)
- `docs/MATCHING_PIPELINE.md` (add export section)
- `README.md` (update quick start)

---

## Open Questions

1. **Unmatched products:** Include in export? (Currently 1,878 products)
   - **Recommendation:** Yes, but mark as `off_barcode: null`

2. **Historical prices:** Include price history?
   - **Recommendation:** No for v1, adds complexity

3. **Auto-refresh:** Cron job for daily export?
   - **Recommendation:** Yes, add GitHub Actions workflow

---

## Next Steps

1. Review this plan (Gemini review)
2. Implement export script
3. Update frontend
4. Test on mobile
5. Deploy to GitHub Pages

---

## Search Results Ranking (Priority Feature)

### Requirement
When displaying search results, **sort by number of store matches (descending)**.

Products available in more stores should appear first, as they offer the best comparison value.

### Example
Search: "кафе" (coffee)

| Rank | Product | Stores | Why First |
|------|---------|--------|-----------|
| 1 | Lavazza Crema | Lidl, Billa, Kaufland | 3 stores = most comparable |
| 2 | Jacobs Kronung | Billa, Kaufland | 2 stores |
| 3 | Tchibo Gold | Lidl | 1 store |

### Implementation
```javascript
// Sort results by store count (descending), then by relevance
results.sort((a, b) => {
    // Primary: number of stores (more = better)
    const storeCountDiff = (b.stores?.length || 1) - (a.stores?.length || 1);
    if (storeCountDiff !== 0) return storeCountDiff;
    
    // Secondary: search relevance score
    return (b.relevance || 0) - (a.relevance || 0);
});
```

### Data Requirements
Each product in `frontend_data.json` needs:
- `stores`: array of store objects with prices
- OR `store_count`: number of stores selling this product

### Status
- [ ] Add `store_count` to export script
- [ ] Implement sort in frontend search
- [ ] Test with multi-store products
