# PromoBG Frontend Edge Cases

## Known Issues (2026-02-17)

### 1. Price Overflow
- **Issue:** Prices like `149.00лв` overflow card boundaries on mobile
- **Fix:** Reduce font-size or add text truncation for prices > 99

### 2. Store Suffixes Still Visible  
- **Issue:** Some product names still show "от свежата витрина", "от деликатесната витрина"
- **Cause:** Suffixes with newlines aren't being stripped (e.g., "Саяна Кашкавал\nот свежата витр")
- **Fix:** Strip suffixes after replacing newlines

### 3. Long Product Names
- **Issue:** Names overflow on narrow cards
- **Current:** Truncated at 45 chars
- **Fix:** Consider 2-line clamp or shorter truncation

## Testing Checklist
- [ ] Mobile view (< 640px)
- [ ] Prices > 100лв display correctly
- [ ] Long product names don't overflow
- [ ] Compare modal shows exactly 2 stores
- [ ] Store suffixes stripped from all names
