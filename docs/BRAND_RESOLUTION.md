# Brand Resolution Strategy

## Problem Statement

Product matching across stores (Kaufland, Lidl, Billa) is limited by missing brand information:
- Store websites show generic names like "Кашкавал от краве мляко" (cow's milk cheese)
- Brands are visible in product images but not in structured data
- OCR extraction works but is expensive (~$0.40/store, ~$1.50/day for all stores)
- Running OCR daily is not sustainable as we scale to more stores

## Solution: Brand Knowledge Base with Incremental OCR

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BRAND RESOLUTION PIPELINE                 │
├─────────────────────────────────────────────────────────────┤
│  Priority 1: Name Pattern Match                              │
│  Priority 2: House Brand Detection                           │
│  Priority 3: Image Hash Cache                                │
│  Priority 4: OCR (last resort)                               │
└─────────────────────────────────────────────────────────────┘
```

### Resolution Steps

#### 1. Name Pattern Match (Free, Instant)
Extract brand from product name using known brand patterns.

```python
# Example patterns
"Милбона Кашкавал" → Milbona
"Кашкавал Милбона" → Milbona  
"MILBONA мляко" → Milbona
```

- Build regex patterns from OCR'd brand names
- Case-insensitive, supports Cyrillic + Latin
- ~60% of products have brand somewhere in name

#### 2. House Brand Detection (Free, Instant)
Each store has known private-label brands.

```python
HOUSE_BRANDS = {
    'Lidl': ['Milbona', 'Pilos', 'Crivit', 'Parkside', 'Kania', 
             'Freshona', 'W5', 'Cien', 'Dulano', 'Tronic', 
             'Solevita', 'Bellarom', 'Sondey', 'Crownfield', 'Floralys'],
    'Kaufland': ['K-Classic', 'K-Bio', 'K-Take It Veggie', 'K-Favourites',
                 'K-Free From', 'K-Budget'],
    'Billa': ['Clever', 'Billa Bio', 'Billa Premium', 'Chef Select']
}
```

- If product name contains house brand → assign it
- Useful for ~30% of store products

#### 3. Image Hash Cache (Free after initial OCR)
Store perceptual hashes of OCR'd product images.

```python
# Table: brand_image_cache
# - image_hash (perceptual hash, 64-bit)
# - brand (extracted brand)
# - confidence (OCR confidence)
# - source_product_id (original product)

# Matching
new_hash = perceptual_hash(new_image)
matches = find_similar_hashes(new_hash, threshold=0.9)
if matches:
    return matches[0].brand
```

- Products often reuse same package photos across weeks
- Handles seasonal re-listings of same products
- Uses pHash (perceptual hash) for robustness

#### 4. OCR Extraction (Last Resort)
Only for truly unknown products.

```python
# Queue for batch processing
if not resolved:
    queue_for_ocr(product_id, image_url)

# Batch OCR at end of day
# Cost: ~$0.002 per image (Google Vision)
# Expected: 5-10 new products/day after initial setup
```

### Database Schema

```sql
-- Brand knowledge base
CREATE TABLE brand_patterns (
    id INTEGER PRIMARY KEY,
    pattern TEXT NOT NULL,          -- regex pattern
    brand TEXT NOT NULL,            -- normalized brand name
    store_id INTEGER,               -- NULL = all stores
    confidence REAL DEFAULT 1.0,
    source TEXT,                    -- 'ocr', 'manual', 'house_brand'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Image hash cache
CREATE TABLE brand_image_cache (
    id INTEGER PRIMARY KEY,
    image_url TEXT NOT NULL,
    image_hash TEXT NOT NULL,       -- perceptual hash
    brand TEXT,
    ocr_text TEXT,                  -- raw OCR output
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast hash lookup
CREATE INDEX idx_image_hash ON brand_image_cache(image_hash);

-- Track which products have been processed
CREATE TABLE products_brand_status (
    product_id INTEGER PRIMARY KEY,
    brand TEXT,
    resolution_method TEXT,         -- 'name_pattern', 'house_brand', 'image_cache', 'ocr'
    resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Cost Analysis

| Phase | Cost | Frequency |
|-------|------|-----------|
| Initial OCR (all stores) | ~$1.50 | One-time |
| Daily OCR (new products only) | ~$0.02-0.05 | Daily |
| Monthly estimate | ~$2-3 | Ongoing |

vs. Full daily OCR: ~$45/month

**Savings: ~95%**

### Implementation Phases

#### Phase 1: Build Pattern Extractor
- Parse 138 Lidl OCR results
- Extract brand name patterns
- Generate regex for each brand

#### Phase 2: House Brand Whitelist
- Compile house brands for each store
- Add to brand_patterns table

#### Phase 3: Image Hash Cache
- Implement perceptual hashing (ImageHash library)
- Store hashes for all OCR'd images
- Build similarity search

#### Phase 4: Resolution Pipeline
- Create `resolve_brand(product)` function
- Integrate into scraper pipeline
- Track resolution stats

#### Phase 5: Incremental OCR Queue
- Queue system for unresolved products
- Batch OCR at configurable intervals
- Auto-update brand_patterns from new OCR

### Usage Example

```python
from brand_resolver import BrandResolver

resolver = BrandResolver(db_path='data/promobg.db')

# Resolve single product
brand = resolver.resolve(
    name="Милбона Кашкавал от краве мляко",
    store="Lidl",
    image_url="https://..."
)
# Returns: {'brand': 'Milbona', 'method': 'name_pattern', 'confidence': 0.95}

# Batch resolve
products = [...]
results = resolver.resolve_batch(products)
unresolved = [p for p in results if not p['brand']]
# Queue unresolved for OCR
resolver.queue_for_ocr(unresolved)
```

### Metrics to Track

- Resolution rate by method (name/house/cache/ocr)
- OCR queue size over time
- Brand coverage per store
- Match accuracy (spot-check)

### Future Enhancements

1. **ML Brand Classifier**: Train on OCR'd images to predict brand from image features
2. **EAN/Barcode Lookup**: Use product barcodes to get brand from Open Food Facts
3. **Cross-store Brand Mapping**: "Milbona" (Lidl) = "K-Classic" (Kaufland) for same supplier
