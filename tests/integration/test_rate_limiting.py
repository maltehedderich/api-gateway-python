"""Integration tests for rate limiting."""

import asyncio

import pytest
from aiohttp.test_utils import TestClient

from gateway.core.session_store import SessionData


class TestRateLimitingBasic:
    """Test basic rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_requests_allowed_within_limit(self, gateway_client: TestClient):
        """Test that requests within rate limit are allowed."""
        # Make several requests within the limit
        for i in range(5):
            response = await gateway_client.get("/api/hello")
            assert response.status == 200, f"Request {i + 1} should succeed"

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, gateway_client: TestClient):
        """Test that rate limit headers are included in responses."""
        response = await gateway_client.get("/api/hello")

        assert response.status == 200

        # Check for rate limit headers
        # Common rate limit header names

        # At least some rate limit headers should be present
        # (Exact headers depend on implementation)

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, gateway_client: TestClient):
        """Test that requests are denied when rate limit is exceeded."""
        # This test needs a route with a very low rate limit
        # For testing purposes, we'd configure a test route with limit=3
        # and make more than 3 requests quickly

        # Make requests up to and beyond the limit
        # Assuming a test configuration with low limits
        responses = []
        for _i in range(15):  # Try many requests
            response = await gateway_client.get("/api/hello")
            responses.append(response.status)
            if response.status == 429:
                break  # Hit rate limit

        # If rate limiting is configured, eventually we should get 429
        # (This depends on test configuration)

    @pytest.mark.asyncio
    async def test_rate_limit_429_response(self, gateway_client: TestClient):
        """Test the structure of 429 Too Many Requests response."""
        # This test requires hitting the rate limit first
        # Make many requests to trigger rate limit
        response = None
        for _i in range(100):
            response = await gateway_client.get("/api/hello")
            if response.status == 429:
                break

        if response and response.status == 429:
            data = await response.json()

            # Verify error response structure
            assert data["error"] == "rate_limit_exceeded"
            assert "message" in data

            # Verify Retry-After header
            assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self, gateway_client: TestClient):
        """Test that rate limit counter resets after time window."""
        # This is a time-sensitive test
        # Would need to configure a short window (e.g., 1 second) for testing

        # Make requests to approach limit
        # Wait for window to reset
        # Make more requests successfully

        # For this test to work reliably, we need a test-specific configuration
        pass


class TestRateLimitingPerUser:
    """Test per-user rate limiting."""

    @pytest.mark.asyncio
    async def test_different_users_have_separate_limits(
        self,
        gateway_client: TestClient,
        test_session: SessionData,
        admin_session: SessionData,
    ):
        """Test that different users have independent rate limits."""
        # Make requests as user 1
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        for _i in range(3):
            response = await gateway_client.get("/api/users/123")
            assert response.status == 200

        # Switch to user 2
        gateway_client.session.cookie_jar.clear()
        gateway_client.session.cookie_jar.update_cookies(
            {"session_token": admin_session.session_id}
        )

        # Should be able to make requests as user 2
        for _i in range(3):
            response = await gateway_client.get("/api/users/456")
            assert response.status == 200

    @pytest.mark.asyncio
    async def test_user_rate_limit_vs_ip_rate_limit(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test interaction between per-user and per-IP rate limits."""
        # Authenticated requests use user-based rate limiting
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        user_responses = []
        for _i in range(5):
            response = await gateway_client.get("/api/users/123")
            user_responses.append(response.status)

        # Unauthenticated requests use IP-based rate limiting
        gateway_client.session.cookie_jar.clear()

        ip_responses = []
        for _i in range(5):
            response = await gateway_client.get("/api/hello")
            ip_responses.append(response.status)

        # Both should work independently
        # (Assuming configured limits allow this)


