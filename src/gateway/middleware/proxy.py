"""Proxy middleware for forwarding requests to upstream services.

This module implements the upstream proxying functionality including:
- Request forwarding to backend services
- Header propagation and modification
- Response streaming
- Connection pooling and timeout management
- Error handling for upstream failures
"""

import asyncio
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

from gateway.core.middleware import Middleware, MiddlewareHandler, RequestContext

logger = logging.getLogger(__name__)


class UpstreamProxyClient:
    """HTTP client for proxying requests to upstream services.

    Manages connection pooling, timeouts, and request forwarding.
    """

    def __init__(self, config):
        """Initialize the upstream proxy client.

        Args:
            config: Gateway configuration with upstream settings
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp client session.

        Returns:
            Configured aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            # Create connector with connection pooling settings
            connector = aiohttp.TCPConnector(
                limit=self.config.upstream.pool_size,
                limit_per_host=self.config.upstream.pool_size,
                enable_cleanup_closed=True,
            )

            # Create timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=self.config.upstream.request_timeout,
                connect=self.config.upstream.connection_timeout,
            )

            # Create session
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                auto_decompress=False,  # Let client handle decompression
            )

            logger.info(
                "Upstream proxy client session created",
                extra={
                    "pool_size": self.config.upstream.pool_size,
                    "connection_timeout": self.config.upstream.connection_timeout,
                    "request_timeout": self.config.upstream.request_timeout,
                },
            )

        return self._session

    async def close(self) -> None:
        """Close the client session and clean up connections."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Upstream proxy client session closed")

    def _construct_upstream_url(
        self,
        base_url: str,
        request_path: str,
        path_params: Dict[str, str],
        query_string: str,
    ) -> str:
        """Construct the full upstream URL.

        Args:
            base_url: Upstream service base URL from route configuration
            request_path: Original request path
            path_params: Extracted path parameters from routing
            query_string: Query string from original request

        Returns:
            Full upstream URL
        """
        # Parse the base URL
        parsed = urlparse(base_url)

        # Combine base path with request path
        if parsed.path and parsed.path != "/":
            # Base URL has a path component
            full_path = parsed.path.rstrip("/") + request_path
        else:
            full_path = request_path

        # Reconstruct the URL with scheme and netloc from base_url
        scheme = parsed.scheme or "http"
        netloc = parsed.netloc

        # Construct the full URL
        if query_string:
            url = f"{scheme}://{netloc}{full_path}?{query_string}"
        else:
            url = f"{scheme}://{netloc}{full_path}"

        return url

    def _prepare_upstream_headers(
        self,
        request_headers: Dict[str, str],
        upstream_url: str,
        correlation_id: str,
        user_id: Optional[str] = None,
        client_ip: str = "unknown",
    ) -> Dict[str, str]:
        """Prepare headers for upstream request.

        Copies headers from original request and adds/modifies proxy-specific headers.

        Args:
            request_headers: Original request headers
            upstream_url: Upstream service URL
            correlation_id: Request correlation ID
            user_id: Authenticated user ID (if available)
            client_ip: Client IP address

        Returns:
            Dictionary of headers for upstream request
        """
        headers = {}

        # Copy most headers from original request
        skip_headers = {
            "host",  # Will be set to upstream host
            "connection",  # Will be managed by aiohttp
            "transfer-encoding",  # Will be managed by aiohttp
            "content-length",  # Will be recalculated if needed
        }

        for key, value in request_headers.items():
            if key.lower() not in skip_headers:
                headers[key] = value

        # Set Host header to upstream service
        parsed_url = urlparse(upstream_url)
        headers["Host"] = parsed_url.netloc

        # Add X-Forwarded-* headers
        # X-Forwarded-For: append client IP
        existing_xff = request_headers.get("X-Forwarded-For", "")
        if existing_xff:
            headers["X-Forwarded-For"] = f"{existing_xff}, {client_ip}"
        else:
            headers["X-Forwarded-For"] = client_ip

        # X-Forwarded-Proto: preserve or set based on original request
        if "X-Forwarded-Proto" not in headers:
            # Determine protocol from upstream URL
            headers["X-Forwarded-Proto"] = parsed_url.scheme or "http"

        # X-Request-ID: correlation ID for tracing
        headers["X-Request-ID"] = correlation_id

        # X-User-ID: optionally add authenticated user ID
        if user_id:
            headers["X-User-ID"] = user_id

        return headers

    async def forward_request(
        self,
        method: str,
        upstream_url: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        correlation_id: str = "unknown",
    ) -> aiohttp.ClientResponse:
        """Forward request to upstream service.

        Args:
            method: HTTP method
            upstream_url: Full upstream URL
            headers: Request headers
            body: Request body (if any)
            correlation_id: Request correlation ID for logging

        Returns:
            aiohttp ClientResponse

        Raises:
            aiohttp.ClientError: On connection or request errors
            asyncio.TimeoutError: On timeout
        """
        session = await self._get_session()

        logger.debug(
            f"Forwarding {method} request to upstream",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "upstream_url": upstream_url,
            },
        )

        try:
            response = await session.request(
                method=method,
                url=upstream_url,
                headers=headers,
                data=body,
                allow_redirects=False,  # Don't follow redirects, pass them through
            )

            logger.debug(
                f"Received response from upstream: {response.status}",
                extra={
                    "correlation_id": correlation_id,
                    "status": response.status,
                    "upstream_url": upstream_url,
                },
            )

            return response

        except Exception as e:
            logger.error(
                f"Upstream request failed: {e}",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "upstream_url": upstream_url,
                    "error": str(e),
                },
            )
            raise


