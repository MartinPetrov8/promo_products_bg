# OCR Scraper for Grocery Brochures

## Overview
Extract product names, prices, and descriptions from scanned brochure images (Publitas, broshura.bg).

## Current Progress

### Publitas (Billa Brochures)
- ✅ Found PDF download URL pattern: `view.publitas.com/{groupId}/{pubId}/pdfs/{pdfId}.pdf`
- ✅ Downloaded test brochure: 50 pages, 17.5MB
- ✅ Extracted page images using `pdfimages`
- ⏳ OCR library installation in progress

### PDF Structure
- **URL pattern:** `https://view.publitas.com/billa-bulgaria/{slug}/`
- **PDF location:** Found in HTML, direct download
- **Page images:** Can extract via `pdfimages -j` or PyMuPDF

## OCR Options Evaluated

### 1. PaddleOCR (Preferred)
- **Pros:** Good Bulgarian support, free, state-of-the-art accuracy
- **Cons:** Large model download, complex setup
- **Languages:** Bulgarian (bg) supported
- **Status:** Installing...

### 2. EasyOCR
- **Pros:** Easy setup, supports Bulgarian, good accuracy
- **Cons:** Slower than PaddleOCR
- **Languages:** Bulgarian (bg) supported
- **Status:** Installing...

### 3. Tesseract
- **Pros:** Fast, widely used, free
- **Cons:** Lower accuracy for Bulgarian, needs training data
- **Languages:** Bulgarian available but quality varies

### 4. Google Vision API
- **Pros:** Best accuracy, handles complex layouts
- **Cons:** Paid (~$1.50/1000 pages)
- **Use case:** Fallback for difficult pages

## Pipeline Design

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│ PDF Download    │───►│ Page Extract │───►│ OCR Engine  │
│ (curl/requests) │    │ (pdfimages)  │    │ (PaddleOCR) │
└─────────────────┘    └──────────────┘    └──────────────┘
                                                  │
                                                  ▼
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│ Database Import │◄───│ Price Parser │◄───│ Text Blocks │
│ (products,      │    │ (regex, NLP) │    │ (structured)│
│  prices tables) │    └──────────────┘    └─────────────┘
└─────────────────┘
```

### Step 1: PDF/Image Acquisition
```python
# Download brochure PDF
curl -o brochure.pdf "https://view.publitas.com/.../pdfs/{id}.pdf"

# Extract pages as images
pdfimages -j brochure.pdf pages/page
```

### Step 2: OCR Processing
```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(lang='bg', use_angle_cls=True)
result = ocr.ocr('page-001.jpg')

# Result: list of [bbox, (text, confidence)]
for line in result[0]:
    bbox = line[0]  # [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
    text = line[1][0]
    conf = line[1][1]
```

### Step 3: Product Extraction
Key patterns to detect:
- **Price:** `X,XX лв` or `X.XX лв`
- **Unit price:** `X,XX лв/кг` or `X,XX лв/л`
- **Old price:** Usually struck through or in red
- **Product name:** Near price, usually above

### Step 4: Database Import
Map extracted products to existing DB schema:
- Match by name similarity to existing products
- Create new products if no match
- Insert prices with `is_promotional=1`

## Test Data
- `data/brochures/billa_cw07.pdf` - 50 pages, Billa weekly 12-18 Feb 2026
- `data/brochures/pages/` - Extracted JPG images

## Next Steps
1. Complete OCR library installation
2. Test on single page with Bulgarian text
3. Build extraction regex for prices
4. Create product matching logic
5. Run on full brochure
6. Integrate with scheduled scraping

## Challenges
- **Layout complexity:** Products arranged in grid, varying sizes
- **Price variations:** "2 за X лв", "от X лв", promotional badges
- **Image quality:** Some pages may have low resolution
- **Brand detection:** Need to extract brand from product name

---

## Installation Issues (2026-02-13)

### Sandbox Limitations
- Cannot install system packages (tesseract-ocr)
- PaddleOCR installed but has shared object loading issues
- Need host-level installation or Docker container with OCR tools

### Workaround Options

#### Option 1: Host Installation (Recommended)
```bash
# On host machine (Martin to run):
sudo apt-get install tesseract-ocr tesseract-ocr-bul
pip install pytesseract paddleocr easyocr
```

#### Option 2: Docker Container with OCR
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-bul
RUN pip install paddleocr easyocr pytesseract
```

#### Option 3: Cloud OCR API
- Use Google Vision API for initial testing
- Costs ~$1.50/1000 images
- Best accuracy for Bulgarian text

### Current Assets Ready
- ✅ PDF download working (Publitas URL pattern found)
- ✅ Page extraction working (pdfimages)
- ✅ Test brochure downloaded (50 pages)
- ⏳ OCR engine needs host installation

### Next Session TODO
1. Martin: Install tesseract-ocr-bul on host
2. Test OCR on sample page
3. Build price extraction regex
4. Create product matcher

---

## Implementation Complete (2026-02-13 23:15 UTC)

### GPT-4 Vision OCR Working ✅

Tested successfully on Billa brochure:
- **5 pages processed** → **41 products extracted**
- Extracts: name, price, old_price, unit, discount_pct
- Cost: ~$0.01-0.02 per page (gpt-4o-mini)

### Created: `ocr_brochure_scraper.py`

```bash
# Usage examples:
python ocr_brochure_scraper.py --url 'https://view.publitas.com/billa-bulgaria/...'
python ocr_brochure_scraper.py --pdf data/brochures/billa.pdf --max-pages 20
```

### Features
- Downloads PDFs from Publitas URLs automatically
- Extracts pages as JPEG using pdfimages
- GPT-4 Vision for Bulgarian text OCR
- Structured JSON output
- Rate limiting (1 req/sec)
- Error handling and stats

### Sample Output
```json
{
  "name": "БЪЛГАРСКА ФЕРМА Пилешки бут",
  "price": 3.79,
  "old_price": 5.99,
  "unit": "кг",
  "discount_pct": 37
}
```

### Cost Estimate
- 50-page brochure: ~$0.50-1.00 with gpt-4o-mini
- Weekly run for 3 stores: ~$3-5/week

### Next Steps
1. Add database import for extracted products
2. Schedule weekly brochure scrapes
3. Add broshura.bg support
4. Improve product matching to existing DB
