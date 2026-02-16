# PromoBG Data Quality & Architecture Overhaul

**Created:** 2026-02-16
**Status:** PLANNING
**Goal:** Clean, consistent, reliable product data across all stores

---

## Current State (Problems)

### Data Quality Issues
| Issue | Count | Impact |
|-------|-------|--------|
| Lidl avg price €37.82 (should be ~€5) | 180 items €100+ | Comparisons broken |
| "| LIDL" suffix in names | 268 items | Matching fails |
| "от нашата витрина" in names | 155 items | Matching fails |
| "различни видове" (various types) | 338 items | Can't match specific products |
| "King оферта" prefix | 29 items | Noise in names |
| Duplicate names | 27 pairs | Confusing UI |
| Non-food mixed with food | 44 items | Category pollution |

### Architecture Issues
1. **No single source of truth** - DBs are empty (0 bytes), JSON files everywhere
2. **Multiple matcher versions** - `cross_store_matcher.py`, `v2.py`, `multi_pass_matcher.py`
3. **No standardization pipeline** - Each store scraped differently
4. **No validation layer** - Garbage goes straight to frontend

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐ │
│  │ SCRAPERS │──▶│ STANDARDIZER │──▶│  VALIDATOR   │──▶│ DATABASE │ │
│  │ K/L/B    │   │              │   │              │   │ (SQLite) │ │
│  └──────────┘   └──────────────┘   └──────────────┘   └──────────┘ │
│                        │                  │                  │      │
│                        ▼                  ▼                  ▼      │
│               ┌──────────────┐   ┌──────────────┐   ┌──────────────┐│
│               │ Name Cleaner │   │ Price Check  │   │ Deduplicator ││
│               │ Brand Extract│   │ Range Valid  │   │ Merge Similar││
│               │ Qty Parser   │   │ Unit Price   │   │              ││
│               └──────────────┘   └──────────────┘   └──────────────┘│
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐ │
│  │   MATCHER    │──▶│   EXPORTER   │──▶│      FRONTEND JSON       │ │
│  │ Cross-Store  │   │              │   │ products.json + groups   │ │
│  └──────────────┘   └──────────────┘   └──────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Standardization Pipeline (Week 1)

### 1.1 Name Cleaner Module
```python
# Clean product names for consistency
def clean_name(name: str, store: str) -> str:
    # Remove store-specific suffixes/prefixes
    name = remove_lidl_suffix(name)      # "Хляб | LIDL" → "Хляб"
    name = remove_kaufland_suffix(name)   # "от нашата витрина" → ""
    name = remove_billa_prefix(name)      # "King оферта - " → ""
    name = remove_variants(name)          # "различни видове" → ""
    
    # Normalize
    name = normalize_whitespace(name)
    name = fix_encoding(name)
    
    return name
```

**Deliverables:**
- [ ] `standardization/name_cleaner.py` - Central name cleaning
- [ ] Unit tests with 50+ edge cases
- [ ] Transformation log for audit

### 1.2 Brand Extractor
```python
# Extract brand from product name
def extract_brand(name: str) -> Optional[str]:
    # Check known brand list first
    for brand in KNOWN_BRANDS:
        if brand.lower() in name.lower():
            return brand
    
    # Heuristic: first capitalized word might be brand
    # "Верея Прясно мляко" → "Верея"
    ...
```

**Deliverables:**
- [ ] `standardization/brand_extractor.py`
- [ ] `data/known_brands.json` - 200+ Bulgarian grocery brands
- [ ] Brand normalization (Coca-Cola = Кока-Кола)

### 1.3 Quantity Parser
```python
# Parse quantity from name or dedicated field
def parse_quantity(text: str) -> Tuple[float, str]:
    # "Мляко 1л" → (1000, "ml")
    # "Хляб 500г" → (500, "g")
    # "Бира 0.5л x 6" → (3000, "ml")
    ...
```

**Deliverables:**
- [ ] `standardization/quantity_parser.py`
- [ ] Handle multi-packs (x4, x6, промопакет)
- [ ] Normalize units (л→ml, кг→g)

### 1.4 Category Classifier
```python
# Classify product into category
def classify(name: str, brand: str = None) -> str:
    # Rule-based first
    if any(kw in name.lower() for kw in DAIRY_KEYWORDS):
        return "dairy"
    
    # Embedding fallback for unknown
    ...
```