class ProxyMiddleware(Middleware):
    """Middleware for proxying requests to upstream services.

    Responsibilities:
    - Construct upstream URL from route configuration
    - Prepare and forward requests to backend services
    - Stream responses back to clients
    - Handle upstream errors and timeouts
    """

    def __init__(self, config):
        """Initialize the proxy middleware.

        Args:
            config: Gateway configuration
        """
        super().__init__(config)
        self.proxy_client = UpstreamProxyClient(config)
        logger.info("Proxy middleware initialized")

    async def close(self) -> None:
        """Close proxy client and clean up resources."""
        await self.proxy_client.close()

    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process request by proxying to upstream service.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler (not used - proxy is typically last)

        Returns:
            web.Response object from upstream or error response
        """
        if not context.route_match:
            # Should not happen if routing is working correctly
            logger.error(
                "Proxy middleware called without route match",
                extra={"correlation_id": context.correlation_id},
            )
            return web.json_response(
                {
                    "error": "internal_error",
                    "message": "No route match found",
                    "correlation_id": context.correlation_id,
                },
                status=500,
            )

        route = context.route_match.route
        path_params = context.route_match.path_params

        try:
            # Construct upstream URL
            query_string = request.query_string
            upstream_url = self.proxy_client._construct_upstream_url(
                base_url=route.upstream_url,
                request_path=context.path,
                path_params=path_params,
                query_string=query_string,
            )

            # Prepare headers
            headers = self.proxy_client._prepare_upstream_headers(
                request_headers=context.headers,
                upstream_url=upstream_url,
                correlation_id=context.correlation_id,
                user_id=context.user_id,
                client_ip=context.client_ip,
            )

            # Read request body if present
            body = None
            if request.can_read_body:
                body = await request.read()

            # Forward request to upstream
            upstream_response = await self.proxy_client.forward_request(
                method=context.method,
                upstream_url=upstream_url,
                headers=headers,
                body=body,
                correlation_id=context.correlation_id,
            )

            # Prepare response headers
            response_headers = self._prepare_response_headers(
                upstream_response.headers,
                context,
            )

            # Stream response body
            response_body = await upstream_response.read()

            # Create response
            response = web.Response(
                status=upstream_response.status,
                headers=response_headers,
                body=response_body,
            )

            logger.info(
                "Request proxied successfully",
                extra={
                    "correlation_id": context.correlation_id,
                    "upstream_url": upstream_url,
                    "status": upstream_response.status,
                    "latency_ms": context.elapsed_ms(),
                },
            )

            return response

        except asyncio.TimeoutError:
            # Upstream timeout
            logger.error(
                "Upstream request timeout",
                extra={
                    "correlation_id": context.correlation_id,
                    "route_id": route.id,
                    "upstream_url": route.upstream_url,
                    "timeout": self.config.upstream.request_timeout,
                },
            )
            return web.json_response(
                {
                    "error": "gateway_timeout",
                    "message": "Upstream service did not respond in time",
                    "correlation_id": context.correlation_id,
                },
                status=504,
            )

        except aiohttp.ClientConnectionError as e:
            # Connection error (upstream unreachable)
            logger.error(
                f"Upstream connection error: {e}",
                extra={
                    "correlation_id": context.correlation_id,
                    "route_id": route.id,
                    "upstream_url": route.upstream_url,
                    "error": str(e),
                },
            )
            return web.json_response(
                {
                    "error": "bad_gateway",
                    "message": "Could not connect to upstream service",
                    "correlation_id": context.correlation_id,
                },
                status=502,
            )

        except aiohttp.ClientError as e:
            # Other client errors
            logger.error(
                f"Upstream client error: {e}",
                extra={
                    "correlation_id": context.correlation_id,
                    "route_id": route.id,
                    "upstream_url": route.upstream_url,
                    "error": str(e),
                },
            )
            return web.json_response(
                {
                    "error": "bad_gateway",
                    "message": "Error communicating with upstream service",
                    "correlation_id": context.correlation_id,
                },
                status=502,
            )

        except Exception as e:
            # Unexpected errors
            logger.exception(
                f"Unexpected error in proxy middleware: {e}",
                extra={
                    "correlation_id": context.correlation_id,
                    "route_id": route.id,
                    "upstream_url": route.upstream_url,
                },
            )
            return web.json_response(
                {
                    "error": "internal_error",
                    "message": "An unexpected error occurred",
                    "correlation_id": context.correlation_id,
                },
                status=500,
            )

    def _prepare_response_headers(
        self,
        upstream_headers: Dict[str, str],
        context: RequestContext,
    ) -> Dict[str, str]:
        """Prepare response headers from upstream response.

        Args:
            upstream_headers: Headers from upstream response
            context: Request context

        Returns:
            Dictionary of headers for client response
        """
        headers = {}

        # Skip headers that shouldn't be forwarded or will be set by aiohttp
        skip_headers = {
            "connection",
            "transfer-encoding",
            "content-encoding",  # Let aiohttp handle encoding
        }

        # Copy headers from upstream response
        for key, value in upstream_headers.items():
            if key.lower() not in skip_headers:
                headers[key] = value

        # Add rate limit headers if available
        if context.rate_limit_remaining is not None:
            headers["X-RateLimit-Remaining"] = str(context.rate_limit_remaining)

        if context.rate_limit_reset is not None:
            headers["X-RateLimit-Reset"] = str(context.rate_limit_reset)

        # Add correlation ID for tracing
        headers["X-Request-ID"] = context.correlation_id

        return headers
