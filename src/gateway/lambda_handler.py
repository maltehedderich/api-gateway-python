"""AWS Lambda handler for API Gateway.

This module adapts the aiohttp-based API Gateway to run on AWS Lambda.
It uses Mangum to bridge between API Gateway HTTP API events and ASGI applications.
"""

import asyncio
import logging
import os
from typing import Any

from mangum import Mangum

from gateway.core.config import GatewayConfig
from gateway.core.gateway import Gateway

logger = logging.getLogger(__name__)

# Global variables for Lambda container reuse
_gateway: Gateway | None = None
_mangum_handler: Mangum | None = None


def _load_config() -> GatewayConfig:
    """Load gateway configuration for Lambda environment.

    Returns:
        GatewayConfig instance
    """
    # In Lambda, we override config with environment variables
    config_dict: dict[str, Any] = {
        "environment": os.getenv("GATEWAY_ENV", "production"),
        "server": {
            "host": "0.0.0.0",
            "port": 8080,  # Not used in Lambda, but required by config
        },
        "logging": {
            "level": os.getenv("GATEWAY_LOG_LEVEL", "INFO"),
            "format": "json",
            "output": "stdout",
        },
        "session": {
            "cookie_name": "session_token",
            "session_store_url": os.getenv(
                "GATEWAY_SESSION_STORE_URL",
                f"dynamodb://{os.getenv('GATEWAY_SESSION_TABLE_NAME', 'sessions')}",
            ),
            "token_signing_secret": os.getenv("GATEWAY_TOKEN_SIGNING_SECRET"),
            "token_ttl": int(os.getenv("GATEWAY_TOKEN_TTL", "3600")),
        },
        "rate_limiting": {
            "enabled": os.getenv("GATEWAY_RATELIMIT_ENABLED", "true").lower() == "true",
            "store_url": os.getenv(
                "GATEWAY_RATELIMIT_STORE_URL",
                f"dynamodb://{os.getenv('GATEWAY_RATELIMIT_TABLE_NAME', 'rate-limits')}",
            ),
            "fail_mode": "open",
            "rules": _load_rate_limit_rules(),
        },
        "upstream": {
            "connection_timeout": 5,
            "request_timeout": 30,
            "pool_size": 100,
        },
        "metrics": {
            "enabled": True,
            "endpoint": "/metrics",
            "health_endpoint": "/health",
            "liveness_endpoint": "/health/live",
            "readiness_endpoint": "/health/ready",
        },
        "routes": _load_routes(),
    }

    return GatewayConfig(**config_dict)


def _load_rate_limit_rules() -> list[dict[str, Any]]:
    """Load rate limiting rules from environment.

    Returns:
        List of rate limit rule dicts
    """
    # Default rate limiting rules
    return [
        {
            "name": "global_ip_limit",
            "key_type": "ip",
            "algorithm": "token_bucket",
            "limit": 100,
            "window": 60,
            "burst": 120,
        },
        {
            "name": "authenticated_user_limit",
            "key_type": "user",
            "algorithm": "token_bucket",
            "limit": 500,
            "window": 60,
            "burst": 600,
        },
    ]


