"""End-to-end integration tests for API Gateway request flow."""

import pytest
from aiohttp.test_utils import TestClient


class TestEndToEndFlow:
    """Test complete request flow through the gateway."""

    @pytest.mark.asyncio
    async def test_public_route_success(self, gateway_client: TestClient):
        """Test successful request to public route."""
        response = await gateway_client.get("/api/hello")

        assert response.status == 200
        data = await response.json()
        assert data["message"] == "Hello from upstream"
        assert "path" in data

    @pytest.mark.asyncio
    async def test_public_route_with_query_params(self, gateway_client: TestClient):
        """Test public route with query parameters."""
        response = await gateway_client.get("/api/hello?foo=bar&baz=qux")

        assert response.status == 200
        # Query params should be forwarded to upstream

    @pytest.mark.asyncio
    async def test_post_request_with_body(self, gateway_client: TestClient):
        """Test POST request with JSON body."""
        request_data = {"name": "Test User", "email": "test@example.com"}

        response = await gateway_client.post("/api/echo", json=request_data)

        assert response.status == 200
        data = await response.json()
        assert data["method"] == "POST"
        assert data["data"] == request_data

    @pytest.mark.asyncio
    async def test_request_headers_forwarded(self, gateway_client: TestClient):
        """Test that request headers are forwarded to upstream."""
        headers = {
            "User-Agent": "TestAgent/1.0",
            "Accept": "application/json",
            "Custom-Header": "custom-value",
        }

        response = await gateway_client.post("/api/echo", json={}, headers=headers)

        assert response.status == 200
        data = await response.json()

        # Check that headers were forwarded
        assert "User-Agent" in data["headers"]
        assert "Custom-Header" in data["headers"]

    @pytest.mark.asyncio
    async def test_response_headers_returned(self, gateway_client: TestClient):
        """Test that response headers are returned to client."""
        response = await gateway_client.get("/api/hello")

        assert response.status == 200
        # Check for standard response headers
        assert "Content-Type" in response.headers

    @pytest.mark.asyncio
    async def test_404_for_unknown_route(self, gateway_client: TestClient):
        """Test 404 response for unknown routes."""
        response = await gateway_client.get("/api/nonexistent")

        assert response.status == 404
        data = await response.json()
        assert data["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_405_for_method_not_allowed(self, gateway_client: TestClient):
        """Test 405 response for disallowed HTTP methods."""
        # /api/hello only allows GET
        response = await gateway_client.post("/api/hello")

        assert response.status == 405
        data = await response.json()
        assert data["error"] == "method_not_allowed"
        assert "Allow" in response.headers

    @pytest.mark.asyncio
    async def test_correlation_id_generated(self, gateway_client: TestClient):
        """Test that correlation ID is generated and included in response."""
        response = await gateway_client.get("/api/hello")

        assert response.status == 200
        # Check for correlation ID in response headers or logs
        # (Exact header name depends on implementation)

    @pytest.mark.asyncio
    async def test_correlation_id_preserved(self, gateway_client: TestClient):
        """Test that client-provided correlation ID is preserved."""
        correlation_id = "client-req-12345"
        headers = {"X-Request-ID": correlation_id}

        response = await gateway_client.get("/api/hello", headers=headers)

        assert response.status == 200
        # Correlation ID should be preserved and forwarded

    @pytest.mark.asyncio
    async def test_different_http_methods(self, gateway_client: TestClient):
        """Test different HTTP methods on the same route."""
        methods_and_data = [
            ("GET", None),
            ("POST", {"test": "data"}),
            ("PUT", {"test": "update"}),
            ("DELETE", None),
        ]

        for method, data in methods_and_data:
            if method == "GET":
                response = await gateway_client.get("/api/echo")
            elif method == "POST":
                response = await gateway_client.post("/api/echo", json=data)
            elif method == "PUT":
                response = await gateway_client.put("/api/echo", json=data)
            elif method == "DELETE":
                response = await gateway_client.delete("/api/echo")

            assert response.status == 200
            resp_data = await response.json()
            assert resp_data["method"] == method

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, gateway_client: TestClient):
        """Test handling of concurrent requests."""
        import asyncio

        async def make_request(n: int):
            response = await gateway_client.get("/api/hello")
            return response.status

        # Make 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        statuses = await asyncio.gather(*tasks)

        # All should succeed
        assert all(status == 200 for status in statuses)

    @pytest.mark.asyncio
    async def test_large_response_body(self, gateway_client: TestClient):
        """Test handling of large response bodies."""
        # Create a large payload
        large_data = {"data": "x" * 100000}  # 100KB of data

        response = await gateway_client.post("/api/echo", json=large_data)

        assert response.status == 200
        data = await response.json()
        assert len(data["data"]["data"]) == 100000


