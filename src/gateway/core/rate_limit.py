"""Rate limiting module for the API Gateway.

This module implements:
- Rate limiting algorithms (Token Bucket, Fixed Window, Sliding Window) (Task 15)
- Rate limiting key generation (Task 16)
- Rate limiting state store integration (Task 17)
- Rate limiting evaluation logic (Task 18)
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    """Rate limiting state information.

    Attributes:
        allowed: Whether the request is allowed
        remaining: Requests remaining in current window
        limit: Total request limit
        reset_at: Unix timestamp when the limit resets
        retry_after: Seconds to wait before retrying (if denied)
    """

    allowed: bool
    remaining: int
    limit: int
    reset_at: int
    retry_after: int | None = None


class RateLimitAlgorithm(ABC):
    """Abstract base class for rate limiting algorithms."""

    @abstractmethod
    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
        burst: int | None = None,
    ) -> RateLimitState:
        """Check if request is within rate limit.

        Args:
            key: Rate limit key
            limit: Request limit
            window: Time window in seconds
            burst: Optional burst allowance

        Returns:
            RateLimitState with decision and metadata
        """
        pass


class TokenBucketAlgorithm(RateLimitAlgorithm):
    """Token bucket rate limiting algorithm.

    Allows bursts of traffic up to the bucket capacity while enforcing
    a sustained rate over time.
    """

    def __init__(self, store: "RateLimitStore"):
        """Initialize token bucket algorithm.

        Args:
            store: Rate limiting state store
        """
        self.store = store

    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
        burst: int | None = None,
    ) -> RateLimitState:
        """Check rate limit using token bucket algorithm.

        Args:
            key: Rate limit key
            limit: Request limit (tokens per window)
            window: Time window in seconds
            burst: Burst capacity (max tokens), defaults to limit

        Returns:
            RateLimitState with decision
        """
        bucket_capacity = burst if burst else limit
        refill_rate = limit / window  # Tokens per second

        now = time.time()

        # Get current bucket state
        bucket_state = await self.store.get_bucket_state(key)

        if bucket_state is None:
            # First request - initialize bucket
            tokens = bucket_capacity - 1  # Consume one token
            last_refill = now
        else:
            tokens, last_refill = bucket_state

            # Calculate tokens to add based on time elapsed
            time_elapsed = now - last_refill
            tokens_to_add = time_elapsed * refill_rate
            tokens = min(bucket_capacity, tokens + tokens_to_add)

            # Try to consume a token
            if tokens >= 1:
                tokens -= 1
            else:
                # No tokens available - rate limit exceeded
                retry_after = int((1 - tokens) / refill_rate) + 1
                reset_at = int(last_refill + window)

                return RateLimitState(
                    allowed=False,
                    remaining=0,
                    limit=limit,
                    reset_at=reset_at,
                    retry_after=retry_after,
                )

            last_refill = now

        # Update bucket state
        await self.store.set_bucket_state(key, tokens, last_refill, window)

        # Calculate reset time
        reset_at = int(now + window)

        return RateLimitState(
            allowed=True,
            remaining=int(tokens),
            limit=limit,
            reset_at=reset_at,
        )


class FixedWindowAlgorithm(RateLimitAlgorithm):
    """Fixed window rate limiting algorithm.

    Time is divided into fixed windows. Simple but can allow bursts at
    window boundaries.
    """

    def __init__(self, store: "RateLimitStore"):
        """Initialize fixed window algorithm.

        Args:
            store: Rate limiting state store
        """
        self.store = store

    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
        burst: int | None = None,
    ) -> RateLimitState:
        """Check rate limit using fixed window algorithm.

        Args:
            key: Rate limit key
            limit: Request limit
            window: Time window in seconds
            burst: Not used in fixed window

        Returns:
            RateLimitState with decision
        """
        now = time.time()

        # Calculate current window start
        window_start = int(now / window) * window

        # Get current count for this window
        count = await self.store.get_window_count(key, window_start)

        # Check if limit exceeded
        if count >= limit:
            # Rate limit exceeded
            reset_at = window_start + window
            retry_after = int(reset_at - now)

            return RateLimitState(
                allowed=False,
                remaining=0,
                limit=limit,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        # Increment counter
        new_count = await self.store.increment_window_count(key, window_start, window)

        reset_at = window_start + window
        remaining = max(0, limit - new_count)

        return RateLimitState(
            allowed=True,
            remaining=remaining,
            limit=limit,
            reset_at=reset_at,
        )


class SlidingWindowAlgorithm(RateLimitAlgorithm):
    """Sliding window counter rate limiting algorithm.

    More accurate than fixed window, estimates current rate based on
    weighted combination of previous and current window counts.
    """

    def __init__(self, store: "RateLimitStore"):
        """Initialize sliding window algorithm.

        Args:
            store: Rate limiting state store
        """
        self.store = store

    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
        burst: int | None = None,
    ) -> RateLimitState:
        """Check rate limit using sliding window algorithm.

        Args:
            key: Rate limit key
            limit: Request limit
            window: Time window in seconds
            burst: Not used in sliding window

        Returns:
            RateLimitState with decision
        """
        now = time.time()

        # Calculate current and previous window starts
        current_window_start = int(now / window) * window
        previous_window_start = current_window_start - window

        # Get counts for both windows
        current_count = await self.store.get_window_count(key, current_window_start)
        previous_count = await self.store.get_window_count(key, previous_window_start)

        # Calculate weighted count
        # Weight is based on how far into the current window we are
        time_in_window = now - current_window_start
        window_progress = time_in_window / window

        # Weighted count = previous_count * (1 - progress) + current_count
        weighted_count = previous_count * (1 - window_progress) + current_count

        # Check if limit exceeded
        if weighted_count >= limit:
            # Rate limit exceeded
            reset_at = current_window_start + window
            retry_after = int(reset_at - now)

            return RateLimitState(
                allowed=False,
                remaining=0,
                limit=limit,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        # Increment current window counter
        new_current_count = await self.store.increment_window_count(
            key, current_window_start, window
        )

        # Recalculate weighted count after increment
        weighted_count = previous_count * (1 - window_progress) + new_current_count
        remaining = max(0, int(limit - weighted_count))

        reset_at = current_window_start + window

        return RateLimitState(
            allowed=True,
            remaining=remaining,
            limit=limit,
            reset_at=reset_at,
        )


class RateLimitStore(ABC):
    """Abstract base class for rate limiting state storage."""

    @abstractmethod
    async def get_bucket_state(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state.

        Args:
            key: Rate limit key

        Returns:
            Tuple of (tokens, last_refill_time) or None if not found
        """
        pass

    @abstractmethod
    async def set_bucket_state(self, key: str, tokens: float, last_refill: float, ttl: int) -> None:
        """Set token bucket state.

        Args:
            key: Rate limit key
            tokens: Current token count
            last_refill: Last refill timestamp
            ttl: Time-to-live in seconds
        """
        pass

    @abstractmethod
    async def get_window_count(self, key: str, window_start: int) -> int:
        """Get request count for a time window.

        Args:
            key: Rate limit key
            window_start: Window start timestamp

        Returns:
            Request count
        """
        pass

    @abstractmethod
    async def increment_window_count(
        self, key: str, window_start: int, window_duration: int
    ) -> int:
        """Increment request count for a time window.

        Args:
            key: Rate limit key
            window_start: Window start timestamp
            window_duration: Window duration in seconds

        Returns:
            New count after increment
        """
        pass


