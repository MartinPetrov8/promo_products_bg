# Session Summary: 2026-02-16

## Overview
Major data quality pipeline overhaul - from JSON files to proper SQLite database with price history tracking, plus hybrid LLM/rules cleaning system.

---

## 1. LLM Cleaning Pipeline

### What Was Built
- **One-time GPT-4o-mini batch cleaning** of 2733 products
- Extracted: brands (790), categories (30), quantities, pack sizes
- Cost: ~$0.30 total

### Files Created
| File | Purpose |
|------|---------|
| `scripts/batch_llm_clean.py` | One-time LLM batch cleaner |
| `scripts/extract_mappings.py` | Generates rules from LLM output |
| `config/brands.json` | 790 brands |
| `config/categories.json` | 30 categories with keywords |
| `config/pack_patterns.json` | 133 pack patterns |
| `config/quantity_patterns.json` | Quantity extraction patterns |

---

## 2. Rule-Based Cleaning (LLM-Free)

### Accuracy vs LLM Ground Truth
| Metric | Score |
|--------|-------|
| Brand extraction | 96.8% |
| Quantity parsing | 84.9% |
| Category assignment | 72.6% |

### Files Created
| File | Purpose |
|------|---------|
| `scripts/clean_products_rules.py` | Pure regex cleaner (slow) |
| `scripts/clean_products_fast.py` | SKU lookup from LLM data |
| `scripts/test_rules_vs_llm.py` | Test framework |

---

## 3. Hybrid Pipeline (Production)

### How It Works
1. Apply rules to ALL products (free, ~90% accurate)
2. Detect low-confidence extractions (~10% of products)
3. Send ONLY edge cases to GPT-4o-mini (~$0.002/run)

### Cost Analysis
| Model | Cost/Run | Monthly |
|-------|----------|---------|
| GPT-4o-mini | $0.002 | $0.05 |

### File Created
- `scripts/clean_products_hybrid.py`

---

## 4. Database Schema (SQLite)

### New Tables
```sql
-- Append-only raw scraper data
raw_scrapes (
    id, scan_run_id, store, sku, raw_name, raw_subtitle,
    raw_description, price_bgn, old_price_bgn, discount_pct,
    image_url, product_url, scraped_at
)

-- Track each scraper execution
scan_runs (
    id, store_id, started_at, completed_at, status,
    products_scraped, new_products, price_changes, errors
)
```

### Updated Tables
```sql
-- Added columns to prices
prices (
    ..., scraped_at, old_price, discount_pct
)
```

### Key Design Decisions
- **raw_scrapes is APPEND-ONLY** - never delete historical data
- **Every scrape creates a scan_run** - timestamped execution log
- **price_history tracks changes** - for trend analysis

### File Created
- `scripts/db_pipeline.py` - Database operations class

---

## 5. Cross-Store Matching

### Results
- 412 validated cross-store matches
- Quantity normalization (ml/l, g/kg)
- Price diff cap at 200%

### Store Rankings (cheapest)
| Store | Win % |
|-------|-------|
| Kaufland | 56.3% |
| Lidl | 34.2% |
| Billa | 9.5% |

### Files Created
- `scripts/cross_store_matcher.py`
- `scripts/export_frontend.py`

---

## 6. Data Issues Found

### Lidl Brand Coverage: Only 2.7%
**Root cause:** Lidl sitemap JSON-LD has no brand field

**Partial fix:** Merged `lidl_fresh.json` (130 products with brands)

**TODO:** Re-scrape Lidl product pages for brand data

### Quantity Coverage: Only 13.6%
**Root cause:** Most products don't have quantity in name/subtitle

**Partial fix:** LLM extraction + strict prompt for edge cases

---

## 7. Full Pipeline (Production Ready)

```bash
# 1. Scrape all stores
python scripts/scrape_all.py

# 2. Import to database
python scripts/db_pipeline.py

# 3. Clean with hybrid pipeline
python scripts/clean_products_hybrid.py

# 4. Match across stores
python scripts/cross_store_matcher.py

# 5. Export for frontend
python scripts/export_frontend.py

# 6. Deploy (GitHub Pages auto-deploys)
git add docs/data/ && git commit -m "Update data" && git push
```

---

## 8. Cost Summary

| Item | Cost |
|------|------|
| Initial LLM cleaning | $0.30 (one-time) |
| Daily hybrid cleaning | $0.002/run |
| Monthly (daily scrapes) | ~$0.05 |

---

## Next Steps
1. [ ] Audit scrapers (see below)
2. [ ] Set up daily cron job
3. [ ] Fresh scrapes (Kaufland promo expired)
4. [ ] Fix Lidl brand extraction
5. [ ] Add more stores (T-Market, Metro)