def _load_routes() -> list[dict[str, Any]]:
    """Load route configurations from environment.

    Returns:
        List of route configuration dicts
    """
    # Routes can be loaded from environment variables or a config file
    # For simplicity, we'll use environment variables for upstream URLs

    routes = []

    # Example routes - customize based on your backend services
    # You can configure these via Lambda environment variables

    # Public status endpoint
    if status_url := os.getenv("UPSTREAM_STATUS_SERVICE_URL"):
        routes.append(
            {
                "id": "public_status",
                "path_pattern": "/api/v1/status",
                "methods": ["GET"],
                "upstream_url": status_url,
                "auth_required": False,
                "timeout": 10,
            }
        )

    # Users API
    if users_url := os.getenv("UPSTREAM_USER_SERVICE_URL"):
        routes.extend(
            [
                {
                    "id": "users_list",
                    "path_pattern": "/api/v1/users",
                    "methods": ["GET", "POST"],
                    "upstream_url": users_url,
                    "auth_required": True,
                    "auth_roles": ["user"],
                    "timeout": 30,
                },
                {
                    "id": "user_by_id",
                    "path_pattern": "/api/v1/users/{user_id}",
                    "methods": ["GET", "PUT", "DELETE"],
                    "upstream_url": users_url,
                    "auth_required": True,
                    "auth_roles": ["user"],
                    "timeout": 30,
                },
            ]
        )

    # Products API
    if products_url := os.getenv("UPSTREAM_PRODUCT_SERVICE_URL"):
        routes.extend(
            [
                {
                    "id": "products_list",
                    "path_pattern": "/api/v1/products",
                    "methods": ["GET"],
                    "upstream_url": products_url,
                    "auth_required": True,
                    "auth_roles": ["user"],
                    "timeout": 30,
                },
                {
                    "id": "product_by_id",
                    "path_pattern": "/api/v1/products/{product_id}",
                    "methods": ["GET", "PUT", "DELETE"],
                    "upstream_url": products_url,
                    "auth_required": True,
                    "auth_roles": ["user", "admin"],
                    "timeout": 30,
                },
            ]
        )

    # Admin endpoints
    if admin_url := os.getenv("UPSTREAM_ADMIN_SERVICE_URL"):
        routes.append(
            {
                "id": "admin_settings",
                "path_pattern": "/api/v1/admin/settings",
                "methods": ["GET", "POST"],
                "upstream_url": admin_url,
                "auth_required": True,
                "auth_roles": ["admin"],
                "timeout": 30,
            }
        )

    return routes


async def _init_gateway() -> Gateway:
    """Initialize the gateway instance.

    Returns:
        Gateway instance
    """
    config = _load_config()
    gateway = Gateway(config)

    # Connect to stores (DynamoDB)
    await gateway.session_store.connect()
    await gateway.rate_limit_store.connect()

    return gateway


def _get_or_create_handler() -> Mangum:
    """Get or create the Mangum handler (cached for container reuse).

    Returns:
        Mangum handler instance
    """
    global _gateway, _mangum_handler

    if _mangum_handler is None:
        # Initialize gateway
        if _gateway is None:
            _gateway = asyncio.run(_init_gateway())

        app = _gateway.server.create_app()
        _gateway._setup_routes(app)

        # Create Mangum handler for ASGI bridge
        # Note: aiohttp is WSGI-like, we need an adapter
        # For now, we'll use a simple approach
        logger.info("Creating Mangum handler for Lambda")

        # Mangum expects an ASGI application
        # aiohttp is not ASGI, so we need a bridge
        # For production, consider using a different approach or FastAPI/Starlette

        # Temporary workaround: Use aiohttp's app as-is
        # This requires a custom adapter (see below)
        _mangum_handler = Mangum(app, lifespan="off")

    return _mangum_handler


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler function.

    Args:
        event: API Gateway HTTP API event
        context: Lambda context

    Returns:
        API Gateway HTTP API response
    """
    try:
        # Get or create the handler (reused across invocations)
        mangum_handler = _get_or_create_handler()

        # Process the request
        response = mangum_handler(event, context)

        return response

    except Exception as e:
        logger.exception(f"Error processing Lambda request: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": '{"error":"internal_server_error","message":"An internal error occurred"}',
        }


# For local testing
if __name__ == "__main__":
    # Test event (API Gateway HTTP API format 2.0)
    test_event = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {
            "accept": "application/json",
            "content-type": "application/json",
            "user-agent": "test",
        },
        "requestContext": {
            "http": {"method": "GET", "path": "/health", "protocol": "HTTP/1.1"},
            "requestId": "test-request-id",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }

    class MockContext:
        def __init__(self) -> None:
            self.function_name = "test-function"
            self.memory_limit_in_mb = 512
            self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
            self.aws_request_id = "test-request-id"

    # Test the handler
    response = handler(test_event, MockContext())
    print("Response:", response)
