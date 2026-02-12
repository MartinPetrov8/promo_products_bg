"""
Scraper Orchestrator

Coordinates all scraping operations with:
- Multi-tier fallback system
- Circuit breakers per store
- Adaptive rate limiting
- Health monitoring
- Session management
- Automatic error recovery
"""

import time
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path
from abc import ABC, abstractmethod
import json

from .rate_limiter import DomainRateLimiter
from .circuit_breaker import CircuitBreaker, CircuitBreakerError, circuit_registry
from .session_manager import SessionManager
from .health_monitor import HealthMonitor, HealthStatus
from .retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)


@dataclass
class ScraperTier:
    """Configuration for a scraping tier"""
    name: str
    scraper_func: Callable[[], List[Dict]]
    priority: int = 1  # Lower = higher priority
    description: str = ""


@dataclass
class StoreConfig:
    """Configuration for a store's scraping"""
    store_id: str
    display_name: str
    tiers: List[ScraperTier]
    min_products: int = 50
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 300.0  # 5 minutes


class BaseScraper(ABC):
    """Base class for all scrapers"""
    
    @abstractmethod
    def scrape(self) -> List[Dict]:
        """Execute scrape and return list of products"""
        pass
    
    @property
    @abstractmethod
    def store_id(self) -> str:
        """Unique identifier for this store"""
        pass
    
    @property
    def tier(self) -> int:
        """Tier level (1 = primary, 2 = fallback, etc.)"""
        return 1


