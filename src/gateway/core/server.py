"""HTTP Server module for the API Gateway.

This module implements the HTTP server foundation including:
- Asynchronous HTTP server using aiohttp
- TLS/HTTPS support
- Connection management and timeouts
- Request/response handling
"""

import logging
import ssl

from aiohttp import web

from gateway.core.config import GatewayConfig
from gateway.core.logging import GatewayLogger
from gateway.core.metrics import GatewayMetrics

logger = logging.getLogger(__name__)


class HTTPServer:
    """HTTP Server for the API Gateway.

    Handles:
    - TCP connection acceptance and HTTP protocol parsing
    - TLS termination for secure connections
    - Connection management and timeouts
    - Request routing to middleware pipeline
    """

    def __init__(
        self,
        config: GatewayConfig,
        structured_logger: GatewayLogger,
        metrics: GatewayMetrics,
    ):
        """Initialize the HTTP server.

        Args:
            config: Gateway configuration
            structured_logger: Gateway logger instance
            metrics: Gateway metrics instance
        """
        self.config = config
        self.structured_logger = structured_logger
        self.metrics = metrics
        self.app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    def create_app(self) -> web.Application:
        """Create and configure the aiohttp application.

        Returns:
            Configured aiohttp Application instance
        """
        app = web.Application(
            client_max_size=10 * 1024 * 1024,  # 10MB max request size
            handler_args={
                "keepalive_timeout": self.config.server.keepalive_timeout,
            },
        )

        # Store references for access in handlers
        app["config"] = self.config
        app["logger"] = self.structured_logger
        app["metrics"] = self.metrics

        # Setup lifecycle hooks
        app.on_startup.append(self._on_startup)
        app.on_shutdown.append(self._on_shutdown)
        app.on_cleanup.append(self._on_cleanup)

        self.app = app
        return app

    def _create_ssl_context(self) -> ssl.SSLContext | None:
        """Create SSL context for TLS support.

        Returns:
            SSLContext if TLS is enabled, None otherwise
        """
        if not self.config.server.tls_enabled:
            return None

        if not self.config.server.tls_cert_path or not self.config.server.tls_key_path:
            logger.warning("TLS enabled but certificate or key path not configured")
            return None

        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(
            certfile=self.config.server.tls_cert_path,
            keyfile=self.config.server.tls_key_path,
        )

        # Configure TLS settings for security
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.set_ciphers("HIGH:!aNULL:!MD5:!RC4")

        logger.info(
            "TLS enabled",
            extra={
                "cert_path": self.config.server.tls_cert_path,
                "min_version": "TLSv1.2",
            },
        )

        return ssl_context

    async def start(self) -> None:
        """Start the HTTP server.

        Raises:
            RuntimeError: If server is already running or fails to start
        """
        if self._runner is not None:
            raise RuntimeError("Server is already running")

        if self.app is None:
            self.create_app()

        # Create SSL context if TLS is enabled
        ssl_context = self._create_ssl_context()

        # Create and start runner
        self._runner = web.AppRunner(
            self.app,
            access_log=None,  # We handle logging ourselves
        )
        await self._runner.setup()

        # Create and start site
        self._site = web.TCPSite(
            self._runner,
            host=self.config.server.host,
            port=self.config.server.port,
            ssl_context=ssl_context,
        )
        await self._site.start()

        protocol = "https" if ssl_context else "http"
        logger.info(
            f"HTTP server started on {protocol}://{self.config.server.host}:{self.config.server.port}",
            extra={
                "host": self.config.server.host,
                "port": self.config.server.port,
                "tls_enabled": self.config.server.tls_enabled,
                "max_connections": self.config.server.max_connections,
            },
        )

    async def stop(self) -> None:
        """Stop the HTTP server gracefully."""
        if self._runner is None:
            logger.warning("Server is not running")
            return

        logger.info("Stopping HTTP server...")

        # Stop accepting new connections
        if self._site:
            await self._site.stop()

        # Cleanup runner
        if self._runner:
            await self._runner.cleanup()

        self._site = None
        self._runner = None

        logger.info("HTTP server stopped")

    async def _on_startup(self, app: web.Application) -> None:
        """Application startup hook.

        Args:
            app: aiohttp Application instance
        """
        logger.info("Application starting up...")
        # Initialize any resources needed at startup

    async def _on_shutdown(self, app: web.Application) -> None:
        """Application shutdown hook.

        Args:
            app: aiohttp Application instance
        """
        logger.info("Application shutting down...")
        # Cleanup resources gracefully

    async def _on_cleanup(self, app: web.Application) -> None:
        """Application cleanup hook.

        Args:
            app: aiohttp Application instance
        """
        logger.info("Application cleanup...")
        # Final cleanup after shutdown
