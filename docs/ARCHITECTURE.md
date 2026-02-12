# PromoBG Architecture

## System Overview

PromoBG is a static-first web application that aggregates grocery prices from Bulgarian supermarkets.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                  │
│   │ Kaufland.bg │   │  Lidl.bg    │   │ssbbilla.site│                  │
│   │   (HTML)    │   │(Embedded JS)│   │(HTML Tables)│                  │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                  │
│          │                 │                 │                          │
│          ▼                 ▼                 ▼                          │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                  │
│   │  Kaufland   │   │    Lidl     │   │    Billa    │                  │
│   │  Scraper    │   │   Scraper   │   │   Scraper   │                  │
│   │  (Python)   │   │  (Python)   │   │  (Python)   │                  │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                  │
│          │                 │                 │                          │
│          └────────────────┼─────────────────┘                          │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │Combined Scraper │                                    │
│                  │  (Merge + ID)   │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │all_products.json│  ← 1,537 products                  │
│                  │   (655 KB)      │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
├───────────────────────────┼─────────────────────────────────────────────┤
│                    PRESENTATION LAYER                                   │
├───────────────────────────┼─────────────────────────────────────────────┤
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │   index.html    │                                    │
│                  │  (Static SPA)   │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│          ┌────────────────┼────────────────┐                            │
│          │                │                │                            │
│          ▼                ▼                ▼                            │
│   ┌───────────┐   ┌───────────┐   ┌───────────┐                        │
│   │  Search   │   │  Filters  │   │  Product  │                        │
│   │  (JS)     │   │  (JS)     │   │  Cards    │                        │
│   └───────────┘   └───────────┘   └───────────┘                        │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                        DEPLOYMENT                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   GitHub Pages (/docs folder)                                           │
│   URL: https://martinpetrov8.github.io/promo_products_bg/               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Scrapers (`services/scraper/scrapers/`)

Each scraper is a Python module that:
- Fetches HTML from store website
- Parses product data (name, price, discount)
- Returns standardized `Product` objects

| Scraper | Source | Method | Products |
|---------|--------|--------|----------|
| `kaufland_scraper.py` | kaufland.bg | CSS selectors | ~1,200 |
| `lidl_scraper.py` | lidl.bg | Embedded JSON parse | ~50 |
| `billa_scraper.py` | ssbbilla.site | HTML table parse | ~280 |

### 2. Combined Scraper (`services/scraper/combined_scraper.py`)

- Imports individual scrapers
- Calls each scraper
- Generates unique IDs (MD5 hash of store+name)
- Merges into single JSON
- Adds timestamps

### 3. Web Frontend (`apps/web/index.html`)

Single-page application using:
- **Tailwind CSS** (via CDN) - Styling
- **Vanilla JavaScript** - Logic
- **Fetch API** - Load JSON data

Features:
- Real-time search (filters as you type)
- Store filter dropdown
- Discount filter dropdown
- Responsive grid layout
- Product cards with discount badges

### 4. Deployment (`docs/`)

Static files served by GitHub Pages:
- `index.html` - Main app
- `data/all_products.json` - Product database

## Data Flow

```
1. SCRAPE (manual or cron)
   └─→ python3 combined_scraper.py
   
2. OUTPUT
   └─→ services/scraper/data/all_products.json
   
3. COPY TO WEB
   └─→ cp data/all_products.json ../../apps/web/data/
   
4. COPY TO DEPLOY
   └─→ cp -r apps/web/* docs/
   
5. PUSH
   └─→ git push origin main
   
6. GITHUB PAGES
   └─→ Auto-deploys from /docs
```

## Technology Choices

| Layer | Technology | Why |
|-------|------------|-----|
| Scraping | Python + BeautifulSoup | Fast, reliable, good encoding support |
| Data | JSON files | Simple, no database needed for MVP |
| Frontend | Vanilla HTML/JS | No build step, fast deployment |
| Styling | Tailwind CSS | Rapid prototyping, responsive |
| Hosting | GitHub Pages | Free, reliable, automatic |

## Scaling Considerations

### Current (MVP)
- Static JSON loaded client-side
- All filtering in browser
- ~1,500 products = ~650KB JSON
- Acceptable load time (<2s)

### Future (10K+ products)
- Move to server-side search
- Add pagination
- Consider SQLite or PostgreSQL
- API endpoints for filtering
- CDN for static assets

## Security

- No user data collected
- No authentication required
- All data is public (scraped from public websites)
- No API keys exposed in frontend
