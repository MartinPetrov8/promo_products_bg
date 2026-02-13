# OFF Matching Plan - Getting Barcodes for Bulgarian Products

## Current State

### OFF Bulgaria Database (Local)
| Metric | Count | Notes |
|--------|-------|-------|
| Total products | 14,853 | Downloaded locally |
| With brand | 10,118 | 68% |
| With quantity | 6,508 | 44% |
| With BG name | 8,618 | 58% |

**Top OFF Brands:** Billa (117), K-Classic (109), Родна стряха (103), Lidl (73), Bonduelle (62), Nestle (54), Milka (52), Olympus (50)

**Quantity Formats:** "400 г", "400 g", "500 г", "1 л", "1 l", "500 ml", etc.

### Store Products (Our Data)
| Store | Products | Brand | Size | Existing Barcodes |
|-------|----------|-------|------|-------------------|
| Kaufland | 2,724 | 2,140 (79%) | 1,524 (56%) | 74 (3%) |
| Lidl | 1,078 | 391 (36%) | 257 (24%) | 4 (0%) |
| Billa | 554 | 76 (14%) | 0 (0%) | 30 (5%) |
| **Total** | **4,356** | **2,607** | **1,781** | **108** |

### Data Quality Issues
1. **Bad normalized_name values** - Contains promo text like "-25% отстъпка с\nkaufland card"
2. **Billa has 0 sizes** - Size extraction not implemented for Billa
3. **Missing brands** - 40% of products have no brand
4. **Quantity format mismatch** - We have "500г", OFF has "500 г" or "500 g"

---

## Matching Strategy

### Phase 1: Data Cleanup (Pre-requisite)
Before matching, fix the data quality issues:

```
1.1 Fix normalized_name field
    - Strip all promo prefixes/suffixes
    - Remove card discounts, special offers text
    - Keep only product description
    
1.2 Extract sizes for Billa
    - Parse "500г", "1л", "200мл" from product names
    - Store in package_size column
    
1.3 Normalize quantity formats
    - Create unified format: lowercase, no spaces ("500g", "1l", "500ml")
    - Handle both Cyrillic (г, л, мл, кг) and Latin (g, l, ml, kg)
```

### Phase 2: Build Match Indices
Create lookup structures for fast matching:

```
2.1 OFF Brand Index
    - Map normalized brand → list of OFF products
    - Normalize: lowercase, remove dashes, transliterate BG↔EN
    - Example: "coca-cola" → [products with Coca-Cola]
    
2.2 OFF Quantity Index  
    - Map normalized quantity → list of OFF products
    - Handle variations: "500 г" = "500g" = "500 g"
    
2.3 OFF Name Token Index
    - Tokenize product names into significant words
    - Map token → list of OFF products
    - Skip stopwords: "с", "за", "от", "и", etc.
```

### Phase 3: Multi-Pass Matching

#### Pass 1: Exact Brand + Quantity Match (Highest Confidence)
```python
for product in our_products:
    # Find OFF products with same brand AND quantity
    candidates = off_by_brand[product.brand] ∩ off_by_quantity[product.size]
    if candidates:
        # Score by name similarity
        best = max(candidates, key=lambda c: name_similarity(product.name, c.name))
        if similarity > 0.7:
            MATCH(confidence=0.95)
```
**Expected:** ~800-1,000 matches (products with both brand AND size)

#### Pass 2: Brand + Name Similarity (High Confidence)
```python
for unmatched in our_products:
    # Find OFF products with same brand
    candidates = off_by_brand[product.brand]
    # Score by name + quantity similarity
    best = max(candidates, key=lambda c: combined_score(product, c))
    if combined_score > 0.75:
        MATCH(confidence=0.85)
```
**Expected:** ~500-700 additional matches

#### Pass 3: Name Token Overlap (Medium Confidence)
```python
for unmatched in our_products:
    # Find OFF products sharing 3+ significant name tokens
    our_tokens = tokenize(product.name)
    candidates = intersect([off_by_token[t] for t in our_tokens])
    # Must share at least 3 tokens
    candidates = [c for c in candidates if shared_tokens(c) >= 3]
    best = max(candidates, key=lambda c: full_similarity(product, c))
    if similarity > 0.70:
        MATCH(confidence=0.75)
```
**Expected:** ~300-500 additional matches

#### Pass 4: Fuzzy Name Match (Low Confidence - Manual Review)
```python
for unmatched in our_products:
    # Use SequenceMatcher on normalized names
    best = max(all_off_products, key=lambda c: SequenceMatcher(product.name, c.name))
    if ratio > 0.80:
        MATCH(confidence=0.60, needs_review=True)
```
**Expected:** ~200-400 additional matches (need human review)

---

## Matching Rules

### Brand Normalization
| Our Brand | OFF Brand | Normalized |
|-----------|-----------|------------|
| Кока-Кола | Coca-Cola | coca-cola |
| ВЕРЕЯ | Vereia | верея |
| K-Classic | K Classic | k-classic |
| Нестле | Nestle | nestle |

