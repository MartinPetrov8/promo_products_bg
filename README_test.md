# Promo Products BG - Test Documentation

A comprehensive Bulgarian grocery price comparison system with web scraping, data pipeline, and OpenFoodFacts integration. This project automates price monitoring across Kaufland, Lidl, and Billa stores, performs cross-store product matching, and enriches product data with nutritional information from the OpenFoodFacts database.

## Overview

Promo Products BG is a Python-based data pipeline that scrapes promotional product information from Bulgarian grocery stores, normalizes and enriches the data, performs intelligent cross-store matching, and exports the results for a web-based price comparison interface. The system is designed to handle thousands of products daily, with robust error handling and data validation throughout the pipeline.

The project follows a modular architecture with clear separation between scraping, data processing, matching logic, and frontend presentation. All scrapers inherit from a common abstract base class, ensuring consistency across store implementations. The system uses SQLite for persistent storage and supports incremental updates with full audit trails.

## Features

### Multi-Store Scraping
- **Kaufland**: Scrapes 800+ promotional products from the Kaufland Bulgaria website
- **Lidl**: Extracts 300+ products from Lidl's online promotional catalog
- **Billa**: Collects 400+ products from Billa's weekly offers

### Data Pipeline
- Automated scraping with configurable scheduling
- Product normalization and cleaning (brand extraction, quantity parsing, price validation)
- Cross-store product matching using multiple strategies (barcode, token-based, transliteration, embeddings)
- OpenFoodFacts integration for nutritional data enrichment
- JSON export for frontend consumption

### Intelligent Matching
- **Token-based matching**: Normalized product name comparison
- **Barcode matching**: Exact barcode linking across stores
- **Transliteration matching**: Handles Cyrillic/Latin variations
- **Embedding matching**: Uses LaBSE embeddings for semantic similarity
- **Fuzzy matching**: Fallback for near-matches
- Match rate: 63.3% of products successfully matched to OpenFoodFacts

### Database Management
- SQLite databases with optimized indexing
- Full scraping history with scan_runs tracking
- Raw scrapes stored for reprocessing
- Cleaned products with normalized attributes
- Price history tracking across time and stores

### Web Interface
- Static HTML/CSS/JS frontend (no build required)
- Price comparison across stores
- Nutritional information display (Nutriscore, ingredients, allergens)
- Responsive design for mobile and desktop
- Deployed to GitHub Pages

## Tech Stack

### Core Technologies
- **Python 3.x**: Primary programming language for all data processing
- **SQLite**: Lightweight database for product data and OpenFoodFacts cache
- **Dataclasses**: Structured data models with type hints
- **Logging Module**: Comprehensive logging throughout the pipeline

### Scraping & Data Processing
- **HTTP Libraries**: Native Python HTTP clients for web scraping
- **HTML Parsing**: Custom parsers for extracting product data from store websites
- **Abstract Base Classes**: BaseScraper defines the scraper interface
- **Enums**: Type-safe store and category constants

### Matching & ML
- **LaBSE Embeddings**: Language-agnostic sentence embeddings for semantic matching
- **Token-based Matching**: Normalized text comparison with brand/quantity extraction
- **Transliteration**: Cyrillic-to-Latin conversion for cross-script matching
- **Fuzzy String Matching**: Levenshtein distance for near-matches

### Frontend & Deployment
- **Static HTML/CSS/JS**: No framework, vanilla web technologies
- **GitHub Pages**: Automated deployment via GitHub Actions
- **JSON Data Format**: Scraped data exported as JSON for frontend consumption

### Development Tools
- **Git**: Version control with feature branch workflow
- **Vendored Dependencies**: Dependencies stored in .pylibs/ directory
- **Direct Script Execution**: No build step, Python scripts run directly

## Architecture

### System Design Overview

Promo Products BG follows a multi-stage pipeline architecture that transforms raw promotional data from Bulgarian grocery stores into enriched, matchable product information for web-based price comparison.

```text
┌─────────────┐    ┌────────────────┐    ┌──────────────┐    ┌─────────────┐
│  Scrapers   │───▶│ Normalization  │───▶│   Matching   │───▶│  Export     │
│  (K/L/B)    │    │ & Enrichment   │    │   Pipeline   │    │  & API      │
└─────────────┘    └────────────────┘    └──────────────┘    └─────────────┘
     │                    │                     │                    │
     ▼                    ▼                     ▼                    ▼
 Raw JSON          Product Cleaning      OFF Integration      JSON Export
 Scrapes           Brand/Qty Extract     Cross-Store Match    GitHub Pages
```

