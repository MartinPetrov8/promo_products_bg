# Competitor UI Patterns Analysis

## Sources Analyzed
- **Idealo.de** - German price comparison leader
- **PriceRunner.com** - UK price comparison

---

## Key UI Patterns to Adopt

### 1. Discount Display (PriceRunner Style)
```
-21%  £85.00  £108.00
      ↑       ↑
    NEW     OLD (strikethrough)
```
- Large discount badge (red/green)
- Current price prominent
- Old price with strikethrough
- Discount percentage FIRST (eye catches this)

### 2. Store Count Indicator
```
"7 stores"  or  "9+ stores"
```
- Shows competition = builds trust
- "More stores = reliable price"

### 3. Social Proof (PriceRunner)
```
"1000+ watching"
"500+ watching"
```
- Creates urgency
- Shows popularity
- Alternative: "X people compared this today"

### 4. Price Alerts (Idealo)
```
"Preiswecker" (Price alarm)
"Merkzettel" (Watchlist)
```
- Set target price
- Get notified when price drops
- Save for later

### 5. Product Ratings
```
★★★★½ 4.5
```
- Star rating next to product
- Helps decision making

---

## Best Price Indicator Patterns

### Pattern A: Badge + Highlight
```
┌──────────────────────────────────────┐
│ 🏆 BEST PRICE                        │
│ ┌────────────────────────────────┐   │
│ │ Store A    €2.49  ✓ CHEAPEST   │   │ ← Green background
│ └────────────────────────────────┘   │
│ │ Store B    €2.79               │   │
│ │ Store C    €2.99               │   │
└──────────────────────────────────────┘
```

### Pattern B: Savings Callout
```
┌──────────────────────────────────────┐
│  Kaufland: €2.49                     │
│  💰 Save €0.50 vs Billa              │
└──────────────────────────────────────┘
```

### Pattern C: Visual Price Bar
```
Kaufland  €2.49  ████████░░░░
Lidl      €2.79  ██████████░░
Billa     €2.99  ████████████
```

---

## Mobile-First Design

### Card Layout (PriceRunner)
```
┌─────────────────────┐
│  -21%               │ ← Badge top-right
│  [Product Image]    │
│                     │
│  Product Name       │
│  ★★★★½ 4.5         │
│                     │
│  €85.00  €108.00   │ ← Prices at bottom
│  7 stores           │
└─────────────────────┘
```

### Swipe Actions
- Swipe right: Add to watchlist
- Swipe left: Share
- Tap: View comparison

---

## Features Priority

### MVP (Now)
1. ✅ Discount badge display
2. ✅ Old vs new price
3. ⏳ Store comparison list
4. ⏳ "Best price" highlight

### Phase 2
1. Price alerts
2. Watchlist/favorites
3. Price history chart
4. Share functionality

### Phase 3
1. User ratings integration
2. "X watching" social proof
3. Personalized recommendations
4. Mobile app

---

## PromoBG Implementation

### Recommended Card Design
```html
<div class="product-card">
  <div class="discount-badge">-35%</div>
  <img src="..." />
  <h3>Product Name</h3>
  <div class="price-row">
    <span class="current">€2.49</span>
    <span class="old">€3.79</span>
  </div>
  <div class="stores">
    <span class="best">🏆 Kaufland</span>
    <span class="count">+2 stores</span>
  </div>
</div>
```

### Comparison View
```html
<div class="comparison">
  <h2>Нутела 400г</h2>
  <div class="store best">
    <span class="badge">🏆 Най-добра цена</span>
    <span class="name">Kaufland</span>
    <span class="price">€3.49</span>
  </div>
  <div class="store">
    <span class="name">Lidl</span>
    <span class="price">€3.79</span>
    <span class="diff">+€0.30</span>
  </div>
  <div class="store">
    <span class="name">Billa</span>
    <span class="price">€3.99</span>
    <span class="diff">+€0.50</span>
  </div>
</div>
```

---

*Research completed 2026-02-12*
