"""Routing engine for the API Gateway.

This module implements the routing engine including:
- Route pattern matching (exact, prefix, parameterized paths)
- HTTP method validation
- Route priority and conflict resolution
- Path parameter extraction
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from aiohttp import web

from gateway.core.config import RouteConfig

logger = logging.getLogger(__name__)


@dataclass
class RouteMatch:
    """Represents a matched route with extracted parameters."""

    route: RouteConfig
    path_params: Dict[str, str]


class PathMatcher:
    """Matches URL paths against route patterns.

    Supports:
    - Exact matches: /users
    - Prefix matches: /api/*
    - Parameter extraction: /users/{user_id}
    """

    def __init__(self, pattern: str):
        """Initialize path matcher.

        Args:
            pattern: Path pattern (e.g., /users/{user_id})
        """
        self.pattern = pattern
        self.regex_pattern, self.param_names = self._compile_pattern(pattern)

    def _compile_pattern(self, pattern: str) -> Tuple[re.Pattern, List[str]]:
        """Compile path pattern into regex.

        Args:
            pattern: Path pattern with parameters in {param} format

        Returns:
            Tuple of (compiled regex pattern, list of parameter names)
        """
        param_names = []
        regex_parts = []

        # Split pattern into parts
        parts = pattern.split("/")

        for part in parts:
            if not part:
                # Empty part (leading/trailing slash)
                continue

            # Check if this part is a parameter
            param_match = re.match(r"^\{(\w+)\}$", part)
            if param_match:
                param_name = param_match.group(1)
                param_names.append(param_name)
                # Match any non-slash characters
                regex_parts.append(r"([^/]+)")
            else:
                # Literal part - escape special regex characters
                regex_parts.append(re.escape(part))

        # Build final regex pattern
        regex_str = "^/" + "/".join(regex_parts) + "$"
        regex = re.compile(regex_str)

        return regex, param_names

    def match(self, path: str) -> Optional[Dict[str, str]]:
        """Match a path against this pattern.

        Args:
            path: URL path to match

        Returns:
            Dictionary of extracted parameters if matched, None otherwise
        """
        match = self.regex_pattern.match(path)
        if not match:
            return None

        # Extract parameter values
        params = {}
        for i, param_name in enumerate(self.param_names):
            params[param_name] = match.group(i + 1)

        return params


class Router:
    """Routes incoming requests to configured route handlers.

    Responsibilities:
    - Matching request paths to route configurations
    - Validating HTTP methods
    - Extracting path parameters
    - Resolving route conflicts based on priority
    """

    def __init__(self, routes: List[RouteConfig]):
        """Initialize the router.

        Args:
            routes: List of route configurations
        """
        self.routes = routes
        self._route_matchers: List[Tuple[RouteConfig, PathMatcher]] = []
        self._initialize_routes()

    def _initialize_routes(self) -> None:
        """Initialize route matchers and sort by priority.

        Routes are sorted to ensure more specific patterns match first:
        1. Exact matches (no parameters)
        2. Patterns with parameters
        3. Prefix matches

        Within each category, longer patterns take precedence.
        """
        # Create matchers for all routes
        route_matchers = []
        for route in self.routes:
            matcher = PathMatcher(route.path_pattern)
            route_matchers.append((route, matcher))

        # Sort by priority:
        # 1. Number of literal segments (more is higher priority)
        # 2. Total length (longer is higher priority)
        def route_priority(item: Tuple[RouteConfig, PathMatcher]) -> Tuple[int, int]:
            route, matcher = item
            pattern = route.path_pattern

            # Count literal (non-parameter) segments
            literal_segments = len([p for p in pattern.split("/") if p and not p.startswith("{")])

            # Use negative values so higher priority routes come first
            return (-literal_segments, -len(pattern))

        self._route_matchers = sorted(route_matchers, key=route_priority)

        logger.info(
            f"Initialized router with {len(self.routes)} routes",
            extra={"route_count": len(self.routes)},
        )

    def match_route(self, path: str, method: str) -> Optional[RouteMatch]:
        """Match a request to a route configuration.

        Args:
            path: Request path
            method: HTTP method

        Returns:
            RouteMatch if a matching route is found, None otherwise
        """
        # Normalize path
        normalized_path = self._normalize_path(path)

        # Try to match against each route in priority order
        for route, matcher in self._route_matchers:
            path_params = matcher.match(normalized_path)

            if path_params is not None:
                # Path matched, now check HTTP method
                if method.upper() in [m.upper() for m in route.methods]:
                    logger.debug(
                        f"Route matched: {route.id}",
                        extra={
                            "route_id": route.id,
                            "path": normalized_path,
                            "method": method,
                            "params": path_params,
                        },
                    )
                    return RouteMatch(route=route, path_params=path_params)

        logger.debug(
            f"No route matched for {method} {path}",
            extra={"path": path, "method": method},
        )
        return None

    def _normalize_path(self, path: str) -> str:
        """Normalize URL path.

        - Remove trailing slashes (except for root /)
        - Handle percent-encoding
        - Ensure leading slash

        Args:
            path: Raw URL path

        Returns:
            Normalized path
        """
        # Ensure leading slash
        if not path.startswith("/"):
            path = "/" + path

        # Remove trailing slash (except for root)
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        return path

    def get_allowed_methods(self, path: str) -> List[str]:
        """Get allowed HTTP methods for a path.

        Used to generate the Allow header for 405 responses.

        Args:
            path: Request path

        Returns:
            List of allowed HTTP methods
        """
        normalized_path = self._normalize_path(path)
        allowed_methods = set()

        for route, matcher in self._route_matchers:
            path_params = matcher.match(normalized_path)
            if path_params is not None:
                allowed_methods.update(route.methods)

        return sorted(allowed_methods)


def create_router(routes: List[RouteConfig]) -> Router:
    """Create a router instance (convenience function).

    Args:
        routes: List of route configurations

    Returns:
        Configured Router instance
    """
    return Router(routes)
