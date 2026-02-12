# Promo Products BG - Project Plan

**Created:** 2026-02-11
**Status:** 🟡 In Progress
**Team:** Martin, Maria, Cookie 🍪
**Repo:** https://github.com/MartinPetrov8/promo_products_bg

---

## 1. Executive Summary

Build a grocery/deals price comparison app for Bulgaria. Differentiate from competitors (MySupermarket.bg, Broshura.bg) with:
- **Cross-store price comparison** (retailers won't do this)
- **Clean, appealing UI** (not clunky like competitors)
- **Smart features** (alerts, basket optimizer, price history)

---

## 2. Market Research Summary

### 2.1 Consumer Behavior (Bulgaria)
| Stat | Value | Source |
|------|-------|--------|
| Price comparison before purchase | **71%** | Novinite |
| Income barely covers expenses | **58%** | Manager.bg |
| Household spending on food | **33%** | NSI |
| Hypermarket sales from promotions | **50%+** | Capital.bg |

**Insight:** Bulgarians are extremely price-sensitive. High demand for price comparison tools.

### 2.2 Competitor Traffic (Jan 2026)
| Site | Monthly Visits | Type |
|------|---------------|------|
| olx.bg | 3,000,000 | Classifieds |
| emag.bg | 2,015,000 | Marketplace |
| pazaruvaj.com | 565,000 | Price comparison (electronics) |
| lidl.bg | 481,000 | Retailer brochures |
| kaufland.bg | 342,000 | Retailer brochures |
| broshura.bg | 74,000 | Brochure aggregator |
| **mysupermarket.bg** | **12,000** | Grocery comparison |
| shopko.bg | <5,000 | Grocery comparison |

**THE GAP:** Lidl.bg gets 481K visits for brochures, but MySupermarket only 12K for comparison.
**40x more people look at deals than compare them** — massive opportunity!

### 2.3 Affiliate Marketing Ecosystem
| Network | Programs | Key Partners |
|---------|----------|--------------|
| VIVnetworks | 43 | Temu (10%), Notino, Philips |
| Admitad | 212 | International brands |
| Profitshare | 57 | **eMAG (1-7%)**, FashionDays, Decathlon |

| Store | Commission | Category |
|-------|-----------|----------|
| hygea.bg | **15%** | Pharmacy |
| Temu | 10% | Marketplace |
| Sportisimo | 10% | Sports |
| eMAG | 1-7% | Electronics |
| zooplus.bg | 2-5% | Pet supplies |

**Note:** Big grocery chains (Lidl, Kaufland, Billa) do NOT have affiliate programs.

### 2.4 Monetization Strategy
| Phase | Revenue Source | When |
|-------|---------------|------|
| 1 | Google AdSense | Month 1 |
| 2 | Pharmacy affiliate (hygea 15%) | Month 2 |
| 3 | eMAG affiliate (1-7%) | Month 3 |
| 4 | Sponsored placements | Month 6+ (with leverage) |

---

## 3. Strategic Decisions

### 3.1 Why Groceries First (Not Niches)
| Factor | Groceries | Niches (Pet/Auto/Baby) |
|--------|-----------|------------------------|
| Competition | MySupermarket: 12K (weak!) | Unknown |
| Market size | Everyone eats | 15-20% of population |
| Frequency | Weekly | Monthly |
| Data access | Brochures public | Scattered |
| Urgency | Euro transition | None |

**Decision:** Start with groceries to prove model, expand to niches later.

### 3.2 Core Differentiator
> **"Retailers will NEVER tell you that a competitor has a better price."**
> Only a third-party can do cross-store comparison.

Features retailers CAN'T offer:
- "Where is Nutella cheapest this week?"
- "My basket costs €23 at Lidl vs €27 at Kaufland"
- "Alert me when coffee drops below 8 лв"
- Price history ("Is this really a deal?")

### 3.3 Data Strategy
**KEY QUESTION:** Are promotional products on the WEBSITE (easy scrape) or only in PDF brochures (hard OCR)?

| Store | Website has promos? | PDF needed? | Status |
|-------|---------------------|-------------|--------|
| Kaufland | ✅ YES | ❌ NO | **DONE - 1,207 products** |
| Lidl | ✅ YES | ❌ NO | **DONE - 53 products** |
| Billa | ✅ YES (ssbbilla.site) | ❌ NO | **DONE - 277 products** |
| Fantastico | ❌ NO | ✅ YES (PDF) | Needs OCR |
| T-Market | ⏳ Check | ⏳ | |
| CBA | ⏳ Check | ⏳ | |
| ProMarket | ⏳ Check | ⏳ | |

**Goal:** Avoid PDF OCR if website has structured data.

---

## 4. Technical Architecture

### 4.1 Existing API Assessment
Found: https://api.naoferta.net (sofia-supermarkets-api)

| Store | Last Updated | Status |
|-------|-------------|--------|
| Lidl | 2025-11-03 | ⚠️ 3 months stale |
| Kaufland | 2025-11-26 | ⚠️ 2.5 months stale |
| Billa | 2025-10-06 | ⚠️ 4 months stale |
| Fantastico | N/A | ❌ No data |
| T-Market | N/A | ❌ No data |

**Decision:** Build our own Python scrapers (API data too stale).

### 4.2 Tech Stack
```
Frontend:
├── Next.js 14 (React, SSR for SEO)
├── Tailwind CSS
└── shadcn/ui components

Backend:
├── Python scrapers (requests + BeautifulSoup)
├── Next.js API routes or FastAPI
└── PostgreSQL (product data)

Deployment:
├── Vercel (frontend)
└── Railway/Render (backend)
```

### 4.3 Website Structure
```
promobg.com/
├── / (Home)
│   ├── Search bar: "Намери най-евтиното"
│   ├── Featured deals carousel
│   └── Categories grid
│
├── /search?q={query}
│   ├── Results across all stores
│   ├── Sort: price, discount %, store
│   └── Filter: store, category
│
├── /product/{id}
│   ├── Price comparison table
│   ├── Price history chart
│   └── "Set alert" button
│
├── /store/{name}
│   └── All current deals
│
└── /categories/{category}
    └── Browse by category
```

### 4.4 Scraping Strategy (⚠️ CRITICAL)

**Full documentation:** [`docs/SCRAPING_STRATEGY.md`](docs/SCRAPING_STRATEGY.md)

This is the backbone of the project. Key points:

#### Three-Tier Fallback System
| Tier | Source | Freshness | Risk |
|------|--------|-----------|------|
| 1 | Direct retailer website | Real-time | High (blocks) |
| 2 | Aggregators (katalozi.bg) | 1-2 days | Low |
| 3 | PDF + OCR | Weekly | None |

#### Fallback Waterfall Logic
```python
for tier in [direct, aggregator, pdf]:
    try:
        products = scrape(tier)
        if len(products) >= MIN_THRESHOLD:
            return products
    except (Block, Timeout):
        continue
return cached_stale_data()  # Never return nothing
```

#### Error Handling
- **Auto-retry:** Timeout, 429, 5xx (with exponential backoff)
- **Switch tier:** 403, Cloudflare block, CAPTCHA
- **Alert human:** All tiers failed, selector breakage

#### Safeguards
- Minimum product thresholds detect selector breakage
- Rate limiting (10 req/min retailers, 30 req/min aggregators)
- User-agent rotation from 5+ real browser strings
- WhatsApp alerts for critical failures

---

## 5. UI/UX Principles

### Design Goals
```
┌─────────────────────────────────────────────────────────┐
│ 1. SIMPLE & CLEAN — Not clunky like competitors        │
│ 2. Mobile-first — Most users on phones                 │
│ 3. Fast — Instant search results                       │
│ 4. Visual — Product images prominent                   │
│ 5. One-tap actions — Save, alert, share                │
│ 6. CLEAR WINNER — Obvious which store has best price   │
└─────────────────────────────────────────────────────────┘
```

### Price Comparison UI Requirements
```
CORE PRINCIPLE: User should know the best deal in <2 seconds

PRODUCT COMPARISON VIEW:
┌─────────────────────────────────────────────────────────┐
│  🏆 BEST PRICE                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Kaufland          2.49€  ← GREEN/HIGHLIGHTED    │   │
│  └─────────────────────────────────────────────────┘   │
│  │ Lidl              2.79€                         │   │
│  │ Billa             2.99€  (was 3.49€)           │   │
└─────────────────────────────────────────────────────────┘

CALL TO ACTION ELEMENTS:
- 🏆 Trophy/badge on best price
- Green highlight on cheapest option
- "Спестяваш X лв" (You save X) vs next best
- Price difference shown clearly
- One-click "Add to shopping list"

COMPARISON CARD FEATURES:
- Side-by-side store prices
- Visual price bar (relative to highest)
- Savings amount in € and лв
- Store logos for recognition
- "Price per kg/L" for fair comparison
```

### UI References (modern, clean)
- Too Good To Go app (simple cards)
- Honey browser extension (price drops)
- Chipp.bg (Bulgarian, clean design)
- **Idealo.de** - Price alerts, watchlists
- **PriceRunner** - Discount badges, "X stores" count, social proof

### Key Patterns from Global Leaders (researched 2026-02-12)
```
FROM PRICERUNNER:
├── Discount badge first: "-21%" prominently displayed
├── Price comparison: "£85.00 £108.00" (new vs old)
├── Store count: "7 stores" builds trust
├── Social proof: "1000+ watching"
└── Star ratings next to products

FROM IDEALO:
├── "Preiswecker" (Price alarm/alert)
├── "Merkzettel" (Watchlist)
├── 600M+ offers, 50K+ shops scale
└── User reviews + test reports

IMPLEMENTATION:
├── MVP: Discount badge, price comparison, best price highlight
├── Phase 2: Price alerts, watchlist, price history
└── Phase 3: Social proof, ratings, personalization
```

See: `/research/competitor-ui-patterns.md` for full analysis

### Anti-Patterns (avoid)
- MySupermarket.bg — Too basic, no visual appeal
- Broshura.bg — PDF viewer, not interactive
- Cluttered layouts with too many filters

---

## 6. Scraper Progress

### 6.1 Kaufland ✅ COMPLETE
```
Status:     Working
Products:   1,207 extracted
With price: 100%
With discount: 75% (907 products)
Max discount: -61%
Method:     Python + BeautifulSoup
Selector:   div.k-product-tile
```

Sample data:
| Product | Price EUR | Discount |
|---------|-----------|----------|
| S POWER Зимна течност | 1.78€ | -61% |
| AQUAPHOR Филтър | 4.08€ | -60% |
| Свинско каре | 3.47€ | -53% |

Code: `services/scraper/scrapers/kaufland_scraper.py`
Data: `services/scraper/data/kaufland_products.json`

### 6.2 Lidl ✅ COMPLETE
```
Status:     Working
Products:   53 extracted
Avg discount: 28.3%
Max discount: 54%
Method:     Parse embedded JSON from HTML
Source:     lidl.bg/c/lidl-plus-promotsii/
```

### 6.3 Billa ✅ COMPLETE
```
Status:     Working
Products:   277 extracted
With discount: 222 (80%)
Avg discount: 36.1%
Method:     Scrape ssbbilla.site (accessibility version)
Source:     ssbbilla.site/catalog/sedmichna-broshura
```

### 6.4 Fantastico ⚠️ REQUIRES PDF OCR
```
Status:     PDF brochures only
Method:     Would need pdf.js/PyMuPDF extraction
Complexity: High - defer to Phase 2
```

### 6.5 T-Market ⏳ PENDING
### 6.6 CBA ⏳ PENDING
### 6.7 ProMarket ⏳ PENDING

---

## 7. Development Phases

### Phase 1: Research & Scrapers (Feb 11-14)
- [x] Market research review
- [x] Kaufland scraper working
- [x] Lidl scraper
- [x] Billa scraper
- [x] Combined scraper (1,537 products)
- [x] FastAPI backend
- [ ] Check remaining stores (website vs PDF)

### Phase 1b: Scraping Infrastructure (Feb 12-14) ⚠️ BACKBONE
- [x] Document scraping strategy (`docs/SCRAPING_STRATEGY.md`)
- [ ] Implement `ScraperOrchestrator` class
- [ ] Add retry logic with exponential backoff
- [ ] Add per-domain rate limiting
- [ ] Implement health tracking per store
- [ ] Build Tier 2 scrapers (katalozi.bg fallback)
- [ ] Test fallback switching (block Tier 1 → Tier 2)
- [ ] Add WhatsApp alerts for failures

### Phase 1c: Product Coverage Strategy (Feb 12-14) 🎯 PRIORITY

**⚠️ CRITICAL DISCOVERY:** Bulgarian supermarkets do NOT have full online product catalogs!
- Lidl, Kaufland, Billa are discount/traditional retailers, not e-commerce
- Websites only show **weekly promotional items** (~10-20% of inventory)
- Full product data exists ONLY in **PDF brochures**

**Two strategies for price comparison:**

**Strategy A: Promo-Only Comparison (Current - Fast)**
- Compare promotional items across stores
- Limited to ~1,500-2,000 products/week
- Updates weekly as promos change
- ✅ Already working with current scrapers

**Strategy B: PDF/OCR Pipeline (Future - Comprehensive)**
- Extract ALL products from PDF brochures
- Covers full promo inventory including non-web items
- Higher accuracy (brochure is source of truth)
- Requires: PDF download → OCR → structured extraction

**Current Product Status:**
- [x] Kaufland - 1,207 promo products ✅
- [x] Lidl - 53 products (Lidl Plus promos) ✅
- [x] Billa - 277 products (weekly brochure) ✅
- [ ] Kaufland additional pages (Mega deals, Top offers) 
- [ ] Fantastico - PDF ONLY (no web data)
- [ ] Metro - shop.metro.bg (JS-rendered, needs browser)

**Action Items:**
1. [x] Scrape ALL Kaufland offer pages (Monday + Wednesday + Weekend)
2. [ ] Explore Lidl additional categories
3. [ ] Build PDF/OCR pipeline for Fantastico (Phase 2)
4. [ ] Test Metro with browser automation

### Phase 1d: Database Architecture 🗄️ CRITICAL
**Design comprehensive schema for:**
- Products (name, ID, category, subcategory, brand, unit, weight/volume)
- Prices (current, old, discount %, per-unit price)
- Stores (ID, name, logo, scrape URL)
- Scrape history (timestamp, source tier, product count)
- Price history (track changes over time for "is this really a deal?")
- Images (URL, local cache path, hash for deduplication)

**Requirements:**
- Handle thousands of products efficiently
- Track price changes over time
- Support fuzzy product matching across stores
- Normalize product names for comparison

**Deliverables:**
- [ ] Database schema design doc
- [ ] SQLite for MVP, PostgreSQL for production
- [ ] Migration scripts
- [ ] Data models (Python dataclasses/Pydantic)

### Phase 1e: Price Comparison UI ⭐ KEY FEATURE
**"Cheapest wins" display:**
- When searching for "coffee costa arabica"
- Backend finds matches across all stores
- Show ONLY the cheapest option prominently
- Visual indicator: 🏆 trophy/star + "X% cheaper than other stores"
- Secondary: collapsed list of other store prices

**UI Elements:**
- Winner badge/trophy icon
- Green highlight on best price
- "Спестяваш X лв" (You save X lv)
- Price comparison bar visualization
- "Налично в X магазина" (Available in X stores)

### Phase 1f: Product Images & Descriptions Research 📸
**Questions to answer:**
- Can we scrape product images from store websites?
- Copyright/legal considerations for displaying images
- Storage strategy: URLs vs local cache vs CDN
- Image deduplication (same product, different stores)
- Description normalization across stores

**Deliverables:**
- [ ] Research doc on image scraping feasibility
- [ ] Storage recommendation
- [ ] Legal considerations summary

---

### Phase 1c-OLD: Data Validation (Per Store) ⚠️ CRITICAL
**For EACH new store, before considering scraper "done":**
- [ ] Download current PDF brochure
- [ ] Pick 5-10 random items from brochure (variety of categories)
- [ ] Cross-check: Are these items on the website?
- [ ] Cross-check: Do prices EXACTLY match? (regular + promo price)
- [ ] Document discrepancies in `research/price-validation/{store}.md`
- [ ] If brochure has items NOT on website → need PDF/OCR pipeline

**Why:** Brochures may contain exclusive deals not on website. This is our price edge.

**Stores to validate:**
- [ ] Kaufland (website vs brochure)
- [ ] Lidl (website vs brochure)
- [ ] Billa (website vs brochure)
- [ ] Metro (website vs brochure)
- [ ] Fantastico (PDF-only, baseline)

### Phase 2: MVP Website (Feb 14-21)
- [ ] Next.js project setup
- [ ] Product search page
- [ ] Store filter
- [ ] Mobile-responsive design
- [ ] Deploy to Vercel

### Phase 3: Features (Feb 21-28)
- [ ] Price comparison view
- [ ] Discount highlighting
- [ ] "Best deals today"
- [ ] Price alerts (email)

### Phase 4: Launch (March 2026)
- [ ] Soft launch (friends/family)
- [ ] SEO optimization
- [ ] Google AdSense
- [ ] Affiliate signups

---

## 12. Deployment

### GitHub Pages Setup
```
1. All web files go to /docs folder
2. GitHub Pages serves from main branch /docs
3. URL: https://martinpetrov8.github.io/promo_products_bg/
```

### Deployment Workflow
```bash
# 1. Update scrapers and run
cd services/scraper
python3 combined_scraper.py

# 2. Copy data to web app
cp data/all_products.json ../../apps/web/data/

# 3. Copy web app to docs (for GitHub Pages)
cp -r ../../apps/web/* ../../docs/

# 4. Commit and push
git add .
git commit -m "Update data and deploy"
git push origin main

# 5. GitHub Pages auto-deploys from /docs
```

### Enable GitHub Pages (one-time setup)
1. Go to repo Settings
2. Navigate to Pages section
3. Source: Deploy from a branch
4. Branch: main
5. Folder: /docs
6. Save

### Live URLs
- **MVP:** https://martinpetrov8.github.io/promo_products_bg/
- **Data:** https://martinpetrov8.github.io/promo_products_bg/data/all_products.json

---

## 8. Success Metrics

| Metric | Month 1 | Month 3 |
|--------|---------|---------|
| Monthly visits | 1,000 | 10,000 |
| Products indexed | 5,000+ | 20,000+ |
| Stores covered | 5 | 8+ |
| Price alerts set | 100 | 1,000 |

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stores block scraping | High | Rotate user agents, respect rate limits |
| Data goes stale | Medium | Daily scraper runs, freshness indicators |
| Low initial traffic | Medium | SEO focus, Viber community |
| UI too complex | Medium | User testing, iterate fast |

---

## 10. Current Status

### Completed (Feb 11)
- [x] Project structure created
- [x] GitHub repo initialized
- [x] Market research reviewed
- [x] Kaufland scraper working (1,207 products)
- [x] Pushed to GitHub

### Next Steps (Feb 12)
| Stage | Task | Question |
|-------|------|----------|
| 4 | Lidl scraper | Website or PDF? |
| 5 | Billa scraper | Website or PDF? |
| 6 | Fantastico check | Website or PDF? |
| 7 | Website skeleton | Clean UI mockup |
| 8 | Deploy MVP | Searchable with Kaufland data |

---

## 11. Resources

### Repositories
- Main: https://github.com/MartinPetrov8/promo_products_bg
- Reference: https://github.com/StefanBratanov/sofia-supermarkets-api

### Research Documents
- Feasibility Study (Manus AI)
- Deep-Dive Analysis (Consumer behavior, traffic, affiliates)

### API References
- naoferta.net API: https://api.naoferta.net (stale data)
- Kaufland: https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html

---

*Last updated: 2026-02-11 21:50 UTC*
