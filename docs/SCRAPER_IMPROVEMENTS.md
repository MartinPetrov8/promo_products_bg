# Scraper Improvements Log

## Date: 2026-02-17
## Objective: Maximize brand, quantity, description, and discount extraction across all 3 stores

---

## Before (Phase 3 baseline — commit 5668acc)

| Store     | Products | Brand  | Quantity | Description | Old Price |
|-----------|----------|--------|----------|-------------|-----------|
| Kaufland  | 890      | 86.3%* | 7.5%*    | ~0%         | ~0%       |
| Billa     | 277      | 78.9%* | 93.6%*   | ~0%         | partial   |
| Lidl      | 339      | 66.2%* | 0%*      | ~0%         | ~0%       |
| **Total** | 1,506    | ~77%*  | ~22%     | ~0%         | partial   |

*These numbers were from the DB after OCR/pipeline processing, not raw scraper output.
Actual raw scraper output was much worse — brands and quantities were not being extracted at scrape time.

## After (commit 87288eb)

| Store     | Products | Brand  | Quantity | Description | Old Price |
|-----------|----------|--------|----------|-------------|-----------|
| Kaufland  | 878      | 63.3%  | 73.7%    | 99.3%       | 71.3%     |
| Billa     | 497      | 46.5%  | 97.0%    | 100%        | 44.9%     |
| Lidl      | 375      | 43.2%  | 69.6%    | 100%        | 34.1%     |
| **Total** | 1,750    | 54.2%  | 79.4%    | 99.5%       | 55.9%     |

---

## Changes Made

### 1. Kaufland Scraper (`scrapers/kaufland/scraper.py`)
- **Combined title + subtitle** into full product name (was title only)
- **Brand extraction** from title (Latin text → brand) — 63% coverage
- **Brand from detailDescription** first line for Cyrillic-titled products
- **detailDescription** captured as `raw_description` — 99% coverage
- **Discount %** from `discount` field — 71% coverage
- **Old price** from `prices.alternative.formatted.old` — 71% coverage
- **Quantity** already good from `unit` field — 74% coverage

### 2. Billa Scraper (`scrapers/billa/scraper.py`)
- **Brand extraction** from cleaned product name (Latin prefix) — 46% coverage
- **Quantity parsing** from name text (regex: "2 x 250 г", "1 кг", etc.) — 97% coverage
- **Discount %** from HTML `discount` div — 46% coverage
- **Old price** from ПРЕДИШНАЦЕНА price pairs — 45% coverage
- **Description** = cleaned product name — 100% coverage

### 3. Lidl Scraper (`scrapers/lidl/scraper.py`) — Major rewrite
- **Switched from NUXT parser to API** (`/q/api/search`) — 375 vs 233 products
- **Detail page enrichment**: fetches individual product pages for brand/qty from NUXT_DATA
- **Persistent cache** (`data/lidl_detail_cache.json`): first run ~90s, subsequent runs ~5s
- **Known brands list**: matches 50+ Lidl private labels from OCR descriptions
- **Keyfact quantity** from detail pages: "500 g/опаковка" patterns — 70% coverage
- **Brand from API** (39%) + **brand from OCR** (4%) = 43% total

### 4. Shared Utilities (`scrapers/base.py`)
- `parse_quantity_from_name()` — handles "2 x 250 г", "1.5 кг", "500 мл", "3 бр."
- `extract_brand_from_name()` — extracts Latin brand names from text start

---

## Known Gaps

### Brand (54% overall)
- **Cyrillic brands not detected**: "Тандем", "Перелик", "КФМ", "Калиакра", "Живкови", etc.
- **Lidl OCR descriptions** are image captions, not structured text — brand often buried mid-sentence
- **Fresh produce/generic items** (~25%) legitimately have no brand

### Quantity (79% overall)
- **Non-food items** (tools, clothing, appliances) don't have weight/volume
- **"За 1 кг" pattern** in Billa = price-per-kg, not package weight — some false positives
- **Lidl remaining 30%** mostly non-food or products where keyfacts lack quantity

### Potential improvements (post-scrape pipeline)
1. Bulgarian brands whitelist — match against names/descriptions
2. Better "За 1 кг" handling (price-per-unit vs package weight)
3. Cross-reference: if same product appears with brand in one store, propagate to others

---

## Architecture

```
Scrape → Raw Products → [Enrichment Pipeline] → DB → Matching → Frontend Export
              ↓
         brand, qty, desc, discount extracted at scrape time
              ↓
         [TODO: Post-scrape enrichment]
         - Bulgarian brands whitelist
         - Quantity normalization
         - Category assignment
         - Cross-store matching
```
