# API & Machine-Readable Feeds Discovery

**Date:** 2026-02-12
**Status:** ✅ Complete

---

## Summary

| Store | Has API? | Format | URL | Reliability |
|-------|----------|--------|-----|-------------|
| **Lidl** | ✅ YES | JSON | `/p/api/gridboxes/BG/bg` | ⭐⭐⭐⭐⭐ |
| Kaufland | ❌ No | HTML | Embedded in page | ⭐⭐⭐ |
| Billa | ❌ No | HTML | ssbbilla.site fallback | ⭐⭐⭐ |
| Metro | ❌ No | JS-rendered | Needs browser | ⭐⭐ |
| Fantastico | ❌ No | PDF only | No web data | ⭐ |

---

## 🎯 Lidl - JACKPOT! Full JSON API

### Primary API Endpoint
```
GET https://www.lidl.bg/p/api/gridboxes/BG/bg
```

**Returns:** Full product catalog in JSON format

### Sample Response (per product)
```json
{
  "productId": 10051415,
  "erpNumber": "10051415",
  "fullTitle": "Livarno Детска стенна етажерка",
  "brand": {
    "name": "Livarno",
    "showBrand": true
  },
  "category": "Нехранителни",
  "canonicalUrl": "/p/livarno-detska-stenna-etazerka/p10051415",
  "image": "https://imgproxy-retcat.assets.schwarz/...",
  "imageList": ["url1", "url2", "url3"],
  "price": {
    "currencyCode": "EUR",
    "currencyCodeSecond": "BGN",
    "price": 10.22,
    "priceSecond": 19.99,
    "oldPrice": 0,
    "oldPriceSecond": 0
  },
  "stockAvailability": {
    "badgeInfo": {
      "badges": [
        {"text": "в магазините от 12.02. - 15.02.", "type": "IN_STORE_TODAY_DATE_RANGE"}
      ]
    }
  },
  "ians": ["496389"],  // Internal article number
  "keyfacts": {
    "description": "<ul><li>60 x 49 x 15 cm</li></ul>"
  }
}
```

### Data Available
- ✅ Product ID, title, brand
- ✅ Category (Bulgarian)
- ✅ Prices in EUR and BGN
- ✅ Old price (for discounts)
- ✅ Multiple images per product
- ✅ Stock availability dates
- ✅ Product descriptions
- ✅ Internal article numbers

### Product Sitemap
```
https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz
```
Gzipped XML with all product URLs - can be used to discover all product pages.

### Rate Limits (Observed)
- No explicit rate limiting detected
- Recommend: 10 requests/minute to be safe

### Integration Notes
- No authentication required
- Returns Bulgarian text natively
- Prices include both EUR and BGN
- CDN images (schwarz assets) - can be hotlinked

---

## Kaufland - HTML Scraping Required

### robots.txt
```
User-agent: *
Disallow: /etc.clientlibs/
Allow: /etc.clientlibs/kaufland
Sitemap: https://www.kaufland.bg/.sitemap.xml
```

### No API Endpoints Found
Checked:
- `/api/v1/offers` - 404
- `/api/products` - 404
- Network requests during page load - no JSON APIs

### Best Approach
Continue with current HTML scraper:
- URL: `https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html`
- Selector: `div.k-product-tile`

### Sitemap
```
https://www.kaufland.bg/.sitemap.xml
```
Contains all offer pages - useful for discovering new sections.

---

## Billa - HTML Scraping Required

### robots.txt
```
Sitemap: https://www.billa.bg/sitemap.xml
```
Very permissive - no explicit blocks.

### No API Endpoints Found
- `/api/products` - 404
- Main site has no structured data

### Best Approach
Continue with accessibility site:
- URL: `https://ssbbilla.site/catalog/sedmichna-broshura`
- Contains structured price data

### Sitemap
```
https://www.billa.bg/sitemap.xml
```
Contains `/products` page but it's HTML, not JSON.

---

## Metro - Browser Required

### robots.txt
```
User-agent: *
Disallow: /MSHOP
Disallow: /rezultati
...
Sitemap: https://www.metro.bg/sitemap.xml
```

### Access Issues
- Main site (metro.bg) returns 403 from datacenter IPs
- shop.metro.bg is JavaScript-rendered

### shop.metro.bg
```
https://shop.metro.bg/shop/broshuri
```
- Requires JavaScript execution
- Shows "outdated browser" message without JS

### Best Approach
- Needs Playwright/Selenium for scraping
- Or use aggregator (katalozi.bg) as Tier 2 fallback

---

## Fantastico - PDF Only

### No Web Presence for Products
- Website has no product catalog
- Only PDF brochures available

### Best Approach
- Download PDF brochures
- Extract via OCR (Tesseract or Claude Vision)
- Phase 2 implementation

---

## Recommendations

### Immediate Actions
1. **Switch Lidl scraper to use API** - Much more reliable than HTML parsing
2. **Keep Kaufland HTML scraper** - Working well, no API available
3. **Keep Billa HTML scraper** - ssbbilla.site is stable

### Future Work
1. **Metro**: Implement Playwright-based scraper
2. **Fantastico**: Build PDF OCR pipeline
3. **Monitor Lidl API** for changes/rate limits

### Priority Order for Data Sources
| Priority | Store | Method |
|----------|-------|--------|
| 1 | Lidl | JSON API (best!) |
| 2 | Kaufland | HTML scraper |
| 3 | Billa | HTML scraper (ssbbilla.site) |
| 4 | Metro | Browser automation |
| 5 | Fantastico | PDF OCR |

---

## Appendix: Full URLs

### Lidl
- API: `https://www.lidl.bg/p/api/gridboxes/BG/bg`
- Product sitemap: `https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz`
- Store sitemap: `https://www.lidl.bg/s/bg-BG/magazini/sitemap.xml`

### Kaufland
- Offers: `https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html`
- Sitemap: `https://www.kaufland.bg/.sitemap.xml`

### Billa
- Main: `https://www.billa.bg/promocii/sedmichna-broshura`
- Accessibility: `https://ssbbilla.site/catalog/sedmichna-broshura`
- Sitemap: `https://www.billa.bg/sitemap.xml`

### Metro
- Shop: `https://shop.metro.bg/shop/broshuri`
- Aggregator fallback: `https://katalozi.bg/supermarketi/metro/`

### Aggregators (Tier 2 Fallback)
- `https://katalozi.bg/supermarketi/{store}/`
- `https://broshura.bg/{store}`
