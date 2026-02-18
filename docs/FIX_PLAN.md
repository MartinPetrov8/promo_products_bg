# PromoBG Fix Plan

**Date:** 2026-02-17
**Based on:** 3 QA reviews (frontend, pipeline, full codebase)

---

## Phase 1: Security & Correctness (Day 1)

### 1.1 Fix XSS Vulnerabilities (Critical)
**What:** Product names injected via `innerHTML` without escaping. `group_id` in inline `onclick` can break out.
**Why:** Only security issue in the codebase. Trivial to exploit if someone injects HTML into product data.
**How:**
- Add `escapeHtml()` utility function
- Replace all `innerHTML` concatenation with escaped values
- Replace inline `onclick` with `data-group-id` + event delegation
**Risk:** Low — purely additive, no logic changes
**Time:** ~1 hour

### 1.2 Add Null/Undefined Guards (High)
**What:** `getNutriscore()`, `getGroupProducts()`, `showComparison()` can throw on missing data.
**Why:** Any missing field in `products.json` crashes the entire page.
**How:** Add optional chaining and early returns
**Risk:** Low
**Time:** ~30 min

### 1.3 Load Image Mappings from JSON (High)
**What:** 146-entry `IMAGE_MAPPINGS` array is hardcoded in HTML instead of loading `data/image_mapping.json`.
**Why:** Maintenance nightmare — every mapping change requires editing HTML. File already exists but isn't used.
**How:** `fetch('data/image_mapping.json')` at startup, remove embedded array
**Risk:** Low — adds one extra HTTP request
**Time:** ~30 min

---

## Phase 2: Matching Quality (Day 2-3)

### 2.1 Brand-Aware Matching (High)
**What:** 66% of groups mix different brands (Cien vs Dove, Верея vs generic).
**Why:** This is the #1 user trust issue. Comparing Cien shower gel to Palmolive is meaningless.
**How:**
- In `pipeline.py` matching: if both products have brands and they differ → skip or heavy penalty (0.3x multiplier)
- If one/both have no brand → allow match but lower confidence
**Risk:** Medium — will reduce group count (fewer but better matches)
**Time:** ~2 hours

### 2.2 Price Ratio Sanity Check (High)
**What:** 32% of groups have >3x price difference. Some are 17x.
**Why:** Usually means different sizes/quantities matched together. Erodes trust.
**How:**
- Add price ratio check in `export_frontend()`: if max/min > 3x, flag group
- Option A: Exclude from export (strict)
- Option B: Add `"warning": true` flag, show ⚠️ in frontend (informative)
- I recommend Option B — shows data, lets users judge
**Risk:** Low
**Time:** ~1 hour

### 2.3 Raise Confidence Threshold (Medium)
**What:** 29% of groups have confidence < 0.5. These are weak matches.
**Why:** Low confidence = high chance of false positive.
**How:**
- Raise `min_threshold` from 0.4 → 0.55 in `config/matching.json`
- Raise `min_common_tokens` from 2 → 3
**Risk:** Medium — fewer groups, but higher quality
**Time:** ~15 min (config change + re-run)

### 2.4 Integrate Quantity in Matching (Medium)
**What:** `quantity_extractor.py` exists but matching ignores quantity data.
**Why:** 1kg cheese shouldn't match 200g cheese.
**How:**
- Extract quantity for all products (not just OCR)
- In matching: if both have quantities and ratio > 2x → penalize score by 0.5x
- Add quantity to exported JSON for frontend display
**Risk:** Medium — depends on extraction accuracy
**Time:** ~3 hours

---

## Phase 3: Data Pipeline Fixes (Day 3-4)

### 3.1 Run Quantity Extraction on All Products
**What:** Currently only 101/1506 products have quantity data.
**Why:** Needed for Phase 2.4 and for showing unit prices in frontend.
**How:** Run `quantity_extractor.py` across all product names in DB, update `products` table
**Time:** ~1 hour

