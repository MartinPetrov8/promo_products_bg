# Promo Products BG

Bulgarian grocery price comparison system with OpenFoodFacts integration.

## Features

- **Multi-store scraping:** Kaufland, Lidl, Billa
- **OFF matching:** 63%+ products matched to OpenFoodFacts
- **Cross-store comparison:** Same products linked via barcode
- **Nutritional data:** Nutriscore, ingredients, allergens from OFF

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run matching pipeline
python3 scripts/matching_pipeline.py

# Start web interface
cd apps/web && npm run dev
```

## Project Structure

```
repo/
├── data/
│   ├── promobg.db          # Main database
│   ├── off_bulgaria.db     # OpenFoodFacts Bulgaria
│   └── indices/            # Token/brand indices
├── scripts/
│   ├── matching_pipeline.py       # Hybrid matching pipeline
│   ├── phase2_embeddings_fixed.py # LaBSE embedding matcher
│   └── *.py                       # Scrapers and utilities
├── apps/
│   └── web/                # Frontend application
└── docs/
    └── MATCHING_PIPELINE.md
```

## Matching Pipeline

| Metric | Value |
|--------|-------|
| Total products | 5,113 |
| Match rate | 63.3% |
| Matched | 3,235 |

### Match Breakdown
| Type | Count |
|------|-------|
| Token | 2,415 |
| Transliteration | 505 |
| Barcode | 288 |
| Embedding | 14 |
| Fuzzy | 13 |

See [docs/MATCHING_PIPELINE.md](docs/MATCHING_PIPELINE.md) for details.

## Database

SQLite databases in `data/`:
- **promobg.db:** Store products, prices, matches
- **off_bulgaria.db:** 14,853 Bulgarian OFF products

## API/Frontend

Web app at `apps/web/` displays price comparisons with OFF data.

Live: [martinpetrov8.github.io/promo-products](https://martinpetrov8.github.io/promo-products)

## License

MIT
