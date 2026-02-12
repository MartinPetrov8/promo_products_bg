"""
Scraper Configuration

Central configuration for all scraping parameters.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from pathlib import Path


@dataclass
class TimeoutConfig:
    """Timeout settings for different scenarios"""
    connect: float = 10.0      # Connection timeout
    read: float = 30.0         # Read timeout  
    total: float = 60.0        # Total request timeout
    
    # For JS-heavy pages (browser automation)
    browser_page_load: float = 30.0
    browser_element_wait: float = 10.0


@dataclass
class RetryConfig:
    """Retry settings"""
    max_attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0
    jitter: str = "full"  # "full", "equal", "decorrelated", "none"
    
    # Status codes that trigger retry
    retryable_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass 
class RateLimitConfig:
    """Per-domain rate limiting"""
    requests_per_minute: float = 10.0
    min_delay: float = 2.0
    max_delay: float = 30.0
    burst_size: int = 3


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker settings"""
    failure_threshold: int = 5      # Failures before opening
    recovery_timeout: float = 300.0  # Seconds before trying again
    half_open_max_calls: int = 3    # Test calls in half-open state
    success_threshold: int = 2      # Successes needed to close


@dataclass
class StoreSettings:
    """Settings for a specific store"""
    enabled: bool = True
    min_products: int = 50
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    tiers: List[str] = field(default_factory=lambda: ["direct", "aggregator"])


@dataclass
class AlertConfig:
    """Alert settings"""
    enabled: bool = True
    whatsapp_target: str = "+359885997747"
    alert_on_status: List[str] = field(default_factory=lambda: ["unhealthy", "critical"])
    cooldown_seconds: int = 300  # 5 minutes between same alerts


@dataclass
class ScraperConfig:
    """Main scraper configuration"""
    # Paths
    data_dir: Path = Path("./data")
    cache_dir: Path = Path("./data/cache")
    cookie_dir: Path = Path("./data/cookies")
    log_dir: Path = Path("./logs")
    
    # Global settings
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    
    # Per-store settings
    stores: Dict[str, StoreSettings] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default store settings"""
        if not self.stores:
            self.stores = {
                'kaufland': StoreSettings(
                    min_products=800,
                    rate_limit=RateLimitConfig(requests_per_minute=10, min_delay=3.0),
                ),
                'lidl': StoreSettings(
                    min_products=40,
                    rate_limit=RateLimitConfig(requests_per_minute=10, min_delay=3.0),
                ),
                'billa': StoreSettings(
                    min_products=200,
                    rate_limit=RateLimitConfig(requests_per_minute=15, min_delay=2.0),
                ),
                'metro': StoreSettings(
                    enabled=False,  # Not yet implemented
                    min_products=500,
                    rate_limit=RateLimitConfig(requests_per_minute=8, min_delay=4.0),
                ),
                'fantastico': StoreSettings(
                    enabled=False,  # PDF only, not yet implemented
                    min_products=300,
                    tiers=["pdf_ocr"],
                ),
            }
        
        # Ensure directories exist
        for dir_path in [self.data_dir, self.cache_dir, self.cookie_dir, self.log_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)


# Default configuration instance
default_config = ScraperConfig()


# Store-specific URLs and selectors
STORE_URLS = {
    'kaufland': {
        'promos': 'https://www.kaufland.bg/aktualni-predlozheniya/ot-ponedelnik.html',
        'base': 'https://www.kaufland.bg',
    },
    'lidl': {
        'promos': 'https://www.lidl.bg/c/lidl-plus-promotsii/a10039565',
        'base': 'https://www.lidl.bg',
    },
    'billa': {
        'promos': 'https://ssbbilla.site/catalog/sedmichna-broshura',
        'base': 'https://ssbbilla.site',
    },
    'metro': {
        'promos': 'https://shop.metro.bg/shop/broshuri',
        'base': 'https://shop.metro.bg',
    },
}

# Aggregator URLs for Tier 2 fallback
AGGREGATOR_URLS = {
    'katalozi': {
        'base': 'https://katalozi.bg',
        'kaufland': 'https://katalozi.bg/supermarketi/kaufland/',
        'lidl': 'https://katalozi.bg/supermarketi/lidl/',
        'billa': 'https://katalozi.bg/supermarketi/billa/',
        'metro': 'https://katalozi.bg/supermarketi/metro/',
    },
    'broshura': {
        'base': 'https://broshura.bg',
    },
}

# Product count thresholds for validation
MIN_PRODUCT_THRESHOLDS = {
    'kaufland': 400,   # Alert if below this
    'lidl': 20,
    'billa': 100,
    'metro': 250,
    'fantastico': 150,
}

# Selector patterns (for detecting changes)
SELECTORS = {
    'kaufland': {
        'product_container': 'div.k-product-tile',
        'price': 'span.k-price',
        'old_price': 'span.k-crossed-price',
        'name': 'div.k-product-tile__title',
    },
    'lidl': {
        'json_pattern': r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
    },
    'billa': {
        'product_container': 'div.product-item',
        'price': 'span.price',
        'old_price': 'span.old-price',
    },
}
