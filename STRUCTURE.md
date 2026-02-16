# PromoBG Project Structure

## Canonical Location
`/host-workspace/promo_products_bg/` - This is the main repo

## Directory Structure

```
promo_products_bg/
├── data/                      # Data files (LOCAL ONLY - gitignored)
│   ├── promobg.db            # Main SQLite database (768KB)
│   ├── off_bulgaria.db       # OpenFoodFacts Bulgaria (26MB)
│   ├── off_embeddings.npy    # Pre-computed embeddings (38MB)
│   ├── categories.json       # Category definitions
│   ├── indices/              # Search indices
│   └── brochures/            # Scraped brochure PDFs
│
├── standardization/          # Data standardization pipeline
│   ├── cleaner_final.py      # Main cleaner (v3)
│   ├── brand_extractor.py    # Brand detection
│   ├── quantity_parser.py    # Size parsing (kg, L, etc)
│   └── category_classifier.py
│
├── services/                 # Backend services
│   ├── scraper/             # Store scrapers
│   │   └── data/            # Scraped JSON files
│   ├── database/            # DB operations
│   ├── matching/            # Cross-store matching
│   └── openfoodfacts/       # OFF integration
│
├── scripts/                  # One-off and utility scripts
│   ├── export_frontend_data_v2.py
│   ├── build_cross_store_matches.py
│   └── qa_cleanup.py
│
├── docs/                     # Documentation
│   └── data/                # Frontend JSON (GitHub Pages)
│       ├── products.json    # Main product data
│       └── products_standardized.json
│
├── apps/
│   └── web/                 # Web frontend
│       └── data/            # Frontend data copy
│
└── api/                     # REST API
```

## Gitignored Files (Local Only)
- `*.db` - SQLite databases
- `*.npy` - NumPy arrays (embeddings)
- `data/brochures/` - Large PDFs
- `services/scraper/data/*.json` - Scraped data (regenerable)

## GitHub Pages
- Served from `/docs/` folder
- URL: https://martinpetrov8.github.io/promo_products_bg/

## Database Schema

### promobg.db
- `products` - 1323 rows (canonical products)
- `stores` - 3 rows (Kaufland, Lidl, Billa)
- `store_products` - Store-specific product entries
- `prices` - Current prices
- `brand_patterns` - Brand detection patterns
- `cross_store_matches` - Cross-store match groups

### off_bulgaria.db  
- `off_products` - 14853 OpenFoodFacts products
- `off_images` - 24154 product images

## Data Flow

```
Scrapers → Raw JSON → Standardization → SQLite DB → Matcher → Frontend JSON
```
