"""Shared pytest fixtures and configuration."""

import pytest
from prometheus_client import REGISTRY


@pytest.fixture(autouse=True)
def reset_prometheus_registry():
    """Reset Prometheus registry before each test to avoid duplicate metric errors."""
    # Get all collectors
    collectors = list(REGISTRY._collector_to_names.keys())

    # Unregister all collectors except default ones
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass  # Ignore errors for default collectors

    yield

    # Clean up after test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
