"""Client-side rate limiter for LLM calls.

Prevents 429 errors by pacing LLM calls to match Vertex AI quotas.
Uses AsyncTokenBucket for rate control + asyncio.Semaphore for concurrency cap.
Includes a CircuitBreaker that trips after consecutive failures.

Usage:
    from src.services.rate_limiter import rate_limited_llm_call
    result = await rate_limited_llm_call(llm.ainvoke(messages))
"""

import asyncio
import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AsyncTokenBucket:
    """Async-safe token bucket for rate limiting LLM calls.

    capacity: max burst size (requests)
    refill_rate: tokens/second (e.g., 1.0 for 60 RPM)
    """

    capacity: float
    refill_rate: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(init=False)

    def __post_init__(self):
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    async def wait_and_consume(self, amount: float = 1.0):
        """Block until a token is available, then consume it."""
        while True:
            async with self._lock:
                await self._refill()
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                needed = amount - self._tokens
                wait_time = needed / self.refill_rate if self.refill_rate > 0 else 1.0
            await asyncio.sleep(wait_time)


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for LLM provider failures.

    Trips after `failure_threshold` consecutive 429/5xx errors.
    After cooldown, allows one attempt (half-open state).
    """

    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    _consecutive_failures: int = field(init=False, default=0)
    _tripped_at: float | None = field(init=False, default=None)

    def record_success(self):
        self._consecutive_failures = 0
        self._tripped_at = None

    def record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._tripped_at = time.monotonic()
            logger.warning(
                "circuit_breaker_tripped",
                consecutive_failures=self._consecutive_failures,
                cooldown_seconds=self.cooldown_seconds,
            )

    @property
    def is_open(self) -> bool:
        if self._tripped_at is None:
            return False
        elapsed = time.monotonic() - self._tripped_at
        if elapsed > self.cooldown_seconds:
            # Half-open: allow one attempt
            self._tripped_at = None
            self._consecutive_failures = 0
            logger.info("circuit_breaker_half_open", msg="allowing retry after cooldown")
            return False
        return True


# ---------------------------------------------------------------------------
# Module-level singletons (created once per process)
# Defaults: 60 RPM = 1 req/sec avg, burst=5, max 10 concurrent
# ---------------------------------------------------------------------------
_llm_bucket: AsyncTokenBucket | None = None
_llm_semaphore: asyncio.Semaphore | None = None
_circuit_breaker: CircuitBreaker | None = None


def _get_bucket() -> AsyncTokenBucket:
    global _llm_bucket
    if _llm_bucket is None:
        from src.config.settings import get_settings

        settings = get_settings()
        rpm = settings.llm_rate_limit_rpm
        refill = rpm / 60.0
        capacity = max(3.0, refill * 5)  # ~5 seconds of burst
        _llm_bucket = AsyncTokenBucket(capacity=capacity, refill_rate=refill)
        logger.info(
            "rate_limiter_init_bucket",
            rpm=rpm,
            refill_rate=refill,
            capacity=capacity,
        )
    return _llm_bucket


def _get_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        from src.config.settings import get_settings

        settings = get_settings()
        _llm_semaphore = asyncio.Semaphore(settings.llm_max_concurrent)
        logger.info(
            "rate_limiter_init_semaphore",
            max_concurrent=settings.llm_max_concurrent,
        )
    return _llm_semaphore


def _get_circuit_breaker() -> CircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=60.0)
    return _circuit_breaker


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and calls are blocked."""


async def rate_limited_llm_call(coro):
    """Wrap any LLM call with rate limiting + concurrency cap + circuit breaker.

    Usage:
        result = await rate_limited_llm_call(llm.ainvoke(messages))
    """
    cb = _get_circuit_breaker()
    if cb.is_open:
        raise CircuitBreakerOpenError(
            "Circuit breaker is open — too many consecutive LLM failures. "
            f"Cooling down for {cb.cooldown_seconds}s."
        )

    bucket = _get_bucket()
    semaphore = _get_semaphore()

    await bucket.wait_and_consume()
    async with semaphore:
        try:
            result = await coro
            cb.record_success()
            return result
        except Exception as exc:
            # Record failure for 429 / 5xx errors
            exc_str = str(exc).lower()
            if "429" in exc_str or "resource exhausted" in exc_str or "500" in exc_str:
                cb.record_failure()
                logger.warning(
                    "rate_limiter_provider_error",
                    error=str(exc)[:200],
                    consecutive_failures=cb._consecutive_failures,
                )
            raise
