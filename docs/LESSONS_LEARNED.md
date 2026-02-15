
## 2026-02-15: Adaptable Scraping (CRITICAL)

### Problem
Lidl changed their website structure - sitemap.xml now returns 404. The rigid sitemap-based scraper broke completely.

### Lesson
Retailers WILL:
- Change site structure
- Remove sitemaps
- Block scrapers
- Update offers frequently

### Solution: Adaptive Scraping Architecture
1. **Multi-strategy approach**: Try sitemap → category pages → search → homepage crawl
2. **Human-like behavior**: 
   - Gaussian delays (not fixed intervals)
   - Coffee breaks (long pauses)
   - Session rotation
   - Real browser fingerprints
3. **Self-healing**: If one method fails, fall back to another
4. **Patience over speed**: 30 minutes for complete data > 30 seconds for partial data
5. **Monitoring**: Track success rates, detect when sites change

### Implementation
- Each scraper must have multiple extraction strategies
- Graceful degradation when primary method fails
- Log which methods work for future optimization