### Quantity Normalization
```python
def normalize_quantity(q):
    q = q.lower().strip()
    # Remove spaces
    q = re.sub(r'\s+', '', q)
    # Cyrillic to Latin
    q = q.replace('г', 'g').replace('л', 'l').replace('мл', 'ml').replace('кг', 'kg')
    # Extract numeric + unit
    match = re.match(r'(\d+(?:[.,]\d+)?)\s*(g|kg|l|ml)', q)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return q
```

### Name Cleaning
```python
PROMO_PATTERNS = [
    r'-?\d+%\s*отстъпка.*',
    r'с\s*kaufland\s*card.*',
    r'king\s*оферта.*',
    r'супер\s*цена.*',
    r'само\s*с\s*billa\s*card.*',
    r'продукт[,\s]+маркиран.*',
]

def clean_name(name):
    name = name.lower()
    for pattern in PROMO_PATTERNS:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    return name.strip()
```

### Stopwords (Bulgarian)
```python
STOPWORDS = {'и', 'с', 'за', 'от', 'на', 'в', 'без', 'или', 'а', 'до', 'по'}
```

---

## Scoring Formula

```
Total Score = (Brand Score × 0.40) + (Name Score × 0.35) + (Quantity Score × 0.25)

Brand Score:
  - Exact match: 1.0
  - Transliteration match: 0.9
  - Substring match: 0.7
  - No brand data: 0.0

Name Score:
  - Token overlap ratio: len(shared_tokens) / len(all_tokens)
  - SequenceMatcher ratio on cleaned names
  - Weighted average of both

Quantity Score:
  - Exact match: 1.0
  - Same unit, ±10%: 0.8
  - Same unit, different value: 0.3
  - No quantity data: 0.0
```

---

## Confidence Tiers

| Tier | Score | Action | Expected Count |
|------|-------|--------|----------------|
| **High** | ≥ 0.85 | Auto-save barcode | ~1,000 |
| **Medium** | 0.70-0.84 | Auto-save, flag for spot-check | ~800 |
| **Low** | 0.55-0.69 | Save to review queue | ~400 |
| **No Match** | < 0.55 | Skip (NULL is better than wrong) | ~2,000 |

---

## Implementation Steps

### Step 1: Fix Data Quality (~30 min)
```bash
# 1.1 Clean normalized_name for all stores
python3 services/matching/fix_normalized_names.py

# 1.2 Extract Billa sizes
python3 services/matching/extract_billa_sizes.py

# 1.3 Verify cleanup
python3 -c "
import sqlite3
conn = sqlite3.connect('data/promobg.db')
cur = conn.cursor()
cur.execute('SELECT name, normalized_name FROM products WHERE normalized_name LIKE \"%отстъпка%\" LIMIT 5')
print('Remaining promo text:', cur.fetchall())
"
```

### Step 2: Build Indices (~5 min)
```bash
python3 services/matching/build_off_indices.py
# Creates: data/off_brand_index.json, data/off_quantity_index.json
```

### Step 3: Run Multi-Pass Matcher (~2 min)
```bash
python3 services/matching/multi_pass_matcher.py --dry-run  # Preview
python3 services/matching/multi_pass_matcher.py            # Execute
```

### Step 4: Review Low-Confidence Matches
```bash
# Generate review spreadsheet
python3 services/matching/export_review.py > data/matches_for_review.csv
```

### Step 5: Apply Approved Matches
```bash
python3 services/matching/apply_reviewed_matches.py data/matches_approved.csv
```

---

## Expected Results

| Store | Total | Expected Matches | Match Rate |
|-------|-------|------------------|------------|
| Kaufland | 2,724 | ~1,400 | ~51% |
| Lidl | 1,078 | ~450 | ~42% |
| Billa | 554 | ~250 | ~45% |
| **Total** | **4,356** | **~2,100** | **~48%** |

**Why not 100%?**
- Many products are store brands not in OFF (K-Classic, Pilos, etc.)
- Fresh/bulk products rarely have barcodes
- Seasonal items may not be in OFF
- Regional products with limited OFF coverage

---

## Validation

Before deploying matches, validate sample:

```python
# Random sample of 50 matches per confidence tier
# Manual verification:
# - Does barcode scan to correct product?
# - Does brand match?
# - Does quantity match?

# If accuracy < 90% for a tier, raise confidence threshold
```

---

## Files to Create

1. `services/matching/fix_normalized_names.py` - Clean promo text
2. `services/matching/extract_billa_sizes.py` - Parse Billa sizes
3. `services/matching/build_off_indices.py` - Create lookup indices
4. `services/matching/multi_pass_matcher.py` - Main matching logic
5. `services/matching/export_review.py` - Generate review CSV
6. `services/matching/apply_reviewed_matches.py` - Apply approved matches

---

## Notes

- **NO API calls** - All matching is local against `off_bulgaria.db`
- **NULL is better than wrong** - Don't force bad matches
- **Commit after each phase** - Allow rollback if issues found
- **48% match rate is realistic** - Higher would require manual data entry
