"""Request handler for the API Gateway.

This module integrates the routing engine and middleware chain
to handle incoming HTTP requests.
"""

import logging
from datetime import datetime

from aiohttp import web

from gateway.core.config import GatewayConfig
from gateway.core.middleware import MiddlewareChain, create_request_context
from gateway.core.routing import Router

logger = logging.getLogger(__name__)


class RequestHandler:
    """Main request handler for the API Gateway.

    Coordinates:
    - Request context creation
    - Route matching
    - Middleware chain execution
    - Error responses (404, 405, etc.)
    """

    def __init__(self, router: Router, middleware_chain: MiddlewareChain, config: GatewayConfig):
        """Initialize the request handler.

        Args:
            router: Router instance
            middleware_chain: Middleware chain instance
            config: Gateway configuration
        """
        self.router = router
        self.middleware_chain = middleware_chain
        self.config = config

    async def handle_request(self, request: web.Request) -> web.Response:
        """Handle an incoming HTTP request.

        Args:
            request: aiohttp Request object

        Returns:
            web.Response object
        """
        # Create request context
        context = create_request_context(request)

        # Add correlation ID to response headers
        headers = {self.config.logging.correlation_id_header: context.correlation_id}

        # Try to match route
        route_match = self.router.match_route(context.path, context.method)

        if route_match is None:
            # No route matched - check if path exists with different method
            allowed_methods = self.router.get_allowed_methods(context.path)

            if allowed_methods:
                # Path exists but method not allowed - return 405
                return web.json_response(
                    {
                        "error": "method_not_allowed",
                        "message": f"Method {context.method} not allowed for this path",
                        "correlation_id": context.correlation_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                    status=405,
                    headers={**headers, "Allow": ", ".join(allowed_methods)},
                )
            else:
                # No route found - return 404
                return web.json_response(
                    {
                        "error": "not_found",
                        "message": "The requested resource was not found",
                        "correlation_id": context.correlation_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                    status=404,
                    headers=headers,
                )

        # Attach route match to context
        context.route_match = route_match

        logger.debug(
            f"Handling request: {context.method} {context.path}",
            extra={
                "correlation_id": context.correlation_id,
                "route_id": route_match.route.id,
                "path_params": route_match.path_params,
            },
        )

        # Execute middleware chain
        try:
            response = await self.middleware_chain.execute(request, context)

            # Add correlation ID to response headers if not already present
            if self.config.logging.correlation_id_header not in response.headers:
                response.headers[self.config.logging.correlation_id_header] = context.correlation_id

            return response

        except web.HTTPException as e:
            # HTTP exceptions are already proper responses
            # Add correlation ID and re-raise
            e.headers[self.config.logging.correlation_id_header] = context.correlation_id
            raise

        except Exception as e:
            # Unexpected error - return 500
            logger.exception(
                f"Unexpected error handling request: {e}",
                extra={"correlation_id": context.correlation_id},
            )

            return web.json_response(
                {
                    "error": "internal_error",
                    "message": "An unexpected error occurred",
                    "correlation_id": context.correlation_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                status=500,
                headers=headers,
            )


from collections.abc import Awaitable, Callable


def create_handler_middleware(
    router: Router, middleware_chain: MiddlewareChain, config: GatewayConfig
) -> Callable[
    [web.Request, Callable[[web.Request], Awaitable[web.Response]]], Awaitable[web.Response]
]:
    """Create an aiohttp middleware that uses our request handler.

    Args:
        router: Router instance
        middleware_chain: Middleware chain instance
        config: Gateway configuration

    Returns:
        aiohttp middleware function
    """
    handler = RequestHandler(router, middleware_chain, config)

    @web.middleware
    async def middleware(
        request: web.Request, handler_func: Callable[[web.Request], Awaitable[web.Response]]
    ) -> web.Response:
        """aiohttp middleware function.

        Args:
            request: aiohttp Request object
            handler_func: Next handler (ignored, we use our own chain)

        Returns:
            web.Response object
        """
        return await handler.handle_request(request)

    return middleware
