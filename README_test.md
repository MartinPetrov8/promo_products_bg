# Promo Products BG

Bulgarian grocery price comparison system with OpenFoodFacts integration.

## Features

- **Multi-store scraping:** Kaufland, Lidl, Billa promotional products
- **OFF matching:** 63.3% products matched to OpenFoodFacts database
- **Cross-store comparison:** Same products linked via barcode and advanced matching
- **Nutritional data:** Nutriscore, ingredients, allergens from OpenFoodFacts
- **Price tracking:** Historical pricing data across all three major stores
- **Web interface:** Interactive frontend for browsing and comparing products

## Quick Start

```bash
# Install dependencies (vendored in .pylibs/)
# No external dependencies required

# Run all scrapers
python3 main.py scrape

# Clean and normalize products
python3 main.py clean

# Run matching pipeline
python3 main.py match

# Export data for frontend
python3 main.py export

# Or run full pipeline
python3 main.py all

# Test all scrapers
python3 test_all_scrapers.py
```

## Technology Stack

- **Language:** Python 3.x with type hints
- **API Framework:** FastAPI with uvicorn (REST API endpoints)
- **Database:** SQLite (promobg.db, off_bulgaria.db)
- **Web Scrapers:** Custom scrapers for Kaufland, Lidl, and Billa
- **Data Models:** Python dataclasses with strict typing
- **Matching:** Hybrid pipeline (token, transliteration, barcode, embeddings, fuzzy)
- **Frontend:** Static HTML/CSS/JS (deployed via GitHub Pages)

## Store Coverage

### Kaufland
- **Product Count:** ~877 promotional products
- **Brand Coverage:** 66.7% products with identified brands
- **Data Quality:** High - structured product data with clear pricing

### Lidl
- **Product Count:** ~374 promotional products  
- **Brand Coverage:** 43.3% products with identified brands
- **Data Quality:** Moderate - requires additional parsing for brand extraction

### Billa
- **Product Count:** ~497 promotional products
- **Brand Coverage:** 64.0% products with identified brands
- **Data Quality:** High - consistent product naming and pricing

## Project Structure

```
promo_products_bg/
├── data/
│   ├── promobg.db          # Main database (products, prices, matches)
│   ├── off_bulgaria.db     # OpenFoodFacts Bulgaria (14,853 products)
│   └── indices/            # Token/brand indices for matching
├── scripts/
│   ├── matching_pipeline.py          # Hybrid matching pipeline
│   ├── phase2_embeddings_fixed.py    # LaBSE embedding matcher
│   ├── db_pipeline.py                # Database operations
│   ├── clean_products_hybrid.py      # Product normalization
│   ├── cross_store_matcher.py        # Cross-store product linking
│   └── export_frontend.py            # JSON export for web app
├── scrapers/
│   ├── base.py              # BaseScraper abstract class + RawProduct
│   ├── kaufland/scraper.py  # Kaufland scraper implementation
│   ├── billa/scraper.py     # Billa scraper implementation
│   └── lidl/scraper.py      # Lidl scraper implementation
├── services/
│   ├── database.py          # Database service layer
│   ├── matching.py          # Matching service
│   └── openfoodfacts.py     # OFF integration service
├── apps/
│   └── web/                 # Frontend application
│       ├── index.html
│       ├── styles.css
│       └── app.js
└── docs/
    └── MATCHING_PIPELINE.md # Detailed matching documentation
```

## Matching Pipeline

The matching pipeline uses a hybrid approach to link store products with OpenFoodFacts database entries:

| Metric | Value |
|--------|-------|
| Total products | 5,113 |
| Match rate | 63.3% |
| Matched products | 3,235 |
| Unmatched products | 1,878 |

### Match Breakdown by Type

| Match Type | Count | Description |
|------------|-------|-------------|
| Token | 2,415 | Token-based matching on normalized names |
| Transliteration | 505 | Cyrillic-Latin transliteration matching |
| Barcode | 288 | Direct barcode matching |
| Embedding | 14 | LaBSE semantic similarity |
| Fuzzy | 13 | Fuzzy string matching |

### OpenFoodFacts Integration

- **Database:** 14,853 Bulgarian products from OpenFoodFacts
- **Match Rate:** 63.3% of store products successfully matched
- **Data Enrichment:** Matched products gain Nutriscore, ingredients, allergens, nutritional facts
- **Update Frequency:** OFF database updated periodically

See [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md) for detailed technical documentation.

## Database

SQLite databases in `data/`:

### promobg.db
Main application database containing:
- **products:** Normalized product catalog
- **prices:** Historical pricing data
- **raw_scrapes:** Raw scraper output
- **scan_runs:** Scrape execution metadata
- **cross_store_matches:** Product links across stores
- **off_matches:** Links to OpenFoodFacts database

### off_bulgaria.db
OpenFoodFacts Bulgarian product database:
- 14,853 products with barcodes
- Nutritional information
- Ingredients and allergens
- Nutriscore ratings
- Product categories

## API/Frontend

Web application located at `apps/web/`:

### Features
- Browse promotional products from all stores
- Compare prices across Kaufland, Lidl, and Billa
- View nutritional information from OpenFoodFacts
- Filter by store, category, and Nutriscore
- Historical price trends

### Deployment
Live site: [martinpetrov8.github.io/promo-products](https://martinpetrov8.github.io/promo-products)

Deployed via GitHub Pages (`.github/workflows/pages.yml`)

### Architecture
- **Static Site:** No backend server required
- **Data Source:** JSON files exported by `scripts/export_frontend.py`
- **Updates:** Automated export process regenerates JSON on each scrape

## Testing

```bash
# Run all scraper tests
python3 test_all_scrapers.py

# Run specific component tests
python3 scripts/test_matching.py
python3 scripts/test_database.py
```

### Test Coverage
- Scraper validation (minimum product counts, price coverage)
- Database integrity checks
- Matching pipeline accuracy
- Export format validation

## Development Workflow

1. **Scrape:** Collect data from stores
2. **Clean:** Normalize product names, extract brands/quantities
3. **Match:** Link products to OpenFoodFacts and across stores
4. **Export:** Generate JSON for frontend
5. **Deploy:** GitHub Pages auto-deploys from docs/

## License

MIT
