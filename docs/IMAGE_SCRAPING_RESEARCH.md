# PromoBG Image Scraping Research
## Bulgarian Grocery Retailer Product Image Analysis

### Research Date: 2026-02-14

---

## 1. Kaufland Bulgaria (kaufland.bg)

### 1.1 robots.txt Analysis
```
User-agent: *
Disallow: /etc.clientlibs/
Sitemap: https://www.kaufland.bg/sitemap.xml
```

**Key Finding:** Very permissive robots.txt with minimal restrictions. Only `/etc.clientlibs/` is disallowed - this contains static assets, not product images. Product and promo pages are accessible.

### 1.2 Image CDN Patterns

**Primary CDN:** `media.kaufland.com`

**URL Structure:**
```
https://media.kaufland.com/images/PPIM/KMO/BG{size}_{productID}_P.jpg
```

**Available Sizes:**
- `BG300_` - Thumbnail (300px)
- `BG860_` - Medium (860px)
- `BG3100_` - High resolution (3100px)

**Example URLs found in HTML:**
```
https://media.kaufland.com/images/PPIM/KMO/BG300_09701733_P.jpg
https://media.kaufland.com/images/PPIM/KMO/BG860_09701733_P.jpg
https://media.kaufland.com/images/PPIM/KMO/BG300_20273693_P.jpg
https://media.kaufland.com/images/PPIM/KMO/BG860_20273693_P.jpg
```

**Product ID Format:** 8-digit numbers (e.g., `09701733`, `20273693`)

### 1.3 API Endpoints Discovered

**Offers API:**
```
GET https://www.kaufland.bg/.kloffers.storeName={storeId}.json
```

**Returns:** JSON array with product data including:
- `klNr` - Product ID (used in image URLs)
- `gueltigAb` / `gueltigBis` - Valid from/to dates
- Product category information

**Note:** The offers API returns product references (klNr) that should map to image URLs via the CDN pattern above.

### 1.4 Technical Challenges

⚠️ **Image CDN Access:** Direct requests to `media.kaufland.com` images returned 404 errors during testing, even with:
- Proper User-Agent headers
- Referer headers from kaufland.bg

**Possible causes:**
- Geographic/IP restrictions
- Session cookies required
- CDN caching/availability issues
- Sandbox datacenter IP blocking

### 1.5 Recommended Approach

1. **Browser automation recommended** - Use Playwright/Puppeteer to navigate to promo pages
2. Parse rendered HTML for actual `<img>` tags with media.kaufland.com URLs
3. Download images with session context (cookies preserved)
4. Alternative: Scrape the offers JSON API for product IDs, then attempt image construction

---

## 2. Lidl Bulgaria (lidl.bg)

### 2.1 robots.txt Analysis
```
User-agent: *
Disallow: /search*
Disallow: /cdn-cgi/
```

**Key Finding:** Blocks search query URLs and CDN-CGI (Cloudflare). No restrictions on promo/product pages themselves.

### 2.2 Technical Architecture

**Framework:** Nuxt.js (Vue-based SSR framework)
- Heavy JavaScript dependency
- Content rendered client-side via Vue components
- Uses Lidl Design System (ODS - OpenDesignSystem)

**Static Assets Path:** `/static/assets/`

### 2.3 Technical Challenges

⚠️ **Heavy JavaScript Dependency:** Page content (including images) is loaded dynamically via JavaScript hydration. The initial HTML response contains minimal content.

⚠️ **Non-browser Request Blocking:** Server returns outdated browser warnings for non-browser user agents, though basic responses are possible.

⚠️ **No Direct Image CDN Pattern Found:** Unlike Kaufland, Lidl doesn't expose a predictable CDN URL structure in the static HTML.

### 2.4 Leaflet/Brochure System

Lidl uses a leaflet-based promotional system:
- URL pattern: `/c/broshuri/s{categoryId}` or `/p/broshura/s{leafletId}`
- Internal API discovered: `http://prod-sfapi.explore-prod.svc.cluster.local:80/` (internal only)

