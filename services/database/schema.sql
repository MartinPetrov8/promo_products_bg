-- PromoBG Database Schema
-- SQLite-compatible (MVP), PostgreSQL upgrade path in comments
-- 
-- Created: 2026-02-12
-- Version: 1.0

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;  -- Better concurrent read performance

-- ============================================
-- CATEGORIES: Hierarchical product categories
-- ============================================
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                          -- Български: "Храни", "Млечни"
    normalized_name TEXT NOT NULL,               -- For matching/search
    parent_id INTEGER,
    level INTEGER DEFAULT 0,                     -- Depth: 0=root, 1=child, etc.
    path TEXT,                                   -- Materialized path: "1.5.12"
    sort_order INTEGER DEFAULT 0,
    icon_url TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT,
    
    FOREIGN KEY (parent_id) REFERENCES categories(id)
);

CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_categories_path ON categories(path);
CREATE INDEX IF NOT EXISTS idx_categories_normalized ON categories(normalized_name);

-- ============================================
-- STORES: Supermarket chains
-- ============================================
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,                   -- 'kaufland', 'lidl', etc.
    name TEXT NOT NULL,                          -- 'Kaufland'
    display_name TEXT NOT NULL,                  -- 'Kaufland България'
    logo_url TEXT,
    website TEXT,
    has_api INTEGER DEFAULT 0,                   -- Has machine-readable feed?
    api_url TEXT,                                -- JSON/XML feed URL if available
    api_format TEXT,                             -- 'json', 'xml', 'rss'
    scrape_config TEXT,                          -- JSON: urls, selectors, etc.
    scrape_schedule TEXT,                        -- Cron expression
    currency TEXT DEFAULT 'EUR',                 -- EUR since Feb 2026
    is_active INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_stores_code ON stores(code);
CREATE INDEX IF NOT EXISTS idx_stores_active ON stores(is_active) WHERE is_active = 1;

-- ============================================
-- PRODUCTS: Canonical product records
-- ============================================
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,               -- Lowercase, stripped for matching
    brand TEXT,
    category_id INTEGER,
    unit TEXT DEFAULT 'бр',                      -- kg, g, L, ml, бр
    quantity REAL,                               -- Weight/volume per unit
    barcode_ean TEXT,                            -- EAN-13 or EAN-8
    image_url TEXT,
    description TEXT,
    is_verified INTEGER DEFAULT 0,
    match_confidence REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT,
    
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE INDEX IF NOT EXISTS idx_products_normalized ON products(normalized_name);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode_ean);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(deleted_at) WHERE deleted_at IS NULL;

-- ============================================
-- STORE_PRODUCTS: Junction + store-specific data
-- ============================================
CREATE TABLE IF NOT EXISTS store_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    store_product_code TEXT NOT NULL,            -- Store's internal SKU/ID
    store_product_url TEXT,
    store_image_url TEXT,
    name_override TEXT,                          -- If store uses different name
    package_size TEXT,                           -- "500 гр", "6x330 мл"
    is_available INTEGER DEFAULT 1,
    last_seen_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT,
    
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (store_id) REFERENCES stores(id),
    UNIQUE(store_id, store_product_code)
);

CREATE INDEX IF NOT EXISTS idx_store_products_product ON store_products(product_id);
CREATE INDEX IF NOT EXISTS idx_store_products_store ON store_products(store_id);
CREATE INDEX IF NOT EXISTS idx_store_products_last_seen ON store_products(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_store_products_available ON store_products(is_available) WHERE is_available = 1;

-- ============================================
-- PRICES: Current price data
-- ============================================
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_product_id INTEGER NOT NULL,
    current_price REAL NOT NULL,
    old_price REAL,                              -- Before discount
    discount_percent REAL,
    price_per_unit REAL,                         -- Normalized (per kg/L)
    price_per_unit_base TEXT,                    -- 'kg', 'L', 'бр'
    currency TEXT NOT NULL DEFAULT 'EUR',
    valid_from TEXT NOT NULL,
    valid_to TEXT,                               -- NULL = active
    is_promotional INTEGER DEFAULT 0,
    promotion_label TEXT,                        -- "2+1", "-30%"
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (store_product_id) REFERENCES store_products(id)
);

CREATE INDEX IF NOT EXISTS idx_prices_store_product ON prices(store_product_id);
CREATE INDEX IF NOT EXISTS idx_prices_current ON prices(store_product_id, valid_from) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_prices_promo ON prices(is_promotional) WHERE is_promotional = 1;

-- ============================================
-- PRICE_HISTORY: Archive of all price changes
-- ============================================
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_product_id INTEGER NOT NULL,
    price REAL NOT NULL,
    old_price REAL,
    discount_percent REAL,
    price_per_unit REAL,
    currency TEXT DEFAULT 'EUR',
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    scrape_run_id INTEGER,
    is_promotional INTEGER DEFAULT 0,
    promotion_label TEXT,
    
    FOREIGN KEY (store_product_id) REFERENCES store_products(id),
    FOREIGN KEY (scrape_run_id) REFERENCES scrape_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(store_product_id);
