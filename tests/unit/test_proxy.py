"""Unit tests for the proxy middleware."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
from aiohttp import web

from gateway.core.config import GatewayConfig, RouteConfig, UpstreamConfig
from gateway.core.middleware import RequestContext
from gateway.core.routing import RouteMatch
from gateway.middleware.proxy import ProxyMiddleware, UpstreamProxyClient


@pytest.fixture
def gateway_config():
    """Create a test gateway configuration."""
    config = GatewayConfig()
    config.upstream = UpstreamConfig(
        connection_timeout=5,
        request_timeout=30,
        pool_size=100,
    )
    return config


@pytest.fixture
def route_config():
    """Create a test route configuration."""
    return RouteConfig(
        id="test-route",
        path_pattern="/api/users/{user_id}",
        methods=["GET", "POST"],
        upstream_url="http://backend-service:8080",
        timeout=30,
    )


@pytest.fixture
def request_context(route_config):
    """Create a test request context."""
    context = RequestContext(
        method="GET",
        path="/api/users/123",
        query_params={"page": "1"},
        headers={
            "User-Agent": "test-agent",
            "Content-Type": "application/json",
        },
        client_ip="192.168.1.100",
        user_agent="test-agent",
        correlation_id="test-correlation-id",
    )
    context.route_match = RouteMatch(
        route=route_config,
        path_params={"user_id": "123"},
    )
    context.user_id = "user-456"
    return context


class TestUpstreamProxyClient:
    """Tests for UpstreamProxyClient."""

    def test_construct_upstream_url_simple(self, gateway_config):
        """Test URL construction with simple path."""
        client = UpstreamProxyClient(gateway_config)

        url = client._construct_upstream_url(
            base_url="http://backend:8080",
            request_path="/api/users",
            path_params={},
            query_string="",
        )

        assert url == "http://backend:8080/api/users"

    def test_construct_upstream_url_with_query(self, gateway_config):
        """Test URL construction with query string."""
        client = UpstreamProxyClient(gateway_config)

        url = client._construct_upstream_url(
            base_url="http://backend:8080",
            request_path="/api/users",
            path_params={},
            query_string="page=1&limit=10",
        )

        assert url == "http://backend:8080/api/users?page=1&limit=10"

    def test_construct_upstream_url_with_base_path(self, gateway_config):
        """Test URL construction when base URL has a path."""
        client = UpstreamProxyClient(gateway_config)

        url = client._construct_upstream_url(
            base_url="http://backend:8080/api/v1",
            request_path="/users",
            path_params={},
            query_string="",
        )

        assert url == "http://backend:8080/api/v1/users"

    def test_prepare_upstream_headers_basic(self, gateway_config):
        """Test header preparation with basic headers."""
        client = UpstreamProxyClient(gateway_config)

        headers = client._prepare_upstream_headers(
            request_headers={
                "User-Agent": "test-agent",
                "Content-Type": "application/json",
                "Authorization": "Bearer token123",
            },
            upstream_url="http://backend:8080/api",
            correlation_id="test-id",
            client_ip="192.168.1.100",
        )

        # Should copy most headers
        assert headers["User-Agent"] == "test-agent"
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer token123"

        # Should set Host to upstream
        assert headers["Host"] == "backend:8080"

        # Should add X-Forwarded-For
        assert headers["X-Forwarded-For"] == "192.168.1.100"

        # Should add X-Request-ID
        assert headers["X-Request-ID"] == "test-id"

        # Should add X-Forwarded-Proto
        assert headers["X-Forwarded-Proto"] == "http"

    def test_prepare_upstream_headers_with_user(self, gateway_config):
        """Test header preparation with authenticated user."""
        client = UpstreamProxyClient(gateway_config)

        headers = client._prepare_upstream_headers(
            request_headers={},
            upstream_url="http://backend:8080",
            correlation_id="test-id",
            user_id="user-123",
            client_ip="192.168.1.100",
        )

        # Should add X-User-ID
        assert headers["X-User-ID"] == "user-123"

    def test_prepare_upstream_headers_skip_connection(self, gateway_config):
        """Test that connection-related headers are skipped."""
        client = UpstreamProxyClient(gateway_config)

        headers = client._prepare_upstream_headers(
            request_headers={
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
                "Content-Length": "1234",
            },
            upstream_url="http://backend:8080",
            correlation_id="test-id",
            client_ip="192.168.1.100",
        )

        # These headers should be skipped
        assert "Connection" not in headers
        assert "Transfer-Encoding" not in headers
        assert "Content-Length" not in headers

    def test_prepare_upstream_headers_xff_chain(self, gateway_config):
        """Test X-Forwarded-For chaining."""
        client = UpstreamProxyClient(gateway_config)

        headers = client._prepare_upstream_headers(
            request_headers={
                "X-Forwarded-For": "10.0.0.1, 10.0.0.2",
            },
            upstream_url="http://backend:8080",
            correlation_id="test-id",
            client_ip="192.168.1.100",
        )

        # Should append to existing X-Forwarded-For
        assert headers["X-Forwarded-For"] == "10.0.0.1, 10.0.0.2, 192.168.1.100"

    @pytest.mark.asyncio
    async def test_get_session_creates_session(self, gateway_config):
        """Test that session is created with correct configuration."""
        client = UpstreamProxyClient(gateway_config)

        session = await client._get_session()

        assert session is not None
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed

        # Clean up
        await session.close()

    @pytest.mark.asyncio
    async def test_get_session_reuses_session(self, gateway_config):
        """Test that session is reused."""
        client = UpstreamProxyClient(gateway_config)

        session1 = await client._get_session()
        session2 = await client._get_session()

        assert session1 is session2

        # Clean up
        await session1.close()

    @pytest.mark.asyncio
    async def test_close_closes_session(self, gateway_config):
        """Test that close properly closes the session."""
        client = UpstreamProxyClient(gateway_config)

        session = await client._get_session()
        await client.close()

        assert session.closed

    @pytest.mark.asyncio
    async def test_forward_request_success(self, gateway_config):
        """Test successful request forwarding."""
        client = UpstreamProxyClient(gateway_config)

        # Mock the session
        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        client._session = mock_session

        response = await client.forward_request(
            method="GET",
            upstream_url="http://backend:8080/api/users",
            headers={"User-Agent": "test"},
            correlation_id="test-id",
        )

        assert response == mock_response
        mock_session.request.assert_called_once_with(
            method="GET",
            url="http://backend:8080/api/users",
            headers={"User-Agent": "test"},
            data=None,
            allow_redirects=False,
        )

    @pytest.mark.asyncio
    async def test_forward_request_with_body(self, gateway_config):
        """Test request forwarding with body."""
        client = UpstreamProxyClient(gateway_config)

        mock_response = AsyncMock()
        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        client._session = mock_session

        body = b'{"test": "data"}'
        await client.forward_request(
            method="POST",
            upstream_url="http://backend:8080/api/users",
            headers={"Content-Type": "application/json"},
            body=body,
            correlation_id="test-id",
        )

        mock_session.request.assert_called_once()
        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["data"] == body


class TestProxyMiddleware:
    """Tests for ProxyMiddleware."""

    @pytest.mark.asyncio
    async def test_process_success(self, gateway_config, request_context):
        """Test successful proxying."""
        middleware = ProxyMiddleware(gateway_config)

        # Mock the proxy client
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {
            "Content-Type": "application/json",
            "X-Custom-Header": "value",
        }
        mock_response.read = AsyncMock(return_value=b'{"result": "success"}')

        middleware.proxy_client.forward_request = AsyncMock(return_value=mock_response)

        # Mock request
        mock_request = AsyncMock()
        mock_request.query_string = "page=1"
        mock_request.can_read_body = False

        # Execute
        response = await middleware.process(mock_request, request_context, AsyncMock())

        # Verify response
        assert response.status == 200
        assert response.body == b'{"result": "success"}'

        # Verify forward_request was called correctly
        middleware.proxy_client.forward_request.assert_called_once()
        call_kwargs = middleware.proxy_client.forward_request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert "backend-service:8080" in call_kwargs["upstream_url"]
        assert call_kwargs["correlation_id"] == "test-correlation-id"

    @pytest.mark.asyncio
    async def test_process_with_request_body(self, gateway_config, request_context):
        """Test proxying with request body."""
        middleware = ProxyMiddleware(gateway_config)

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.headers = {}
        mock_response.read = AsyncMock(return_value=b'{"id": "123"}')

        middleware.proxy_client.forward_request = AsyncMock(return_value=mock_response)

        # Mock request with body
        mock_request = AsyncMock()
        mock_request.query_string = ""
        mock_request.can_read_body = True
        mock_request.read = AsyncMock(return_value=b'{"name": "test"}')

        request_context.method = "POST"

        response = await middleware.process(mock_request, request_context, AsyncMock())

        assert response.status == 201

        # Verify body was forwarded
        call_kwargs = middleware.proxy_client.forward_request.call_args.kwargs
        assert call_kwargs["body"] == b'{"name": "test"}'

    @pytest.mark.asyncio
    async def test_process_timeout_error(self, gateway_config, request_context):
        """Test handling of timeout error."""
        middleware = ProxyMiddleware(gateway_config)

        # Mock timeout error
        middleware.proxy_client.forward_request = AsyncMock(side_effect=asyncio.TimeoutError())

        mock_request = AsyncMock()
        mock_request.query_string = ""
        mock_request.can_read_body = False

        response = await middleware.process(mock_request, request_context, AsyncMock())

        # Should return 504 Gateway Timeout
        assert response.status == 504
        assert response.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_process_connection_error(self, gateway_config, request_context):
        """Test handling of connection error."""
        middleware = ProxyMiddleware(gateway_config)

        # Mock connection error
        middleware.proxy_client.forward_request = AsyncMock(
            side_effect=aiohttp.ClientConnectionError("Connection refused")
        )

        mock_request = AsyncMock()
        mock_request.query_string = ""
        mock_request.can_read_body = False

        response = await middleware.process(mock_request, request_context, AsyncMock())

        # Should return 502 Bad Gateway
        assert response.status == 502
        assert response.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_process_client_error(self, gateway_config, request_context):
        """Test handling of generic client error."""
        middleware = ProxyMiddleware(gateway_config)

        # Mock client error
        middleware.proxy_client.forward_request = AsyncMock(
            side_effect=aiohttp.ClientError("Generic error")
        )

        mock_request = AsyncMock()
        mock_request.query_string = ""
        mock_request.can_read_body = False

        response = await middleware.process(mock_request, request_context, AsyncMock())

        # Should return 502 Bad Gateway
        assert response.status == 502

    @pytest.mark.asyncio
    async def test_process_unexpected_error(self, gateway_config, request_context):
        """Test handling of unexpected error."""
        middleware = ProxyMiddleware(gateway_config)

        # Mock unexpected error
        middleware.proxy_client.forward_request = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        mock_request = AsyncMock()
        mock_request.query_string = ""
        mock_request.can_read_body = False

        response = await middleware.process(mock_request, request_context, AsyncMock())

        # Should return 500 Internal Server Error
        assert response.status == 500

    @pytest.mark.asyncio
    async def test_process_no_route_match(self, gateway_config):
        """Test error when no route match is present."""
        middleware = ProxyMiddleware(gateway_config)

        # Create context without route match
        context = RequestContext(
            method="GET",
            path="/api/users",
            query_params={},
            headers={},
            client_ip="192.168.1.100",
            user_agent="test",
            correlation_id="test-id",
        )

        mock_request = AsyncMock()

        response = await middleware.process(mock_request, context, AsyncMock())

        # Should return 500 error
        assert response.status == 500

    def test_prepare_response_headers(self, gateway_config, request_context):
        """Test response header preparation."""
        middleware = ProxyMiddleware(gateway_config)

        upstream_headers = {
            "Content-Type": "application/json",
            "X-Custom-Header": "value",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        }

        request_context.rate_limit_remaining = 95
        request_context.rate_limit_reset = 1234567890

        headers = middleware._prepare_response_headers(upstream_headers, request_context)

        # Should copy allowed headers
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Custom-Header"] == "value"

        # Should skip connection headers
        assert "Connection" not in headers
        assert "Transfer-Encoding" not in headers

        # Should add rate limit headers
        assert headers["X-RateLimit-Remaining"] == "95"
        assert headers["X-RateLimit-Reset"] == "1234567890"

        # Should add correlation ID
        assert headers["X-Request-ID"] == "test-correlation-id"

    def test_prepare_response_headers_without_rate_limit(self, gateway_config, request_context):
        """Test response header preparation without rate limit info."""
        middleware = ProxyMiddleware(gateway_config)

        upstream_headers = {"Content-Type": "text/plain"}

        headers = middleware._prepare_response_headers(upstream_headers, request_context)

        # Should not add rate limit headers if not available
        assert "X-RateLimit-Remaining" not in headers
        assert "X-RateLimit-Reset" not in headers

    @pytest.mark.asyncio
    async def test_close(self, gateway_config):
        """Test middleware cleanup."""
        middleware = ProxyMiddleware(gateway_config)

        # Create a session
        await middleware.proxy_client._get_session()

        # Close
        await middleware.close()

        # Session should be closed
        assert middleware.proxy_client._session.closed
