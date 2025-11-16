"""Logging module for the API Gateway.

Provides structured logging with JSON format, correlation IDs, and sensitive data redaction.
"""

import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from gateway.core.config import LoggingConfig


class CorrelationIdFilter(logging.Filter):
    """Logging filter that adds correlation ID to log records."""

    def __init__(self) -> None:
        """Initialize the correlation ID filter."""
        super().__init__()
        self._correlation_id: str | None = None

    def set_correlation_id(self, correlation_id: str) -> None:
        """Set the correlation ID for the current request.

        Args:
            correlation_id: The correlation ID to use
        """
        self._correlation_id = correlation_id

    def clear_correlation_id(self) -> None:
        """Clear the correlation ID."""
        self._correlation_id = None

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to the log record.

        Args:
            record: The log record to filter

        Returns:
            True to include the record
        """
        record.correlation_id = self._correlation_id or "none"  # type: ignore
        return True


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def __init__(self, redact_patterns: list[str] | None = None):
        """Initialize the JSON formatter.

        Args:
            redact_patterns: List of field names to redact from logs
        """
        super().__init__()
        self.redact_patterns = redact_patterns or []

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON.

        Args:
            record: The log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "none"),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from the record
        if hasattr(record, "extra_fields"):
            extra = record.extra_fields
            if isinstance(extra, dict):
                log_data.update(self._redact_sensitive_data(extra))

        # Add any custom attributes
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "correlation_id",
                "extra_fields",
            ]:
                log_data[key] = value

        return json.dumps(log_data, default=str)

    def _redact_sensitive_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive data from log fields.

        Args:
            data: Dictionary potentially containing sensitive data

        Returns:
            Dictionary with sensitive fields redacted
        """
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            if any(pattern.lower() in key.lower() for pattern in self.redact_patterns):
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive_data(value)
            else:
                redacted[key] = value
        return redacted


class TextFormatter(logging.Formatter):
    """Custom text formatter for human-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as text.

        Args:
            record: The log record to format

        Returns:
            Formatted log string
        """
        timestamp = datetime.now(UTC).isoformat()
        correlation_id = getattr(record, "correlation_id", "none")

        base = (
            f"{timestamp} [{record.levelname}] "
            f"[{correlation_id}] "
            f"{record.name}: {record.getMessage()}"
        )

        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base


