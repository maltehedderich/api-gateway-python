"""Rate limiting middleware for the API Gateway.

This module implements:
- Rate limiting key generation (Task 16)
- Rate limiting evaluation logic (Task 18)
- Rate limiting middleware (Task 19)
"""

import logging
from datetime import datetime
from typing import Optional

from aiohttp import web

from gateway.core.config import GatewayConfig, RateLimitRule
from gateway.core.middleware import Middleware, MiddlewareHandler, RequestContext
from gateway.core.rate_limit import (
    FixedWindowAlgorithm,
    RateLimitAlgorithm,
    RateLimitState,
    RateLimitStore,
    SlidingWindowAlgorithm,
    TokenBucketAlgorithm,
)

logger = logging.getLogger(__name__)


class RateLimitKeyGenerator:
    """Generates rate limiting keys based on configuration.

    Supports different key strategies:
    - ip: Based on client IP address
    - user: Based on authenticated user ID
    - route: Based on route path
    - composite: Combination of multiple dimensions
    """

    def generate_key(
        self,
        context: RequestContext,
        rule: RateLimitRule,
    ) -> str:
        """Generate rate limiting key based on rule configuration.

        Args:
            context: Request context
            rule: Rate limiting rule

        Returns:
            Rate limiting key
        """
        key_type = rule.key_type

        if key_type == "ip":
            return self._generate_ip_key(context, rule)
        elif key_type == "user":
            return self._generate_user_key(context, rule)
        elif key_type == "route":
            return self._generate_route_key(context, rule)
        elif key_type == "composite":
            return self._generate_composite_key(context, rule)
        else:
            logger.warning(f"Unknown key type {key_type}, defaulting to IP")
            return self._generate_ip_key(context, rule)

    def _generate_ip_key(self, context: RequestContext, rule: RateLimitRule) -> str:
        """Generate key based on client IP.

        Args:
            context: Request context
            rule: Rate limiting rule

        Returns:
            IP-based key
        """
        return f"ip:{context.client_ip}:{rule.name}"

    def _generate_user_key(self, context: RequestContext, rule: RateLimitRule) -> str:
        """Generate key based on user ID.

        Args:
            context: Request context
            rule: Rate limiting rule

        Returns:
            User-based key
        """
        # If not authenticated, fall back to IP
        if not context.authenticated or not context.user_id:
            logger.debug("User not authenticated, falling back to IP-based key")
            return self._generate_ip_key(context, rule)

        return f"user:{context.user_id}:{rule.name}"

    def _generate_route_key(self, context: RequestContext, rule: RateLimitRule) -> str:
        """Generate key based on route path.

        Args:
            context: Request context
            rule: Rate limiting rule

        Returns:
            Route-based key
        """
        route_id = context.route_match.route.id if context.route_match else "unknown"
        return f"route:{route_id}:{rule.name}"

    def _generate_composite_key(
        self, context: RequestContext, rule: RateLimitRule
    ) -> str:
        """Generate composite key based on multiple dimensions.

        Combines user (or IP) + route for fine-grained control.

        Args:
            context: Request context
            rule: Rate limiting rule

        Returns:
            Composite key
        """
        # Use user if authenticated, otherwise IP
        if context.authenticated and context.user_id:
            user_part = f"user:{context.user_id}"
        else:
            user_part = f"ip:{context.client_ip}"

        # Add route
        route_id = context.route_match.route.id if context.route_match else "unknown"

        return f"{user_part}:route:{route_id}:{rule.name}"


class RateLimitEvaluator:
    """Evaluates rate limiting rules and makes allow/deny decisions."""

    def __init__(
        self,
        store: RateLimitStore,
        fail_mode: str = "open",
    ):
        """Initialize rate limit evaluator.

        Args:
            store: Rate limiting state store
            fail_mode: Fail mode ('open' or 'closed') when store is unavailable
        """
        self.store = store
        self.fail_mode = fail_mode
        self.key_generator = RateLimitKeyGenerator()

        # Cache algorithm instances
        self.algorithms: dict[str, RateLimitAlgorithm] = {
            "token_bucket": TokenBucketAlgorithm(store),
            "fixed_window": FixedWindowAlgorithm(store),
            "sliding_window": SlidingWindowAlgorithm(store),
        }

    def _get_algorithm(self, algorithm_name: str) -> RateLimitAlgorithm:
        """Get rate limiting algorithm by name.

        Args:
            algorithm_name: Algorithm name

        Returns:
            Rate limiting algorithm instance
        """
        return self.algorithms.get(
            algorithm_name, self.algorithms["token_bucket"]  # Default to token bucket
        )

    async def evaluate(
        self, context: RequestContext, rule: RateLimitRule
    ) -> RateLimitState:
        """Evaluate rate limiting rule for a request.

        Args:
            context: Request context
            rule: Rate limiting rule

        Returns:
            RateLimitState with decision and metadata
        """
        try:
            # Check if store is healthy
            if not await self.store.is_healthy():
                logger.warning("Rate limit store unhealthy, using fail mode")
                return self._handle_store_failure(rule)

            # Generate rate limiting key
            key = self.key_generator.generate_key(context, rule)

            # Get algorithm
            algorithm = self._get_algorithm(rule.algorithm)

            # Check limit
            state = await algorithm.check_limit(
                key=key,
                limit=rule.limit,
                window=rule.window,
                burst=rule.burst,
            )

            # Log rate limiting decision
            if not state.allowed:
                logger.info(
                    f"Rate limit exceeded for key {key}",
                    extra={
                        "correlation_id": context.correlation_id,
                        "key": key,
                        "rule": rule.name,
                        "limit": rule.limit,
                        "window": rule.window,
                    },
                )
            else:
                logger.debug(
                    f"Rate limit check passed for key {key}",
                    extra={
                        "correlation_id": context.correlation_id,
                        "key": key,
                        "remaining": state.remaining,
                    },
                )

            return state

        except Exception as e:
            logger.error(f"Error evaluating rate limit: {e}", exc_info=True)
            return self._handle_store_failure(rule)

    def _handle_store_failure(self, rule: RateLimitRule) -> RateLimitState:
        """Handle rate limit store failure based on fail mode.

        Args:
            rule: Rate limiting rule

        Returns:
            RateLimitState based on fail mode
        """
        if self.fail_mode == "open":
            # Fail-open: allow requests when store is unavailable
            logger.warning("Failing open: allowing request due to store failure")
            return RateLimitState(
                allowed=True,
                remaining=rule.limit,
                limit=rule.limit,
                reset_at=0,
            )
        else:
            # Fail-closed: deny requests when store is unavailable
            logger.warning("Failing closed: denying request due to store failure")
            return RateLimitState(
                allowed=False,
                remaining=0,
                limit=rule.limit,
                reset_at=0,
                retry_after=60,  # Retry after 1 minute
            )