### 2.5 Recommended Approach

1. **Browser automation required** - Playwright/Puppeteer essential due to JS-heavy architecture
2. Navigate to promotional pages and wait for full hydration
3. Extract image URLs from rendered DOM
4. May need to handle lazy-loading (scroll to load all products)
5. Consider screenshot approach for leaflet pages as fallback

---

## 3. Billa Bulgaria (billa.bg)

### 3.1 robots.txt Analysis
```
User-agent: *
Sitemap: https://www.billa.bg/sitemap.xml
```

**Key Finding:** Most permissive robots.txt - no Disallow rules at all. All paths are accessible for scraping.

### 3.2 Image CDN Patterns

**Primary CDN:** Kentico Kontent (`assets-eu-01.kc-usercontent.com`)

**URL Structure:**
```
https://assets-eu-01.kc-usercontent.com:443/{projectId}/{assetId}/{filename}.{ext}
```

**Project ID Found:** `67ab30e1-a5ea-0103-0955-0146e30b09e6`

**Example URLs:**
```
https://assets-eu-01.kc-usercontent.com:443/67ab30e1-a5ea-0103-0955-0146e30b09e6/a10cde79-6bb6-4486-b501-b74b0107facc/favicon.png
https://assets-eu-01.kc-usercontent.com:443/67ab30e1-a5ea-0103-0955-0146e30b09e6/0d6e9453-3bf1-42f0-aac8-60ef338e30a0/Billa_Vauchers_General_1000x563_1.jpg
```

**Image Transformation Parameters (query string):**
- `w={width}` - Resize width
- `fm=webp` - Output format (webp, jpg, png)
- `lossless=0|1` - Lossless compression
- `q={quality}` - Quality (0-100)
- `dpr={ratio}` - Device pixel ratio

**Example with transforms:**
```
?w=200&fm=webp&lossless=0&q=80&dpr=2
```

### 3.3 Technical Architecture

**Framework:** Nuxt.js (Vue-based)
- Similar JS dependency to Lidl
- NUXT state config embedded in HTML
- Content managed via Kentico Kontent CMS

### 3.4 CMS Backend

Billa uses **Kentico Kontent** headless CMS:
- Assets stored in EU region (`assets-eu-01`)
- Each asset has a UUID-based path
- Image transformation API available at URL level

### 3.5 Recommended Approach

1. **Mixed approach works:**
   - Basic promotional banners/images can be extracted via simple HTTP requests
   - Product detail images may require browser automation
2. Parse HTML for `assets-eu-01.kc-usercontent.com` URLs
3. Modify image transform parameters to get desired resolution
4. Store original asset URLs (without transforms) for maximum quality

---

## 4. Legal/TOS Considerations

### 4.1 General Guidelines

| Retailer | robots.txt Compliance | Rate Limiting | Public Data |
|----------|----------------------|---------------|-------------|
| Kaufland | ✅ Permissive | Unknown | Yes |
| Lidl | ✅ Permissive (except search) | Unknown | Yes |
| Billa | ✅ Most permissive | Unknown | Yes |

### 4.2 Recommendations

1. **Respect robots.txt** - All three sites are generally permissive
2. **Implement rate limiting** - Add delays between requests (1-2 seconds minimum)
3. **Use appropriate User-Agent** - Identify your scraper clearly
4. **Cache aggressively** - Product images don't change frequently
5. **Store attribution** - Keep record of image source URLs

### 4.3 Terms of Service Notes

Standard Bulgarian e-commerce TOS typically:
- Allow viewing/caching for personal use
- Restrict bulk downloading for commercial purposes
- May require permission for republishing

**Recommendation:** For a price comparison/promo aggregator like PromoBG:
- This constitutes "fair use" in most jurisdictions
- Displaying promo information benefits consumers
- Maintain proper attribution to source retailers
- Consider reaching out for formal API access if scaling significantly

---

## 5. Implementation Recommendations

### 5.1 Recommended Tech Stack

```
Playwright (Node.js or Python)
├── Browser automation for all three sites
├── Screenshot capabilities for leaflets
└── Cookie/session handling
```

