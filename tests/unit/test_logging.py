"""Unit tests for logging module."""

import json
import logging

import pytest

from gateway.core.config import LoggingConfig
from gateway.core.logging import (
    CorrelationIdFilter,
    GatewayLogger,
    JsonFormatter,
    TextFormatter,
    initialize_logging,
)


@pytest.fixture
def log_config() -> LoggingConfig:
    """Create a test logging configuration."""
    return LoggingConfig(
        level="DEBUG",
        format="json",
        output="stdout",
        redact_headers=["Authorization", "Cookie"],
    )


@pytest.fixture
def gateway_logger(log_config: LoggingConfig) -> GatewayLogger:
    """Create a test gateway logger."""
    return GatewayLogger(log_config)


def test_correlation_id_filter() -> None:
    """Test CorrelationIdFilter adds correlation ID to records."""
    filter_obj = CorrelationIdFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )

    # Without correlation ID
    filter_obj.filter(record)
    assert record.correlation_id == "none"  # type: ignore

    # With correlation ID
    filter_obj.set_correlation_id("test-123")
    filter_obj.filter(record)
    assert record.correlation_id == "test-123"  # type: ignore

    # After clearing
    filter_obj.clear_correlation_id()
    filter_obj.filter(record)
    assert record.correlation_id == "none"  # type: ignore


def test_json_formatter() -> None:
    """Test JsonFormatter produces valid JSON."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "test-123"  # type: ignore

    result = formatter.format(record)
    log_data = json.loads(result)

    assert log_data["level"] == "INFO"
    assert log_data["message"] == "test message"
    assert log_data["correlation_id"] == "test-123"
    assert "timestamp" in log_data


def test_json_formatter_redaction() -> None:
    """Test JsonFormatter redacts sensitive data."""
    formatter = JsonFormatter(redact_patterns=["Authorization", "Cookie"])
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "test-123"  # type: ignore
    record.extra_fields = {  # type: ignore
        "headers": {
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
            "Cookie": "session=abc123",
        }
    }

    result = formatter.format(record)
    log_data = json.loads(result)

    assert log_data["headers"]["Authorization"] == "***REDACTED***"
    assert log_data["headers"]["Cookie"] == "***REDACTED***"
    assert log_data["headers"]["Content-Type"] == "application/json"


def test_text_formatter() -> None:
    """Test TextFormatter produces human-readable output."""
    formatter = TextFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "test-123"  # type: ignore

    result = formatter.format(record)

    assert "[INFO]" in result
    assert "[test-123]" in result
    assert "test message" in result


def test_gateway_logger_initialization(gateway_logger: GatewayLogger) -> None:
    """Test GatewayLogger initializes correctly."""
    assert gateway_logger.config.level == "DEBUG"
    assert gateway_logger.config.format == "json"

    logger = gateway_logger.get_logger()
    assert logger.level == logging.DEBUG


def test_generate_correlation_id(gateway_logger: GatewayLogger) -> None:
    """Test correlation ID generation."""
    correlation_id = gateway_logger.generate_correlation_id()
    assert correlation_id.startswith("req-")
    assert len(correlation_id) == 20  # "req-" + 16 hex chars

    # Should generate unique IDs
    correlation_id2 = gateway_logger.generate_correlation_id()
    assert correlation_id != correlation_id2


def test_set_correlation_id(gateway_logger: GatewayLogger) -> None:
    """Test setting correlation ID."""
    # Set custom correlation ID
    result = gateway_logger.set_correlation_id("custom-123")
    assert result == "custom-123"

    # Generate new correlation ID
    result = gateway_logger.set_correlation_id()
    assert result.startswith("req-")


def test_log_request(gateway_logger: GatewayLogger, caplog: pytest.LogCaptureFixture) -> None:
    """Test request logging."""
    with caplog.at_level(logging.INFO):
        gateway_logger.log_request(
            method="GET",
            path="/api/users",
            client_ip="192.168.1.1",
            user_agent="TestAgent/1.0",
            user_id="user-123",
        )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "GET" in record.message
    assert "/api/users" in record.message


def test_log_response(gateway_logger: GatewayLogger, caplog: pytest.LogCaptureFixture) -> None:
    """Test response logging."""
    # Test successful response (INFO level)
    with caplog.at_level(logging.INFO):
        gateway_logger.log_response(
            method="GET",
            path="/api/users",
            status_code=200,
            latency_ms=45.5,
            response_size=1024,
        )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "INFO"

    caplog.clear()

    # Test client error (WARNING level)
    with caplog.at_level(logging.WARNING):
        gateway_logger.log_response(
            method="GET", path="/api/users", status_code=404, latency_ms=10.0
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"

    caplog.clear()

    # Test server error (ERROR level)
    with caplog.at_level(logging.ERROR):
        gateway_logger.log_response(
            method="GET", path="/api/users", status_code=500, latency_ms=100.0
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "ERROR"


def test_log_auth_event(gateway_logger: GatewayLogger, caplog: pytest.LogCaptureFixture) -> None:
    """Test authentication event logging."""
    with caplog.at_level(logging.INFO):
        gateway_logger.log_auth_event(event="auth_success", user_id="user-123", success=True)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "INFO"

    caplog.clear()

    with caplog.at_level(logging.WARNING):
        gateway_logger.log_auth_event(
            event="auth_failure",
            user_id="user-456",
            success=False,
            reason="invalid_token",
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert "invalid_token" in caplog.records[0].message


def test_log_rate_limit_event(
    gateway_logger: GatewayLogger, caplog: pytest.LogCaptureFixture
) -> None:
    """Test rate limit event logging."""
    with caplog.at_level(logging.DEBUG):
        gateway_logger.log_rate_limit_event(
            key="user-123:/api/users", limit=100, current=50, exceeded=False
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "DEBUG"

    caplog.clear()

    with caplog.at_level(logging.WARNING):
        gateway_logger.log_rate_limit_event(
            key="user-123:/api/users", limit=100, current=101, exceeded=True
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"


def test_log_upstream_event(
    gateway_logger: GatewayLogger, caplog: pytest.LogCaptureFixture
) -> None:
    """Test upstream event logging."""
    with caplog.at_level(logging.DEBUG):
        gateway_logger.log_upstream_event(
            upstream_url="http://backend:8080/api/users",
            method="GET",
            status_code=200,
            latency_ms=25.5,
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "DEBUG"

    caplog.clear()

    with caplog.at_level(logging.ERROR):
        gateway_logger.log_upstream_event(
            upstream_url="http://backend:8080/api/users",
            method="GET",
            error="Connection timeout",
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "ERROR"
    assert "Connection timeout" in caplog.records[0].message


def test_initialize_logging(log_config: LoggingConfig) -> None:
    """Test global logger initialization."""
    logger = initialize_logging(log_config)
    assert isinstance(logger, GatewayLogger)
