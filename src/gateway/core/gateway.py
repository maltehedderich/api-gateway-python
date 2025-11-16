"""Main Gateway integration module.

This module integrates all components:
- HTTP Server
- Router
- Middleware Chain
- Configuration
- Logging
- Metrics
- Session Store
- Authentication
"""

import logging

from aiohttp import web

from gateway.core.config import GatewayConfig
from gateway.core.handler import create_handler_middleware
from gateway.core.logging import GatewayLogger
from gateway.core.metrics import GatewayMetrics
from gateway.core.middleware import (
    ErrorHandlingMiddleware,
    Middleware,
    MiddlewareChain,
    RequestLoggingMiddleware,
    ResponseLoggingMiddleware,
)
from gateway.core.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitStore,
    RedisRateLimitStore,
)
from gateway.core.routing import Router
from gateway.core.server import HTTPServer
from gateway.core.session_store import RedisSessionStore, SessionStore
from gateway.middleware.auth import AuthenticationMiddleware
from gateway.middleware.proxy import ProxyMiddleware
from gateway.middleware.ratelimit import RateLimitingMiddleware

logger = logging.getLogger(__name__)


class Gateway:
    """Main API Gateway class.

    Integrates all components and manages the gateway lifecycle.
    """

    def __init__(self, config: GatewayConfig):
        """Initialize the gateway.

        Args:
            config: Gateway configuration
        """
        self.config = config
        self.structured_logger = GatewayLogger(config.logging)
        self.metrics = GatewayMetrics(config.metrics)
        self.router = Router(config.routes)

        # Initialize session store
        self.session_store = self._create_session_store()

        # Initialize rate limit store
        self.rate_limit_store = self._create_rate_limit_store()

        self.middleware_chain = self._create_middleware_chain()
        self.server = HTTPServer(config, self.structured_logger, self.metrics)

    def _create_session_store(self) -> SessionStore:
        """Create session store instance.

        Returns:
            SessionStore instance
        """
        return RedisSessionStore(
            redis_url=self.config.session.session_store_url, key_prefix="session:"
        )

    def _create_rate_limit_store(self) -> RateLimitStore:
        """Create rate limit store instance.

        Returns:
            RateLimitStore instance
        """
        # Check if Redis URL is provided for rate limiting
        if self.config.rate_limiting.store_url.startswith("redis://"):
            return RedisRateLimitStore(
                redis_url=self.config.rate_limiting.store_url, key_prefix="ratelimit:"
            )
        elif self.config.rate_limiting.store_url == "memory":
            # Use in-memory store for development/testing
            logger.warning("Using in-memory rate limit store - not suitable for production")
            return InMemoryRateLimitStore()
        else:
            # Default to Redis
            return RedisRateLimitStore(
                redis_url=self.config.rate_limiting.store_url, key_prefix="ratelimit:"
            )

    def _create_middleware_chain(self) -> MiddlewareChain:
        """Create the middleware chain.

        Middleware execution order (section 9.6):
        1. Error handling (wraps everything)
        2. Request logging
        3. Authentication and Authorization (section 9.3)
        4. Rate limiting (section 9.4)
        5. Proxy (section 9.5)
        6. Response logging

        Returns:
            MiddlewareChain instance
        """
        middlewares: list[Middleware] = [
            ErrorHandlingMiddleware(self.config),
            RequestLoggingMiddleware(self.config),
            AuthenticationMiddleware(self.config, self.session_store),
            RateLimitingMiddleware(self.config, self.rate_limit_store),
            ProxyMiddleware(self.config),
            ResponseLoggingMiddleware(self.config),
        ]

        return MiddlewareChain(middlewares)

    def _setup_routes(self, app: web.Application) -> None:
        """Setup routes and handlers.

        Args:
            app: aiohttp Application instance
        """
        # Create handler middleware
        handler_middleware = create_handler_middleware(
            self.router, self.middleware_chain, self.config
        )

        # Add to app middlewares (need to cast as aiohttp expects specific middleware type)
        app.middlewares.append(handler_middleware)  # type: ignore[arg-type]

        # Add health check routes
        if self.config.metrics.enabled:
            app.router.add_get(self.config.metrics.health_endpoint, self._health_check)
            app.router.add_get(self.config.metrics.liveness_endpoint, self._liveness_check)
            app.router.add_get(self.config.metrics.readiness_endpoint, self._readiness_check)
            app.router.add_get(self.config.metrics.endpoint, self._metrics_endpoint)

    async def _health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint.

        Args:
            request: aiohttp Request object

        Returns:
            Health status response
        """
        health_status = {
            "status": "healthy",
            "environment": self.config.environment,
            "version": "0.1.0",
        }
        return web.json_response(health_status, status=200)

    async def _liveness_check(self, request: web.Request) -> web.Response:
        """Liveness check endpoint.

        Args:
            request: aiohttp Request object

        Returns:
            Liveness status response
        """
        return web.json_response({"status": "alive"}, status=200)

    async def _readiness_check(self, request: web.Request) -> web.Response:
        """Readiness check endpoint.

        Args:
            request: aiohttp Request object

        Returns:
            Readiness status response
        """
        # Check session store connectivity
        try:
            # Simple connectivity check - try to get a non-existent key
            await self.session_store.get("readiness-check")
            session_store_ready = True
        except Exception as e:
            logger.error(f"Session store not ready: {e}")
            session_store_ready = False

        if not session_store_ready:
            return web.json_response(
                {"status": "not_ready", "reason": "session_store_unavailable"}, status=503
            )

        # Check rate limit store health (only if rate limiting is enabled)
        rate_limit_store_ready = True
        if self.config.rate_limiting.enabled:
            try:
                rate_limit_store_ready = await self.rate_limit_store.is_healthy()
            except Exception as e:
                logger.error(f"Rate limit store not ready: {e}")
                rate_limit_store_ready = False

            if not rate_limit_store_ready:
                return web.json_response(
                    {"status": "not_ready", "reason": "rate_limit_store_unavailable"}, status=503
                )

        return web.json_response({"status": "ready"}, status=200)

    async def _metrics_endpoint(self, request: web.Request) -> web.Response:
        """Metrics endpoint (Prometheus format).

        Args:
            request: aiohttp Request object

        Returns:
            Metrics in Prometheus format
        """
        metrics_bytes = self.metrics.export_metrics()
        metrics_text = metrics_bytes.decode("utf-8")
        return web.Response(text=metrics_text, content_type="text/plain; version=0.0.4")

    async def start(self) -> None:
        """Start the gateway."""
        logger.info(
            f"Starting API Gateway in {self.config.environment} environment",
            extra={"environment": self.config.environment, "routes": len(self.config.routes)},
        )

        # Connect to session store
        await self.session_store.connect()

        # Connect to rate limit store
        await self.rate_limit_store.connect()

        # Create and configure app
        app = self.server.create_app()
        self._setup_routes(app)

        # Start server
        await self.server.start()

        logger.info("API Gateway started successfully")

    async def stop(self) -> None:
        """Stop the gateway."""
        logger.info("Stopping API Gateway...")
        await self.server.stop()

        # Disconnect from session store
        await self.session_store.disconnect()

        # Disconnect from rate limit store
        await self.rate_limit_store.disconnect()

        logger.info("API Gateway stopped")

    async def run_forever(self) -> None:
        """Run the gateway until interrupted."""
        await self.start()

        # Wait forever (until interrupted)
        import asyncio

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown signal received")
        finally:
            await self.stop()