class GatewayLogger:
    """Gateway logger with structured logging and correlation ID support."""

    def __init__(self, config: LoggingConfig):
        """Initialize the gateway logger.

        Args:
            config: Logging configuration
        """
        self.config = config
        self.correlation_filter = CorrelationIdFilter()
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Set up logging configuration."""
        # Get or create root logger
        logger = logging.getLogger("gateway")
        logger.setLevel(getattr(logging, self.config.level))
        logger.handlers.clear()

        # Create handler based on output configuration
        handler: logging.Handler
        if self.config.output == "stdout":
            handler = logging.StreamHandler(sys.stdout)
        elif self.config.output == "stderr":
            handler = logging.StreamHandler(sys.stderr)
        else:
            # Assume it's a file path
            handler = logging.FileHandler(self.config.output)

        # Set formatter based on format configuration
        formatter: logging.Formatter
        if self.config.format.lower() == "json":
            formatter = JsonFormatter(redact_patterns=self.config.redact_headers)
        else:
            formatter = TextFormatter()

        handler.setFormatter(formatter)
        handler.addFilter(self.correlation_filter)
        logger.addHandler(handler)

        # Prevent propagation to root logger
        logger.propagate = False

    def set_correlation_id(self, correlation_id: str | None = None) -> str:
        """Set or generate a correlation ID for the current request.

        Args:
            correlation_id: Optional correlation ID. If None, generates a new one.

        Returns:
            The correlation ID that was set
        """
        if correlation_id is None:
            correlation_id = self.generate_correlation_id()
        self.correlation_filter.set_correlation_id(correlation_id)
        return correlation_id

    def clear_correlation_id(self) -> None:
        """Clear the current correlation ID."""
        self.correlation_filter.clear_correlation_id()

    @staticmethod
    def generate_correlation_id() -> str:
        """Generate a unique correlation ID.

        Returns:
            A unique correlation ID
        """
        return f"req-{uuid.uuid4().hex[:16]}"

    def get_logger(self, name: str = "gateway") -> logging.Logger:
        """Get a logger instance.

        Args:
            name: Logger name (default: "gateway")

        Returns:
            Logger instance
        """
        return logging.getLogger(name)

    def log_request(
        self,
        method: str,
        path: str,
        client_ip: str,
        user_agent: str | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an incoming request.

        Args:
            method: HTTP method
            path: Request path
            client_ip: Client IP address
            user_agent: User agent string
            user_id: Authenticated user ID
            **kwargs: Additional fields to log
        """
        logger = self.get_logger()
        extra_fields = {
            "event_type": "request_received",
            "request": {
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "user_agent": user_agent,
            },
        }
        if user_id:
            extra_fields["auth"] = {"user_id": user_id}

        extra_fields.update(kwargs)

        # Create a log record with extra fields
        logger.info(
            f"{method} {path} from {client_ip}",
            extra={"extra_fields": extra_fields},
        )

    def log_response(
        self,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        response_size: int | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log a response.

        Args:
            method: HTTP method
            path: Request path
            status_code: HTTP status code
            latency_ms: Request latency in milliseconds
            response_size: Response body size in bytes
            user_id: Authenticated user ID
            **kwargs: Additional fields to log
        """
        logger = self.get_logger()
        extra_fields = {
            "event_type": "request_completed",
            "request": {"method": method, "path": path},
            "response": {
                "status_code": status_code,
                "latency_ms": latency_ms,
                "body_size": response_size,
            },
        }
        if user_id:
            extra_fields["auth"] = {"user_id": user_id}

        extra_fields.update(kwargs)

        # Determine log level based on status code
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        logger.log(
            log_level,
            f"{method} {path} -> {status_code} ({latency_ms:.2f}ms)",
            extra={"extra_fields": extra_fields},
        )

    def log_auth_event(
        self,
        event: str,
        user_id: str | None = None,
        success: bool = True,
        reason: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an authentication or authorization event.

        Args:
            event: Event type (e.g., "auth_attempt", "auth_success", "auth_failure")
            user_id: User ID if available
            success: Whether the event was successful
            reason: Failure reason if applicable
            **kwargs: Additional fields to log
        """
        logger = self.get_logger()
        auth_data: dict[str, Any] = {"user_id": user_id, "success": success}
        if reason:
            auth_data["reason"] = reason

        extra_fields: dict[str, Any] = {
            "event_type": event,
            "auth": auth_data,
        }
        extra_fields.update(kwargs)

        log_level = logging.INFO if success else logging.WARNING
        message = f"Auth event: {event}"
        if reason:
            message += f" - {reason}"

        logger.log(log_level, message, extra={"extra_fields": extra_fields})

    def log_rate_limit_event(
        self,
        key: str,
        limit: int,
        current: int,
        exceeded: bool,
        **kwargs: Any,
    ) -> None:
        """Log a rate limiting event.

        Args:
            key: Rate limit key
            limit: Rate limit threshold
            current: Current request count
            exceeded: Whether the limit was exceeded
            **kwargs: Additional fields to log
        """
        logger = self.get_logger()
        extra_fields = {
            "event_type": "rate_limit_check",
            "ratelimit": {
                "key": key,
                "limit": limit,
                "current": current,
                "exceeded": exceeded,
            },
        }
        extra_fields.update(kwargs)

        log_level = logging.WARNING if exceeded else logging.DEBUG
        message = f"Rate limit {'exceeded' if exceeded else 'checked'} for key {key}"

        logger.log(log_level, message, extra={"extra_fields": extra_fields})

    def log_upstream_event(
        self,
        upstream_url: str,
        method: str,
        status_code: int | None = None,
        latency_ms: float | None = None,
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an upstream service interaction.

        Args:
            upstream_url: Upstream service URL
            method: HTTP method
            status_code: Response status code
            latency_ms: Request latency in milliseconds
            error: Error message if request failed
            **kwargs: Additional fields to log
        """
        logger = self.get_logger()
        upstream_data: dict[str, Any] = {
            "url": upstream_url,
            "method": method,
            "status_code": status_code,
            "latency_ms": latency_ms,
        }
        if error:
            upstream_data["error"] = error

        extra_fields: dict[str, Any] = {
            "event_type": "upstream_request",
            "upstream": upstream_data,
        }
        extra_fields.update(kwargs)

        log_level = logging.ERROR if error else logging.DEBUG
        message = f"Upstream {method} {upstream_url}"
        if status_code:
            message += f" -> {status_code}"
        if error:
            message += f" - {error}"

        logger.log(log_level, message, extra={"extra_fields": extra_fields})


# Global logger instance (will be initialized by the application)
_gateway_logger: GatewayLogger | None = None


def initialize_logging(config: LoggingConfig) -> GatewayLogger:
    """Initialize the global gateway logger.

    Args:
        config: Logging configuration

    Returns:
        Initialized GatewayLogger instance
    """
    global _gateway_logger
    _gateway_logger = GatewayLogger(config)
    return _gateway_logger


def get_logger() -> GatewayLogger:
    """Get the global gateway logger.

    Returns:
        The global GatewayLogger instance

    Raises:
        RuntimeError: If logging has not been initialized
    """
    if _gateway_logger is None:
        raise RuntimeError("Logging not initialized. Call initialize_logging() first.")
    return _gateway_logger
