# Product Matching Strategy

## Overview

PromoBG needs to match the **same product across different stores** to enable price comparison. This document describes our multi-tier matching approach.

## The Challenge

Same product, different names across stores:

| Store | Product Name | Price |
|-------|-------------|-------|
| Kaufland | Прясно мляко Верея 3% | 2.49 лв |
| Lidl | Верея прясно краве мляко 3% | 2.39 лв |
| Billa | Мляко прясно 3% Верея | 2.59 лв |

These are ALL the same product (Vereia 3% milk), but string matching fails because:
- Word order varies
- Some include "краве" (cow's), others don't
- Brand position differs (start vs end)

## Solution: Multi-Tier Matching

We use a **3-tier matching system**, from most reliable to least:

```
┌─────────────────────────────────────────────┐
│  TIER 1: BARCODE MATCHING (Most Reliable)   │
│  EAN-13 barcode = universal product ID      │
│  Same barcode = guaranteed same product     │
├─────────────────────────────────────────────┤
│  TIER 2: BRAND + NORMALIZED NAME            │
│  For products without barcodes              │
│  "Верея" + "мляко 3%" = match               │
├─────────────────────────────────────────────┤
│  TIER 3: CATEGORY + ATTRIBUTES              │
│  For bulk/unbranded products                │
│  "Плодове" + "банани" + "кг" = match        │
└─────────────────────────────────────────────┘
```

---

## Tier 1: Barcode Matching

### What is EAN-13?

Every packaged product sold in stores has a **European Article Number (EAN-13)** barcode printed on it. This 13-digit code uniquely identifies the product globally.

```
Example: 3800748001317
         ^^^
         380 = Bulgaria country code
```

### Why Barcodes?

| Method | Reliability | Coverage |
|--------|-------------|----------|
| Barcode | 100% | ~70% of products |
| Name matching | ~60% | 100% of products |

**Same barcode = same product. Period.** No fuzzy matching, no false positives.

### The Problem: Stores Don't Expose Barcodes

Bulgarian stores (Lidl, Kaufland, Billa) don't include barcodes in their websites. They use internal SKUs:

| Store | What They Expose | Example |
|-------|-----------------|---------|
| Lidl | `erpNumber`, `itemId` | 10051415 |
| Kaufland | Image ID | 20767324_P |
| Billa | Nothing | - |

### The Solution: Open Food Facts

[Open Food Facts](https://world.openfoodfacts.org/) is a free, crowdsourced database of food products with:
- **2.5M+ products** worldwide
- **Barcodes** (EAN-13)
- **Brand names**
- **Product names** (often in multiple languages)
- **Images**
- **Nutrition data**

**Bulgarian coverage:** ~5,000+ products with `countries_tags=en:bulgaria`

### Enrichment Flow

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  OUR DATABASE    │     │ OPEN FOOD FACTS │     │  ENRICHED DATA   │
│                  │     │                 │     │                  │
│  name: "Верея    │────►│  Search by      │────►│  name: "Верея    │
│   мляко 3%"      │     │  brand + name   │     │   мляко 3%"      │
│  brand: "Верея"  │     │                 │     │  brand: "Верея"  │
│  barcode: NULL   │     │  Returns:       │     │  barcode:        │
│                  │     │  3800748001317  │     │   3800748001317  │
└──────────────────┘     └─────────────────┘     └──────────────────┘
```

### Matching Algorithm

```python
def enrich_with_barcode(product):
    """
    Try to find barcode from Open Food Facts.
    Returns barcode if found, None otherwise.
    """
    
    # Strategy 1: Search by brand + product terms
    if product.brand:
        results = off_search(
            brands_tags=normalize(product.brand),
            search_terms=extract_product_terms(product.name),
            countries_tags="en:bulgaria"
        )
        if results and confidence_score(results[0], product) > 0.8:
            return results[0].barcode
    
    # Strategy 2: Search by full name
    results = off_search(
        search_terms=product.normalized_name,
        countries_tags="en:bulgaria"
    )
    if results and confidence_score(results[0], product) > 0.8:
        return results[0].barcode
    
    return None
```

### Confidence Scoring

When OFF returns results, we calculate confidence:

```python
def confidence_score(off_product, our_product):
    score = 0.0
    
    # Brand match: +0.4
    if brands_match(off_product.brands, our_product.brand):
        score += 0.4
    
    # Key terms match: +0.1 each (max 0.4)
    terms = extract_terms(our_product.name)  # ["мляко", "3%", "прясно"]
    for term in terms:
        if term in off_product.product_name.lower():
            score += 0.1
    
    # Quantity match: +0.2
    if quantities_match(off_product.quantity, our_product.quantity):
        score += 0.2
    
    return min(score, 1.0)
```

**Threshold: 0.8** — Only accept matches with 80%+ confidence.

---

## Tier 2: Brand + Normalized Name Matching

For products not found in Open Food Facts, we fall back to our own matching.

### Normalization Rules

```python
def normalize_name(name):
    """
    Normalize product name for matching.
    """
    name = name.lower()
    
    # Remove common store-specific prefixes
    name = re.sub(r'^(k-classic|clever|chef select|pilos|milbona)\s+', '', name)
    
    # Remove size/quantity at end
    name = re.sub(r'\d+\s*(г|гр|кг|мл|л|бр)\.?$', '', name)
    
    # Remove special characters
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # Collapse whitespace
    name = ' '.join(name.split())
    
    return name.strip()
```

### Group Key Generation

```python
def generate_group_key(product):
    """
    Create a matching key from brand + normalized name.
    """
    parts = []
    
    if product.brand:
        parts.append(normalize(product.brand))
    
    # Extract core product terms (skip brand if already added)
    name_terms = normalize_name(product.name)
    if product.brand:
        name_terms = name_terms.replace(normalize(product.brand), '')
    
    parts.append(name_terms.strip())
    
    # Truncate for fuzzy tolerance
    key = ' '.join(parts)[:50]
    
    return key
```

### Example

| Product | Brand | Group Key |
|---------|-------|-----------|
| "Прясно мляко Верея 3% 1л" | Верея | `верея мляко прясно` |
| "Верея прясно краве мляко 3%" | Верея | `верея мляко прясно краве` |

These won't match exactly, so we use **fuzzy matching**:

```python
from difflib import SequenceMatcher

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

# similarity("верея мляко прясно", "верея мляко прясно краве") = 0.82
# Threshold: 0.75 → MATCH
```

---

## Tier 3: Category + Attributes (Bulk Products)

For unbranded bulk products (fruits, vegetables, meat by weight), we match by:

1. **Category** — "Плодове и зеленчуци"
2. **Core term** — "банани", "домати", "картофи"
3. **Unit** — "кг" (by weight)

### Bulk Product Detection

```python
def is_bulk_product(product):
    """
    Detect if product is sold in bulk (no barcode possible).
    """
    bulk_indicators = [
        product.unit == 'кг',
        product.category in BULK_CATEGORIES,
        not product.brand,
        any(term in product.name.lower() for term in BULK_TERMS)
    ]
    return sum(bulk_indicators) >= 2

BULK_CATEGORIES = [
    'Плодове', 'Зеленчуци', 'Месо', 'Риба', 
    'Хляб', 'Печива', 'Деликатеси'
]

BULK_TERMS = [
    'пресен', 'прясна', 'на кг', 'bulgarian',
    'домашен', 'домашна', 'селски'
]
```

### Bulk Matching

```python
def match_bulk_product(product):
    """
    Match bulk product by category + normalized term.
    """
    core_term = extract_core_term(product.name)  # "банани" from "Банани еквадор"
    
    return f"bulk:{product.category}:{core_term}"
```

---

## Database Schema

```sql
-- Products table (existing)
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    brand TEXT,
    barcode_ean TEXT,              -- ← Tier 1 matching
    group_key TEXT,                -- ← Tier 2 matching
    category_id INTEGER,
    unit TEXT,
    quantity REAL,
    is_bulk INTEGER DEFAULT 0,     -- ← Tier 3 flag
    match_confidence REAL,         -- How confident is our match?
    ...
);

-- Index for fast barcode lookup
CREATE INDEX idx_products_barcode ON products(barcode_ean);
CREATE INDEX idx_products_group_key ON products(group_key);
```

---

## Matching Priority

When comparing products across stores:

```python
def find_matches(product, all_products):
    """
    Find matching products from other stores.
    Priority: barcode > group_key > bulk_key
    """
    matches = []
    
    # Priority 1: Exact barcode match
    if product.barcode_ean:
        barcode_matches = [p for p in all_products 
                          if p.barcode_ean == product.barcode_ean
                          and p.store_id != product.store_id]
        matches.extend([(p, 1.0, 'barcode') for p in barcode_matches])
    
    # Priority 2: Group key match (fuzzy)
    if product.group_key and not matches:
        for p in all_products:
            if p.store_id != product.store_id and p.group_key:
                sim = similarity(product.group_key, p.group_key)
                if sim > 0.75:
                    matches.append((p, sim, 'group_key'))
    
    # Priority 3: Bulk product match
    if product.is_bulk and not matches:
        bulk_key = get_bulk_key(product)
        bulk_matches = [p for p in all_products
                       if p.is_bulk and get_bulk_key(p) == bulk_key
                       and p.store_id != product.store_id]
        matches.extend([(p, 0.7, 'bulk') for p in bulk_matches])
    
    return sorted(matches, key=lambda x: -x[1])
```

---

## Implementation Plan

### Phase 1: Barcode Enrichment (Current)

1. **Build OFF integration** — `services/matching/off_client.py`
2. **Enrich existing products** — Run against 919 products in DB
3. **Store barcodes** — Update `barcode_ean` field
4. **Measure coverage** — Target: 50%+ of branded products

### Phase 2: Improved Name Matching

1. **Refine group_key algorithm** — Better normalization
2. **Add fuzzy matching** — For products without barcodes
3. **Manual verification UI** — Confirm/reject suggested matches

### Phase 3: Continuous Enrichment

1. **On scrape** — Check OFF for new products
2. **Periodic refresh** — Re-check unmatched products monthly
3. **Crowdsource** — Let users report incorrect matches

---

## API Endpoints

```
GET /api/products/{id}/matches
    → Returns matching products from other stores

GET /api/compare?barcode=3800748001317
    → Returns all store prices for barcode

GET /api/compare?name=мляко+верея+3%
    → Fuzzy search + match across stores
```

---

## Metrics & Monitoring

Track matching quality:

| Metric | Target | Current |
|--------|--------|---------|
| Products with barcode | 50% | 0% |
| Cross-store matches found | 200+ | 6 |
| Match confidence avg | >0.85 | - |
| False positive rate | <5% | - |

---

## Open Food Facts API Reference

### Search Endpoint

```
GET https://world.openfoodfacts.org/cgi/search.pl?
    search_terms={query}&
    tagtype_0=countries&
    tag_contains_0=contains&
    tag_0=bulgaria&
    json=1&
    page_size=20
```

### Get by Barcode

```
GET https://world.openfoodfacts.org/api/v0/product/{barcode}.json
```

### Response Fields We Use

```json
{
  "code": "3800748001317",
  "product": {
    "product_name": "Прясно мляко 3%",
    "brands": "Верея",
    "quantity": "1 l",
    "categories_tags": ["en:milks"],
    "image_url": "https://..."
  }
}
```

---

## Re-Scraping: NOT Required

We already have the data needed for matching:
- ✅ Product name
- ✅ Brand (when available)
- ✅ Price
- ✅ Category

We only need to **enrich** existing data with barcodes from Open Food Facts. No re-scraping necessary.

---

*Last updated: 2026-02-12*
*Author: Cookie 🍪*
