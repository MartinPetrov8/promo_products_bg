# PromoBG 🛒

> Bulgarian grocery price comparison - Find the best deals across supermarkets

**Live Demo:** https://martinpetrov8.github.io/promo_products_bg/

---

## 🎯 What is PromoBG?

PromoBG aggregates promotional offers from major Bulgarian supermarkets, allowing users to:
- **Compare prices** across Kaufland, Lidl, and Billa
- **Find the best deals** with discount filtering
- **Search products** in Bulgarian
- **Save money** by knowing where to shop

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PromoBG System                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Kaufland    │    │    Lidl      │    │    Billa     │      │
│  │   Scraper    │    │   Scraper    │    │   Scraper    │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │ Combined Scraper │                         │
│                    │ (merged data)    │                         │
│                    └────────┬────────┘                          │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │ all_products.json│                         │
│                    │  (1,537 items)   │                         │
│                    └────────┬────────┘                          │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │   Web Frontend   │                         │
│                    │  (Static HTML)   │                         │
│                    └──────────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
promo_products_bg/
├── docs/                    # GitHub Pages deployment
│   ├── index.html          # Live MVP
│   └── data/               # Product JSON
│
├── apps/
│   └── web/                # Web application source
│       ├── index.html
│       └── data/
│
├── services/
│   ├── scraper/
│   │   ├── scrapers/       # Individual store scrapers
│   │   │   ├── kaufland_scraper.py
│   │   │   ├── lidl_scraper.py
│   │   │   └── billa_scraper.py
│   │   ├── combined_scraper.py
│   │   └── data/           # Scraped data
│   │
│   └── api/                # FastAPI backend (future)
│       └── main.py
│
├── research/               # Market research & UI patterns
│   └── competitor-ui-patterns.md
│
├── PLAN.md                 # Detailed project plan
└── README.md               # This file
```

---

## 🔄 Data Flow

### Step 1: Scraping
```
Kaufland.bg ──→ kaufland_scraper.py ──→ kaufland_products.json
Lidl.bg     ──→ lidl_scraper.py     ──→ lidl_products.json
ssbbilla.site ─→ billa_scraper.py   ──→ billa_products.json
```

### Step 2: Combining
```
All JSON files ──→ combined_scraper.py ──→ all_products.json
```

### Step 3: Serving
```
all_products.json ──→ index.html (loads via fetch) ──→ User sees deals
```

---

## 🚀 Quick Start

### Run Scrapers
```bash
cd services/scraper
python3 combined_scraper.py
```

### View Locally
```bash
cd apps/web
python3 -m http.server 3001
# Open http://localhost:3001
```

### Deploy to GitHub Pages
```bash
# Copy web files to docs/
cp -r apps/web/* docs/

# Commit and push
git add docs/
git commit -m "Update deployment"
git push

# Enable GitHub Pages in repo settings:
# Settings → Pages → Source: Deploy from branch → main → /docs
```

---

## 📊 Data Schema

Each product follows this schema:

```json
{
  "id": "abc123def456",
  "name": "Нутела 400г",
  "store": "Kaufland",
  "price_eur": 3.49,
  "price_bgn": 6.83,
  "old_price_eur": 4.99,
  "old_price_bgn": 9.76,
  "discount_pct": 30,
  "quantity": "400 г",
  "category": "Сладко",
  "image_url": "https://...",
  "scraped_at": "2026-02-12T05:30:00Z"
}
```

---

## 🛠️ Development Workflow

### Adding a New Store

1. **Create scraper** in `services/scraper/scrapers/`
   ```python
   # newstore_scraper.py
   def scrape_newstore() -> List[Product]:
       # Fetch and parse store website
       # Return list of Product objects
   ```

2. **Add to combined scraper**
   ```python
   # In combined_scraper.py
   from scrapers.newstore_scraper import scrape_newstore
   
   def scrape_all():
       # ... existing code ...
       all_products.extend(scrape_newstore())
   ```

3. **Run and verify**
   ```bash
   python3 combined_scraper.py
   ```

4. **Update deployment**
   ```bash
   cp services/scraper/data/all_products.json docs/data/
   git add . && git commit -m "Add NewStore" && git push
   ```

### Updating UI

1. Edit `apps/web/index.html`
2. Test locally: `python3 -m http.server 3001`
3. Copy to docs: `cp apps/web/index.html docs/`
4. Commit and push

---

## 📈 Roadmap

### Phase 1: MVP ✅
- [x] Kaufland scraper
- [x] Lidl scraper
- [x] Billa scraper
- [x] Combined data pipeline
- [x] Basic search UI
- [x] Store/discount filters
- [x] GitHub Pages deployment

### Phase 2: Enhanced Comparison
- [ ] Side-by-side price comparison
- [ ] "Best price" winner highlighting
- [ ] Price per kg/L normalization
- [ ] Price history tracking

### Phase 3: Engagement
- [ ] Price alerts (email/Viber)
- [ ] Watchlist/favorites
- [ ] User accounts
- [ ] Mobile app

### Phase 4: Monetization
- [ ] Google AdSense
- [ ] Affiliate links (eMAG, etc.)
- [ ] Sponsored placements

---

## 👥 Team

- **Martin** - Project lead
- **Maria** - Business development
- **Cookie 🍪** - AI development assistant

---

## 📄 License

MIT License - See [LICENSE](LICENSE)

---

## 🔗 Links

- **Live Demo:** https://martinpetrov8.github.io/promo_products_bg/
- **Project Plan:** [PLAN.md](PLAN.md)
- **UI Research:** [research/competitor-ui-patterns.md](research/competitor-ui-patterns.md)
