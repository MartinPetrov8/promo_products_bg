"""
Health Monitoring for Scrapers

Tracks per-scraper health metrics and provides alerting
when scrapers degrade or fail.
"""

import time
import logging
from enum import Enum
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable
from threading import Lock
import json

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"       # All good, Tier 1 working
    DEGRADED = "degraded"     # Using fallback or reduced performance
    UNHEALTHY = "unhealthy"   # Significant issues, may need intervention
    CRITICAL = "critical"     # All tiers failed, serving stale data


@dataclass
class HealthThresholds:
    """Thresholds for health status determination"""
    # Error rate thresholds
    degraded_error_rate: float = 0.20     # 20% errors -> degraded
    unhealthy_error_rate: float = 0.40    # 40% errors -> unhealthy
    critical_error_rate: float = 0.60     # 60% errors -> critical
    
    # Response time thresholds (seconds)
    degraded_response_time: float = 5.0
    unhealthy_response_time: float = 10.0
    critical_response_time: float = 30.0
    
    # Product count thresholds (percentage of expected)
    degraded_product_ratio: float = 0.80   # <80% of expected
    unhealthy_product_ratio: float = 0.50  # <50% of expected
    critical_product_ratio: float = 0.20   # <20% of expected
    
    # Consecutive failure thresholds
    degraded_consecutive_failures: int = 2
    unhealthy_consecutive_failures: int = 4
    critical_consecutive_failures: int = 6


