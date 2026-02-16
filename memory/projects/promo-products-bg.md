# PromoBG Project Memory

## Overview
Cross-store Bulgarian grocery price comparison platform.

## 2026-02-16: Data Quality Pipeline Session

### What Happened
- Started with regex-based cleaning: 33% brand coverage
- Martin manually added ~50 brands, still many wrong categories
- Pivoted to LLM-powered cleaning (GPT-4o-mini)
- LLM parses all 2,733 products → extracts brands, categories, quantities
- One-time cost: ~$0.30

### Key Outcomes
1. **Clean reference data** → output/products_llm_cleaned.json
2. **Config files for rules** → config/brands.json, categories.json, pack_patterns.json
3. **Rule-based cleaner** → scripts/clean_products_rules.py (auto-generated)

### Architecture Decision
- LLM cleaning = ONE TIME ONLY (bootstrap)
- Future cleaning = pure rule-based (config-driven)
- Daily scrapes → rules → DB → price history

### Database Needs (Next Step)
- PostgreSQL with: brands, categories, products, price_history, cross_store_matches
- Daily pipeline: SCRAPE → CLEAN → UPSERT → PRICE → MATCH → EXPORT

### Files Created
- docs/SESSION_SUMMARY_2026-02-16.md
- docs/LESSONS_LEARNED.md
- scripts/batch_llm_clean_v2.py
- scripts/extract_mappings.py

## Tech Stack
- Scrapers: Python (requests, playwright)
- Cleaning: Rule-based with config files
- DB: PostgreSQL (planned)
- Frontend: Static site on GitHub Pages

## Stores
- Kaufland (1,698 products)
- Lidl (247 products)
- Billa (277 products)