class ScraperOrchestrator:
    """
    Main orchestrator that coordinates all scraping operations.
    
    Features:
    - Multi-tier fallback (direct -> aggregator -> PDF/OCR)
    - Per-store circuit breakers
    - Adaptive rate limiting
    - Health monitoring with alerts
    - Session management with rotation
    - Stale data caching as last resort
    """
    
    def __init__(
        self,
        data_dir: str = "./data",
        alert_callback: Optional[Callable[[str, str, Dict], None]] = None
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Core components
        self.rate_limiter = DomainRateLimiter()
        self.session_manager = SessionManager(cookie_dir=str(self.data_dir / "cookies"))
        self.health_monitor = HealthMonitor(alert_callback=alert_callback)
        self.retry_handler = RetryHandler(RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            jitter="full"
        ))
        
        # Store configurations
        self.store_configs: Dict[str, StoreConfig] = {}
        
        # Circuit breakers per store
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Cache for stale data fallback
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
    
    def register_store(self, config: StoreConfig):
        """Register a store configuration"""
        self.store_configs[config.store_id] = config
        
        # Create circuit breaker for store
        self.circuit_breakers[config.store_id] = CircuitBreaker(
            name=f"store_{config.store_id}",
            failure_threshold=config.circuit_failure_threshold,
            recovery_timeout=config.circuit_recovery_timeout,
        )
        
        logger.info(f"Registered store: {config.display_name} with {len(config.tiers)} tiers")
    
    def scrape_store(self, store_id: str) -> Dict:
        """
        Scrape a single store using tier waterfall.
        
        Returns:
            Dict with keys: success, products, tier_used, error, from_cache
        """
        config = self.store_configs.get(store_id)
        if not config:
            raise ValueError(f"Unknown store: {store_id}")
        
        circuit = self.circuit_breakers[store_id]
        
        # Check circuit breaker
        if circuit.is_open:
            logger.warning(f"[{store_id}] Circuit is OPEN, using cached data")
            return self._get_cached_result(store_id)
        
        # Sort tiers by priority
        tiers = sorted(config.tiers, key=lambda t: t.priority)
        
        # Try each tier
        for tier_idx, tier in enumerate(tiers, 1):
            try:
                logger.info(f"[{store_id}] Attempting Tier {tier_idx}: {tier.name}")
                
                start_time = time.time()
                products = self._execute_tier(store_id, tier)
                elapsed = time.time() - start_time
                
                # Validate results
                if len(products) < config.min_products * 0.5:
                    logger.warning(
                        f"[{store_id}] Tier {tier_idx} returned only {len(products)} products "
                        f"(expected >= {config.min_products * 0.5:.0f})"
                    )
                    continue
                
                # Success!
                self.health_monitor.record_success(
                    scraper_id=store_id,
                    response_time=elapsed,
                    product_count=len(products),
                    tier=tier_idx
                )
                
                # Cache successful results
                self._cache_results(store_id, products)
                
                logger.info(
                    f"[{store_id}] Tier {tier_idx} SUCCESS: {len(products)} products in {elapsed:.2f}s"
                )
                
                return {
                    'success': True,
                    'products': products,
                    'tier_used': tier_idx,
                    'tier_name': tier.name,
                    'elapsed': elapsed,
                    'from_cache': False,
                }
            
            except CircuitBreakerError as e:
                logger.error(f"[{store_id}] Circuit breaker tripped: {e}")
                break
            
            except Exception as e:
                logger.error(f"[{store_id}] Tier {tier_idx} ({tier.name}) failed: {e}")
                self.health_monitor.record_failure(
                    scraper_id=store_id,
                    error=str(e),
                    tier=tier_idx
                )
                continue
        
        # All tiers failed
        logger.critical(f"[{store_id}] ALL TIERS FAILED - using cached data")
        return self._get_cached_result(store_id)
    
    def _execute_tier(self, store_id: str, tier: ScraperTier) -> List[Dict]:
        """Execute a single tier with rate limiting and retries"""
        circuit = self.circuit_breakers[store_id]
        
        def do_scrape():
            # Apply rate limiting
            self.rate_limiter.wait(f"https://{store_id}.bg")
            
            # Execute scraper
            products = tier.scraper_func()
            
            # Report success to rate limiter
            self.rate_limiter.report_success(f"https://{store_id}.bg")
            
            return products
        
        # Execute through circuit breaker with retries
        return circuit.call(
            lambda: self.retry_handler.execute(do_scrape)
        )
    
    def _cache_results(self, store_id: str, products: List[Dict]):
        """Cache results for fallback"""
        cache_file = self.cache_dir / f"{store_id}_cache.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'store_id': store_id,
                    'products': products,
                    'cached_at': time.time(),
                    'product_count': len(products),
                }, f, ensure_ascii=False)
            logger.debug(f"Cached {len(products)} products for {store_id}")
        except Exception as e:
            logger.error(f"Failed to cache results for {store_id}: {e}")
    
    def _get_cached_result(self, store_id: str) -> Dict:
        """Get cached results as fallback"""
        cache_file = self.cache_dir / f"{store_id}_cache.json"
        
        try:
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                
                age_hours = (time.time() - cached['cached_at']) / 3600
                logger.warning(
                    f"[{store_id}] Using cached data ({cached['product_count']} products, "
                    f"{age_hours:.1f}h old)"
                )
                
                return {
                    'success': True,
                    'products': cached['products'],
                    'tier_used': 0,
                    'tier_name': 'cache',
                    'from_cache': True,
                    'cache_age_hours': age_hours,
                }
        except Exception as e:
            logger.error(f"Failed to load cache for {store_id}: {e}")
        
        return {
            'success': False,
            'products': [],
            'tier_used': 0,
            'error': 'All tiers failed and no cache available',
            'from_cache': False,
        }
    
    def scrape_all(self) -> Dict[str, Dict]:
        """Scrape all registered stores"""
        results = {}
        
        for store_id in self.store_configs:
            logger.info(f"Starting scrape for {store_id}")
            results[store_id] = self.scrape_store(store_id)
        
        # Log summary
        total_products = sum(
            len(r.get('products', [])) for r in results.values()
        )
        successful = sum(1 for r in results.values() if r.get('success'))
        
        logger.info(
            f"Scrape complete: {successful}/{len(results)} stores successful, "
            f"{total_products} total products"
        )
        
        return results
    
    def get_health_report(self) -> Dict:
        """Get comprehensive health report"""
        return {
            'scrapers': self.health_monitor.get_health_report(),
            'rate_limiters': self.rate_limiter.get_stats(),
            'circuits': {
                name: cb.stats 
                for name, cb in self.circuit_breakers.items()
            },
            'sessions': self.session_manager.get_all_stats(),
        }
    
    def get_health_summary(self) -> str:
        """Get human-readable health summary"""
        return self.health_monitor.get_summary()
    
    def reset_circuit(self, store_id: str):
        """Manually reset circuit breaker for a store"""
        if store_id in self.circuit_breakers:
            self.circuit_breakers[store_id].reset()
            logger.info(f"Reset circuit breaker for {store_id}")
    
    def reset_all_circuits(self):
        """Reset all circuit breakers"""
        for cb in self.circuit_breakers.values():
            cb.reset()
        logger.info("Reset all circuit breakers")


# Factory function for creating orchestrator with default stores
def create_default_orchestrator(
    data_dir: str = "./data",
    alert_callback: Optional[Callable] = None
) -> ScraperOrchestrator:
    """
    Create orchestrator with Bulgarian supermarket stores pre-configured.
    
    Note: Actual scraper functions should be passed in after import.
    This is a factory template.
    """
    orchestrator = ScraperOrchestrator(
        data_dir=data_dir,
        alert_callback=alert_callback
    )
    
    # Store configs will be registered by the main scraper module
    # after importing the actual scraper functions
    
    return orchestrator
