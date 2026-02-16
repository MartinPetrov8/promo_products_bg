# Kaufland Scraper Documentation

## Overview
Kaufland.bg only publishes **promotional offers** online - no full product catalog available.

## Data Source
- **URL:** `https://www.kaufland.bg/aktualni-predlozheniya/oferti.html`
- **Format:** JSON embedded in HTML (`"offers":[]` arrays)
- **Update frequency:** Weekly (offers change every Thursday)

## Scraper Flow
```
1. Fetch offers page (4.4MB HTML)
2. Extract JSON arrays with regex bracket matching
3. Parse each offer object
4. Filter: only include offers WITH price
5. Output: RawProduct objects
```

## Data Fields Extracted
| Field | Source | Coverage |
|-------|--------|----------|
| SKU | `klNr` | 100% |
| Name | `title` | 100% |
| Subtitle | `subtitle` | ~80% |
| Price BGN | `prices.alternative.formatted.standard` | 100% (filtered) |
| Old Price | `prices.alternative.formatted.old` | ~60% |
| Image | `detailImages[0]` | ~95% |
| Brand | `brand` | ~5% (rarely provided) |

## Products Filtered Out
- **Kaufland Card loyalty offers** (`bonusbuy: true`) - no fixed price, only % discount
- These are "-20% with Kaufland Card" type offers without base price

## Current Stats (2026-02-16)
- Total offers on page: ~1126
- Products with price: **878**
- Products filtered (no price): 128

## Limitations
1. **No full catalog** - Kaufland.bg business model only shows promotional items
2. **Low brand coverage** - brand rarely in JSON
3. **Weekly rotation** - products change every Thursday

## Alternative Sources Investigated
| Source | Status |
|--------|--------|
| `/aktualni-predlozheniya/ot-ponedelnik.html` | Same data as oferti.html |
| `/aktualni-predlozheniya/sledvashta-sedmitsa.html` | Same data |
| `/broshuri.html` | No product data (PDF links only) |
| `/asortiment.html` | Brand pages only, no products |
| Sitemap | No product URLs |
| API | None found |

## Code Location
- **Scraper:** `scrapers/kaufland/scraper.py`
- **Base class:** `scrapers/base.py`

## Usage
```python
from scrapers.kaufland.scraper import KauflandScraper

scraper = KauflandScraper()
if scraper.health_check():
    products = scraper.scrape()
    print(f"Got {len(products)} products")
```
