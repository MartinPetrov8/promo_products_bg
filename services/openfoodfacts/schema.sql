-- Open Food Facts Bulgarian Products Database
-- Downloaded bulk for offline matching

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Main products table
CREATE TABLE IF NOT EXISTS off_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode TEXT UNIQUE NOT NULL,           -- EAN-13/EAN-8 code
    product_name TEXT,                       -- Name in original language
    product_name_bg TEXT,                    -- Bulgarian name if available
    product_name_en TEXT,                    -- English name if available
    brands TEXT,                             -- Brand name(s)
    brands_tags TEXT,                        -- Normalized brand tags (JSON array)
    categories TEXT,                         -- Category string
    categories_tags TEXT,                    -- Normalized category tags (JSON array)
    quantity TEXT,                           -- "500g", "1L", etc.
    serving_size TEXT,
    packaging TEXT,
    
    -- Images
    image_url TEXT,                          -- Main product image
    image_small_url TEXT,                    -- Thumbnail
    image_front_url TEXT,                    -- Front of package
    image_ingredients_url TEXT,              -- Ingredients photo
    image_nutrition_url TEXT,                -- Nutrition label photo
    
    -- Nutrition per 100g
    energy_kcal REAL,
    fat REAL,
    saturated_fat REAL,
    carbohydrates REAL,
    sugars REAL,
    fiber REAL,
    proteins REAL,
    salt REAL,
    
    -- Scores
    nutriscore_grade TEXT,                   -- a/b/c/d/e
    nutriscore_score INTEGER,
    nova_group INTEGER,                      -- 1-4 processing level
    ecoscore_grade TEXT,                     -- a/b/c/d/e
    
    -- Ingredients
    ingredients_text TEXT,
    ingredients_text_bg TEXT,
    allergens TEXT,
    traces TEXT,
    
    -- Labels & certifications
    labels TEXT,
    labels_tags TEXT,
    
    -- Origin
    countries TEXT,
    countries_tags TEXT,
    origins TEXT,
    manufacturing_places TEXT,
    
    -- Metadata
    created_t INTEGER,                       -- Unix timestamp
    last_modified_t INTEGER,
    completeness REAL,                       -- Data completeness score
    
    -- Our matching fields
    normalized_name TEXT,                    -- For our matching algorithm
    normalized_brand TEXT,
    
    -- Timestamps
    downloaded_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for fast matching
CREATE INDEX IF NOT EXISTS idx_off_barcode ON off_products(barcode);
CREATE INDEX IF NOT EXISTS idx_off_brands ON off_products(brands);
CREATE INDEX IF NOT EXISTS idx_off_normalized_name ON off_products(normalized_name);
CREATE INDEX IF NOT EXISTS idx_off_normalized_brand ON off_products(normalized_brand);
CREATE INDEX IF NOT EXISTS idx_off_categories ON off_products(categories_tags);

-- Images table (for tracking downloaded images)
CREATE TABLE IF NOT EXISTS off_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode TEXT NOT NULL,
    image_type TEXT NOT NULL,                -- 'main', 'front', 'ingredients', 'nutrition'
    url TEXT NOT NULL,
    local_path TEXT,                         -- Path to downloaded image
    downloaded INTEGER DEFAULT 0,
    download_error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    
    FOREIGN KEY (barcode) REFERENCES off_products(barcode),
    UNIQUE(barcode, image_type)
);

CREATE INDEX IF NOT EXISTS idx_off_images_barcode ON off_images(barcode);

-- Download progress tracking
CREATE TABLE IF NOT EXISTS off_download_state (
    id INTEGER PRIMARY KEY,
    total_products INTEGER,
    downloaded_products INTEGER,
    last_page INTEGER,
    started_at TEXT,
    completed_at TEXT,
    status TEXT DEFAULT 'pending'            -- pending/running/completed/failed
);