**Data Flow:**

1. **Scraping Layer** - Store-specific scrapers extract promotional products
   - Kaufland: 800+ products from website
   - Lidl: 300+ products from promotional catalog
   - Billa: 400+ products from weekly offers
   - Raw data saved to JSON files for audit trail

2. **Normalization Layer** - Product cleaning and enrichment
   - Brand extraction from product names
   - Quantity parsing (weights, volumes, multipacks)
   - Price validation and currency conversion
   - Text normalization (Cyrillic/Latin handling)

3. **Matching Layer** - Multi-strategy product matching
   - **Barcode matching**: Exact EAN lookup (100% confidence)
   - **Token matching**: Weighted Jaccard similarity on tokenized names
   - **Transliteration matching**: Cyrillic→Latin conversion for cross-script matching
   - **Embedding matching**: LaBSE semantic similarity (≥0.75 threshold)
   - **Fuzzy matching**: SequenceMatcher fallback for near-matches

4. **Export Layer** - API and frontend data generation
   - JSON export for web interface
   - Cross-store price comparison data
   - Nutritional information from OpenFoodFacts
   - Static site deployment to GitHub Pages

### Database Architecture

The system uses two SQLite databases for persistent storage:

#### 1. promobg.db (Main Product Database)

**Core Tables:**
- `scan_runs` - Tracks each scraping run (timestamp, store, product count, status)
- `raw_scrapes` - Raw scraped data for historical tracking and reprocessing
- `products` - Cleaned and normalized product data with extracted attributes
- `prices` - Current and historical price data across stores
- `store_products` - Store-specific product information (SKU, URL, image, status)
- `cross_store_matches` - Links between products across different stores
- `product_off_matches` - Links between store products and OpenFoodFacts entries

**Schema Highlights:**
```sql
products (
    id, name, normalized_name, brand,
    quantity, unit, category_code, category_name,
    barcode_ean, image_url, created_at, updated_at
)

store_products (
    id, product_id, store_id,
    external_id, status, last_seen_at,
    product_url, image_url
)

prices (
    id, store_product_id,
    current_price, old_price, discount_percent,
    recorded_at
)

product_off_matches (
    id, product_id, off_product_id,
    match_type, match_confidence, is_verified,
    created_at
)
```

#### 2. off_bulgaria.db (OpenFoodFacts Cache)

- **Purpose**: Local cache of OpenFoodFacts Bulgaria entries for offline matching
- **Size**: 14,853 products with nutritional data
- **Contents**: Product names, barcodes, Nutri-Score, ingredients, allergens
- **Update**: Periodic sync with OpenFoodFacts API

### Matching Pipeline

The matching pipeline connects store products to OpenFoodFacts entries and enables cross-store price comparison through a three-phase approach:

**Phase 1a: Token & Barcode Matching**
- Barcode match (100% confidence): Exact EAN lookup in OFF database
- Token match (60-95% confidence): Weighted Jaccard similarity on normalized tokens
- Fuzzy match (40-60% confidence): SequenceMatcher fallback for partial matches
- **Result**: 2,716 matches (2,415 token + 288 barcode + 13 fuzzy)

**Phase 1b: Transliteration Matching**
- Cyrillic→Latin transliteration for unmatched products
- Confidence tiers:
  - `translit_confident` (≥0.85): 11 matches
  - `translit_likely` (0.75-0.84): 61 matches
  - `translit_low` (0.60-0.74): 433 matches
- **Result**: +505 additional matches

**Phase 2: Embedding-Based Semantic Matching**
- LaBSE (Language-agnostic BERT Sentence Embeddings)
- Cosine similarity ≥0.75 threshold
- Confidence tiers:
  - `embedding_confident` (≥0.85): 1 match
  - `embedding_likely` (0.75-0.84): 13 matches
- **Result**: +14 additional matches

**Overall Performance:**
- **Total store products**: 5,113
- **Successfully matched**: 3,235 (63.3%)
- **Unmatched**: 1,878 (primarily local Bulgarian brands not in OpenFoodFacts)

### Match Type Distribution

