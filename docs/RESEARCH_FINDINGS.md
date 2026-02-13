# Website Research Findings

**Date:** 2026-02-13
**Researchers:** Sub-agents using web_fetch and curl analysis

---

## KAUFLAND FINDINGS

### Data Source
- **URL:** https://www.kaufland.bg/aktualni-predlozheniya/oferti.html
- **Method:** JSON embedded in HTML (found 2366 `klNr` entries)

### Available Fields (16 fields per offer)
| Field | Description | Example |
|-------|-------------|---------|
| offerId | Unique offer ID | "20260209000000.09902170.BG.3100" |
| dateFrom/dateTo | Validity dates | "2026-02-09" |
| **title** | Product name | "Тиландсия в керамична кашпа" |
| **subtitle** | Often contains SIZE | "Ø9 см" |
| **price** | Current price (EUR) | 7 |
| **detailTitle** | Cleaner product name | "Тиландсия" |
| **detailDescription** | Full description with specs | Multi-line text |
| unit | Price unit | "бр.", "кг" |
| **basePrice** | Per-unit price | "(1 кг = 2.50 лв)" |
| discount | Discount percentage | May be present |
| listImage | Product image URL | Full URL |
| detailImages | Array of images | Array |
| klNr | Kaufland article number | "09902170" |

### Key Insights
1. **NO oldPrice field** - discount needs to be calculated differently
2. **basePrice** has per-unit pricing - useful for comparison!
3. **detailDescription** has rich specs (origin, storage, etc.)
4. **klNr** is separate from offers array - need to link them

### Scraper Recommendations
```python
# Extract from embedded JSON
pattern = r'"offers":\[(\{[^\]]+)\]'
# Fields to extract: title, subtitle, price, unit, detailTitle, detailDescription, basePrice
```

---

## LIDL FINDINGS

### Data Source
- **Sitemap:** https://www.lidl.bg/p/export/BG/bg/product_sitemap.xml.gz (803 products)
- **Product pages:** https://www.lidl.bg/p/{slug}/p{id}

### Critical Discovery
**Individual product pages have JSON-LD with FULL data including prices!**

```json
{
  "@type": "Product",
  "sku": "10051379",
  "name": "Мандарини",
  "description": "<ul> <li>Произход: Гърция</li> </ul>",
  "image": ["..."],
  "offers": [{
    "price": 0.76,
    "priceCurrency": "BGN",
    "availability": "InStoreOnly"
  }]
}
```

### Available Fields
| Field | Source | Notes |
|-------|--------|-------|
| sku | JSON-LD | Product ID |
| name | JSON-LD | Product name |
| description | JSON-LD | Has origin info |
| price | JSON-LD offers | In BGN |
| availability | JSON-LD offers | InStoreOnly/OutOfStock |
| brand | JSON-LD | Often empty |

### Why Current Scraper Gets 8% Prices
- Sitemap doesn't include prices
- Need to fetch EACH product page for price data
- ~803 product pages need individual fetching

### Scraper Recommendations
1. Get product URLs from sitemap
2. For each URL, fetch page and extract JSON-LD
3. Parse `<script type="application/ld+json">` for Product data
4. Use checkpoint/resume for 803 pages

---

## BILLA FINDINGS

### Data Source
- **Best source:** https://ssbbilla.site/catalog/sedmichna-broshura
- **Main site:** billa.bg is a Vue.js SPA - NOT scrapable

### ssbbilla.site Structure
Simple HTML with product divs:
```html
<div class="product">
  <div class="actualProduct">Product Name</div>
  <div class="priceText">Price</div>
  <div class="discount">Discount %</div>
</div>
```

### Available Brochures
1. `/catalog/sedmichna-broshura` - Current week
2. `/catalog/predstoyashta-broshura` - Upcoming (often empty)
3. `/catalog/proteinov-izbor-jan-2026` - Special promotions

### Limitations
- **NO descriptions** - just product names
- **NO categories** - flat list
- **NO barcodes**
- Names include promo text ("King оферта - Супер цена - ...")

### Scraper Recommendations
1. Stick with ssbbilla.site (only reliable source)
2. Clean promo prefixes from names (already implemented)
3. Extract size from product names (already implemented)
4. Cannot improve beyond current 80% size coverage without descriptions

---

## SUMMARY: IMPROVEMENT POTENTIAL

| Store | Current | Can Improve To | How |
|-------|---------|----------------|-----|
| **Kaufland** | 24% size, 11% brand | ~50%+ | Extract from detailDescription, basePrice |
| **Lidl** | 8% price | 100% price | Fetch individual product pages |
| **Billa** | 80% size, 100% price | No change | Already maxed out |

## PRIORITY ORDER
1. **Lidl** - Biggest gain: 8% → 100% prices
2. **Kaufland** - Extract more from detailDescription
3. **Billa** - Already optimized

