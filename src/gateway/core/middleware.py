"""Middleware framework for the API Gateway.

This module implements the middleware framework including:
- Middleware interface and execution chain
- Middleware composition and ordering
- Request context propagation
- Support for per-route and global middleware
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from aiohttp import web

from gateway.core.config import GatewayConfig
from gateway.core.routing import RouteMatch

logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """Request context that flows through the middleware chain.

    This context accumulates data as the request flows through middleware:
    - HTTP request data
    - Client information
    - Route information
    - User and session context (populated by auth middleware)
    - Timing information
    - Custom attributes
    """

    # HTTP Request Data
    method: str
    path: str
    query_params: Dict[str, str]
    headers: Dict[str, str]
    client_ip: str
    user_agent: str

    # Correlation and Timing
    correlation_id: str
    start_time: float = field(default_factory=time.time)

    # Route Information
    route_match: Optional[RouteMatch] = None

    # Authentication/Authorization Context (populated by auth middleware)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    authenticated: bool = False

    # Rate Limiting Context (populated by rate limiting middleware)
    rate_limit_key: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[int] = None

    # Custom attributes for middleware to attach data
    attributes: Dict[str, Any] = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        """Calculate elapsed time since request start in milliseconds.

        Returns:
            Elapsed time in milliseconds
        """
        return (time.time() - self.start_time) * 1000


# Type alias for middleware handler functions
MiddlewareHandler = Callable[[web.Request, RequestContext], Any]


class Middleware(ABC):
    """Abstract base class for middleware components.

    Middleware can:
    - Inspect and modify the request context
    - Short-circuit the request flow by returning a response
    - Execute logic before and after the next middleware in the chain
    """

    def __init__(self, config: GatewayConfig):
        """Initialize the middleware.

        Args:
            config: Gateway configuration
        """
        self.config = config

    @abstractmethod
    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process the request.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler in the chain

        Returns:
            web.Response object
        """
        pass

    @property
    def name(self) -> str:
        """Get middleware name.

        Returns:
            Middleware class name
        """
        return self.__class__.__name__


class MiddlewareChain:
    """Executes middleware in a chain/pipeline pattern.

    Middleware are executed in order, with each middleware having the opportunity
    to call the next handler or short-circuit the chain by returning a response.
    """

    def __init__(self, middlewares: List[Middleware]):
        """Initialize the middleware chain.

        Args:
            middlewares: List of middleware in execution order
        """
        self.middlewares = middlewares
        logger.info(
            f"Middleware chain initialized with {len(middlewares)} middleware",
            extra={"middleware": [m.name for m in middlewares]},
        )

    async def execute(self, request: web.Request, context: RequestContext) -> web.Response:
        """Execute the middleware chain.

        Args:
            request: aiohttp Request object
            context: Request context

        Returns:
            web.Response object
        """
        # Build the chain from the end
        async def build_handler(index: int) -> MiddlewareHandler:
            """Build handler at given index.

            Args:
                index: Middleware index

            Returns:
                Handler function
            """
            if index >= len(self.middlewares):
                # End of chain - should not reach here in normal flow
                async def end_handler(req: web.Request, ctx: RequestContext) -> web.Response:
                    return web.Response(
                        status=500,
                        text='{"error": "internal_error", "message": "End of middleware chain reached without response"}',
                        content_type="application/json",
                    )

                return end_handler

            middleware = self.middlewares[index]

            async def handler(req: web.Request, ctx: RequestContext) -> web.Response:
                """Handler for current middleware.

                Args:
                    req: aiohttp Request object
                    ctx: Request context

                Returns:
                    web.Response object
                """
                # Get the next handler
                next_handler = await build_handler(index + 1)

                # Execute current middleware
                return await middleware.process(req, ctx, next_handler)

            return handler

        # Start execution from first middleware
        first_handler = await build_handler(0)
        return await first_handler(request, context)


class RequestLoggingMiddleware(Middleware):
    """Middleware for logging incoming requests.

    Logs request metadata at the start of request processing.
    """

    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process request with logging.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler

        Returns:
            web.Response object
        """
        # Get structured logger from app
        structured_logger = request.app.get("logger")

        # Log request start
        if structured_logger:
            await structured_logger.log_request(
                correlation_id=context.correlation_id,
                method=context.method,
                path=context.path,
                client_ip=context.client_ip,
                user_agent=context.user_agent,
                headers=context.headers,
            )

        # Continue to next middleware
        return await next_handler(request, context)


class ResponseLoggingMiddleware(Middleware):
    """Middleware for logging responses.

    Logs response metadata after request processing completes.
    Should be placed at the end of the middleware chain.
    """

    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process request with response logging.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler

        Returns:
            web.Response object
        """
        # Execute next middleware
        response = await next_handler(request, context)

        # Get structured logger from app
        structured_logger = request.app.get("logger")

        # Log response with full context per design spec section 9.6 Task 28
        if structured_logger:
            log_params = {
                "correlation_id": context.correlation_id,
                "status_code": response.status,
                "latency_ms": context.elapsed_ms(),
                "user_id": context.user_id,
                "route_id": context.route_match.route.id if context.route_match else None,
            }

            # Add rate limiting context if available
            if context.rate_limit_key:
                log_params["ratelimit"] = {
                    "key": context.rate_limit_key,
                    "remaining": context.rate_limit_remaining,
                    "reset_at": context.rate_limit_reset,
                }

            await structured_logger.log_response(**log_params)

        # Update metrics
        metrics = request.app.get("metrics")
        if metrics:
            metrics.record_request(
                method=context.method,
                path=context.path,
                status_code=response.status,
                latency_ms=context.elapsed_ms(),
            )

        return response


class ErrorHandlingMiddleware(Middleware):
    """Middleware for handling errors and exceptions.

    Catches exceptions from downstream middleware and converts them
    to appropriate HTTP error responses.
    """

    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process request with error handling.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler

        Returns:
            web.Response object
        """
        try:
            return await next_handler(request, context)
        except web.HTTPException:
            # Re-raise HTTP exceptions (they're already proper responses)
            raise
        except Exception as e:
            logger.exception(
                f"Unhandled exception in middleware chain: {e}",
                extra={
                    "correlation_id": context.correlation_id,
                    "path": context.path,
                    "method": context.method,
                },
            )

            # Return 500 error response with timestamp per design spec section 6.1
            from datetime import datetime
            return web.json_response(
                {
                    "error": "internal_error",
                    "message": "An unexpected error occurred",
                    "correlation_id": context.correlation_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                status=500,
            )


def create_request_context(request: web.Request, correlation_id: Optional[str] = None) -> RequestContext:
    """Create a request context from an aiohttp request.

    Args:
        request: aiohttp Request object
        correlation_id: Optional correlation ID (generated if not provided)

    Returns:
        RequestContext instance
    """
    # Generate correlation ID if not provided
    if not correlation_id:
        # Check if client provided correlation ID
        config = request.app.get("config")
        if config:
            header_name = config.logging.correlation_id_header
            correlation_id = request.headers.get(header_name)

        # Generate if still not available
        if not correlation_id:
            correlation_id = f"req-{uuid.uuid4().hex[:16]}"

    # Extract client IP (handle proxies)
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.remote or "unknown"

    # Get user agent
    user_agent = request.headers.get("User-Agent", "unknown")

    # Build query params dict
    query_params = dict(request.query)

    # Build headers dict (convert to regular dict)
    headers = dict(request.headers)

    return RequestContext(
        method=request.method,
        path=request.path,
        query_params=query_params,
        headers=headers,
        client_ip=client_ip,
        user_agent=user_agent,
        correlation_id=correlation_id,
    )
