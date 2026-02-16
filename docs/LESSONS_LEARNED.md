# Lessons Learned - Data Quality Pipeline

## Date: 2026-02-16

### Critical Technical Lessons

1. **Substring Matching Bugs**
   - Problem: "шоколад" contains "кола" → wrong category (drinks instead of sweets)
   - Fix: Category check ORDER matters - check specific before generic

2. **Brand Word Boundaries**
   - Problem: "бони" (brand) matched "бонбони" (candy)
   - Fix: Regex word boundaries: `(?:^|[\s\-/])brand(?:[\s\-/]|$)`

3. **Category Priority Order**
   - Problem: "Торта Йогурт" matched "йогурт" → dairy instead of sweets
   - Fix: Check "торта" BEFORE "йогурт" in category rules

4. **Long Job Timeouts**
   - Problem: 10-min exec timeout killed 92-batch job at batch 15
   - Fix: Use `nohup` + incremental saves after each batch

5. **LLM = One-Time Bootstrap**
   - LLM extracts patterns → config files → rule-based cleaning forever
   - Cost: ~$0.30 once, then $0

### Process Lessons

1. **Manual Review Doesn't Scale**
   - Quote: "bleeding my eyes out" - too many products to review manually
   - Solution: Automated LLM pass first, then spot-check

2. **Data Quality Before Features**
   - Can't do cross-store matching without clean, consistent data
   - Clean brand + category extraction is foundational

3. **Incremental Saves**
   - Any batch job should save progress after each step
   - Resumable processing prevents wasted work

### Architecture Decisions

1. **Config-Driven Rules**
   ```
   config/brands.json     → Add new brands here
   config/categories.json → Category keywords
   config/pack_patterns.json → Pack size patterns
   ```

2. **Database Schema Needed**
   - brands, categories (reference tables)
   - products (store, sku, clean_name, brand_id, category_id)
   - price_history (daily prices)
   - cross_store_matches (product pairs)

3. **Daily Pipeline**
   ```
   SCRAPE → CLEAN (rules) → UPSERT → PRICE → MATCH → EXPORT
   ```

### What Worked
- GPT-4o-mini for Bulgarian product parsing
- Kimi (moonshot) for initial test
- Batch processing with progress saves
- Config-driven architecture

### What Didn't Work
- Manual brand additions one by one
- Regex-only cleaning without LLM bootstrap
- Long exec jobs without nohup
