"""Unit tests for metrics module."""

import pytest

from gateway.core.config import MetricsConfig
from gateway.core.metrics import ComponentHealth, GatewayMetrics, HealthStatus, initialize_metrics


@pytest.fixture
def metrics_config() -> MetricsConfig:
    """Create a test metrics configuration."""
    return MetricsConfig(
        enabled=True,
        endpoint="/metrics",
        health_endpoint="/health",
        liveness_endpoint="/health/live",
        readiness_endpoint="/health/ready",
    )


@pytest.fixture
def gateway_metrics(metrics_config: MetricsConfig) -> GatewayMetrics:
    """Create a test gateway metrics instance."""
    return GatewayMetrics(metrics_config)


def test_component_health() -> None:
    """Test ComponentHealth model."""
    health = ComponentHealth(
        name="test_component",
        status=HealthStatus.HEALTHY,
        message="All good",
        details={"version": "1.0"},
    )

    health_dict = health.to_dict()
    assert health_dict["name"] == "test_component"
    assert health_dict["status"] == "healthy"
    assert health_dict["message"] == "All good"
    assert health_dict["details"]["version"] == "1.0"


def test_gateway_metrics_initialization(gateway_metrics: GatewayMetrics) -> None:
    """Test GatewayMetrics initializes correctly."""
    assert gateway_metrics.config.enabled is True
    assert gateway_metrics.config.endpoint == "/metrics"


def test_record_request(gateway_metrics: GatewayMetrics) -> None:
    """Test recording HTTP requests."""
    gateway_metrics.record_request(
        method="GET",
        path="/api/users/123",
        status_code=200,
        duration_seconds=0.05,
        request_size=100,
        response_size=500,
    )

    # Verify metrics were recorded (can't easily check values without exposing internals)
    # Just ensure no exceptions were raised


def test_normalize_path(gateway_metrics: GatewayMetrics) -> None:
    """Test path normalization for metrics."""
    # Test UUID replacement
    normalized = gateway_metrics._normalize_path("/api/users/550e8400-e29b-41d4-a716-446655440000")
    assert normalized == "/api/users/:id"

    # Test numeric ID replacement
    normalized = gateway_metrics._normalize_path("/api/users/123")
    assert normalized == "/api/users/:id"

    # Test multiple IDs
    normalized = gateway_metrics._normalize_path("/api/users/123/posts/456")
    assert normalized == "/api/users/:id/posts/:id"

    # Test no IDs
    normalized = gateway_metrics._normalize_path("/api/users")
    assert normalized == "/api/users"


def test_record_auth_attempt(gateway_metrics: GatewayMetrics) -> None:
    """Test recording authentication attempts."""
    # Successful auth
    gateway_metrics.record_auth_attempt(success=True)

    # Failed auth
    gateway_metrics.record_auth_attempt(success=False, reason="invalid_token")

    # No exceptions should be raised


def test_record_authz_denial(gateway_metrics: GatewayMetrics) -> None:
    """Test recording authorization denials."""
    gateway_metrics.record_authz_denial(route="/api/admin")
    # No exceptions should be raised


def test_record_rate_limit_exceeded(gateway_metrics: GatewayMetrics) -> None:
    """Test recording rate limit violations."""
    gateway_metrics.record_rate_limit_exceeded(rule_name="global", key_type="ip")
    # No exceptions should be raised


def test_update_rate_limit_keys(gateway_metrics: GatewayMetrics) -> None:
    """Test updating rate limit key count."""
    gateway_metrics.update_rate_limit_keys(100)
    gateway_metrics.update_rate_limit_keys(50)
    # No exceptions should be raised


def test_record_upstream_request(gateway_metrics: GatewayMetrics) -> None:
    """Test recording upstream requests."""
    # Successful request
    gateway_metrics.record_upstream_request(
        upstream="user-service",
        status_code=200,
        duration_seconds=0.025,
    )

    # Failed request
    gateway_metrics.record_upstream_request(
        upstream="user-service",
        status_code=0,
        duration_seconds=5.0,
        error_type="timeout",
    )

    # No exceptions should be raised


