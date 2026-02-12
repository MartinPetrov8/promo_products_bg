"""
Adaptive Rate Limiting with Per-Domain Controls

Features:
- Exponential backoff on failures
- Gradual recovery on success
- Per-domain rate tracking
- Human-like timing with jitter
"""

import time
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional
from threading import Lock
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting a specific domain"""
    requests_per_minute: float = 10.0
    min_delay: float = 0.5
    max_delay: float = 30.0
    burst_size: int = 3
    
    # Human-like timing
    use_jitter: bool = True
    jitter_factor: float = 0.3  # ±30% randomness


class AdaptiveRateLimiter:
    """
    Self-adjusting rate limiter that backs off on errors
    and speeds up on consistent success.
    """
    
    def __init__(
        self,
        initial_delay: float = 2.0,
        min_delay: float = 0.5,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        recovery_factor: float = 0.9,
        success_threshold: int = 5
    ):
        self.initial_delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.recovery_factor = recovery_factor
        self.success_threshold = success_threshold
        
        self.current_delay = initial_delay
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.last_request_time = 0
        self._lock = Lock()
    
    def wait(self) -> float:
        """
        Wait appropriate time before next request.
        Returns actual wait time.
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_request_time
            
            # Add human-like jitter
            jittered_delay = self._add_jitter(self.current_delay)
            
            wait_time = max(0, jittered_delay - elapsed)
            
            if wait_time > 0:
                time.sleep(wait_time)
            
            self.last_request_time = time.time()
            return wait_time
    
    def _add_jitter(self, delay: float) -> float:
        """Add randomness to delay (human-like behavior)"""
        # Use Gaussian distribution centered on delay
        jittered = random.gauss(delay, delay * 0.3)
        return max(self.min_delay, min(jittered, self.max_delay))
    
    def report_success(self, response_time: Optional[float] = None):
        """Call after successful request"""
        with self._lock:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            
            # Gradually speed up after consistent success
            if self.consecutive_successes >= self.success_threshold:
                new_delay = self.current_delay * self.recovery_factor
                self.current_delay = max(new_delay, self.min_delay)
                self.consecutive_successes = 0
                logger.debug(f"Rate limiter speeding up: {self.current_delay:.2f}s")
    
    def report_failure(self, status_code: Optional[int] = None):
        """Call after failed request"""
        with self._lock:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            
            # Exponential backoff
            new_delay = self.current_delay * self.backoff_multiplier
            
            # Extra aggressive backoff for rate limit errors
            if status_code == 429:
                new_delay *= 1.5
                logger.warning(f"Rate limit hit (429), aggressive backoff: {new_delay:.2f}s")
            
            self.current_delay = min(new_delay, self.max_delay)
            logger.debug(f"Rate limiter slowing down: {self.current_delay:.2f}s")
    
    def reset(self):
        """Reset to initial state"""
        with self._lock:
            self.current_delay = self.initial_delay
            self.consecutive_successes = 0
            self.consecutive_failures = 0
    
    @property
    def status(self) -> Dict:
        """Current rate limiter status"""
        return {
            'current_delay': self.current_delay,
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'is_throttled': self.current_delay > self.initial_delay * 2
        }


class DomainRateLimiter:
    """
    Manages rate limiting across multiple domains.
    Each domain gets its own adaptive limiter.
    """
    
    # Default configs for known domains
    DEFAULT_CONFIGS = {
        'kaufland.bg': RateLimitConfig(requests_per_minute=10, min_delay=3.0),
        'lidl.bg': RateLimitConfig(requests_per_minute=10, min_delay=3.0),
        'ssbbilla.site': RateLimitConfig(requests_per_minute=20, min_delay=2.0),
        'billa.bg': RateLimitConfig(requests_per_minute=10, min_delay=3.0),
        'metro.bg': RateLimitConfig(requests_per_minute=8, min_delay=4.0),
        'katalozi.bg': RateLimitConfig(requests_per_minute=30, min_delay=1.0),
        'broshura.bg': RateLimitConfig(requests_per_minute=30, min_delay=1.0),
    }
    
    def __init__(self, default_config: Optional[RateLimitConfig] = None):
        self.default_config = default_config or RateLimitConfig()
        self.domain_limiters: Dict[str, AdaptiveRateLimiter] = {}
        self.request_history: Dict[str, deque] = {}
        self._lock = Lock()
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def _get_limiter(self, domain: str) -> AdaptiveRateLimiter:
        """Get or create limiter for domain"""
        if domain not in self.domain_limiters:
            config = self.DEFAULT_CONFIGS.get(domain, self.default_config)
            self.domain_limiters[domain] = AdaptiveRateLimiter(
                initial_delay=60.0 / config.requests_per_minute,
                min_delay=config.min_delay,
                max_delay=config.max_delay,
            )
            self.request_history[domain] = deque(maxlen=100)
        return self.domain_limiters[domain]
    
    def wait(self, url: str) -> float:
        """Wait before making request to URL"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        wait_time = limiter.wait()
        
        # Track request time
        with self._lock:
            self.request_history[domain].append(time.time())
        
        return wait_time
    
    def report_success(self, url: str, response_time: Optional[float] = None):
        """Report successful request"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        limiter.report_success(response_time)
    
    def report_failure(self, url: str, status_code: Optional[int] = None):
        """Report failed request"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        limiter.report_failure(status_code)
    
    def get_stats(self, domain: Optional[str] = None) -> Dict:
        """Get rate limiting stats"""
        if domain:
            limiter = self.domain_limiters.get(domain)
            if limiter:
                history = self.request_history.get(domain, [])
                recent = [t for t in history if time.time() - t < 60]
                return {
                    **limiter.status,
                    'requests_last_minute': len(recent)
                }
            return {}
        
        return {
            d: self.get_stats(d)
            for d in self.domain_limiters
        }


# Pre-configured instance for easy import
default_rate_limiter = DomainRateLimiter()