@dataclass 
class ScraperMetrics:
    """Metrics for a single scraper"""
    scraper_id: str
    
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Product metrics
    last_product_count: int = 0
    expected_product_count: int = 0
    
    # Timing metrics
    response_times: deque = field(default_factory=lambda: deque(maxlen=50))
    
    # Error tracking
    recent_results: deque = field(default_factory=lambda: deque(maxlen=20))
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    
    # Tier tracking
    current_tier: int = 1
    
    # Timestamps
    last_success_time: Optional[float] = None
    last_attempt_time: Optional[float] = None
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate from recent results"""
        if not self.recent_results:
            return 0.0
        failures = sum(1 for r in self.recent_results if not r)
        return failures / len(self.recent_results)
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    @property
    def product_ratio(self) -> float:
        """Ratio of actual to expected products"""
        if self.expected_product_count == 0:
            return 1.0
        return self.last_product_count / self.expected_product_count


class HealthMonitor:
    """
    Monitors health of multiple scrapers and triggers alerts.
    """
    
    # Expected product counts per store (baseline)
    EXPECTED_PRODUCTS = {
        'kaufland': 800,
        'lidl': 40,
        'billa': 200,
        'metro': 500,
        'fantastico': 300,
        't-market': 200,
        'cba': 150,
    }
    
    def __init__(
        self,
        thresholds: Optional[HealthThresholds] = None,
        alert_callback: Optional[Callable[[str, str, Dict], None]] = None
    ):
        self.thresholds = thresholds or HealthThresholds()
        self.alert_callback = alert_callback
        self.metrics: Dict[str, ScraperMetrics] = {}
        self._lock = Lock()
        self._alert_cooldowns: Dict[str, float] = {}
        self._alert_cooldown_seconds = 300  # 5 minutes between same alerts
    
    def _get_metrics(self, scraper_id: str) -> ScraperMetrics:
        """Get or create metrics for scraper"""
        if scraper_id not in self.metrics:
            expected = self.EXPECTED_PRODUCTS.get(scraper_id.lower(), 100)
            self.metrics[scraper_id] = ScraperMetrics(
                scraper_id=scraper_id,
                expected_product_count=expected
            )
        return self.metrics[scraper_id]
    
    def record_success(
        self,
        scraper_id: str,
        response_time: float,
        product_count: int,
        tier: int = 1
    ):
        """Record a successful scrape"""
        with self._lock:
            m = self._get_metrics(scraper_id)
            m.total_requests += 1
            m.successful_requests += 1
            m.consecutive_failures = 0
            m.last_success_time = time.time()
            m.last_attempt_time = time.time()
            m.last_product_count = product_count
            m.current_tier = tier
            m.response_times.append(response_time)
            m.recent_results.append(True)
            
            logger.debug(
                f"[{scraper_id}] Success: {product_count} products in {response_time:.2f}s (Tier {tier})"
            )
    
    def record_failure(
        self,
        scraper_id: str,
        error: str,
        tier: int = 1
    ):
        """Record a failed scrape"""
        with self._lock:
            m = self._get_metrics(scraper_id)
            m.total_requests += 1
            m.failed_requests += 1
            m.consecutive_failures += 1
            m.last_error = error
            m.last_error_time = time.time()
            m.last_attempt_time = time.time()
            m.current_tier = tier
            m.recent_results.append(False)
            
            logger.warning(f"[{scraper_id}] Failure (Tier {tier}): {error}")
            
            # Check if we need to alert
            self._check_alerts(scraper_id, m)
    
    def get_status(self, scraper_id: str) -> HealthStatus:
        """Determine health status for a scraper"""
        with self._lock:
            m = self._get_metrics(scraper_id)
            t = self.thresholds
            
            # Check for critical conditions
            if m.consecutive_failures >= t.critical_consecutive_failures:
                return HealthStatus.CRITICAL
            if m.error_rate >= t.critical_error_rate:
                return HealthStatus.CRITICAL
            if m.avg_response_time >= t.critical_response_time:
                return HealthStatus.CRITICAL
            if m.product_ratio <= t.critical_product_ratio and m.last_product_count > 0:
                return HealthStatus.CRITICAL
            
            # Check for unhealthy conditions
            if m.consecutive_failures >= t.unhealthy_consecutive_failures:
                return HealthStatus.UNHEALTHY
            if m.error_rate >= t.unhealthy_error_rate:
                return HealthStatus.UNHEALTHY
            if m.avg_response_time >= t.unhealthy_response_time:
                return HealthStatus.UNHEALTHY
            if m.product_ratio <= t.unhealthy_product_ratio and m.last_product_count > 0:
                return HealthStatus.UNHEALTHY
            
            # Check for degraded conditions
            if m.consecutive_failures >= t.degraded_consecutive_failures:
                return HealthStatus.DEGRADED
            if m.error_rate >= t.degraded_error_rate:
                return HealthStatus.DEGRADED
            if m.avg_response_time >= t.degraded_response_time:
                return HealthStatus.DEGRADED
            if m.current_tier > 1:
                return HealthStatus.DEGRADED
            if m.product_ratio <= t.degraded_product_ratio and m.last_product_count > 0:
                return HealthStatus.DEGRADED
            
            return HealthStatus.HEALTHY
    
    def _check_alerts(self, scraper_id: str, m: ScraperMetrics):
        """Check if alerts should be sent"""
        status = self.get_status(scraper_id)
        
        if status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
            alert_key = f"{scraper_id}:{status.value}"
            
            # Check cooldown
            last_alert = self._alert_cooldowns.get(alert_key, 0)
            if time.time() - last_alert < self._alert_cooldown_seconds:
                return
            
            self._alert_cooldowns[alert_key] = time.time()
            
            # Build alert context
            context = {
                'scraper_id': scraper_id,
                'status': status.value,
                'error_rate': f"{m.error_rate:.1%}",
                'consecutive_failures': m.consecutive_failures,
                'last_error': m.last_error,
                'current_tier': m.current_tier,
                'avg_response_time': f"{m.avg_response_time:.2f}s",
            }
            
            # Log alert
            level = "CRITICAL" if status == HealthStatus.CRITICAL else "WARNING"
            logger.log(
                logging.CRITICAL if status == HealthStatus.CRITICAL else logging.WARNING,
                f"[ALERT] Scraper {scraper_id} is {status.value}: {context}"
            )
            
            # Call alert callback if configured
            if self.alert_callback:
                try:
                    self.alert_callback(scraper_id, status.value, context)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")
    
    def get_health_report(self) -> Dict:
        """Get full health report for all scrapers"""
        report = {}
        for scraper_id, m in self.metrics.items():
            status = self.get_status(scraper_id)
            report[scraper_id] = {
                'status': status.value,
                'current_tier': m.current_tier,
                'metrics': {
                    'total_requests': m.total_requests,
                    'successful_requests': m.successful_requests,
                    'failed_requests': m.failed_requests,
                    'error_rate': f"{m.error_rate:.1%}",
                    'avg_response_time': f"{m.avg_response_time:.2f}s",
                    'consecutive_failures': m.consecutive_failures,
                },
                'products': {
                    'last_count': m.last_product_count,
                    'expected': m.expected_product_count,
                    'ratio': f"{m.product_ratio:.1%}",
                },
                'last_success': m.last_success_time,
                'last_error': m.last_error,
            }
        return report
    
    def get_summary(self) -> str:
        """Get human-readable health summary"""
        lines = ["📊 Scraper Health Summary", "=" * 40]
        
        for scraper_id, m in self.metrics.items():
            status = self.get_status(scraper_id)
            emoji = {
                HealthStatus.HEALTHY: "✅",
                HealthStatus.DEGRADED: "⚠️",
                HealthStatus.UNHEALTHY: "🔴",
                HealthStatus.CRITICAL: "🚨",
            }[status]
            
            lines.append(
                f"{emoji} {scraper_id}: {status.value} "
                f"(Tier {m.current_tier}, {m.last_product_count} products, "
                f"{m.error_rate:.0%} errors)"
            )
        
        return "\n".join(lines)


# Default health monitor instance
default_health_monitor = HealthMonitor()
