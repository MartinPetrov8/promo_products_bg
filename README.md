# Promo Products BG

Bulgarian grocery price comparison system with OpenFoodFacts integration.

## Features

- **Multi-store scraping:** Kaufland, Lidl, Billa
- **OFF matching:** 79%+ food products matched to OpenFoodFacts
- **Cross-store comparison:** Same products linked via barcode
- **Nutritional data:** Nutriscore, ingredients, allergens from OFF

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run matching pipeline
python3 scripts/fast_matching_v2.py

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
│   ├── fast_matching_v2.py # Main matching pipeline
│   └── *.py                # Scrapers and utilities
├── apps/
│   └── web/                # Frontend application
└── docs/
    └── MATCHING_PIPELINE.md
```

## Matching Pipeline

| Metric | Value |
|--------|-------|
| Food products | 3,444 |
| Match rate | 79.4% |
| Cross-store links | 179 products |

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
