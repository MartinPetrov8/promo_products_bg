"""
Circuit Breaker Pattern for Scraper Resilience

Prevents cascading failures by temporarily stopping requests
to failing endpoints.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failing, all requests rejected immediately  
- HALF_OPEN: Testing recovery, limited requests allowed
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Dict
from threading import Lock
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject requests
    HALF_OPEN = "half_open" # Testing if recovered


@dataclass
class CircuitStats:
    """Statistics for a circuit breaker"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changes: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit is open"""
    def __init__(self, circuit_name: str, retry_after: float):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(f"Circuit '{circuit_name}' is OPEN. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    """
    Circuit breaker that trips after consecutive failures
    and recovers after a timeout period.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 2,
        excluded_exceptions: tuple = ()
    ):
        """
        Args:
            name: Identifier for this circuit
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            half_open_max_calls: Max calls allowed in half-open state
            success_threshold: Successes needed in half-open to close
            excluded_exceptions: Exceptions that don't count as failures
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        self.excluded_exceptions = excluded_exceptions
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.time()
        self._stats = CircuitStats()
        self._lock = Lock()
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state (may trigger state transition)"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state
    
    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to try recovery"""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout
    
    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state"""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()
        self._stats.state_changes += 1
        
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
        
        logger.info(f"Circuit '{self.name}': {old_state.value} -> {new_state.value}")
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.
        
        Raises:
            CircuitBreakerError: If circuit is open
        """
        with self._lock:
            state = self.state  # May trigger state transition
            self._stats.total_requests += 1
            
            if state == CircuitState.OPEN:
                self._stats.rejected_requests += 1
                retry_after = self.recovery_timeout - (time.time() - self._last_failure_time)
                raise CircuitBreakerError(self.name, max(0, retry_after))
            
            if state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._stats.rejected_requests += 1
                    raise CircuitBreakerError(self.name, 5.0)
                self._half_open_calls += 1
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.excluded_exceptions:
            # Don't count excluded exceptions as failures
            raise
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        with self._lock:
            self._stats.successful_requests += 1
            self._stats.last_success_time = time.time()
            self._failure_count = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
    
    def _on_failure(self):
        """Handle failed call"""
        with self._lock:
            self._stats.failed_requests += 1
            self._stats.last_failure_time = time.time()
            self._last_failure_time = time.time()
            self._failure_count += 1
            
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition_to(CircuitState.OPEN)
            elif self._failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)
    
    def reset(self):
        """Manually reset circuit to closed state"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
    
    def record_success(self):
        """Public API to record a successful operation (for manual use outside call())"""
        self._on_success()
    
    def record_failure(self):
        """Public API to record a failed operation (for manual use outside call())"""
        self._on_failure()
    
    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN
    
    @property
    def stats(self) -> Dict:
        """Get circuit statistics"""
        return {
            'name': self.name,
            'state': self._state.value,
            'failure_count': self._failure_count,
            'success_count': self._success_count,
            'stats': {
                'total': self._stats.total_requests,
                'successful': self._stats.successful_requests,
                'failed': self._stats.failed_requests,
                'rejected': self._stats.rejected_requests,
                'state_changes': self._stats.state_changes,
            },
            'last_failure': self._stats.last_failure_time,
            'last_success': self._stats.last_success_time,
        }


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0
):
    """
    Decorator to wrap function with circuit breaker.
    
    Usage:
        @circuit_breaker("my_api", failure_threshold=3)
        def call_api():
            ...
    """
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout
    )
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        # Expose circuit breaker for inspection
        wrapper.circuit_breaker = breaker
        return wrapper
    
    return decorator


class CircuitBreakerRegistry:
    """
    Manages multiple circuit breakers by name.
    Useful for per-domain circuits.
    """
    
    def __init__(self, default_config: Optional[Dict] = None):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.default_config = default_config or {
            'failure_threshold': 5,
            'recovery_timeout': 60.0,
            'half_open_max_calls': 3,
        }
        self._lock = Lock()
    
    def get(self, name: str) -> CircuitBreaker:
        """Get or create circuit breaker by name"""
        with self._lock:
            if name not in self.breakers:
                self.breakers[name] = CircuitBreaker(
                    name=name,
                    **self.default_config
                )
            return self.breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get stats for all circuits"""
        return {name: cb.stats for name, cb in self.breakers.items()}
    
    def reset_all(self):
        """Reset all circuit breakers"""
        for cb in self.breakers.values():
            cb.reset()


# Global registry for easy access
circuit_registry = CircuitBreakerRegistry()
