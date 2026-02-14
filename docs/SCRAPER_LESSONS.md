# Scraper Lessons Learned

## Lidl (Completed ✅)

### What Works
- **Search API**: `/q/api/search?category.id=X` returns structured JSON
- **Category IDs**: 
  - Food: 10071012-10071049
  - Non-food: 10068166-10068374
- **Brochure products ARE on website** - no need for PDF/image OCR

### Key Validations
```python
MAX_REASONABLE_PRICE = 200  # EUR - reject anything higher
MAX_SCHEMA_INDEX = 100      # Reject bogus indices in embedded JSON
```

### Lessons
1. **Brochures are marketing wrappers** - same products available via API
2. **Discount validation catches garbage** - before: 420 products >70% off, after: 0
3. **URL regex typos break data** - caused 77% missing URLs
4. **Products with discounts = weekly offers** (188/496 products)

### Final Stats
- 496 products (274 food, 166 non-food)
- 188 with discounts (all 0-69% range)
- 5/5 sample validation passed against live website

---

## Billa (Completed ✅)

### What Works
- **ssbbilla.site** - accessibility version, more reliable than main site
- **HTML parsing** - BeautifulSoup on `.product` divs

### Key Validations
```python
# Discount must have % symbol and be 1-70%
match = re.search(r'-?\s*(\d{1,2})\s*%', discount_text)
if discount < 1 or discount > 70:
    discount = None

# Discount requires old_price
if discount and not old_price_eur:
    discount = None
```

### Bug Fixed (2026-02-14)
- **Issue**: 19 products had 100% discount from "100% Арабика" text
- **Root cause**: Regex captured any number, not just discount badges
- **Fix**: Require `%` symbol and validate 1-70% range + old_price required

### Final Stats
- 277 products
- 203 with discounts (all 10-59% range)
- Avg discount: 30.1%

---

## General Rules

1. **Never trust raw scraped data** - always validate
2. **Price caps prevent garbage** - MAX_REASONABLE_PRICE catches errors
3. **Discount requires old_price** - otherwise it's meaningless
4. **Test against live website** - sample 5 products, verify prices match
5. **Document the API/endpoints** - makes debugging easier
