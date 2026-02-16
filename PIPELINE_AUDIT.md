# PromoBG Pipeline Audit - 2026-02-16

## Current State: BROKEN

### Problem: No consistent data flow
Every scrape/match run is ad-hoc. Files scattered, logic duplicated, no single source of truth.

### Current Mess:

```
SCRAPING (inconsistent):
  - Kaufland: ??? (unclear source)
  - Billa: ??? (unclear source)  
  - Lidl: lidl_jsonld_scraper.py → JSON files → manual import

DATA STORAGE (fragmented):
  - SQLite DB: products, store_products, prices, cross_store_matches
  - JSON files: standardized_final.json, cross_store_matches_final.json
  - Scraped JSON: lidl_jsonld_batch*.json, lidl_products.json, etc.

MATCHING (changes every run):
  - cross_store_matcher.py (v1-v7 versions!)
  - improved_matcher.py
  - Various thresholds, algorithms

EXPORT (multiple scripts):
  - export_final.py
  - export_frontend_data.py (v1, v2)
  - quick_export.py
```

### Root Causes:
1. **No single source of truth** - DB and JSON files both used inconsistently
2. **No standardized scraper interface** - each store scraper is different
3. **Matching logic not parameterized** - hardcoded thresholds scattered
4. **No pipeline orchestrator** - manual script running

---

## Target State: Production Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAILY CRON                                │
│                     (6:00 AM Sofia)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: SCRAPE (per store)                                      │
│  ─────────────────────────────────────────────────────────────  │
│  Input: Store URL/sitemap                                        │
│  Output: Raw products → raw_scrapes/{store}_{date}.json          │
│  DB: Nothing yet (raw files only)                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: CLEAN & NORMALIZE                                       │
│  ─────────────────────────────────────────────────────────────  │
│  Input: raw_scrapes/{store}_{date}.json                          │
│  Process:                                                        │
│    - Normalize names (remove ®™, fix encoding)                   │
│    - Extract brand (pattern matching)                            │
│    - Categorize (keyword rules)                                  │
│    - Validate prices (sanity checks)                             │
│    - Convert currency (BGN → EUR)                                │
│  Output: DB tables (products, store_products, prices)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: MATCH                                                   │
│  ─────────────────────────────────────────────────────────────  │
│  Input: DB (products with prices)                                │
│  Process:                                                        │
│    - Token similarity (threshold: 0.4)                           │
│    - Same category required                                      │
│    - Deduplicate by product pair                                 │
│  Output: DB table (cross_store_matches)                          │
│  Config: config/matching.json (thresholds, rules)                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: EXPORT                                                  │
│  ─────────────────────────────────────────────────────────────  │
│  Input: DB (all tables)                                          │
│  Output: docs/data/products.json (frontend)                      │
│  Trigger: Git push → GitHub Pages deploy                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Lessons Learned (MUST NOT REPEAT)

### 1. DB is the single source of truth
- ❌ Don't read/write JSON files as intermediate storage
- ✅ Scrape → DB → Export to JSON only at the end

### 2. Matching algorithm must be configurable, not hardcoded
- ❌ Don't create matcher_v1, v2, v3... v7 scripts
- ✅ One matcher script with config file for thresholds

### 3. Each store scraper must follow same interface
- ❌ Don't have different output formats per store
- ✅ All scrapers output same schema: {name, brand, price, currency, url, image}

### 4. Pipeline must be idempotent
- ❌ Don't require manual intervention between steps
- ✅ Run full pipeline with one command: `python pipeline.py --full`

### 5. Never change matching logic without versioning
- ❌ Don't tweak thresholds ad-hoc
- ✅ Config file with version, thresholds documented

---

## Files to DELETE (cleanup)
```
cross_store_matcher.py (use scripts/pipeline.py instead)
cross_store_matcher_v2.py
export_matches.py
scripts/cross_store_matcher_v5.py
scripts/cross_store_matcher_v6.py
scripts/cross_store_matcher_v7.py
scripts/export_frontend_data.py
scripts/export_frontend_data_v2.py
scripts/quick_export.py
scripts/improved_matcher.py
standardized_final.json (intermediate file, not needed)
```

## Files to KEEP/CREATE
```
scripts/pipeline.py          # Main orchestrator
scripts/scrapers/base.py     # Base scraper class
scripts/scrapers/kaufland.py # Store-specific scrapers
scripts/scrapers/lidl.py
scripts/scrapers/billa.py
scripts/cleaner.py           # Normalization logic
scripts/matcher.py           # Single matching script
scripts/exporter.py          # DB → frontend JSON
config/matching.json         # Matching thresholds
config/cleaning.json         # Cleaning rules
```