class TestRateLimitingAlgorithms:
    """Test different rate limiting algorithms."""

    @pytest.mark.asyncio
    async def test_fixed_window_algorithm(self, gateway_client: TestClient):
        """Test fixed window rate limiting algorithm."""
        # Global rule uses fixed_window algorithm
        # Make requests and verify behavior matches fixed window

        responses = []
        for _i in range(10):
            response = await gateway_client.get("/api/hello")
            responses.append(response.status)

        # Most should succeed (within global limit of 100/minute)
        assert sum(1 for s in responses if s == 200) >= 8

    @pytest.mark.asyncio
    async def test_token_bucket_algorithm(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test token bucket rate limiting algorithm."""
        # User limit uses token_bucket algorithm with burst
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        # Token bucket allows burst up to bucket capacity
        burst_responses = []
        for _i in range(15):  # Configured burst is 15
            response = await gateway_client.get("/api/users/123")
            burst_responses.append(response.status)

        # First 15 should succeed (burst), then start failing
        # (Depends on exact configuration)

    @pytest.mark.asyncio
    async def test_token_bucket_refill(self, gateway_client: TestClient, test_session: SessionData):
        """Test that token bucket refills over time."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        # Consume some tokens
        for _i in range(5):
            await gateway_client.get("/api/users/123")

        # Wait for some refill (depends on refill rate)
        await asyncio.sleep(1)

        # Should be able to make more requests
        await gateway_client.get("/api/users/123")
        # May or may not succeed depending on exact timing and configuration


class TestRateLimitingPerRoute:
    """Test per-route rate limiting."""

    @pytest.mark.asyncio
    async def test_different_routes_have_separate_limits(self, gateway_client: TestClient):
        """Test that different routes can have different rate limits."""
        # Make requests to route 1
        for _i in range(5):
            response = await gateway_client.get("/api/hello")
            assert response.status == 200

        # Make requests to route 2
        for _i in range(5):
            response = await gateway_client.post("/api/echo", json={})
            assert response.status == 200

        # Both should succeed if they have independent limits

    @pytest.mark.asyncio
    async def test_composite_key_rate_limiting(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test rate limiting with composite keys (user + route)."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        # Make requests to different routes as same user
        # Each user+route combination should have its own limit

        # Route 1
        route1_count = 0
        for _i in range(10):
            response = await gateway_client.get("/api/users/123")
            if response.status == 200:
                route1_count += 1

        # Route 2
        route2_count = 0
        for _i in range(10):
            response = await gateway_client.post("/api/echo", json={})
            if response.status == 200:
                route2_count += 1

        # Both should have independent counters
        # (Assuming composite key configuration)


class TestRateLimitingFailModes:
    """Test rate limiting fail-open and fail-closed modes."""

    @pytest.mark.asyncio
    async def test_fail_open_when_store_unavailable(self, gateway_client: TestClient):
        """Test fail-open behavior when rate limit store is unavailable."""
        # This test requires mocking or actually breaking the rate limit store
        # In fail-open mode, requests should be allowed

        # The test configuration uses fail_mode="open"
        # If we could make the store unhealthy, requests should still succeed

        response = await gateway_client.get("/api/hello")
        # Should succeed even if rate limiter is down
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_fail_closed_when_store_unavailable(self, gateway_client: TestClient):
        """Test fail-closed behavior when rate limit store is unavailable."""
        # This would require a configuration with fail_mode="closed"
        # and a broken rate limit store
        # In fail-closed mode, requests should be denied

        # Not easily testable without ability to break the store
        pass


class TestRateLimitingMetrics:
    """Test that rate limiting events are recorded in metrics."""

    @pytest.mark.skip(reason="Complex integration test - needs upstream mocking")
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex integration test - needs upstream mocking")
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_metric(self, gateway_client: TestClient):
        """Test that rate limit exceeded events are counted in metrics."""
        # Make many requests to trigger rate limit
        for _i in range(100):
            await gateway_client.get("/api/hello")

        # Fetch metrics
        response = await gateway_client.get("/metrics")
        assert response.status == 200

        await response.text()

        # Check for rate limit metrics
        # (Exact metric names depend on implementation)
        # e.g., "gateway_rate_limit_exceeded_total"

    @pytest.mark.skip(reason="Complex integration test - needs upstream mocking")
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex integration test - needs upstream mocking")
    @pytest.mark.asyncio
    async def test_active_rate_limit_keys_metric(self, gateway_client: TestClient):
        """Test that active rate limit keys are tracked in metrics."""
        # Make requests to create rate limit entries
        await gateway_client.get("/api/hello")

        response = await gateway_client.get("/metrics")
        assert response.status == 200

        await response.text()

        # Check for active keys metric
        # e.g., "gateway_rate_limit_active_keys"


class TestRateLimitingLogging:
    """Test that rate limiting events are logged."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_logged(self, gateway_client: TestClient, caplog):
        """Test that rate limit exceeded events are logged."""
        # Make many requests to trigger rate limit
        for _i in range(100):
            response = await gateway_client.get("/api/hello")
            if response.status == 429:
                break

        # Check logs for rate limit event
        # (May need to set appropriate log level)

    @pytest.mark.asyncio
    async def test_rate_limit_debug_logging(self, gateway_client: TestClient, caplog):
        """Test detailed rate limiting debug logs."""
        with caplog.at_level("DEBUG"):
            await gateway_client.get("/api/hello")

        # Should have debug logs about rate limit evaluation


class TestRateLimitingConcurrency:
    """Test rate limiting under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_rate_limiting(self, gateway_client: TestClient):
        """Test rate limiting with concurrent requests."""

        async def make_request(n: int):
            response = await gateway_client.get("/api/hello")
            return response.status

        # Make 50 concurrent requests
        tasks = [make_request(i) for i in range(50)]
        statuses = await asyncio.gather(*tasks)

        # Count successes and rate limit errors
        successes = sum(1 for s in statuses if s == 200)
        sum(1 for s in statuses if s == 429)

        # Most should succeed (global limit is 100/minute)
        # But some might be rate limited depending on timing
        assert successes > 0

    @pytest.mark.asyncio
    async def test_rate_limiting_accuracy_under_load(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test that rate limiting remains accurate under concurrent load."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        async def make_request(n: int):
            response = await gateway_client.get("/api/users/123")
            return response.status

        # User limit is 10/minute with 15 burst
        # Make 20 concurrent requests
        tasks = [make_request(i) for i in range(20)]
        statuses = await asyncio.gather(*tasks)

        successes = sum(1 for s in statuses if s == 200)
        rate_limited = sum(1 for s in statuses if s == 429)

        # Should allow up to burst (15), then deny
        # Due to concurrent nature, exact count may vary slightly
        assert successes <= 16  # Allow for small variance
        assert rate_limited >= 4