CREATE INDEX IF NOT EXISTS idx_price_history_recorded ON price_history(store_product_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(recorded_at);

-- ============================================
-- SCRAPE_RUNS: Track scraper executions
-- ============================================
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    status TEXT DEFAULT 'running',               -- running, success, partial_failure, failed
    tier_used INTEGER DEFAULT 1,                 -- Which tier: 1=direct, 2=aggregator, 3=cache
    products_found INTEGER DEFAULT 0,
    products_updated INTEGER DEFAULT 0,
    products_added INTEGER DEFAULT 0,
    errors TEXT,                                 -- JSON array
    duration_seconds INTEGER,
    
    FOREIGN KEY (store_id) REFERENCES stores(id)
);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_store ON scrape_runs(store_id);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_started ON scrape_runs(started_at);

-- ============================================
-- PRODUCT_MATCHES: Fuzzy matching links
-- ============================================
CREATE TABLE IF NOT EXISTS product_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_a_id INTEGER NOT NULL,
    product_b_id INTEGER NOT NULL,
    match_confidence REAL NOT NULL,
    match_type TEXT DEFAULT 'automatic',         -- automatic, manual, suggested, rejected
    matched_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT,
    
    FOREIGN KEY (product_a_id) REFERENCES products(id),
    FOREIGN KEY (product_b_id) REFERENCES products(id),
    UNIQUE(product_a_id, product_b_id),
    CHECK (product_a_id < product_b_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_product_a ON product_matches(product_a_id);
CREATE INDEX IF NOT EXISTS idx_matches_product_b ON product_matches(product_b_id);
CREATE INDEX IF NOT EXISTS idx_matches_confidence ON product_matches(match_confidence);

-- ============================================
-- PRICE_STATISTICS: Pre-computed analytics
-- ============================================
CREATE TABLE IF NOT EXISTS price_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_product_id INTEGER NOT NULL UNIQUE,
    avg_price_30d REAL,
    avg_price_90d REAL,
    min_price_ever REAL,
    max_price_ever REAL,
    price_volatility REAL,
    deal_threshold REAL,                         -- Price below this = "good deal"
    trend_direction TEXT,                        -- rising, falling, stable
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (store_product_id) REFERENCES store_products(id)
);

CREATE INDEX IF NOT EXISTS idx_stats_product ON price_statistics(store_product_id);

-- ============================================
-- DB_METRICS: Track database size for monitoring
-- ============================================
CREATE TABLE IF NOT EXISTS db_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    db_size_bytes INTEGER,
    products_count INTEGER,
    store_products_count INTEGER,
    prices_count INTEGER,
    price_history_count INTEGER,
    scrape_runs_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_db_metrics_date ON db_metrics(recorded_at);

-- ============================================
-- SEED DATA: Bulgarian supermarket chains
-- ============================================
INSERT OR IGNORE INTO stores (code, name, display_name, website, is_active, priority) VALUES
    ('kaufland', 'Kaufland', 'Kaufland България', 'https://www.kaufland.bg', 1, 1),
    ('lidl', 'Lidl', 'Lidl България', 'https://www.lidl.bg', 1, 2),
    ('billa', 'Billa', 'Billa България', 'https://www.billa.bg', 1, 3),
    ('metro', 'Metro', 'Metro Cash & Carry', 'https://www.metro.bg', 0, 4),
    ('fantastico', 'Fantastico', 'Фантастико', 'https://www.fantastico.bg', 0, 5);

-- ============================================
-- SEED DATA: Top-level categories
-- ============================================
INSERT OR IGNORE INTO categories (id, name, normalized_name, level, path) VALUES
    (1, 'Храни', 'храни', 0, '1'),
    (2, 'Напитки', 'напитки', 0, '2'),
    (3, 'Домакинство', 'домакинство', 0, '3'),
    (4, 'Хигиена', 'хигиена', 0, '4'),
    (5, 'Замразени', 'замразени', 0, '5');

INSERT OR IGNORE INTO categories (id, name, normalized_name, parent_id, level, path) VALUES
    (10, 'Млечни продукти', 'млечни продукти', 1, 1, '1.10'),
    (11, 'Месо', 'месо', 1, 1, '1.11'),
    (12, 'Плодове и зеленчуци', 'плодове и зеленчуци', 1, 1, '1.12'),
    (13, 'Хляб и тестени', 'хляб и тестени', 1, 1, '1.13'),
    (14, 'Консерви', 'консерви', 1, 1, '1.14'),
    (20, 'Безалкохолни', 'безалкохолни', 2, 1, '2.20'),
    (21, 'Алкохолни', 'алкохолни', 2, 1, '2.21'),
    (22, 'Кафе и чай', 'кафе и чай', 2, 1, '2.22');