def test_record_error(gateway_metrics: GatewayMetrics) -> None:
    """Test recording errors."""
    gateway_metrics.record_error(error_type="internal_error")
    gateway_metrics.record_error(error_type="validation_error")
    # No exceptions should be raised


def test_connection_tracking(gateway_metrics: GatewayMetrics) -> None:
    """Test active connection tracking."""
    gateway_metrics.increment_connections()
    gateway_metrics.increment_connections()
    gateway_metrics.decrement_connections()
    # No exceptions should be raised


def test_health_check_registration(gateway_metrics: GatewayMetrics) -> None:
    """Test registering health checks."""

    def healthy_check() -> ComponentHealth:
        return ComponentHealth(
            name="test_component",
            status=HealthStatus.HEALTHY,
        )

    gateway_metrics.register_health_check("test_component", healthy_check)

    health = gateway_metrics.check_health(detailed=True)
    assert health["status"] == "healthy"
    assert len(health["components"]) == 1
    assert health["components"][0]["name"] == "test_component"


def test_health_check_unhealthy(gateway_metrics: GatewayMetrics) -> None:
    """Test health check with unhealthy component."""

    def unhealthy_check() -> ComponentHealth:
        return ComponentHealth(
            name="failing_component",
            status=HealthStatus.UNHEALTHY,
            message="Component is down",
        )

    gateway_metrics.register_health_check("failing_component", unhealthy_check)

    health = gateway_metrics.check_health(detailed=True)
    assert health["status"] == "unhealthy"
    assert health["components"][0]["status"] == "unhealthy"
    assert health["components"][0]["message"] == "Component is down"


def test_health_check_degraded(gateway_metrics: GatewayMetrics) -> None:
    """Test health check with degraded component."""

    def degraded_check() -> ComponentHealth:
        return ComponentHealth(
            name="degraded_component",
            status=HealthStatus.DEGRADED,
            message="Component is slow",
        )

    gateway_metrics.register_health_check("degraded_component", degraded_check)

    health = gateway_metrics.check_health(detailed=True)
    assert health["status"] == "degraded"


def test_health_check_exception(gateway_metrics: GatewayMetrics) -> None:
    """Test health check handles exceptions."""

    def failing_check() -> ComponentHealth:
        raise Exception("Health check crashed")

    gateway_metrics.register_health_check("crashing_component", failing_check)

    health = gateway_metrics.check_health(detailed=True)
    assert health["status"] == "unhealthy"
    assert "Health check failed" in health["components"][0]["message"]


def test_liveness_check(gateway_metrics: GatewayMetrics) -> None:
    """Test liveness check."""
    liveness = gateway_metrics.check_liveness()
    assert liveness["status"] == "healthy"
    assert "timestamp" in liveness


def test_readiness_check(gateway_metrics: GatewayMetrics) -> None:
    """Test readiness check."""
    # No health checks registered - should be ready
    readiness = gateway_metrics.check_readiness()
    assert readiness["ready"] is True

    # Add unhealthy component - should not be ready
    def unhealthy_check() -> ComponentHealth:
        return ComponentHealth(
            name="failing_component",
            status=HealthStatus.UNHEALTHY,
        )

    gateway_metrics.register_health_check("failing_component", unhealthy_check)

    readiness = gateway_metrics.check_readiness()
    assert readiness["ready"] is False


def test_export_metrics(gateway_metrics: GatewayMetrics) -> None:
    """Test exporting metrics in Prometheus format."""
    # Record some metrics
    gateway_metrics.record_request(
        method="GET",
        path="/api/test",
        status_code=200,
        duration_seconds=0.1,
    )

    # Export metrics
    metrics_output = gateway_metrics.export_metrics()
    assert isinstance(metrics_output, bytes)
    assert b"gateway_requests_total" in metrics_output


def test_initialize_metrics(metrics_config: MetricsConfig) -> None:
    """Test global metrics initialization."""
    metrics = initialize_metrics(metrics_config)
    assert isinstance(metrics, GatewayMetrics)
