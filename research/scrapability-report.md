# Scrapability Research Report

**Date:** 2026-02-11
**Status:** Preliminary (manual research, agents failed)

---

## Executive Summary

The Kimi sub-agents failed due to limited tool access in isolated sessions. Manual research was conducted instead. Key finding: **The existing API has stale data (3-4 months old)** and will need to be supplemented or replaced.

---

## Site-by-Site Analysis

### 1. Lidl.bg

**URL Structure:**
- Main: https://www.lidl.bg
- Categories: `/c/{category-slug}/s{id}` (e.g., `/c/khrani-i-napitki/s10068374`)
- Weekly offers: URL patterns have changed, old paths return 404

**Key Observations:**
- Euro adoption confirmed: "Since 01.02.2026, purchases can only be paid in EUR"
- Categories visible in HTML (Храни и напитки, Кухня и домакинство, etc.)
- Modern SPA-like structure, likely React/Vue
- Product data loaded via internal API

**Scrapability Score: 3/5**
- Products in HTML but structure complex
- Dynamic loading requires headless browser
- Existing scraper in sofia-supermarkets-api (Kotlin)

---

### 2. Kaufland.bg

**URL Structure:**
- Main: https://www.kaufland.bg
- Offers: `/aktualni-predlozheniya.html`
- Weekly: `/aktualni-predlozheniya/ot-ponedelnik.html`
- Brochures: `/broshuri.html`

**Offer Schedule:**
- Monday: Main weekly offers (meat, fish, dairy, beverages)
- Wednesday: "Mega deals" (Мега сделки)
- Friday/Saturday: "Top offers" for weekend

**Channels:**
- Digital brochures (PDF available)
- K-App mobile app
- Viber & WhatsApp channels
- Kaufland Card loyalty

**Scrapability Score: 4/5**
- Well-structured offer pages
- Clear URL patterns
- PDF brochures downloadable
- Existing scraper available

---

### 3. MySupermarket.bg (Competitor)

**Site Content:**
- Title: "Сравнение на цени и промоции на хранителни продукти"
- Claims: "Save up to 30% of monthly food budget"
- Very minimal content extracted (282 chars) - likely JS-heavy SPA

**Traffic:** ~12,000 visits/month (per research data)

**Why It's Failing:**
- Minimal SEO content
- Possibly abandoned or low investment
- No clear value proposition differentiation

**Opportunity:** Very weak competition in grocery comparison space

---

### 4. Naoferta.net (Uses same API)

**Focus:** Alcohol only ("Алкохол на оферта")
- Niche focus, not general grocery
- Uses sofia-supermarkets-api

**Not a direct competitor** for general grocery comparison

---

## API Assessment (api.naoferta.net)

| Store | Last Updated | Products | Status |
|-------|-------------|----------|--------|
| Lidl | 2025-11-03 | 87 | ⚠️ 3 months stale |
| Kaufland | 2025-11-26 | 817 | ⚠️ 2.5 months stale |
| Billa | 2025-10-06 | 186 | ⚠️ 4 months stale |
| Fantastico | N/A | 0 | ❌ No data |
| T-Market | N/A | 0 | ❌ No data |

**Conclusion:** API exists but is not maintained. Cannot rely on it for production.

---

## Recommendations

### Option A: Fork & Self-Host (Recommended for MVP)
1. Fork sofia-supermarkets-api
2. Set up own infrastructure (JDK 17, PostgreSQL)
3. Run scrapers on schedule
4. Fix/update broken scrapers

**Pros:** Fastest to working data
**Cons:** Kotlin maintenance, infrastructure costs

### Option B: Build Python Scrapers
1. Build new scrapers using Scrapy/Playwright
2. Use existing repo as reference for parsing logic
3. Store in own database

**Pros:** Full control, Python expertise
**Cons:** More upfront work, reinventing wheel

### Option C: Hybrid Approach
1. Use existing API for stores that work
2. Build Python scrapers for missing/stale stores
3. Migrate to full Python over time

**Pros:** Balanced approach
**Cons:** Complexity of two systems

---

## Priority Stores for MVP

| Priority | Store | Reason | Approach |
|----------|-------|--------|----------|
| 1 | Kaufland | 817 products, structured site | Scrape directly |
| 2 | Lidl | Major chain, 481K traffic | Update scraper |
| 3 | Billa | Strong presence | Update scraper |
| 4 | Fantastico | PDF brochures | OCR approach |
| 5 | T-Market | Online store | API if available |

---

## Next Steps

1. [ ] Test Kaufland scraping with Python (Scrapy)
2. [ ] Verify Lidl's current page structure
3. [ ] Evaluate PDF OCR for Fantastico
4. [ ] Decide: Fork Kotlin API vs. Python rewrite
5. [ ] Set up data storage (PostgreSQL or SQLite for MVP)

---

*Report will be updated with agent results if they complete successfully.*