| Match Type | Count | Confidence Range | Use Case |
|------------|-------|------------------|----------|
| token | 2,415 | 60-95% | Primary matching method |
| translit_low | 433 | 60-74% | Cyrillic/Latin variations |
| barcode | 288 | 100% | Exact product identification |
| translit_likely | 61 | 75-84% | High-confidence transliteration |
| fuzzy | 13 | 40-60% | Near-match fallback |
| embedding_likely | 13 | 75-84% | Semantic similarity |
| translit_confident | 11 | ≥85% | Very high-confidence transliteration |
| embedding_confident | 1 | ≥85% | Very high semantic similarity |

### Cross-Store Matching

Products from different stores can be linked via shared OpenFoodFacts barcode, enabling price comparison:

```sql
-- Find same products across multiple stores
SELECT off_product_id, GROUP_CONCAT(DISTINCT store_name)
FROM product_off_matches pom
JOIN products p ON pom.product_id = p.id
JOIN store_products sp ON sp.product_id = p.id
JOIN stores s ON sp.store_id = s.id
GROUP BY off_product_id
HAVING COUNT(DISTINCT s.id) > 1;
```

### Performance Metrics

**Current System Performance:**
- **Products processed**: 5,113 across 3 stores
- **Match rate**: 63.3% (3,235/5,113 matched to OpenFoodFacts)
- **Cross-store groups**: 162 high-quality matches (0.92+ confidence)
- **Price comparison coverage**: 82 products with valid cross-store pricing
- **Categories classified**: 29 GS1 GPC categories
- **Daily scraping capacity**: 1,500+ products per run
- **Average scrape time**: 15-20 minutes for all stores
- **Database size**: ~50MB (promobg.db + off_bulgaria.db)

**Store-Level Metrics:**

| Store | Products | Brand Coverage | Quantity Coverage | Avg Price |
|-------|----------|----------------|-------------------|-----------|
| Kaufland | 800+ | 68% | 39% | €2.50 |
| Lidl | 300+ | 37% | 33% | €2.20 |
| Billa | 400+ | 35% | 53% | €2.80 |

### Related Documentation

For detailed architecture documentation, see:
- **[DAILY_SCAN_ARCHITECTURE.md](./DAILY_SCAN_ARCHITECTURE.md)** - Daily scraping workflow and incremental updates
- **[MATCHING_PIPELINE.md](./docs/MATCHING_PIPELINE.md)** - Detailed matching algorithm documentation
- **[DATA_PIPELINE.md](./docs/DATA_PIPELINE.md)** - Complete data flow and transformation pipeline
- **[ARCHITECTURE.md](./docs/ARCHITECTURE.md)** - System overview and component design

## Project Structure

```text
promo_products_bg/
├── main.py                          # CLI entry point (scrape/clean/match/export)
├── scrapers/                        # Store-specific scrapers
│   ├── base.py                     # BaseScraper abstract class + RawProduct dataclass
│   ├── kaufland/
│   │   └── scraper.py              # KauflandScraper implementation
│   ├── billa/
│   │   └── scraper.py              # BillaScraper implementation
│   └── lidl/
│       └── scraper.py              # LidlScraper implementation
├── scripts/                         # Data processing pipeline scripts
│   ├── db_pipeline.py              # PromoBGDatabase context manager
│   ├── clean_products_hybrid.py    # Product normalization & enrichment
│   ├── cross_store_matcher.py     # Multi-strategy product matching
│   ├── export_frontend.py         # JSON export for web app
│   └── matching_pipeline.py       # Orchestrates full matching workflow
├── services/                        # Service layer modules
│   ├── api_service.py              # API endpoints (if applicable)
│   ├── database_service.py         # Database abstraction layer
│   ├── matching_service.py         # Matching logic encapsulation
│   └── off_service.py              # OpenFoodFacts integration
├── data/                            # SQLite databases & indices
│   ├── promobg.db                  # Main product database
│   ├── off_bulgaria.db             # OpenFoodFacts Bulgaria cache (14,853 products)
│   └── indices/                    # Token and brand indices for matching
├── apps/web/                        # Static HTML frontend
│   ├── index.html                  # Main page
│   ├── styles.css                  # Styling
│   └── script.js                   # Client-side logic
├── docs/                            # Documentation
│   ├── MATCHING_PIPELINE.md        # Detailed matching algorithm documentation
│   └── *.md                        # Additional documentation files
├── .pylibs/                         # Vendored Python dependencies
├── .github/workflows/
│   └── pages.yml                   # GitHub Pages deployment workflow
├── test_all_scrapers.py            # Integration test for all scrapers
└── README.md                        # Main project README
```