class RedisRateLimitStore(RateLimitStore):
    """Redis-based rate limiting state store."""

    def __init__(self, redis_url: str, key_prefix: str = "ratelimit:"):
        """Initialize Redis rate limit store.

        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for rate limit keys
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.client: redis.Redis | None = None

    async def connect(self) -> None:
        """Connect to Redis."""
        if self.client is None:
            self.client = await redis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            logger.info(f"Connected to Redis rate limit store at {self.redis_url}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from Redis rate limit store")

    async def is_healthy(self) -> bool:
        """Check if Redis connection is healthy.

        Returns:
            True if connected and responsive, False otherwise
        """
        if not self.client:
            return False

        try:
            await self.client.ping()
            return True
        except Exception:
            return False

    def _make_key(self, key: str) -> str:
        """Generate Redis key with prefix.

        Args:
            key: Base key

        Returns:
            Prefixed key
        """
        return f"{self.key_prefix}{key}"

    def _bucket_key(self, key: str) -> str:
        """Generate bucket state key.

        Args:
            key: Rate limit key

        Returns:
            Bucket state key
        """
        return f"{self._make_key(key)}:bucket"

    def _window_key(self, key: str, window_start: int) -> str:
        """Generate window count key.

        Args:
            key: Rate limit key
            window_start: Window start timestamp

        Returns:
            Window count key
        """
        return f"{self._make_key(key)}:window:{window_start}"

    async def get_bucket_state(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state from Redis.

        Args:
            key: Rate limit key

        Returns:
            Tuple of (tokens, last_refill_time) or None
        """
        if not self.client:
            raise RuntimeError("Rate limit store not connected")

        try:
            bucket_key = self._bucket_key(key)
            data = await self.client.hgetall(bucket_key)

            if not data:
                return None

            tokens = float(data.get("tokens", 0))
            last_refill = float(data.get("last_refill", 0))

            return tokens, last_refill

        except Exception as e:
            logger.error(f"Failed to get bucket state for {key}: {e}")
            return None

    async def set_bucket_state(self, key: str, tokens: float, last_refill: float, ttl: int) -> None:
        """Set token bucket state in Redis.

        Args:
            key: Rate limit key
            tokens: Current token count
            last_refill: Last refill timestamp
            ttl: Time-to-live in seconds
        """
        if not self.client:
            raise RuntimeError("Rate limit store not connected")

        try:
            bucket_key = self._bucket_key(key)

            # Use pipeline for atomic operation
            async with self.client.pipeline(transaction=True) as pipe:
                await pipe.hset(
                    bucket_key,
                    mapping={
                        "tokens": str(tokens),
                        "last_refill": str(last_refill),
                    },
                )
                await pipe.expire(bucket_key, ttl * 2)  # TTL = 2x window for safety
                await pipe.execute()

        except Exception as e:
            logger.error(f"Failed to set bucket state for {key}: {e}")
            raise

    async def get_window_count(self, key: str, window_start: int) -> int:
        """Get request count for a time window from Redis.

        Args:
            key: Rate limit key
            window_start: Window start timestamp

        Returns:
            Request count
        """
        if not self.client:
            raise RuntimeError("Rate limit store not connected")

        try:
            window_key = self._window_key(key, window_start)
            count = await self.client.get(window_key)

            return int(count) if count else 0

        except Exception as e:
            logger.error(f"Failed to get window count for {key}: {e}")
            return 0

    async def increment_window_count(
        self, key: str, window_start: int, window_duration: int
    ) -> int:
        """Increment request count for a time window in Redis.

        Args:
            key: Rate limit key
            window_start: Window start timestamp
            window_duration: Window duration in seconds

        Returns:
            New count after increment
        """
        if not self.client:
            raise RuntimeError("Rate limit store not connected")

        try:
            window_key = self._window_key(key, window_start)

            # Use pipeline for atomic increment and expiration
            async with self.client.pipeline(transaction=True) as pipe:
                await pipe.incr(window_key)
                await pipe.expire(window_key, window_duration * 2)  # TTL = 2x window
                results = await pipe.execute()

            return int(results[0])

        except Exception as e:
            logger.error(f"Failed to increment window count for {key}: {e}")
            raise


