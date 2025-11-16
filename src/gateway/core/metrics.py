"""Observability and metrics module for the API Gateway.

Provides metrics collection, health checks, and integration with monitoring systems.
"""

import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from gateway.core.config import MetricsConfig


class HealthStatus(Enum):
    """Health check status enumeration."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class ComponentHealth:
    """Health status of a component."""

    def __init__(
        self,
        name: str,
        status: HealthStatus,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize component health status.

        Args:
            name: Component name
            status: Health status
            message: Optional status message
            details: Optional additional details
        """
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the health status
        """
        result: Dict[str, Any] = {
            "name": self.name,
            "status": self.status.value,
        }
        if self.message:
            result["message"] = self.message
        if self.details:
            result["details"] = self.details
        return result


class GatewayMetrics:
    """Gateway metrics collector using Prometheus."""

    def __init__(self, config: MetricsConfig):
        """Initialize the metrics collector.

        Args:
            config: Metrics configuration
        """
        self.config = config
        self._health_checks: Dict[str, Callable[[], ComponentHealth]] = {}

        # Request metrics
        self.request_total = Counter(
            "gateway_requests_total",
            "Total number of HTTP requests",
            ["method", "path", "status"],
        )

        self.request_duration = Histogram(
            "gateway_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "path"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        self.request_size = Histogram(
            "gateway_request_size_bytes",
            "HTTP request size in bytes",
            ["method", "path"],
            buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
        )

        self.response_size = Histogram(
            "gateway_response_size_bytes",
            "HTTP response size in bytes",
            ["method", "path"],
            buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
        )

        # Connection metrics
        self.active_connections = Gauge(
            "gateway_active_connections", "Number of active connections"
        )

        # Authentication metrics
        self.auth_attempts = Counter(
            "gateway_auth_attempts_total",
            "Total number of authentication attempts",
            ["result"],
        )

        self.auth_failures = Counter(
            "gateway_auth_failures_total",
            "Total number of authentication failures",
            ["reason"],
        )

        # Authorization metrics
        self.authz_denials = Counter(
            "gateway_authz_denials_total",
            "Total number of authorization denials",
            ["route"],
        )

        # Rate limiting metrics
        self.rate_limit_exceeded = Counter(
            "gateway_rate_limit_exceeded_total",
            "Total number of rate limit violations",
            ["rule", "key_type"],
        )

        self.rate_limit_keys = Gauge(
            "gateway_rate_limit_keys",
            "Number of active rate limit keys",
        )

        # Upstream metrics
        self.upstream_requests = Counter(
            "gateway_upstream_requests_total",
            "Total number of upstream requests",
            ["upstream", "status"],
        )

        self.upstream_duration = Histogram(
            "gateway_upstream_duration_seconds",
            "Upstream request latency in seconds",
            ["upstream"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        self.upstream_errors = Counter(
            "gateway_upstream_errors_total",
            "Total number of upstream errors",
            ["upstream", "error_type"],
        )

        # Error metrics
        self.errors_total = Counter(
            "gateway_errors_total",
            "Total number of errors",
            ["error_type"],
        )

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
    ) -> None:
        """Record a completed HTTP request.

        Args:
            method: HTTP method
            path: Request path
            status_code: HTTP status code
            duration_seconds: Request duration in seconds
            request_size: Request body size in bytes
            response_size: Response body size in bytes
        """
        # Normalize path for metrics (remove IDs, etc.)
        normalized_path = self._normalize_path(path)

        self.request_total.labels(
            method=method, path=normalized_path, status=str(status_code)
        ).inc()

        self.request_duration.labels(method=method, path=normalized_path).observe(
            duration_seconds
        )

        if request_size is not None:
            self.request_size.labels(method=method, path=normalized_path).observe(request_size)

        if response_size is not None:
            self.response_size.labels(method=method, path=normalized_path).observe(response_size)

    def record_auth_attempt(self, success: bool, reason: Optional[str] = None) -> None:
        """Record an authentication attempt.

        Args:
            success: Whether authentication succeeded
            reason: Failure reason if unsuccessful
        """
        result = "success" if success else "failure"
        self.auth_attempts.labels(result=result).inc()

        if not success and reason:
            self.auth_failures.labels(reason=reason).inc()

    def record_authz_denial(self, route: str) -> None:
        """Record an authorization denial.

        Args:
            route: The route that was denied
        """
        self.authz_denials.labels(route=route).inc()

    def record_rate_limit_exceeded(self, rule_name: str, key_type: str) -> None:
        """Record a rate limit violation.

        Args:
            rule_name: Name of the rate limit rule
            key_type: Type of rate limit key (ip, user, etc.)
        """
        self.rate_limit_exceeded.labels(rule=rule_name, key_type=key_type).inc()

    def update_rate_limit_keys(self, count: int) -> None:
        """Update the number of active rate limit keys.

        Args:
            count: Number of active keys
        """
        self.rate_limit_keys.set(count)

    def record_upstream_request(
        self,
        upstream: str,
        status_code: int,
        duration_seconds: float,
        error_type: Optional[str] = None,
    ) -> None:
        """Record an upstream request.

        Args:
            upstream: Upstream service identifier
            status_code: HTTP status code (0 if error)
            duration_seconds: Request duration in seconds
            error_type: Error type if request failed
        """
        status_str = str(status_code) if status_code > 0 else "error"
        self.upstream_requests.labels(upstream=upstream, status=status_str).inc()

        self.upstream_duration.labels(upstream=upstream).observe(duration_seconds)

        if error_type:
            self.upstream_errors.labels(upstream=upstream, error_type=error_type).inc()

    def record_error(self, error_type: str) -> None:
        """Record an error.

        Args:
            error_type: Type of error
        """
        self.errors_total.labels(error_type=error_type).inc()

    def increment_connections(self) -> None:
        """Increment active connection count."""
        self.active_connections.inc()

    def decrement_connections(self) -> None:
        """Decrement active connection count."""
        self.active_connections.dec()

    def register_health_check(
        self, name: str, check_func: Callable[[], ComponentHealth]
    ) -> None:
        """Register a health check function.

        Args:
            name: Component name
            check_func: Function that returns ComponentHealth
        """
        self._health_checks[name] = check_func

    def check_health(self, detailed: bool = False) -> Dict[str, Any]:
        """Check health of all registered components.

        Args:
            detailed: Whether to include detailed component status

        Returns:
            Dictionary with health check results
        """
        if not self._health_checks:
            return {
                "status": HealthStatus.HEALTHY.value,
                "message": "No health checks registered",
            }

        component_results: List[ComponentHealth] = []
        overall_status = HealthStatus.HEALTHY

        for name, check_func in self._health_checks.items():
            try:
                result = check_func()
                component_results.append(result)

                # Determine overall status
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED

            except Exception as e:
                # Health check itself failed
                component_results.append(
                    ComponentHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check failed: {str(e)}",
                    )
                )
                overall_status = HealthStatus.UNHEALTHY

        result: Dict[str, Any] = {
            "status": overall_status.value,
            "timestamp": time.time(),
        }

        if detailed:
            result["components"] = [c.to_dict() for c in component_results]

        return result

    def check_liveness(self) -> Dict[str, Any]:
        """Check if the service is alive (simple check).

        Returns:
            Dictionary with liveness status
        """
        return {
            "status": HealthStatus.HEALTHY.value,
            "timestamp": time.time(),
        }

    def check_readiness(self) -> Dict[str, Any]:
        """Check if the service is ready to accept traffic.

        Returns:
            Dictionary with readiness status
        """
        # Readiness is based on all health checks passing
        health = self.check_health(detailed=False)
        return {
            "status": health["status"],
            "ready": health["status"] == HealthStatus.HEALTHY.value,
            "timestamp": time.time(),
        }

    def export_metrics(self) -> bytes:
        """Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics
        """
        return generate_latest(REGISTRY)

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize path for metrics to avoid cardinality explosion.

        Replaces UUIDs and numeric IDs with placeholders.

        Args:
            path: Original request path

        Returns:
            Normalized path
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            ":id",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs (sequences of digits)
        path = re.sub(r"/\d+", "/:id", path)

        return path


# Global metrics instance (will be initialized by the application)
_gateway_metrics: Optional[GatewayMetrics] = None


def initialize_metrics(config: MetricsConfig) -> GatewayMetrics:
    """Initialize the global gateway metrics.

    Args:
        config: Metrics configuration

    Returns:
        Initialized GatewayMetrics instance
    """
    global _gateway_metrics
    _gateway_metrics = GatewayMetrics(config)
    return _gateway_metrics


def get_metrics() -> GatewayMetrics:
    """Get the global gateway metrics.

    Returns:
        The global GatewayMetrics instance

    Raises:
        RuntimeError: If metrics have not been initialized
    """
    if _gateway_metrics is None:
        raise RuntimeError("Metrics not initialized. Call initialize_metrics() first.")
    return _gateway_metrics
