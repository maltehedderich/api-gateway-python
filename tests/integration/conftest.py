"""Shared fixtures for integration tests."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.core.config import GatewayConfig, RateLimitRule, RouteConfig
from gateway.core.gateway import Gateway
from gateway.core.session_store import InMemorySessionStore, SessionData


@pytest.fixture
def mock_upstream_app() -> web.Application:
    """Create a mock upstream service for testing."""
    app = web.Application()

    async def hello_handler(request: web.Request) -> web.Response:
        """Simple GET endpoint."""
        return web.json_response({"message": "Hello from upstream", "path": request.path})

    async def echo_handler(request: web.Request) -> web.Response:
        """Echo back request data."""
        data = await request.json() if request.can_read_body else {}
        return web.json_response(
            {
                "method": request.method,
                "path": request.path,
                "headers": dict(request.headers),
                "data": data,
            }
        )

    async def slow_handler(request: web.Request) -> web.Response:
        """Slow endpoint for timeout testing."""
        await asyncio.sleep(2)
        return web.json_response({"message": "Slow response"})

    async def error_handler(request: web.Request) -> web.Response:
        """Endpoint that returns error."""
        return web.json_response(
            {"error": "server_error", "message": "Internal server error"}, status=500
        )

    async def users_handler(request: web.Request) -> web.Response:
        """Mock users endpoint."""
        user_id = request.match_info.get("user_id", "unknown")
        return web.json_response({"user_id": user_id, "username": f"user_{user_id}"})

    # Register routes
    app.router.add_get("/api/hello", hello_handler)
    app.router.add_post("/api/echo", echo_handler)
    app.router.add_get("/api/slow", slow_handler)
    app.router.add_get("/api/error", error_handler)
    app.router.add_get("/api/users/{user_id}", users_handler)
    app.router.add_route("*", "/api/echo", echo_handler)

    return app


@pytest.fixture
async def mock_upstream_server(
    mock_upstream_app: web.Application,
) -> AsyncGenerator[TestServer, None]:
    """Create and start a test server for the mock upstream service."""
    server = TestServer(mock_upstream_app, port=8888)
    await server.start_server()
    yield server
    await server.close()


@pytest.fixture
def integration_config(mock_upstream_server: TestServer) -> GatewayConfig:
    """Create gateway configuration for integration tests."""
    config = GatewayConfig()

    # Use in-memory stores for testing
    config.session.session_store_url = "memory"
    config.rate_limiting.store_url = "memory"

    # Configure routes
    config.routes = [
        RouteConfig(
            id="public_route",
            path_pattern="/api/hello",
            methods=["GET"],
            upstream_url="http://localhost:8888",
            auth_required=False,
            auth_roles=[],
            timeout=30,
        ),
        RouteConfig(
            id="protected_route",
            path_pattern="/api/users/{user_id}",
            methods=["GET"],
            upstream_url="http://localhost:8888",
            auth_required=True,
            auth_roles=["user"],
            timeout=30,
        ),
        RouteConfig(
            id="admin_route",
            path_pattern="/api/admin",
            methods=["GET"],
            upstream_url="http://localhost:8888",
            auth_required=True,
            auth_roles=["admin"],
            timeout=30,
        ),
        RouteConfig(
            id="echo_route",
            path_pattern="/api/echo",
            methods=["GET", "POST", "PUT", "DELETE"],
            upstream_url="http://localhost:8888",
            auth_required=False,
            auth_roles=[],
            timeout=30,
        ),
        RouteConfig(
            id="slow_route",
            path_pattern="/api/slow",
            methods=["GET"],
            upstream_url="http://localhost:8888",
            auth_required=False,
            auth_roles=[],
            timeout=1,  # Short timeout for testing
        ),
        RouteConfig(
            id="error_route",
            path_pattern="/api/error",
            methods=["GET"],
            upstream_url="http://localhost:8888",
            auth_required=False,
            auth_roles=[],
            timeout=30,
        ),
    ]

    # Configure rate limiting
    config.rate_limiting.enabled = True
    config.rate_limiting.fail_mode = "open"
    config.rate_limiting.rules = [
        RateLimitRule(
            name="global",
            key_type="ip",
            algorithm="fixed_window",
            limit=100,
            window=60,
        ),
        RateLimitRule(
            name="user_limit",
            key_type="user",
            algorithm="token_bucket",
            limit=10,
            window=60,
            burst=15,
        ),
    ]

    return config


@pytest.fixture
async def session_store() -> AsyncGenerator[InMemorySessionStore, None]:
    """Create and initialize a session store for testing."""
    store = InMemorySessionStore()
    await store.connect()
    yield store
    await store.disconnect()


@pytest.fixture
async def test_session(gateway: Gateway) -> SessionData:
    """Create a test session."""
    now = datetime.now(UTC)
    session = SessionData(
        session_id="test-session-123",
        user_id="user-123",
        username="testuser",
        created_at=now,
        last_accessed_at=now,
        expires_at=now + timedelta(hours=1),
        roles=["user"],
        permissions=["read:data", "write:data"],
    )
    await gateway.session_store.create(session)
    return session


@pytest.fixture
async def admin_session(gateway: Gateway) -> SessionData:
    """Create an admin test session."""
    now = datetime.now(UTC)
    session = SessionData(
        session_id="admin-session-456",
        user_id="admin-456",
        username="adminuser",
        created_at=now,
        last_accessed_at=now,
        expires_at=now + timedelta(hours=1),
        roles=["user", "admin"],
        permissions=["read:data", "write:data", "admin:all"],
    )
    await gateway.session_store.create(session)
    return session


@pytest.fixture
async def gateway(
    integration_config: GatewayConfig,
) -> AsyncGenerator[Gateway, None]:
    """Create and initialize an API Gateway instance for testing."""
    gw = Gateway(integration_config)
    await gw.start()
    yield gw
    await gw.stop()


@pytest.fixture
async def gateway_client(gateway: Gateway) -> AsyncGenerator[TestClient, None]:
    """Create a test client for the gateway."""
    # Gateway.start() creates the app, so we access it via server.app
    if gateway.server.app is None:
        raise RuntimeError("Gateway app not initialized")
    server = TestServer(gateway.server.app, port=9999)
    await server.start_server()
    client = TestClient(server)
    yield client
    await client.close()
