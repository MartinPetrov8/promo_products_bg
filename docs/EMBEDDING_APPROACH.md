# Embedding-Based Matching: Lessons Learned

## Summary
We tried using LaBSE (Language-agnostic BERT Sentence Embeddings) to match Bulgarian promo products against Open Food Facts. **It didn't work.**

## What We Tried
- **Model:** `sentence-transformers/LaBSE` (multilingual, 768-dim embeddings)
- **Thresholds tested:** 0.65, 0.75, 0.85
- **Products:** 2,345 unmatched promo products vs 14,853 OFF products

## Results
| Threshold | Matches Found | False Positive Rate |
|-----------|---------------|---------------------|
| ≥0.85 (confident) | 0 | N/A |
| ≥0.75 (likely) | 17 | **100%** |
| ≥0.65 (low) | 194 | **~100%** |

## Why It Failed

### 1. Phonetic/Visual Matching Instead of Semantic
LaBSE matched words that *sound* similar, not products that *are* the same:

| Score | Promo Product | OFF Match | Reality |
|-------|--------------|-----------|---------|
| 0.828 | Меко (soft) | Мляко (milk) | Different words |
| 0.811 | Кухненска везна (kitchen scale) | Зехтин за готвене (cooking oil) | Appliance vs food |
| 0.794 | Препарат за съдове (dish soap) | Маргарин XXL | Cleaning vs food |
| 0.787 | Крем душ гел (shower gel) | Крем халва | Cosmetic vs food |
| 0.758 | Пасатор (blender) | Пастърма (pastrami) | Appliance vs meat |
| 0.773 | Бебешки клинове (baby clothes) | Кренвирши за деца (sausages) | Clothing vs food |

### 2. Domain Mismatch
- **Open Food Facts** = food products only
- **Promo database** = ALL products (food, appliances, cosmetics, clothes, flowers, tools)
- Most unmatched products are **non-food** — no valid match exists!

### 3. LaBSE Not Designed for This
LaBSE is optimized for sentence-level semantic similarity across languages, not product identity matching. It treats "kitchen scale" and "cooking oil" as related (both kitchen-related) even though they're completely different products.

## Conclusion
**Embedding-based matching is the wrong approach for this problem.**

## What Works Instead
1. **Barcode matching** — 288 matches (100% accurate)
2. **Token matching** — 2,415 matches (high accuracy)
3. **Transliteration matching** — 1,031 matches (good accuracy)
4. **Manual/LLM matching** — For remaining food products

## Files
- `scripts/phase2_embeddings_fixed.py` — Original embedding script
- `scripts/phase2_embeddings_v3.py` — Lower threshold version (confirmed failure)