**Categories (simplified):**
- `dairy` - Milk, cheese, yogurt
- `meat` - Fresh meat, deli
- `produce` - Fruits, vegetables
- `bakery` - Bread, pastries
- `beverages` - Drinks
- `snacks` - Chips, chocolate
- `household` - Cleaning, personal care
- `nonfood` - Electronics, home goods

---

## Phase 2: Validation Layer (Week 1-2)

### 2.1 Price Validator
```python
def validate_price(product: dict) -> ValidationResult:
    price = product['price']
    category = product['category']
    
    # Category-specific ranges
    ranges = {
        'dairy': (0.30, 15.00),
        'meat': (1.00, 50.00),
        'bakery': (0.20, 10.00),
        'beverages': (0.30, 20.00),
        'household': (0.50, 50.00),
        'nonfood': (1.00, 500.00),
    }
    
    min_p, max_p = ranges.get(category, (0.10, 100.00))
    
    if price < min_p or price > max_p:
        return ValidationResult(
            valid=False,
            reason=f"Price {price} outside range [{min_p}, {max_p}] for {category}"
        )
    
    return ValidationResult(valid=True)
```

### 2.2 Lidl Price Fixer
```python
def fix_lidl_price(product: dict) -> dict:
    """Fix Lidl prices that are 100x too high (stotinki vs leva bug)."""
    if product['store'] != 'Lidl':
        return product
    
    price = product['price']
    category = product['category']
    
    # If food item > €50, likely 100x bug
    if category not in ['nonfood', 'household'] and price > 50:
        product['price'] = price / 100
        product['price_fixed'] = True
    
    return product
```

### 2.3 Deduplicator
```python
def deduplicate(products: List[dict]) -> List[dict]:
    """Merge duplicate products, keep best data."""
    # Group by (store, normalized_name)
    groups = group_by(products, key=lambda p: (p['store'], p['normalized_name']))
    
    result = []
    for key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
        else:
            # Merge: keep lowest price, best image, most complete data
            merged = merge_products(group)
            result.append(merged)
    
    return result
```

---

## Phase 3: Database & Single Source of Truth (Week 2)

### 3.1 Schema
```sql
-- Core tables
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,      -- Cleaned, standardized
    raw_name TEXT NOT NULL,            -- Original from scraper
    brand TEXT,
    category TEXT NOT NULL,
    quantity_value REAL,
    quantity_unit TEXT,
    image_url TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE store_products (
    id INTEGER PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    store TEXT NOT NULL,               -- 'Kaufland', 'Lidl', 'Billa'
    store_sku TEXT,                    -- Store's internal ID
    current_price REAL NOT NULL,
    old_price REAL,
    discount_pct INTEGER,
    unit_price REAL,                   -- Price per kg/L
    unit_price_base TEXT,              -- 'kg' or 'L'
    valid_from DATE,
    valid_until DATE,
    scraped_at TIMESTAMP
);

CREATE TABLE product_matches (
    id INTEGER PRIMARY KEY,
    product_id_1 INTEGER REFERENCES products(id),
    product_id_2 INTEGER REFERENCES products(id),
    match_confidence REAL,
    match_type TEXT,                   -- 'exact', 'brand_name', 'embedding'
    verified BOOLEAN DEFAULT FALSE
);

-- Indexes
CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_store_products_store ON store_products(store);
CREATE INDEX idx_store_products_price ON store_products(current_price);
```

### 3.2 Import Pipeline
```python
def import_products(store: str, raw_data: List[dict]):
    """Import scraped products through full pipeline."""
    for raw in raw_data:
        # 1. Standardize
        clean = standardize(raw)
        
        # 2. Validate
        validation = validate(clean)
        if not validation.valid:
            log_invalid(raw, validation.reason)
            continue
        
        # 3. Deduplicate
        existing = find_existing(clean)
        if existing:
            update_product(existing, clean)
        else:
            create_product(clean)
```

---

## Phase 4: Cross-Store Matching (Week 2-3)

### 4.1 Matching Strategy (Priority Order)

1. **Exact Match** - Same brand + normalized name + quantity
   - Confidence: 1.0
   - Example: "Верея Мляко 3% 1л" = "Верея Мляко 3% 1л"

