"""Unit tests for the routing engine."""

from gateway.core.config import RouteConfig
from gateway.core.routing import PathMatcher, Router


class TestPathMatcher:
    """Tests for PathMatcher class."""

    def test_exact_match(self):
        """Test exact path matching."""
        matcher = PathMatcher("/api/users")

        # Should match
        result = matcher.match("/api/users")
        assert result is not None
        assert result == {}

        # Should not match
        assert matcher.match("/api/products") is None
        assert matcher.match("/api/users/123") is None

    def test_parameter_extraction(self):
        """Test path parameter extraction."""
        matcher = PathMatcher("/api/users/{user_id}")

        # Should match and extract parameter
        result = matcher.match("/api/users/123")
        assert result is not None
        assert result == {"user_id": "123"}

        # Should match different ID
        result = matcher.match("/api/users/abc-def")
        assert result is not None
        assert result == {"user_id": "abc-def"}

        # Should not match
        assert matcher.match("/api/users") is None
        assert matcher.match("/api/users/123/posts") is None

    def test_multiple_parameters(self):
        """Test extraction of multiple path parameters."""
        matcher = PathMatcher("/api/users/{user_id}/posts/{post_id}")

        result = matcher.match("/api/users/123/posts/456")
        assert result is not None
        assert result == {"user_id": "123", "post_id": "456"}

        # Should not match partial paths
        assert matcher.match("/api/users/123") is None
        assert matcher.match("/api/users/123/posts") is None

    def test_trailing_slash_normalization(self):
        """Test that trailing slashes are handled correctly."""
        matcher = PathMatcher("/api/users")

        # Both should match after normalization
        assert matcher.match("/api/users") is not None
        assert matcher.match("/api/users/") is None  # Matcher doesn't normalize


class TestRouter:
    """Tests for Router class."""

    def create_test_routes(self):
        """Create test route configurations."""
        return [
            RouteConfig(
                id="users_list",
                path_pattern="/api/users",
                methods=["GET", "POST"],
                upstream_url="http://localhost:8081",
                auth_required=True,
                timeout=30,
            ),
            RouteConfig(
                id="user_by_id",
                path_pattern="/api/users/{user_id}",
                methods=["GET", "PUT", "DELETE"],
                upstream_url="http://localhost:8081",
                auth_required=True,
                timeout=30,
            ),
            RouteConfig(
                id="products_list",
                path_pattern="/api/products",
                methods=["GET"],
                upstream_url="http://localhost:8082",
                auth_required=True,
                timeout=30,
            ),
            RouteConfig(
                id="product_by_id",
                path_pattern="/api/products/{product_id}",
                methods=["GET", "PUT"],
                upstream_url="http://localhost:8082",
                auth_required=True,
                timeout=30,
            ),
        ]

    def test_exact_route_match(self):
        """Test exact route matching."""
        router = Router(self.create_test_routes())

        match = router.match_route("/api/users", "GET")
        assert match is not None
        assert match.route.id == "users_list"
        assert match.path_params == {}

    def test_parameterized_route_match(self):
        """Test parameterized route matching."""
        router = Router(self.create_test_routes())

        match = router.match_route("/api/users/123", "GET")
        assert match is not None
        assert match.route.id == "user_by_id"
        assert match.path_params == {"user_id": "123"}

    def test_method_validation(self):
        """Test HTTP method validation."""
        router = Router(self.create_test_routes())

        # Valid method
        match = router.match_route("/api/users", "GET")
        assert match is not None

        # Invalid method
        match = router.match_route("/api/users", "DELETE")
        assert match is None

    def test_route_priority(self):
        """Test that more specific routes take precedence."""
        routes = [
            RouteConfig(
                id="generic",
                path_pattern="/api/{resource}",
                methods=["GET"],
                upstream_url="http://localhost:8080",
                auth_required=False,
                timeout=30,
            ),
            RouteConfig(
                id="specific",
                path_pattern="/api/users",
                methods=["GET"],
                upstream_url="http://localhost:8081",
                auth_required=False,
                timeout=30,
            ),
        ]

        router = Router(routes)

        # More specific route should match
        match = router.match_route("/api/users", "GET")
        assert match is not None
        assert match.route.id == "specific"

    def test_no_route_match(self):
        """Test when no route matches."""
        router = Router(self.create_test_routes())

        match = router.match_route("/api/unknown", "GET")
        assert match is None

    def test_get_allowed_methods(self):
        """Test getting allowed methods for a path."""
        router = Router(self.create_test_routes())

        # Path with multiple methods
        methods = router.get_allowed_methods("/api/users")
        assert set(methods) == {"GET", "POST"}

        # Path with different methods
        methods = router.get_allowed_methods("/api/users/123")
        assert set(methods) == {"DELETE", "GET", "PUT"}

        # Non-existent path
        methods = router.get_allowed_methods("/api/unknown")
        assert methods == []

    def test_path_normalization(self):
        """Test path normalization."""
        router = Router(self.create_test_routes())

        # Trailing slash should be removed
        match = router.match_route("/api/users/", "GET")
        assert match is not None
        assert match.route.id == "users_list"

        # Missing leading slash should be added
        match = router.match_route("api/users", "GET")
        assert match is not None
        assert match.route.id == "users_list"

    def test_case_sensitive_method_matching(self):
        """Test that HTTP methods are matched case-insensitively."""
        router = Router(self.create_test_routes())

        # Lowercase method
        match = router.match_route("/api/users", "get")
        assert match is not None

        # Uppercase method
        match = router.match_route("/api/users", "GET")
        assert match is not None

        # Mixed case
        match = router.match_route("/api/users", "Get")
        assert match is not None
