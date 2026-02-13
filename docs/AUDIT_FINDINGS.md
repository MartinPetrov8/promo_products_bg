# Scraper Code Audit - 2026-02-13

## Summary
Two independent audits (DeepSeek + Gemini) identified **35-47 issues** across 10 files.

## Combined Priority Issues

### CRITICAL - Must Fix Before Running

#### 1. Pickle Deserialization (session_manager.py ~215-225)
**Risk:** Remote Code Execution if cookie files are tampered
**Fix:** Replace pickle with JSON for cookie storage

#### 2. Circuit Breaker Missing Public Methods
**Risk:** Scrapers call `record_failure()`/`record_success()` which don't exist!
**Affected:** lidl_product_scraper.py, billa_scraper.py
**Fix:** Add public wrapper methods to CircuitBreaker class

#### 3. is_open() Called as Method (lidl_product_scraper.py ~252)
**Risk:** `if self.circuit_breaker.is_open():` always truthy (returns bound method)
**Fix:** Remove parentheses: `if self.circuit_breaker.is_open:`

### HIGH - Fix Before Production

#### 4. No Transaction Rollback (all scrapers)
**Risk:** Partial data saved on errors
**Fix:** Add explicit BEGIN TRANSACTION / ROLLBACK / COMMIT

#### 5. No Price Validation
**Risk:** Negative or absurd prices stored
**Fix:** Validate 0.01 <= price <= 10000

#### 6. Checkpoint File Race Condition (lidl_product_scraper.py)
**Risk:** File corruption with parallel runs
**Fix:** Use file locking (fcntl) or atomic rename

#### 7. Billa Scraper No DB Save
**Risk:** Inconsistent - only saves JSON, not DB
**Fix:** Add save_to_db() method

#### 8. Thread Safety - Sleep Inside Lock (rate_limiter.py)
**Risk:** Blocks all threads during delay
**Fix:** Sleep outside the lock

### MEDIUM - Fix Soon

- COALESCE doesn't handle empty strings (billa_cleaner.py)
- JSON search range too large (kaufland_enhanced_scraper.py)
- HTML parsing with regex instead of BeautifulSoup (lidl_cleaner.py)
- Hardcoded store IDs, exchange rates, paths
- Fuzzy matching too aggressive (lidl_cleaner.py)
- Thread safety gaps in session_manager.py

### LOW - Fix When Convenient

- Missing type hints
- Regex compiled on each call instead of module-level
- Retry-After header doesn't handle date format
- Brand extraction too aggressive
- No unit tests

## Audit Sources
- DeepSeek R1 (via fallback): 35 issues
- Gemini 2.5 Pro (via fallback): 47 issues (more detailed)