2. **Brand + Name Match** - Same brand, similar name (>0.85)
   - Confidence: 0.9
   - Example: "Верея Прясно мляко 3%" ≈ "Верея Мляко прясно 3%"

3. **Generic Match** - No brand, very similar name + same category
   - Confidence: 0.75
   - Example: "Портокали" = "Портокали"

4. **Embedding Match** - Semantic similarity >0.92
   - Confidence: 0.7
   - Only as fallback, requires manual verification

### 4.2 Matching Rules
```python
def can_match(p1: dict, p2: dict) -> bool:
    # Must be different stores
    if p1['store'] == p2['store']:
        return False
    
    # Must be same category
    if p1['category'] != p2['category']:
        return False
    
    # Price ratio check
    ratio = max(p1['price'], p2['price']) / min(p1['price'], p2['price'])
    if ratio > 2.5:
        return False
    
    # If both have brands, must match
    if p1['brand'] and p2['brand']:
        if normalize_brand(p1['brand']) != normalize_brand(p2['brand']):
            return False
    
    return True
```

---

## Phase 5: Frontend Export (Week 3)

### 5.1 Export Format
```json
{
  "meta": {
    "updated_at": "ISO timestamp",
    "total_products": 3000,
    "cross_store_matches": 100,
    "stores": ["Kaufland", "Lidl", "Billa"]
  },
  "products": [
    {
      "id": 1,
      "name": "Верея Прясно мляко 3% 1л",  // Clean name
      "brand": "Верея",
      "category": "dairy",
      "store": "Kaufland",
      "price": 1.99,
      "old_price": 2.49,
      "discount_pct": 20,
      "unit_price": 1.99,
      "unit_price_base": "L",
      "image_url": "...",
      "match_group": "mg_abc123"  // If cross-store match exists
    }
  ],
  "match_groups": {
    "mg_abc123": {
      "canonical_name": "Верея Прясно мляко 3% 1л",
      "brand": "Верея",
      "category": "dairy",
      "products": [1, 45, 892],  // Product IDs
      "best_price": {"store": "Lidl", "price": 1.79},
      "price_range": [1.79, 2.19]
    }
  }
}
```

---

## Implementation Order

### Week 1
- [ ] **Day 1-2:** Name cleaner + unit tests
- [ ] **Day 3-4:** Brand extractor + known brands list
- [ ] **Day 5:** Quantity parser
- [ ] **Day 6-7:** Category classifier

### Week 2
- [ ] **Day 1-2:** Price validator + Lidl fixer
- [ ] **Day 3:** Deduplicator
- [ ] **Day 4-5:** Database schema + import pipeline
- [ ] **Day 6-7:** Migration from JSON → SQLite

### Week 3
- [ ] **Day 1-3:** Cross-store matcher v3
- [ ] **Day 4-5:** Frontend export
- [ ] **Day 6-7:** Integration testing + deploy

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Avg Lidl price | €37.82 | €5-10 |
| Products with clean names | ~60% | 100% |
| Cross-store matches | 32 | 100+ |
| Price validation pass rate | Unknown | 99%+ |
| Match false positive rate | ~30% | <5% |

---

## Files to Create

```
promo_products_bg/
├── standardization/
│   ├── __init__.py
│   ├── name_cleaner.py      # Name standardization
│   ├── brand_extractor.py   # Brand detection
│   ├── quantity_parser.py   # Quantity parsing
│   └── category_classifier.py
├── validation/
│   ├── __init__.py
│   ├── price_validator.py
│   ├── deduplicator.py
│   └── rules.py             # Validation rules config
├── database/
│   ├── __init__.py
│   ├── schema.sql
│   ├── models.py
│   └── import_pipeline.py
├── matching/
│   ├── __init__.py
│   ├── matcher_v3.py
│   └── strategies.py
├── export/
│   ├── __init__.py
│   └── frontend_exporter.py
├── data/
│   ├── known_brands.json
│   ├── categories.json
│   └── promobg.db           # SQLite database
└── tests/
    ├── test_name_cleaner.py
    ├── test_brand_extractor.py
    ├── test_price_validator.py
    └── test_matcher.py
```

---

## Next Steps

1. **Approve plan** - Adjust timeline/priorities if needed
2. **Start Phase 1** - Name cleaner is highest impact
3. **Daily progress** - I'll update on each component

Ready to start when you give the go-ahead.
