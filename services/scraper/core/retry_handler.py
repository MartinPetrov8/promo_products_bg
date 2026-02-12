"""
Retry Logic with Exponential Backoff and Jitter

Implements intelligent retry strategies for transient failures.
"""

import time
import random
import logging
from functools import wraps
from typing import Optional, Callable, Any, Tuple, Type, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: str = "full"  # "full", "equal", "decorrelated", "none"
    
    # Status codes that should trigger retry
    retryable_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)
    
    # Exceptions that should trigger retry
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
    )


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted"""
    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_exception}")


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: str = "full"
) -> float:
    """
    Calculate delay with exponential backoff and jitter.
    
    Jitter strategies:
    - "full": Random between 0 and calculated delay (AWS recommendation)
    - "equal": Half fixed, half random
    - "decorrelated": Based on previous delay with randomness
    - "none": Pure exponential, no randomness
    """
    # Base exponential backoff
    delay = min(base_delay * (exponential_base ** attempt), max_delay)
    
    if jitter == "full":
        # Full jitter: random between 0 and delay
        return random.uniform(0, delay)
    
    elif jitter == "equal":
        # Equal jitter: half fixed, half random
        return delay / 2 + random.uniform(0, delay / 2)
    
    elif jitter == "decorrelated":
        # Decorrelated jitter: min + random * (delay * 3 - min)
        return min(max_delay, random.uniform(base_delay, delay * 3))
    
    else:  # "none"
        return delay


class RetryHandler:
    """
    Handles retry logic with configurable strategies.
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
    
    def should_retry(
        self,
        exception: Optional[Exception] = None,
        status_code: Optional[int] = None,
        attempt: int = 0
    ) -> bool:
        """Determine if request should be retried"""
        if attempt >= self.config.max_attempts:
            return False
        
        if status_code and status_code in self.config.retryable_status_codes:
            return True
        
        if exception:
            for exc_type in self.config.retryable_exceptions:
                if isinstance(exception, exc_type):
                    return True
        
        return False
    
    def get_delay(self, attempt: int) -> float:
        """Get delay for given attempt number"""
        return calculate_backoff(
            attempt=attempt,
            base_delay=self.config.base_delay,
            max_delay=self.config.max_delay,
            exponential_base=self.config.exponential_base,
            jitter=self.config.jitter
        )
    
    def execute(
        self,
        func: Callable,
        *args,
        on_retry: Optional[Callable[[int, Exception, float], None]] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            on_retry: Callback called before each retry (attempt, exception, delay)
        """
        last_exception = None
        
        for attempt in range(self.config.max_attempts):
            try:
                return func(*args, **kwargs)
            
            except Exception as e:
                last_exception = e
                
                if not self.should_retry(exception=e, attempt=attempt):
                    raise
                
                delay = self.get_delay(attempt)
                
                logger.warning(
                    f"Attempt {attempt + 1}/{self.config.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s"
                )
                
                if on_retry:
                    on_retry(attempt, e, delay)
                
                time.sleep(delay)
        
        raise RetryExhausted(last_exception, self.config.max_attempts)


def retry_with_jitter(
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: str = "full"
):
    """
    Decorator for automatic retry with exponential backoff and jitter.
    
    Usage:
        @retry_with_jitter(max_attempts=3, base_delay=1.0)
        def unreliable_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts - 1:
                        raise
                    
                    delay = calculate_backoff(
                        attempt=attempt,
                        base_delay=base_delay,
                        max_delay=max_delay,
                        jitter=jitter
                    )
                    
                    logger.warning(
                        f"[{func.__name__}] Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    
                    time.sleep(delay)
            
            raise RetryExhausted(last_exception, max_attempts)
        
        return wrapper
    return decorator


class RetryWithStatusCode:
    """
    Retry handler that also checks HTTP status codes.
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            last_response = None
            
            for attempt in range(self.config.max_attempts):
                try:
                    response = func(*args, **kwargs)
                    last_response = response
                    
                    # Check if status code indicates we should retry
                    if hasattr(response, 'status_code'):
                        if response.status_code in self.config.retryable_status_codes:
                            if attempt < self.config.max_attempts - 1:
                                delay = calculate_backoff(
                                    attempt=attempt,
                                    base_delay=self.config.base_delay,
                                    max_delay=self.config.max_delay,
                                    jitter=self.config.jitter
                                )
                                
                                # Check for Retry-After header
                                retry_after = response.headers.get('Retry-After')
                                if retry_after:
                                    try:
                                        delay = max(delay, float(retry_after))
                                    except ValueError:
                                        pass
                                
                                logger.warning(
                                    f"[{func.__name__}] Got {response.status_code}, "
                                    f"retrying in {delay:.2f}s"
                                )
                                time.sleep(delay)
                                continue
                    
                    return response
                
                except self.config.retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt == self.config.max_attempts - 1:
                        raise
                    
                    delay = calculate_backoff(
                        attempt=attempt,
                        base_delay=self.config.base_delay,
                        max_delay=self.config.max_delay,
                        jitter=self.config.jitter
                    )
                    
                    logger.warning(
                        f"[{func.__name__}] Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
            
            # Return last response if we have one, even if it had a bad status
            if last_response is not None:
                return last_response
            
            if last_exception:
                raise last_exception
        
        return wrapper


# Pre-configured retry handlers
default_retry_handler = RetryHandler()
aggressive_retry_handler = RetryHandler(RetryConfig(
    max_attempts=7,
    base_delay=2.0,
    max_delay=120.0,
))
gentle_retry_handler = RetryHandler(RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=10.0,
))
