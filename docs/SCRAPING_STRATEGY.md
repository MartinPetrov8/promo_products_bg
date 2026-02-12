# Scraping Strategy & Fallback Plan

> **Version:** 1.0
> **Last Updated:** 2026-02-12
> **Status:** Draft → Needs Testing

This document defines the core scraping logic, error handling, and fallback strategies for PromoBG. **This is the backbone of the project.**

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Scraping Tiers](#scraping-tiers)
3. [Per-Store Strategy](#per-store-strategy)
4. [Error Classification](#error-classification)
5. [Fallback Waterfall](#fallback-waterfall)
6. [Rate Limiting & Politeness](#rate-limiting--politeness)
7. [Monitoring & Alerts](#monitoring--alerts)
8. [Recovery Procedures](#recovery-procedures)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      SCRAPER ORCHESTRATOR                        │
│  (Manages scheduling, retries, fallbacks, health monitoring)     │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   TIER 1      │    │   TIER 2      │    │   TIER 3      │
│ Direct Scrape │───▶│  Aggregators  │───▶│  Manual/OCR   │
│  (Primary)    │    │  (Fallback)   │    │  (Emergency)  │
└───────────────┘    └───────────────┘    └───────────────┘
```

### Design Principles
1. **Fail gracefully** — Never crash the whole system; isolate failures per-store
2. **Degrade, don't die** — Stale data > no data > crashed scraper
3. **Be polite** — Respect robots.txt, rate limits; we're not attacking
4. **Log everything** — Every request, response, error for debugging
5. **Alert early** — Detect issues before users notice

---

## Scraping Tiers

### Tier 1: Direct Website Scraping (Primary)
- Scrape retailer's own website
- Freshest data, most accurate
- Higher risk of blocks

### Tier 2: Aggregator Scraping (Fallback)
- Scrape from katalozi.bg, broshura.bg, etc.
- Data may be 1-2 days delayed
- Lower block risk (they expect scrapers)

### Tier 3: Manual/OCR (Emergency)
- PDF brochure download + OCR extraction
- Highest latency, lowest accuracy
- Last resort only

---

## Per-Store Strategy

### Kaufland
| Tier | Source | Method | Reliability |
|------|--------|--------|-------------|
| 1 | kaufland.bg/aktualni-predlozheniya | CSS selectors (`div.k-product-tile`) | ⭐⭐⭐⭐ |
| 2 | katalozi.bg/supermarketi/kaufland | HTML parsing | ⭐⭐⭐ |
| 3 | PDF brochure OCR | Tesseract/Claude Vision | ⭐⭐ |

**Known issues:**
- None currently; stable scraping

### Lidl
| Tier | Source | Method | Reliability |
|------|--------|--------|-------------|
| 1 | lidl.bg/c/lidl-plus-promotsii | Embedded JSON extraction | ⭐⭐⭐⭐ |
| 2 | katalozi.bg/supermarketi/lidl | HTML parsing | ⭐⭐⭐ |
| 3 | PDF brochure OCR | Tesseract/Claude Vision | ⭐⭐ |

**Known issues:**
- Data is HTML-escaped JSON; needs `html.unescape()`
- Product count lower than expected (53 vs expected ~100+)

### Billa
| Tier | Source | Method | Reliability |
|------|--------|--------|-------------|
| 1 | ssbbilla.site/catalog/sedmichna-broshura | CSS selectors | ⭐⭐⭐⭐ |
| 2 | katalozi.bg/supermarketi/billa | HTML parsing | ⭐⭐⭐ |
| 3 | billa.bg PDF + OCR | Tesseract/Claude Vision | ⭐⭐ |

**Known issues:**
- Main billa.bg has no structured data
- ssbbilla.site is accessibility version (stable)

### Metro (Planned)
| Tier | Source | Method | Reliability |
|------|--------|--------|-------------|
| 1 | shop.metro.bg/shop/broshuri | JS rendering needed | ⭐⭐⭐ |
| 2 | katalozi.bg/supermarketi/metro | HTML parsing | ⭐⭐⭐ |
| 3 | PDF brochure OCR | Tesseract/Claude Vision | ⭐⭐ |

**Known issues:**
- metro.bg blocks datacenter IPs (403)
- B2B focus; may have different promo structure

### Fantastico (Planned)
| Tier | Source | Method | Reliability |
|------|--------|--------|-------------|
| 1 | N/A | No web data | ❌ |
| 2 | katalozi.bg/supermarketi/fantastico | HTML parsing | ⭐⭐⭐ |
| 3 | PDF brochure OCR | Primary method | ⭐⭐⭐ |

**Known issues:**
- PDF-only retailer; OCR is primary, not fallback

---

## Error Classification

### Transient Errors (Auto-Retry)
| Error | Detection | Action |
|-------|-----------|--------|
| Timeout | `requests.Timeout` | Retry 3x with exponential backoff |
| 429 Too Many Requests | HTTP 429 | Wait `Retry-After` header or 60s |
| 500/502/503 | HTTP 5xx | Retry 3x, then mark store unhealthy |
| Connection Reset | `ConnectionError` | Retry 3x with 30s delay |
| Empty Response | `len(products) == 0` | Retry 2x, then check selectors |

### Permanent Errors (Escalate to Fallback)
| Error | Detection | Action |
|-------|-----------|--------|
| 403 Forbidden | HTTP 403 | Switch to Tier 2 immediately |
| 401 Unauthorized | HTTP 401 | Check if auth required; switch tier |
| Cloudflare Block | Error 1010/1020 | Switch to Tier 2 or use browser |
| CAPTCHA | Pattern in HTML | Switch to Tier 2 |
| Selector Changed | 0 products + 200 OK | Alert + manual review |

### Critical Errors (Human Intervention)
| Error | Detection | Action |
|-------|-----------|--------|
| All tiers failed | 3 consecutive tier failures | Alert Martin |
| Selector breakage | Multiple stores affected | Alert + pause scraper |
| Legal notice | Cease & desist pattern | STOP immediately, alert |

---

## Fallback Waterfall

```python
async def scrape_store(store: str) -> List[Product]:
    """
    Waterfall through tiers until success.
    """
    tiers = get_tiers_for_store(store)  # [tier1_fn, tier2_fn, tier3_fn]
    
    for tier_num, scrape_fn in enumerate(tiers, 1):
        try:
            log.info(f"[{store}] Attempting Tier {tier_num}")
            products = await scrape_fn()
            
            # Sanity check: did we get reasonable data?
            if len(products) < MIN_PRODUCTS[store] * 0.5:
                log.warning(f"[{store}] Tier {tier_num} returned suspiciously few products")
                continue  # Try next tier
            
            log.info(f"[{store}] Tier {tier_num} SUCCESS: {len(products)} products")
            record_success(store, tier_num)
            return products
            
        except TransientError as e:
            log.warning(f"[{store}] Tier {tier_num} transient error: {e}")
            # Retry logic handled inside scrape_fn
            continue
            
        except PermanentError as e:
            log.error(f"[{store}] Tier {tier_num} permanent error: {e}")
            continue  # Move to next tier
            
        except Exception as e:
            log.exception(f"[{store}] Tier {tier_num} unexpected error")
            continue
    
    # All tiers failed
    log.critical(f"[{store}] ALL TIERS FAILED")
    alert_human(store, "All scraping tiers failed")
    return get_cached_data(store)  # Return stale data as last resort
```

### Minimum Product Thresholds
Used to detect selector breakage vs actual empty data:

| Store | Min Expected | Alert If Below |
|-------|-------------|----------------|
| Kaufland | 800 | 400 |
| Lidl | 40 | 20 |
| Billa | 200 | 100 |
| Metro | 500 | 250 |
| Fantastico | 300 | 150 |

---

## Rate Limiting & Politeness

### Per-Domain Limits
```python
RATE_LIMITS = {
    "kaufland.bg": {"requests_per_minute": 10, "delay_between": 6},
    "lidl.bg": {"requests_per_minute": 10, "delay_between": 6},
    "ssbbilla.site": {"requests_per_minute": 20, "delay_between": 3},
    "katalozi.bg": {"requests_per_minute": 30, "delay_between": 2},
    "broshura.bg": {"requests_per_minute": 30, "delay_between": 2},
}
```

### Request Headers
```python
HEADERS = {
    "User-Agent": rotate_user_agent(),  # Rotate from pool of 10+ real browsers
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}
```

### User-Agent Rotation Pool
```python
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]
```

### Robots.txt Compliance
- Check robots.txt on first run for each domain
- Cache for 24 hours
- Respect `Crawl-delay` if specified
- Skip disallowed paths

---

## Monitoring & Alerts

### Health Metrics (per store)
```python
@dataclass
class StoreHealth:
    store: str
    last_success: datetime
    last_failure: datetime | None
    current_tier: int  # Which tier is working
    consecutive_failures: int
    products_last_scrape: int
    avg_scrape_time_ms: float
    status: Literal["healthy", "degraded", "unhealthy", "critical"]
```

### Status Definitions
| Status | Meaning | Action |
|--------|---------|--------|
| `healthy` | Tier 1 working, normal product count | None |
| `degraded` | Using Tier 2 or product count below normal | Log, monitor |
| `unhealthy` | Using Tier 3 or 2+ consecutive failures | Alert Martin |
| `critical` | All tiers failed, serving stale data | Alert immediately |

### Alert Channels
1. **Log file** — All events (DEBUG level)
2. **Console** — Warnings and above
3. **WhatsApp** — Critical alerts only (via OpenClaw message tool)
4. **Daily digest** — Summary of all store health at 08:00

### Alert Message Format
```
🚨 SCRAPER ALERT: {store}
Status: {status}
Error: {error_type}
Last success: {time_ago}
Current tier: {tier}
Action needed: {recommendation}
```

---

## Recovery Procedures

### Scenario 1: Single Store Blocked (403/Cloudflare)
1. Scraper auto-switches to Tier 2
2. Log the event with timestamp
3. After 24h, attempt Tier 1 again (IP might be unblocked)
4. If persists 72h+, consider:
   - Residential proxy for that store
   - Browser automation (Playwright)
   - Accept Tier 2 as new primary

### Scenario 2: Selector Changed (0 products, 200 OK)
1. Scraper alerts with "selector breakage suspected"
2. Human reviews page structure manually
3. Update selectors in `selectors.py`
4. Test with `--dry-run` flag
5. Deploy fix

### Scenario 3: Aggregator Down
1. Tier 2 fails, try Tier 3 (PDF/OCR)
2. If critical store, manually check aggregator
3. Find alternative aggregator if needed
4. Update tier config

### Scenario 4: Mass Failure (3+ stores down)
1. PAUSE all scraping immediately
2. Check if it's our IP (try from different network)
3. Check if sites are actually down (downdetector)
4. If our fault: review recent code changes
5. If their fault: wait and monitor

---

## Implementation Checklist

### Phase 1: Core Logic (Current)
- [x] Basic scrapers for 3 stores
- [ ] Implement `ScraperOrchestrator` class
- [ ] Add retry logic with exponential backoff
- [ ] Add per-domain rate limiting
- [ ] Implement health tracking

### Phase 2: Fallbacks
- [ ] Build Tier 2 scrapers (katalozi.bg, broshura.bg)
- [ ] Implement tier waterfall logic
- [ ] Add stale data caching
- [ ] Test fallback switching

### Phase 3: Monitoring
- [ ] Health dashboard endpoint
- [ ] WhatsApp alert integration
- [ ] Daily digest cron job
- [ ] Metrics logging (Prometheus-compatible)

### Phase 4: Hardening
- [ ] Proxy rotation support
- [ ] Browser automation fallback (Playwright)
- [ ] PDF/OCR pipeline for Fantastico
- [ ] Automated selector healing (experimental)

---

## Configuration File

All settings in `config/scraper_config.yaml`:

```yaml
scraper:
  global:
    max_concurrent_stores: 3
    request_timeout_seconds: 30
    retry_attempts: 3
    retry_backoff_base: 2  # Exponential: 2^attempt seconds
    
  stores:
    kaufland:
      enabled: true
      tiers: [direct, katalozi, pdf]
      min_products: 800
      schedule: "0 6 * * *"  # 6 AM daily
      
    lidl:
      enabled: true
      tiers: [direct, katalozi, pdf]
      min_products: 40
      schedule: "0 6 * * *"
      
    billa:
      enabled: true
      tiers: [direct, katalozi, pdf]
      min_products: 200
      schedule: "0 6 * * *"
      
  alerts:
    whatsapp_enabled: true
    whatsapp_target: "+359885997747"
    alert_on: [unhealthy, critical]
    daily_digest_time: "08:00"
    
  rate_limits:
    default_rpm: 10
    default_delay: 6
    overrides:
      katalozi.bg: {rpm: 30, delay: 2}
```

---

## Appendix: Error Codes Quick Reference

| Code | Meaning | Retry? | Fallback? |
|------|---------|--------|-----------|
| 200 + 0 products | Selector broken | No | Yes |
| 403 | Forbidden/Blocked | No | Yes |
| 429 | Rate limited | Yes (with delay) | If persists |
| 500 | Server error | Yes | If persists |
| 502 | Bad gateway | Yes | If persists |
| 503 | Service unavailable | Yes | If persists |
| Timeout | Network issue | Yes | If persists |
| ConnectionError | Network issue | Yes | If persists |
| 1010/1020 | Cloudflare | No | Yes |

---

*This document is the source of truth for scraping behavior. Update it when adding stores or changing logic.*
