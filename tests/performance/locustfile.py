"""Locust load tests for API Gateway.

Run with:
    locust -f tests/performance/locustfile.py --host=http://localhost:8080

Or for headless mode:
    locust -f tests/performance/locustfile.py --host=http://localhost:8080 \
           --users 100 --spawn-rate 10 --run-time 60s --headless
"""

import random
from locust import HttpUser, task, between, constant_pacing


class PublicRouteUser(HttpUser):
    """Simulates users accessing public routes (no authentication)."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    @task(10)
    def get_hello(self):
        """Test public GET endpoint."""
        self.client.get("/api/hello")

    @task(5)
    def post_echo(self):
        """Test public POST endpoint."""
        payload = {
            "message": "Test message",
            "timestamp": "2025-11-16T12:00:00Z",
            "data": {"key": "value"},
        }
        self.client.post("/api/echo", json=payload)

    @task(2)
    def get_with_query_params(self):
        """Test endpoint with query parameters."""
        params = {"foo": "bar", "baz": random.randint(1, 100)}
        self.client.get("/api/hello", params=params)

    @task(1)
    def different_methods(self):
        """Test different HTTP methods."""
        method = random.choice(["GET", "POST", "PUT", "DELETE"])
        payload = {"test": "data"} if method in ["POST", "PUT"] else None
        self.client.request(method, "/api/echo", json=payload)


class AuthenticatedUser(HttpUser):
    """Simulates authenticated users accessing protected routes."""

    wait_time = between(0.5, 2)

    def on_start(self):
        """Setup - create session token."""
        # In real scenario, would authenticate and get token
        # For load testing, we'll use a test session token
        self.session_token = "test-session-123"
        self.client.cookies.set("session_token", self.session_token)

    @task(10)
    def get_user_profile(self):
        """Test authenticated user endpoint."""
        user_id = random.randint(100, 999)
        self.client.get(f"/api/users/{user_id}")

    @task(5)
    def post_user_data(self):
        """Test authenticated POST endpoint."""
        payload = {
            "name": f"User {random.randint(1, 1000)}",
            "email": f"user{random.randint(1, 1000)}@example.com",
        }
        self.client.post("/api/echo", json=payload)

    @task(2)
    def update_user_data(self):
        """Test authenticated PUT endpoint."""
        user_id = random.randint(100, 999)
        payload = {"name": "Updated Name"}
        self.client.put(f"/api/echo", json=payload)

    @task(1)
    def unauthorized_access(self):
        """Test attempting to access admin routes (will fail)."""
        with self.client.get("/api/admin", catch_response=True) as response:
            if response.status_code == 403:
                # Expected behavior - mark as success
                response.success()


class RateLimitTestUser(HttpUser):
    """User specifically for testing rate limiting behavior."""

    wait_time = constant_pacing(0.1)  # Very fast requests to trigger rate limits

    @task
    def rapid_requests(self):
        """Make rapid requests to test rate limiting."""
        with self.client.get("/api/hello", catch_response=True) as response:
            if response.status_code == 429:
                # Rate limited - this is expected behavior
                response.success()
            elif response.status_code == 200:
                # Normal success
                response.success()
            else:
                # Unexpected error
                response.failure(f"Unexpected status code: {response.status_code}")


class HighThroughputUser(HttpUser):
    """Simulates high-throughput scenario with minimal wait time."""

    wait_time = between(0.1, 0.5)

    @task
    def fast_requests(self):
        """Make fast sequential requests."""
        endpoints = ["/api/hello", "/api/echo"]
        endpoint = random.choice(endpoints)

        if endpoint == "/api/echo":
            self.client.post(endpoint, json={"test": "data"})
        else:
            self.client.get(endpoint)


class MixedWorkloadUser(HttpUser):
    """Simulates realistic mixed workload."""

    wait_time = between(1, 5)

    def on_start(self):
        """Setup session for authenticated requests."""
        # 50% chance of being authenticated
        if random.random() < 0.5:
            self.session_token = f"test-session-{random.randint(1, 100)}"
            self.client.cookies.set("session_token", self.session_token)
            self.authenticated = True
        else:
            self.authenticated = False

    @task(20)
    def read_operations(self):
        """Simulate read operations (GET requests)."""
        if self.authenticated:
            user_id = random.randint(1, 1000)
            self.client.get(f"/api/users/{user_id}")
        else:
            self.client.get("/api/hello")

    @task(5)
    def write_operations(self):
        """Simulate write operations (POST/PUT requests)."""
        payload = {
            "timestamp": "2025-11-16T12:00:00Z",
            "data": {"random": random.randint(1, 10000)},
        }
        self.client.post("/api/echo", json=payload)

    @task(2)
    def slow_operations(self):
        """Simulate potentially slow operations."""
        # Test with larger payload
        large_payload = {"data": "x" * 10000}
        self.client.post("/api/echo", json=large_payload)

    @task(1)
    def check_health(self):
        """Check health endpoints."""
        self.client.get("/health")


class StressTestUser(HttpUser):
    """User for stress testing - pushes limits."""

    wait_time = between(0.01, 0.1)  # Very aggressive

    @task(10)
    def concurrent_reads(self):
        """Rapid read requests."""
        self.client.get("/api/hello")

    @task(5)
    def concurrent_writes(self):
        """Rapid write requests."""
        payload = {"id": random.randint(1, 100000)}
        self.client.post("/api/echo", json=payload)

    @task(1)
    def large_payload(self):
        """Test with large payloads."""
        large_payload = {"data": "x" * 100000}  # 100KB
        with self.client.post(
            "/api/echo", json=large_payload, catch_response=True
        ) as response:
            if response.status_code in [200, 413]:  # 413 = Payload Too Large
                response.success()


class HealthCheckMonitor(HttpUser):
    """Continuously monitors health endpoints."""

    wait_time = constant_pacing(5)  # Every 5 seconds

    @task(5)
    def check_health(self):
        """Check detailed health."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    response.success()
                else:
                    response.failure(f"Unhealthy status: {data.get('status')}")

    @task(3)
    def check_liveness(self):
        """Check liveness endpoint."""
        self.client.get("/health/live")

    @task(3)
    def check_readiness(self):
        """Check readiness endpoint."""
        self.client.get("/health/ready")

    @task(1)
    def check_metrics(self):
        """Fetch Prometheus metrics."""
        self.client.get("/metrics")
