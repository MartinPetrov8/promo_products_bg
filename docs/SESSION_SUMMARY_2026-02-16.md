# Session Summary: Data Quality Pipeline Build
**Date:** 2026-02-16

## Goal
Build a robust data quality pipeline for PromoBG to clean product names, extract brands, categorize products, validate prices, and enable accurate cross-store matching.

## What We Built

### 1. LLM-Powered One-Time Cleaning
- Used GPT-4o-mini to parse 2,733 products
- Extracts: brand, clean product name, quantity, unit, pack_size, category
- Cost: ~$0.30 for full dataset
- Creates reference data for future rule-based cleaning

### 2. Config-Driven Rule System
```
config/
├── brands.json           # Master brand list (add new brands here)
├── categories.json       # Category keywords (learned from LLM)
├── pack_patterns.json    # Pack patterns (промопакет, витрина, etc.)
└── quantity_patterns.json # Quantity regex patterns
```

### 3. Generated Rule-Based Cleaner
`scripts/clean_products_rules.py` - Auto-generated from LLM results, uses config files for instant cleaning without LLM.

## Key Lessons Learned

### Technical
1. **Substring matching bugs** - "шоколад" contains "кола", causing wrong category. Fixed with category order.

2. **Brand word boundaries** - "бони" matched "бонбони". Fixed with regex word boundaries.

3. **Category order matters** - Check specific categories (торта→сладкарски) BEFORE generic (йогурт→млечни).

4. **Exec timeouts kill long jobs** - Use nohup for jobs >10 mins. Save progress incrementally.

5. **LLM cleaning = one-time bootstrap** - Use it once to learn patterns, then pure rules forever.

### Process
1. **Manual brand/category review doesn't scale** - Need automated LLM pass first

2. **Data quality is foundational** - Can't do cross-store matching without clean data

3. **Incremental saves prevent data loss** - Batch jobs should save after each step

## Data Structure Needs

### Required Database Schema
- brands table (master list, add new brands here)
- categories table (keywords per category)
- products table (store, sku, clean_name, brand_id, category_id, quantity, first_seen, last_seen)
- price_history table (product_id, price_eur, price_bgn, promo_price, scraped_at)
- cross_store_matches table (product_a, product_b, confidence, method, verified)

### Daily Scraping Pipeline
1. SCRAPE → raw_scrapes/{store}_{date}.json
2. CLEAN  → Apply rules from config/*.json  
3. UPSERT → Insert new products, update last_seen
4. PRICE  → Insert price_history record
5. MATCH  → Run cross-store matching on new products
6. EXPORT → Generate static site data

## Cost Summary
- GPT-4o-mini cleaning: ~$0.30 (one-time)
- Future cleaning: $0 (rule-based)
