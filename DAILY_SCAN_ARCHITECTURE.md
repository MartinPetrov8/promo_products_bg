# Daily Scan Architecture - PromoBG

## Objectives

When running daily scraper, we need to handle:

| Scenario | Detection | Action |
|----------|-----------|--------|
| **A) New product** | Product URL/SKU not in DB | INSERT new product + price |
| **B) Price change** | Product exists, price differs | UPDATE price, LOG history |
| **C) Delisted product** | Product in DB, not in scrape | Mark as `inactive`, keep data |

## Current Schema Gaps

```sql
-- CURRENT (insufficient)
products (id, name, brand)
prices (store_product_id, current_price)  -- No history!

-- NEEDED
products (id, name, brand, created_at, updated_at)
store_products (id, store_id, product_id, external_id, status, last_seen_at)
prices (id, store_product_id, price, recorded_at)  -- HISTORY table
price_history (id, store_product_id, old_price, new_price, changed_at)
```

## Proposed Daily Scan Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: SCRAPE                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  For each store:                                                 │
│    1. Fetch all product URLs from sitemap/API                    │
│    2. Scrape each product page                                   │
│    3. Save raw to: raw_scrapes/{store}_{YYYYMMDD}.json           │
│    4. Track: urls_found, products_scraped, errors                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: DIFF & SYNC                                            │
│  ─────────────────────────────────────────────────────────────  │
│  For each scraped product:                                       │
│                                                                  │
│  ┌─ NEW? (external_id not in DB)                                │
│  │   → INSERT product                                            │
│  │   → INSERT store_product (status='active')                    │
│  │   → INSERT price                                              │
│  │   → Log: "New product: {name} @ €{price}"                     │
│  │                                                               │
│  ├─ EXISTS + PRICE CHANGED?                                     │
│  │   → UPDATE prices.current_price                               │
│  │   → INSERT price_history (old, new, timestamp)                │
│  │   → UPDATE store_products.last_seen_at                        │
│  │   → Log: "Price change: {name} €{old}→€{new}"                 │
│  │                                                               │
│  └─ EXISTS + SAME PRICE?                                        │
│      → UPDATE store_products.last_seen_at                        │
│      → (No price history entry needed)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3: DETECT DELISTED                                        │
│  ─────────────────────────────────────────────────────────────  │
│  Query: Products with last_seen_at < today                       │
│                                                                  │
│  If not seen in 3+ days:                                         │
│    → UPDATE store_products SET status='inactive'                 │
│    → Log: "Delisted: {name} (last seen: {date})"                 │
│                                                                  │
│  Note: Don't DELETE - keep for history                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4: MATCH & EXPORT                                         │
│  ─────────────────────────────────────────────────────────────  │
│  1. Run matching on active products only                         │
│  2. Export to frontend JSON                                      │
│  3. Git commit + push                                            │
│  4. Generate daily report                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Edge Cases to Handle

### 1. Duplicate Detection
- **Problem:** Same product, different URLs or slight name variations
- **Solution:** Match by `external_id` (store's SKU) first, then fuzzy name match

### 2. Price Spikes/Errors
- **Problem:** Scraper captures wrong price (€999 instead of €9.99)
- **Solution:** Sanity check - flag prices >200% or <20% of previous price

### 3. Currency Confusion
- **Problem:** Some stores show BGN, some EUR
- **Solution:** Always convert to EUR, store original + converted

### 4. Rate Limiting
- **Problem:** Store blocks IP after too many requests
- **Solution:** 
  - Humanized delays (1-3s between requests)
  - Coffee breaks every 50 requests
  - Rotate user agents
  - Respect robots.txt

### 5. Encoding Issues
- **Problem:** Cyrillic characters corrupted
- **Solution:** Always use UTF-8, validate after scrape

### 6. Partial Scrape Failure
- **Problem:** Scrape fails halfway through
- **Solution:** 
  - Save progress incrementally
  - Resume from last successful URL
  - Don't mark products as delisted if scrape failed

### 7. Seasonal/Temporary Products
- **Problem:** Products appear/disappear frequently (weekly offers)
- **Solution:** 
  - Don't mark as delisted until 7+ days missing
  - Tag weekly offer products differently

## Schema Changes Required

```sql
-- Add to store_products
ALTER TABLE store_products ADD COLUMN external_id TEXT;
ALTER TABLE store_products ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE store_products ADD COLUMN last_seen_at TIMESTAMP;
ALTER TABLE store_products ADD COLUMN product_url TEXT;
ALTER TABLE store_products ADD COLUMN image_url TEXT;

-- Add to products
ALTER TABLE products ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE products ADD COLUMN updated_at TIMESTAMP;

-- Create price history table
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY,
    store_product_id INTEGER NOT NULL,
    old_price REAL,
    new_price REAL NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (store_product_id) REFERENCES store_products(id)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_store_products_external_id 
ON store_products(store_id, external_id);

CREATE INDEX IF NOT EXISTS idx_store_products_last_seen 
ON store_products(last_seen_at);
```

## Daily Report Output

```
========================================
PROMOBG DAILY SCAN REPORT - 2026-02-17
========================================

SCRAPE RESULTS:
  Lidl:     1,104 URLs → 450 products (42 errors)
  Kaufland: 2,341 URLs → 891 products (12 errors)
  Billa:    892 URLs → 277 products (5 errors)

CHANGES DETECTED:
  New products:      +23
  Price increases:   47 (avg +8.3%)
  Price decreases:   31 (avg -12.1%)
  Delisted:          8

TOP PRICE DROPS:
  1. Milka Chocolate 100g: €2.99 → €1.49 (-50%)
  2. Coca-Cola 2L: €2.49 → €1.99 (-20%)
  ...

CROSS-STORE MATCHES:
  Total: 217
  New matches: +5

ALERTS:
  ⚠️ Lidl scraper: 42 errors (3.8% failure rate)
  ⚠️ Price spike: "Product X" €9.99 → €99.99 (flagged)

========================================
```

## Implementation Priority

1. **Schema migration** - Add missing columns and tables
2. **Diff & sync logic** - Handle A, B, C scenarios
3. **Delisted detection** - Mark inactive products
4. **Price history** - Track changes over time
5. **Daily report** - Generate summary
6. **Alerting** - Flag anomalies

## Questions for Martin

1. **Delisted threshold:** After how many days should we mark a product as inactive? (suggested: 3-7 days)
2. **Price spike threshold:** What % change should trigger an alert? (suggested: >50% change)
3. **Historical data:** How long to keep price history? (suggested: 90 days)
4. **Weekly offers:** Should we track Lidl's weekly offers separately?