### 3.2 Re-run OCR for Failed Entries
**What:** 259/526 Lidl OCR entries failed.
**Why:** Missing brands = worse matching for Lidl products.
**How:** Check image URL accessibility first, retry with different settings
**Time:** ~2 hours (mostly waiting for OCR API)

### 3.3 Add Retry Logic to Frontend Data Load
**What:** If `products.json` fetch fails, page stays broken.
**Why:** Network hiccups shouldn't kill the entire app.
**How:** 3 retries with exponential backoff, user-friendly error + retry button
**Time:** ~30 min

---

## Phase 4: Frontend Polish (Day 4-5)

### 4.1 Show Data Freshness
**What:** No indication of when data was last updated.
**Why:** Users need to know if prices are current.
**How:** Display `meta.exported_at` from `products.json` as "Обновено: преди X часа"
**Time:** ~20 min

### 4.2 Add Price Warning Badge
**What:** Groups with suspicious price ratios get ⚠️ indicator.
**Why:** Transparency — user sees "these might be different sizes"
**How:** Check `warning` flag from Phase 2.2, show badge in comparison modal
**Time:** ~30 min

### 4.3 Show Quantity in Product Cards
**What:** Display "500г" or "1л" on product cards when available.
**Why:** Helps users understand price differences.
**How:** Read `quantity` + `quantity_unit` from product data
**Time:** ~30 min

### 4.4 Cache DOM Lookups + Constants
**What:** Repeated `document.getElementById()` calls, magic numbers everywhere.
**Why:** Code cleanliness. Minor perf improvement.
**How:** Cache elements at init, extract constants
**Time:** ~30 min

---

## Phase 5: Testing & Documentation (Day 5-6)

### 5.1 Add Core Tests
**What:** Zero tests currently.
**Why:** Can't verify matching changes don't break things. Every review flagged this.
**How:**
- `tests/test_matching.py` — known product pairs, expected match/no-match
- `tests/test_quantity.py` — unit parsing edge cases
- `tests/test_export.py` — group validation rules
**Time:** ~3 hours

### 5.2 Update Documentation
**What:** Reflect all changes in docs.
**Why:** Docs are currently A- quality, keep them there.
**How:** Update `DATA_PIPELINE.md`, `EDGE_CASES.md`, `DATA_QUALITY_REPORT.md`
**Time:** ~1 hour

### 5.3 Re-run Full Pipeline
**What:** After all fixes, run complete pipeline: scrape → sync → match → export.
**Why:** Validate everything works together.
**How:** `python scripts/pipeline.py --daily && python scripts/pipeline.py --match --export`
**Time:** ~30 min

---

## What I'm NOT Doing (and Why)

| Suggestion from reviews | Why skipping |
|---|---|
| **i18n / translations system** | Overkill — this is a Bulgarian site for Bulgarian users |
| **PostgreSQL migration** | Not needed at 1,506 products. SQLite is fine for 10x this |
| **PWA / service worker** | Nice-to-have, not a fix |
| **Shopping cart optimizer** | Feature, not fix — separate project |
| **Server-side rendering** | Premature. Static site works fine |
| **DOM element caching** | Doing a lightweight version (Phase 4.4) but not a full refactor |
| **Trie/radix tree for image lookup** | 146 items. Linear search is fine. |

---

## Expected Outcomes

| Metric | Before | After |
|---|---|---|
| Valid groups | 91 | ~60-70 (fewer but correct) |
| Groups with brand mismatch | 66% | <10% |
| Groups with >3x price diff | 32% | Flagged with ⚠️ |
| XSS vulnerabilities | 2 | 0 |
| Products with quantity | 0% | ~60-80% |
| Test coverage | 0% | Core matching + export covered |

---

## Estimated Total: 5-6 working sessions

All changes pushed to GitHub after each phase. No pipeline re-run until Phase 5.3 (after all fixes are in).