class InMemoryRateLimitStore(RateLimitStore):
    """In-memory rate limiting store for testing and development."""

    def __init__(self) -> None:
        """Initialize in-memory rate limit store."""
        self.buckets: dict[str, tuple[float, float]] = {}
        self.windows: dict[str, int] = {}

    async def connect(self) -> None:
        """Connect (no-op for in-memory store)."""
        logger.info("In-memory rate limit store ready")

    async def disconnect(self) -> None:
        """Disconnect (no-op for in-memory store)."""
        self.buckets.clear()
        self.windows.clear()

    async def is_healthy(self) -> bool:
        """Check if store is healthy.

        Returns:
            Always True for in-memory store
        """
        return True

    async def get_bucket_state(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state.

        Args:
            key: Rate limit key

        Returns:
            Tuple of (tokens, last_refill_time) or None
        """
        return self.buckets.get(key)

    async def set_bucket_state(self, key: str, tokens: float, last_refill: float, ttl: int) -> None:
        """Set token bucket state.

        Args:
            key: Rate limit key
            tokens: Current token count
            last_refill: Last refill timestamp
            ttl: Time-to-live (ignored for in-memory)
        """
        self.buckets[key] = (tokens, last_refill)

    async def get_window_count(self, key: str, window_start: int) -> int:
        """Get request count for a time window.

        Args:
            key: Rate limit key
            window_start: Window start timestamp

        Returns:
            Request count
        """
        window_key = f"{key}:{window_start}"
        return self.windows.get(window_key, 0)

    async def increment_window_count(
        self, key: str, window_start: int, window_duration: int
    ) -> int:
        """Increment request count for a time window.

        Args:
            key: Rate limit key
            window_start: Window start timestamp
            window_duration: Window duration (ignored for in-memory)

        Returns:
            New count after increment
        """
        window_key = f"{key}:{window_start}"
        current = self.windows.get(window_key, 0)
        new_count = current + 1
        self.windows[window_key] = new_count
        return new_count
