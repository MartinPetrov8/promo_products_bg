# Matching Pipeline v3 — Transliteration + Better Tokenization

**Date:** 2026-02-18
**Based on:** Kimi K2.5 + Sonnet audit findings
**Goal:** Increase match rate from 6.4% (96 matches) to 20-40% (300-600 matches)

## Changes (in order)

### 1. Transliteration Layer (`scripts/transliteration.py`)
- Cyrillic→Latin and Latin→Cyrillic conversion
- Brand alias dictionary (50+ common brands)
- Product type synonym dictionary
- All tokens expanded with transliteration variants before comparison

### 2. Better Tokenizer (update `tokenize()` in pipeline.py)
- Split on hyphens, slashes, parentheses
- Separate numbers from units: "400гр" → "400", "гр"
- Normalize units to canonical forms
- Less aggressive stopword removal

### 3. Character N-gram Secondary Signal
- Trigram Jaccard as fuzzy backup (catches transliteration without dictionary)
- Combined score: 0.7 × token_similarity + 0.3 × ngram_similarity

### 4. Soft Category Gating
- Category mismatch = 0.9x penalty instead of hard reject
- Category compatibility map for known overlaps

### 5. Lower Thresholds
- Min threshold: 0.5 → 0.4
- Min common tokens: 2 → 1 (after transliteration expansion)

## Success Criteria
- Match count: 96 → 200+ (conservative target)
- False positive rate: < 10% (spot-check 20 random matches)
- No regression on existing high-confidence matches