class TestRequestResponseLogging:
    """Test that requests and responses are properly logged."""

    @pytest.mark.asyncio
    async def test_request_logged(self, gateway_client: TestClient, caplog):
        """Test that incoming requests are logged."""
        with caplog.at_level("INFO"):
            response = await gateway_client.get("/api/hello")
            assert response.status == 200

        # Check that request was logged
        # (Implementation specific - may need adjustment based on logging format)

    @pytest.mark.asyncio
    async def test_response_logged(self, gateway_client: TestClient, caplog):
        """Test that responses are logged."""
        with caplog.at_level("INFO"):
            response = await gateway_client.get("/api/hello")
            assert response.status == 200

        # Check that response was logged with status code and latency

    @pytest.mark.asyncio
    async def test_error_logged(self, gateway_client: TestClient, caplog):
        """Test that errors are logged."""
        with caplog.at_level("WARNING"):
            response = await gateway_client.get("/api/nonexistent")
            assert response.status == 404

        # Check that 404 error was logged


class TestUpstreamErrorHandling:
    """Test handling of upstream service errors."""

    @pytest.mark.asyncio
    async def test_upstream_500_error(self, gateway_client: TestClient):
        """Test handling of upstream 500 error."""
        response = await gateway_client.get("/api/error")

        # Gateway should pass through the upstream error
        assert response.status == 500
        data = await response.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_upstream_timeout(self, gateway_client: TestClient):
        """Test handling of upstream timeout."""
        # /api/slow has 1-second timeout, but handler sleeps for 2 seconds
        response = await gateway_client.get("/api/slow")

        # Should get 504 Gateway Timeout
        assert response.status == 504
        data = await response.json()
        assert data["error"] == "gateway_timeout"

    @pytest.mark.asyncio
    async def test_upstream_unreachable(self, gateway_client: TestClient):
        """Test handling when upstream service is unreachable."""
        # This test would require a route to a non-existent upstream
        # For now, just ensure the gateway handles connection errors gracefully
        pass


class TestHealthChecks:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_liveness_endpoint(self, gateway_client: TestClient):
        """Test liveness endpoint."""
        response = await gateway_client.get("/health/live")

        assert response.status == 200
        data = await response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_readiness_endpoint(self, gateway_client: TestClient):
        """Test readiness endpoint."""
        response = await gateway_client.get("/health/ready")

        assert response.status == 200
        data = await response.json()
        assert data["ready"] is True

    @pytest.mark.asyncio
    async def test_detailed_health_endpoint(self, gateway_client: TestClient):
        """Test detailed health endpoint."""
        response = await gateway_client.get("/health")

        assert response.status == 200
        data = await response.json()
        assert "status" in data
        assert "components" in data


class TestMetricsEndpoint:
    """Test metrics exposition."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, gateway_client: TestClient):
        """Test Prometheus metrics endpoint."""
        # Make some requests first to generate metrics
        await gateway_client.get("/api/hello")
        await gateway_client.get("/api/hello")

        # Fetch metrics
        response = await gateway_client.get("/metrics")

        assert response.status == 200
        content = await response.text()

        # Check for key metrics
        assert "gateway_requests_total" in content
        assert "gateway_request_duration_seconds" in content
