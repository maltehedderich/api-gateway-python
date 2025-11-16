"""Main Gateway integration module.

This module integrates all components:
- HTTP Server
- Router
- Middleware Chain
- Configuration
- Logging
- Metrics
"""

import logging
from typing import List

from aiohttp import web

from gateway.core.config import GatewayConfig
from gateway.core.handler import create_handler_middleware
from gateway.core.logging import StructuredLogger
from gateway.core.metrics import MetricsCollector
from gateway.core.middleware import (
    ErrorHandlingMiddleware,
    Middleware,
    MiddlewareChain,
    RequestLoggingMiddleware,
    ResponseLoggingMiddleware,
)
from gateway.core.routing import Router
from gateway.core.server import HTTPServer
from gateway.middleware.proxy import ProxyMiddleware

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
        self.structured_logger = StructuredLogger(config.logging)
        self.metrics = MetricsCollector(config.metrics)
        self.router = Router(config.routes)
        self.middleware_chain = self._create_middleware_chain()
        self.server = HTTPServer(config, self.structured_logger, self.metrics)

    def _create_middleware_chain(self) -> MiddlewareChain:
        """Create the middleware chain.

        Middleware execution order:
        1. Error handling (wraps everything)
        2. Request logging
        3. Authentication (placeholder - to be implemented in 9.3)
        4. Authorization (placeholder - to be implemented in 9.3)
        5. Rate limiting (placeholder - to be implemented in 9.4)
        6. Proxy (placeholder - to be implemented in 9.5)
        7. Response logging

        Returns:
            MiddlewareChain instance
        """
        middlewares: List[Middleware] = [
            ErrorHandlingMiddleware(self.config),
            RequestLoggingMiddleware(self.config),
            # TODO: Add AuthenticationMiddleware when implemented (section 9.3)
            # TODO: Add AuthorizationMiddleware when implemented (section 9.3)
            # TODO: Add RateLimitingMiddleware when implemented (section 9.4)
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

        # Add to app middlewares
        app.middlewares.append(handler_middleware)

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
        # TODO: Check dependencies (session store, rate limiter) when implemented
        return web.json_response({"status": "ready"}, status=200)

    async def _metrics_endpoint(self, request: web.Request) -> web.Response:
        """Metrics endpoint (Prometheus format).

        Args:
            request: aiohttp Request object

        Returns:
            Metrics in Prometheus format
        """
        metrics_text = self.metrics.export_prometheus()
        return web.Response(text=metrics_text, content_type="text/plain; version=0.0.4")

    async def start(self) -> None:
        """Start the gateway."""
        logger.info(
            f"Starting API Gateway in {self.config.environment} environment",
            extra={"environment": self.config.environment, "routes": len(self.config.routes)},
        )

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
