# Scraper Audit - 2026-02-16

## Current State

`scrape_all.py` is **NOT actually scraping** - it loads from existing data files:
- Kaufland: `data/kaufland_enhanced.json`
- Lidl: `data/lidl_jsonld_batch*.json`
- Billa: SQLite database

---

## Store-by-Store Audit

### 1. KAUFLAND

**Current scraper:** `kaufland_enhanced_scraper.py`
**Data source:** `data/kaufland_enhanced.json` (1977 products)
**Last scraped:** Feb 16, 2026

**Output fields:**
- ✅ title, subtitle, description
- ✅ price_bgn, old_price_bgn
- ✅ image_url
- ✅ kl_nr (SKU)
- ❌ brand (NOT in raw data)
- ❌ quantity (parsed from title)

**Issues:**
1. Promo data expired Feb 15 - needs fresh scrape
2. No brand field - relies on LLM/rules extraction
3. No direct DB integration

**TODO:**
- [ ] Re-run scraper for fresh data
- [ ] Add DB integration (db_pipeline.py)

---

### 2. LIDL

**Current scraper:** `lidl_jsonld_scraper.py`
**Data source:** `data/lidl_jsonld_batch*.json` (479 products)
**Last scraped:** Feb 16, 2026

**Output fields:**
- ✅ name
- ✅ price
- ✅ image_url, product_url
- ✅ product_id (SKU)
- ❌ brand (NOT in JSON-LD!)
- ❌ description
- ❌ old_price (only some products)

**Issues:**
1. **JSON-LD has NO brand field** - root cause of 2.7% brand coverage
2. `lidl_fresh.json` from promo pages HAS brands but only 130 products
3. Multiple scraper versions (6+ files) - messy

**TODO:**
- [ ] Merge scrapers - use one that gets brand data
- [ ] Scrape product detail pages for brand
- [ ] Add DB integration

---

### 3. BILLA

**Current scraper:** `billa_scraper.py`
**Data source:** SQLite database (277 products)
**Last scraped:** Unknown

**Output fields:**
- ✅ name
- ✅ current_price
- ✅ image_url
- ❌ brand (in products table)
- ❌ old_price

**Issues:**
1. Smallest dataset (277 products)
2. Prices in EUR, need BGN conversion
3. No promo/old_price tracking

**TODO:**
- [ ] Fresh scrape with price tracking
- [ ] Add promo detection

---

## Required Changes

### 1. Update scrape_all.py to ACTUALLY scrape

```python
def scrape_kaufland():
    # Actually call the Kaufland API
    # NOT just load existing JSON

def scrape_lidl():
    # Use lidl_fresh.json approach (has brands)
    # NOT just load JSON-LD batches

def scrape_billa():
    # Actually scrape Billa website
    # NOT just read database
```

### 2. Integrate with DB pipeline

Each scraper should:
```python
from scripts.db_pipeline import PromoBGDatabase

with PromoBGDatabase() as db:
    run_id = db.start_scan_run("Kaufland")
    
    for product in scrape():
        db.append_raw_scrape(run_id, product)
    
    db.complete_scan_run(run_id, stats)
```

### 3. Standardize output format

All scrapers must output:
```python
{
    'store': str,           # Required
    'sku': str,             # Required
    'raw_name': str,        # Required
    'raw_subtitle': str,    # Optional
    'raw_description': str, # Optional
    'price_bgn': float,     # Required
    'old_price_bgn': float, # Optional (promo)
    'discount_pct': float,  # Optional
    'image_url': str,       # Optional
    'product_url': str,     # Optional
    'brand': str,           # Optional (if available)
}
```

---

## Priority Actions

1. **HIGH: Fix Lidl brand extraction**
   - Option A: Scrape product detail pages
   - Option B: OCR from brochure
   - Option C: Keep LLM fallback

2. **HIGH: Fresh Kaufland scrape**
   - Promo expired Feb 15

3. **MEDIUM: DB integration**
   - All scrapers write to raw_scrapes
   - Enable price history tracking

4. **LOW: Billa refresh**
   - Only 277 products
   - May need new scraping approach
