# PromoBG Architecture

## System Overview

PromoBG is a Bulgarian grocery price comparison platform that aggregates promotional offers from Kaufland, Lidl, and Billa (with plans for Fantastico), normalizes product data, and enables cross-store price comparison.

**Key Metrics:**
- 90 → 2,346 cross-store matches (post-standardization)
- 5,664 total products across 3 stores
- 802 products standardized in first pass

---

## Core Principles

### 1. Standardized Product Schema (v1.0)

All products from all stores must conform to this schema:

```python
class StandardProduct:
    # Identity
    store: str                    # "Kaufland" | "Lidl" | "Billa"
    external_id: str              # Store's native product ID
    
    # Core Attributes (REQUIRED for comparison)
    name: str                     # Clean product name (no promo prefixes)
    normalized_name: str          # Lowercase, normalized for matching
    brand: Optional[str]          # Extracted brand name
    
    # Quantity (standardized to base units)
    quantity_value: Optional[float]  # Numeric value (e.g., 500)
    quantity_unit: Optional[str]     # "ml" | "g" | "pcs" | "kg" | "l"
    
    # Category (for blocking)
    category: Optional[str]       # GS1 GPC category code
    category_name: Optional[str]  # Human-readable category
    
    # Price & Availability
    price: float                  # Current price (BGN)
    old_price: Optional[float]    # Regular/strikethrough price
    price_per_unit: Optional[float]  # Price per 100ml or 100g
    valid_from: date
    valid_to: Optional[date]
    
    # Metadata
    image_url: Optional[str]
    description: Optional[str]    # Full description if available
    is_house_brand: bool         # Is this a store-exclusive brand?
    
    # Tracking
    scraped_at: datetime
    hash: str                     # Content hash for change detection
```

### 2. Brand Tier Classification

| Tier | Definition | Examples | Matching Rule |
|------|-----------|----------|---------------|
| **National** | Well-known international/national brands | Coca-Cola, Nestlé, Milka | Exact brand match required |
| **Regional** | Regional Bulgarian brands | Верея, Olympus, Калиакра | Exact brand match required |
| **House** | Store-exclusive private labels | K-Classic, Pilos, Clever | Match as "comparable" |
| **Generic** | No brand/generic | "Баничка", "Пресни яйца" | Embedding-only matching |

### 3. Category Taxonomy (GS1 GPC Based)

```
10000000 - Food/Beverage/Tobacco
  10100000 - Produce
    10101500 - Fresh fruits
    10101600 - Fresh vegetables
  10200000 - Meat/Poultry/Fish
    10202600 - Fresh meat
    10202900 - Processed meat
  10300000 - Dairy/Eggs
    10303400 - Milk
    10303500 - Cheese
    10303600 - Yogurt
  10400000 - Bakery
    10403800 - Bread
    10403900 - Pastries
  10500000 - Beverages
    10504900 - Soft drinks
    10505200 - Beer

20000000 - Health/Beauty/Personal Care
30000000 - Household Cleaning
40000000 - Home/Garden
```

### 4. Matching Rules

#### Rule 1: Category Blocking
- Products must share the same GS1 GPC category to be match candidates
- Reduces comparison space 1000x (5K products → ~50 per category)

#### Rule 2: Exact Match (Confidence: 0.95)
- brand_match = normalized(brand1) == normalized(brand2)
- name_similarity >= 0.95 (normalized names)
- quantity_compatible(q1, u1, q2, u2)
- category_match

#### Rule 3: Brand + Fuzzy (Confidence: 0.75-0.90)
- brand_match = True
- name_similarity >= 0.80 (embedding)
- quantity_compatible()
- category_match

#### Rule 4: House Brand Comparable (Confidence: 0.70)
- both_are_house_brands = True
- same_product_type (embedding > 0.85)
- quantity_compatible()
- category_match
- Example: K-Classic Milk ↔ Pilos Milk

### 5. Quantity Compatibility

```python
def quantities_compatible(q1, u1, q2, u2):
    # Normalize to base units (ml or g)
    # Allow 25% variance for multipacks
    ratio = max(base1, base2) / min(base1, base2)
    return ratio <= 1.25
```

### 6. Price Per Unit Calculation

```python
def calculate_price_per_unit(price, quantity, unit):
    # Return price per 100ml or 100g for fair comparison
    base_qty = normalize_to_base(quantity, unit)
    if unit in ('ml', 'л', 'l', 'мл'):
        return (price / base_qty) * 100  # per 100ml
    elif unit in ('g', 'г', 'kg', 'кг'):
        return (price / base_qty) * 100  # per 100g
```

---

## Store-Specific Notes

### Kaufland
- **Data Quality:** High (65% brand coverage)
- **Challenges:** Unit field sometimes contains descriptions
- **API/Scraper:** JSON API available

### Lidl
- **Data Quality:** Medium (37% brand coverage)
- **Challenges:** HTML in unit field
- **Fix Required:** Strip HTML before parsing quantity

### Billa
- **Data Quality:** Low (9% → 35% after fixes)
- **Challenges:** Promo prefixes pollute names
- **Fix Required:** Strip "King оферта -", "Само с Billa Card -" prefixes

---

## Matching Confidence Tiers

| Tier | Confidence | Match Type | UX Display |
|------|-----------|------------|------------|
| 🟢 **Exact** | 0.95 | Same brand, similar name, compatible qty | "Same product" |
| 🟡 **Very Similar** | 0.80-0.94 | Same brand, fuzzy name match | "Same brand, check details" |
| 🟠 **Comparable** | 0.70-0.79 | House brands, similar product | "Comparable product" |
| 🔴 **Possible** | < 0.70 | Embedding match only | "Might be similar" |

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| Database | SQLite (development), PostgreSQL (production) |
| Embedding Model | paraphrase-multilingual-MiniLM-L12-v2 |
| API Framework | FastAPI |
| Frontend | React or Vue.js |
| Scraping | Python + BeautifulSoup / Playwright |