### 5.2 Scraping Strategy by Retailer

#### Kaufland
```python
# Priority: Use offers API + image URL construction
1. Fetch /.kloffers.storeName={store}.json
2. Extract klNr (product IDs)
3. Construct image URLs: media.kaufland.com/images/PPIM/KMO/BG860_{klNr}_P.jpg
4. Download with browser session context
```

#### Lidl
```python
# Priority: Full browser automation
1. Navigate to /aktualni-predlozheniya or leaflet pages
2. Wait for full page hydration (networkidle)
3. Scroll to trigger lazy loading
4. Extract all img[src] elements
5. Download images with session preserved
```

#### Billa
```python
# Priority: HTTP + browser hybrid
1. Fetch promo page HTML
2. Regex/parse for assets-eu-01.kc-usercontent.com URLs
3. Direct download without browser (CDN is publicly accessible)
4. Use w=800&fm=jpg&q=85 for standardized output
```

### 5.3 Image Storage Recommendations

```
/images/
├── kaufland/
│   └── {productId}_{timestamp}.jpg
├── lidl/
│   └── {leafletId}_{productIndex}_{timestamp}.jpg
└── billa/
    └── {assetId}_{timestamp}.jpg
```

### 5.4 Rate Limiting Guidelines

| Site | Recommended Delay | Max Concurrent |
|------|-------------------|----------------|
| Kaufland | 1-2 seconds | 2 connections |
| Lidl | 2-3 seconds | 1 connection |
| Billa | 1 second | 3 connections |

---

## 6. Summary Comparison Table

| Feature | Kaufland | Lidl | Billa |
|---------|----------|------|-------|
| **robots.txt** | Permissive | Semi-restrictive | Most permissive |
| **JS Required** | Partial | Yes (heavy) | Partial |
| **CDN Pattern** | Predictable | Unknown | Predictable |
| **API Available** | Yes (offers JSON) | No (internal only) | No |
| **Direct Download** | Problematic | No | Yes |
| **Browser Needed** | Recommended | Required | Optional |
| **Image Quality** | Up to 3100px | Variable | Configurable |
| **Ease of Scraping** | Medium | Hard | Easy |

---

## 7. Quick Start Code Snippets

### Billa (Easiest - Direct HTTP)
```python
import re
import requests

def scrape_billa_images(url):
    resp = requests.get(url, headers={'User-Agent': 'PromoBG-Scraper/1.0'})
    pattern = r'https://assets-eu-01\.kc-usercontent\.com:443/[^"\s]+'
    return list(set(re.findall(pattern, resp.text)))
```

### Kaufland (Medium - API + Browser)
```python
import requests
import json

def get_kaufland_offers(store_id='1234'):
    url = f'https://www.kaufland.bg/.kloffers.storeName={store_id}.json'
    resp = requests.get(url)
    offers = json.loads(resp.text)
    
    images = []
    for offer in offers:
        kl_nr = offer.get('klNr', '')
        if kl_nr:
            images.append(f'https://media.kaufland.com/images/PPIM/KMO/BG860_{kl_nr}_P.jpg')
    return images
```

### Lidl (Hardest - Full Browser Automation)
```python
from playwright.sync_api import sync_playwright

def scrape_lidl_images():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto('https://www.lidl.bg/aktualni-predlozheniya')
        page.wait_for_load_state('networkidle')
        
        # Scroll to load lazy images
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(2000)
        
        images = page.query_selector_all('img')
        urls = [img.get_attribute('src') for img in images if img.get_attribute('src')]
        browser.close()
        return urls
```

---

## 8. Next Steps

1. **Implement Billa scraper first** - Lowest friction, good for MVP
2. **Add Kaufland API integration** - Medium effort, good product data
3. **Build Lidl browser automation** - Most complex, save for last
4. **Set up image storage pipeline** - S3 or local with CDN
5. **Create product matching system** - Link images to promo data

---

*Research completed: 2026-02-14*
*Researcher: PromoBG Image Research Subagent*