## Quick Start

### Prerequisites
- Python 3.8 or higher
- SQLite3
- Git

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd promo_products_bg

# No package installation needed (dependencies vendored in .pylibs/)
```

### Running the Pipeline

```bash
# Run all scrapers and process data
python3 main.py all

# Run individual scrapers
python3 -m scrapers.kaufland.scraper
python3 -m scrapers.lidl.scraper
python3 -m scrapers.billa.scraper

# Run matching pipeline
python3 scripts/matching_pipeline.py

# Export data for frontend
python3 scripts/export_frontend.py
```

### Testing

```bash
# Run integration tests for all scrapers
python3 test_all_scrapers.py

# Expected output:
# Kaufland: 877 products scraped (66.7% with brand)
# Billa: 497 products scraped (64.0% with brand)
# Lidl: 374 products scraped (43.3% with brand)
```

### Viewing the Web Interface

```bash
# Open the local frontend
cd apps/web
python3 -m http.server 8000
# Navigate to http://localhost:8000

# Or view the live deployment
# https://martinpetrov8.github.io/promo-products
```

## Database Schema

The SQLite database (`data/promobg.db`) contains the following key tables:

- **scan_runs**: Tracks each scraping run with timestamp, store, product count, and status
- **raw_scrapes**: Stores raw scraped data for historical tracking and reprocessing
- **products**: Cleaned and normalized product data with extracted attributes
- **prices**: Price history across stores and time periods
- **product_matches**: Cross-store product links (barcode, token, embedding matches)
- **off_matches**: Links between promobg products and OpenFoodFacts entries

## Scraping Architecture

All scrapers follow a consistent pattern defined by the `BaseScraper` abstract base class:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class RawProduct:
    name: str
    price: Optional[float]
    image_url: Optional[str]
    store: str
    # ... additional fields

class BaseScraper(ABC):
    @property
    @abstractmethod
    def store(self) -> Store:
        """Return the Store enum value"""
        pass
    
    @abstractmethod
    def scrape(self) -> List[RawProduct]:
        """Main scraping logic, returns list of RawProduct instances"""
        pass
    
    def health_check(self) -> bool:
        """Optional: Check if scraper can run successfully"""
        return True
```

### Error Handling Pattern

All scrapers implement robust error handling:
- Try/except blocks around HTTP requests and parsing
- Logging of errors with context (store, product, URL)
- Graceful degradation (return partial results on non-critical errors)
- Validation of results (minimum product count, price coverage thresholds)

## Naming Conventions

The codebase follows strict naming conventions:

- **Files**: snake_case.py (e.g., `db_pipeline.py`, `cross_store_matcher.py`)
- **Classes**: PascalCase (e.g., `KauflandScraper`, `BaseScraper`, `RawProduct`)
- **Functions/Methods**: snake_case (e.g., `scrape()`, `parse_bgn_price()`, `extract_brand_from_name()`)
- **Variables**: snake_case (e.g., `product_list`, `match_rate`, `total_count`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `OFFERS_URL`, `KNOWN_BRANDS`, `MIN_PRODUCTS`)
- **Private Helpers**: Prefix with underscore (e.g., `_extract_offers()`, `_parse_offer()`)

## Development Workflow

1. **Make Changes**: Edit scrapers or pipeline scripts
2. **Test Locally**: Run `python3 test_all_scrapers.py` or individual scripts
3. **Check Logs**: Review logs for errors or warnings
4. **Run Full Pipeline**: Execute `python3 main.py all` to verify end-to-end flow
5. **Commit**: Use conventional commit messages (e.g., `feat:`, `fix:`, `docs:`)
6. **Deploy**: Push to main branch triggers GitHub Pages deployment

## Contributing

This project follows these development patterns:

- **Type Hints**: All functions use type hints (`Optional[str]`, `List[RawProduct]`, etc.)
- **Dataclasses**: Use `@dataclass` for structured data models
- **Logging**: Use Python's logging module, not print() for operational messages
- **No Build Step**: Python scripts run directly, no compilation required
- **Transaction Safety**: Database operations wrapped in transactions
- **Idempotent Scripts**: All scripts safe to re-run without side effects

## License

MIT License - see LICENSE file for details

## Contact

For questions or issues, please open an issue on the GitHub repository.

---

**Note**: This is test documentation for the Promo Products BG project. For the main documentation, see README.md.
