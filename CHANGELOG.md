# Changelog

All notable changes to PromoBG will be documented in this file.

## [0.1.0] - 2026-02-12

### Added
- **Scrapers**
  - Kaufland scraper (1,207 products)
  - Lidl scraper (53 products)
  - Billa scraper (277 products)
  - Combined scraper merging all stores

- **Web MVP**
  - Product search functionality
  - Store filter (Kaufland, Lidl, Billa)
  - Discount filter (20%, 40%, 50%+)
  - Top deals display
  - Mobile-responsive design
  - Bulgarian language UI

- **Deployment**
  - GitHub Pages setup (/docs folder)
  - Static JSON data serving

- **Documentation**
  - README with architecture diagram
  - PLAN.md with detailed roadmap
  - Scraper documentation
  - CONTRIBUTING guide
  - Competitor UI research

### Technical Details
- Total products: 1,537
- Data format: JSON
- Frontend: Vanilla HTML/JS + Tailwind CSS
- Backend: Python scrapers (no server required)

---

## Planned

### [0.2.0] - Target: Feb 2026
- [ ] Price comparison view (same product, multiple stores)
- [ ] "Best price" winner highlighting
- [ ] Price per kg/L normalization

### [0.3.0] - Target: Mar 2026
- [ ] Price alerts (email)
- [ ] Watchlist/favorites
- [ ] Price history tracking

### [0.4.0] - Target: Apr 2026
- [ ] Additional stores (Fantastico, T-Market)
- [ ] User accounts
- [ ] Viber bot integration

## [2026-02-15] Brand Resolution Pipeline v1

### Added
- **Brand Resolution System** (`brand_resolver.py`)
  - Multi-strategy resolver: name patterns → house brands → image cache → OCR
  - 355 brand patterns saved to `brand_patterns` table
  - 138 Lidl OCR results cached in `brand_image_cache`

### Improved  
- **Brand Coverage**: Kaufland 84.6%, Lidl 54.4%, Billa 75.8%
- **Cross-store Matches**: 49 → **127** (+159%)
- **Top Savings**: Parkside tools up to 199.91 лв difference

### Data
- `api/matches.json` - v5_brand_coverage_84pct
- 61 global + Bulgarian brand patterns
- House brands: Parkside, Milbona, Pilos (Lidl), K-Classic (Kaufland)

### Technical
- Threshold: 0.82 (brand info adds matching signal)
- Price ratio filter: 3x max
- O(n²) matching on 1,431 products
