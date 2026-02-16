# PromoBG MVP Roadmap

## Current State (v2.5)

| Metric | Value |
|--------|-------|
| Products | 1,319 |
| Cross-store matches | 51 |
| Total savings | €93.45 |
| Categories | 34 |
| Stores | 3 (Kaufland, Lidl, Billa) |

**Live site:** https://martinpetrov8.github.io/promo_products_bg/

---

## Phase 1: Data Foundation ✅ DONE

- [x] Store scrapers (Kaufland, Lidl, Billa)
- [x] Data standardization pipeline
- [x] Category classification (34 categories)
- [x] Brand extraction (87% coverage)
- [x] Homoglyph normalization (Latin↔Cyrillic)
- [x] Name cleaning (remove suffixes, promotional text)
- [x] Cross-store matching algorithm

---

## Phase 2: MVP Stability (Next 1-2 weeks)

### 2.1 Data Quality
- [ ] **Fix Lidl 100x price bug** - Root cause in scraper
- [ ] **Increase Lidl coverage** - Only 152 products (vs 890 Kaufland)
- [ ] **Add product images** - Currently null for all
- [ ] **Extract quantities** - 77% missing (1,017/1,319)

### 2.2 Matching Improvements
- [ ] **Quantity-aware matching** - Same product different sizes shouldn't match
- [ ] **Per-kg price normalization** - Compare unit prices, not total prices
- [ ] **Manual review queue** - Flag low-confidence matches for human review

### 2.3 Frontend Fixes
- [ ] **Mobile responsiveness** - Test and fix
- [ ] **Filter by store** - Let users focus on stores near them
- [ ] **Sort options** - By savings, price, category
- [ ] **Compare view** - Side-by-side price comparison

### 2.4 Infrastructure
- [ ] **Automated scraper runs** - Daily cron job
- [ ] **Data freshness indicator** - Show when prices were last updated
- [ ] **Error monitoring** - Alert on scraper failures

---

## Phase 3: Growth (Weeks 3-4)

### 3.1 More Stores
Priority order:
1. **Fantastico** - Major chain, PDF brochures (needs OCR)
2. **T-Market** - Regional chain
3. **CBA** - Smaller stores
4. **Metro** - Wholesale (different pricing model)

### 3.2 More Products
- [ ] **Historical price tracking** - Show price trends
- [ ] **Scrape full product catalog** - Not just promotions
- [ ] **Open Food Facts integration** - Nutritional data, images

### 3.3 User Features
- [ ] **Shopping list** - Save products, calculate total savings
- [ ] **Price alerts** - Notify when favorite products go on sale
- [ ] **Share comparison** - Social sharing

---

## Phase 4: Monetization (Month 2+)

### Options (ranked by effort/reward):

1. **Ads** (Low effort, low reward)
   - Google AdSense
   - ~€0.50-2 CPM for Bulgarian traffic

2. **Affiliate links** (Medium effort, medium reward)
   - Partner with stores for click tracking
   - ~2-5% commission on purchases

3. **Premium features** (High effort, high reward)
   - Price alerts, historical data, API access

4. **Data licensing** (High effort, high reward)
   - Sell aggregated price data to market research firms

---

## Success Metrics

### MVP Success (Phase 2):
- [ ] 100+ cross-store matches
- [ ] €200+ total savings potential
- [ ] <5% false positive matches
- [ ] Daily automated updates
- [ ] Mobile-friendly UI

---

## Immediate Next Steps

1. **Fix Lidl scraper** - Root cause of 100x price bug
2. **Add quantity extraction** - Enable unit price comparison
3. **Set up daily cron** - Automate scraper runs
4. **Mobile test** - Fix responsive issues
5. **Add 4th store** - Fantastico (PDF OCR)

---

*Last updated: 2026-02-16*
