-- PromoBG Database Schema
-- Version: 2.0 (2026-02-16)

-- Stores table
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- Scan runs tracking
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running',  -- running, completed, failed
    products_scraped INTEGER DEFAULT 0,
    new_products INTEGER DEFAULT 0,
    price_changes INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    error_log TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

-- Raw scrapes (append-only historical data)
CREATE TABLE IF NOT EXISTS raw_scrapes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL,
    store TEXT NOT NULL,
    sku TEXT NOT NULL,
    raw_name TEXT,
    raw_subtitle TEXT,
    raw_description TEXT,
    brand TEXT,
    price_bgn REAL,
    old_price_bgn REAL,
    discount_pct REAL,
    image_url TEXT,
    product_url TEXT,
    scraped_at TIMESTAMP NOT NULL,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_raw_scrapes_run_id ON raw_scrapes(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_raw_scrapes_store_sku ON raw_scrapes(store, sku);
CREATE INDEX IF NOT EXISTS idx_raw_scrapes_scraped_at ON raw_scrapes(scraped_at);
CREATE INDEX IF NOT EXISTS idx_scan_runs_store_status ON scan_runs(store_id, status);
CREATE INDEX IF NOT EXISTS idx_scan_runs_completed ON scan_runs(completed_at DESC);

-- Master products table (cleaned/enriched)
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT,
    brand TEXT,
    category TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store-specific product links
CREATE TABLE IF NOT EXISTS store_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    external_id TEXT,  -- Store's SKU
    status TEXT DEFAULT 'active',
    last_seen_at TIMESTAMP,
    product_url TEXT,
    image_url TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Current prices
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_product_id INTEGER NOT NULL,
    current_price REAL,
    old_price REAL,
    discount_pct REAL,
    scraped_at TIMESTAMP,
    FOREIGN KEY (store_product_id) REFERENCES store_products(id)
);

-- Price history
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_product_id INTEGER NOT NULL,
    old_price REAL,
    new_price REAL,
    change_pct REAL,
    changed_at TIMESTAMP,
    FOREIGN KEY (store_product_id) REFERENCES store_products(id)
);

-- Cross-store matches
CREATE TABLE IF NOT EXISTS cross_store_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT,
    canonical_brand TEXT,
    canonical_quantity REAL,
    canonical_unit TEXT,
    match_type TEXT,
    confidence REAL,
    store_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