class RateLimitingMiddleware(Middleware):
    """Middleware for rate limiting.

    This middleware:
    1. Determines which rate limiting rules apply to the request
    2. Generates rate limiting keys based on configuration
    3. Evaluates rate limits
    4. Returns 429 Too Many Requests if limits are exceeded
    5. Adds rate limit headers to responses
    """

    def __init__(
        self,
        config: GatewayConfig,
        rate_limit_store: RateLimitStore,
    ):
        """Initialize rate limiting middleware.

        Args:
            config: Gateway configuration
            rate_limit_store: Rate limiting state store
        """
        super().__init__(config)
        self.rate_limit_store = rate_limit_store
        self.evaluator = RateLimitEvaluator(
            store=rate_limit_store,
            fail_mode=config.rate_limiting.fail_mode,
        )
        self.enabled = config.rate_limiting.enabled
        self.rules = config.rate_limiting.rules

    def _find_applicable_rules(self, context: RequestContext) -> list[RateLimitRule]:
        """Find rate limiting rules that apply to this request.

        Args:
            context: Request context

        Returns:
            List of applicable rules
        """
        applicable_rules = []

        route_id = context.route_match.route.id if context.route_match else None

        for rule in self.rules:
            # If rule has no specific routes, it applies to all
            if not rule.routes:
                applicable_rules.append(rule)
            # If rule specifies routes, check if current route matches
            elif route_id and route_id in rule.routes:
                applicable_rules.append(rule)

        return applicable_rules

    def _add_rate_limit_headers(
        self, response: web.Response, state: RateLimitState
    ) -> None:
        """Add rate limit headers to response.

        Args:
            response: Response object
            state: Rate limit state
        """
        response.headers["X-RateLimit-Limit"] = str(state.limit)
        response.headers["X-RateLimit-Remaining"] = str(state.remaining)
        response.headers["X-RateLimit-Reset"] = str(state.reset_at)

        if state.retry_after is not None:
            response.headers["Retry-After"] = str(state.retry_after)

    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process request with rate limiting.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler

        Returns:
            web.Response object
        """
        # Skip if rate limiting is disabled
        if not self.enabled:
            return await next_handler(request, context)

        # Skip if no route matched (will be handled by routing error)
        if not context.route_match:
            return await next_handler(request, context)

        # Find applicable rules
        applicable_rules = self._find_applicable_rules(context)

        if not applicable_rules:
            # No rules apply, continue
            return await next_handler(request, context)

        # Evaluate all applicable rules
        # Request is allowed only if ALL rules allow it
        for rule in applicable_rules:
            state = await self.evaluator.evaluate(context, rule)

            # Populate context with rate limiting info (from first/most restrictive rule)
            if context.rate_limit_key is None:
                context.rate_limit_key = self.evaluator.key_generator.generate_key(
                    context, rule
                )
                context.rate_limit_remaining = state.remaining
                context.rate_limit_reset = state.reset_at

            if not state.allowed:
                # Rate limit exceeded - return 429
                logger.info(
                    f"Rate limit exceeded for rule {rule.name}",
                    extra={
                        "correlation_id": context.correlation_id,
                        "rule": rule.name,
                        "user_id": context.user_id,
                        "client_ip": context.client_ip,
                    },
                )

                response = web.json_response(
                    {
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests, please try again later",
                        "correlation_id": context.correlation_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                    status=429,
                )

                self._add_rate_limit_headers(response, state)

                # Update metrics if available
                metrics = request.app.get("metrics")
                if metrics:
                    metrics.record_rate_limit_exceeded(rule.name, rule.key_type)

                return response

        # All rules passed - proceed with request
        response = await next_handler(request, context)

        # Add rate limit headers to successful response
        # Use the most restrictive state (lowest remaining)
        if context.rate_limit_remaining is not None:
            final_state = RateLimitState(
                allowed=True,
                remaining=context.rate_limit_remaining,
                limit=applicable_rules[0].limit,
                reset_at=context.rate_limit_reset or 0,
            )
            self._add_rate_limit_headers(response, final_state)

        return response
