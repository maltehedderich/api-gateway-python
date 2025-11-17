"""Configuration management module for the API Gateway.

This module handles loading and validating configuration from multiple sources:
- Configuration files (YAML)
- Environment variables
- Command-line arguments
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8080, ge=1, le=65535, description="Server port")
    tls_enabled: bool = Field(default=False, description="Enable TLS/HTTPS")
    tls_cert_path: str | None = Field(default=None, description="Path to TLS certificate")
    tls_key_path: str | None = Field(default=None, description="Path to TLS private key")
    connection_timeout: int = Field(default=60, ge=1, description="Connection timeout in seconds")
    keepalive_timeout: int = Field(default=75, ge=1, description="Keep-alive timeout in seconds")
    max_connections: int = Field(default=1000, ge=1, description="Maximum concurrent connections")

    @field_validator("tls_cert_path", "tls_key_path")
    @classmethod
    def validate_tls_paths(cls, v: str | None, info: Any) -> str | None:
        """Validate TLS certificate and key paths exist if TLS is enabled."""
        if v is not None and not Path(v).exists():
            raise ValueError(f"TLS file not found: {v}")
        return v


class RouteConfig(BaseModel):
    """Route configuration."""

    id: str = Field(description="Unique route identifier")
    path_pattern: str = Field(description="URL path pattern")
    methods: list[str] = Field(description="Allowed HTTP methods")
    upstream_url: str = Field(description="Backend service URL")
    auth_required: bool = Field(default=True, description="Whether authentication is required")
    auth_roles: list[str] = Field(
        default_factory=list, description="Required roles for authorization"
    )
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json or text)")
    output: str = Field(default="stdout", description="Log output (stdout, file path, etc.)")
    correlation_id_header: str = Field(
        default="X-Request-ID", description="Header name for correlation ID"
    )
    redact_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Cookie", "Set-Cookie"],
        description="Headers to redact from logs",
    )

    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper


class SessionConfig(BaseModel):
    """Session and authentication configuration."""

    cookie_name: str = Field(default="session_token", description="Session cookie name")
    session_store_url: str = Field(
        default="redis://localhost:6379/0", description="Session store connection URL"
    )
    token_signing_secret: str | None = Field(default=None, description="Secret for signing tokens")
    token_ttl: int = Field(default=3600, ge=60, description="Token TTL in seconds")
    refresh_enabled: bool = Field(default=True, description="Enable token refresh")
    refresh_threshold: int = Field(default=300, ge=0, description="Refresh threshold in seconds")


class RateLimitRule(BaseModel):
    """Rate limiting rule configuration."""

    name: str = Field(description="Rule name")
    key_type: str = Field(default="user", description="Key type (ip, user, route, composite)")
    algorithm: str = Field(default="token_bucket", description="Rate limiting algorithm")
    limit: int = Field(ge=1, description="Request limit")
    window: int = Field(ge=1, description="Time window in seconds")
    burst: int | None = Field(default=None, ge=1, description="Burst allowance")
    routes: list[str] = Field(
        default_factory=list, description="Routes this rule applies to (empty = all)"
    )

    @field_validator("key_type")
    @classmethod
    def validate_key_type(cls, v: str) -> str:
        """Validate key type is valid."""
        valid_types = ["ip", "user", "route", "composite"]
        if v not in valid_types:
            raise ValueError(f"Invalid key_type: {v}. Must be one of {valid_types}")
        return v

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        """Validate algorithm is valid."""
        valid_algorithms = ["token_bucket", "fixed_window", "sliding_window"]
        if v not in valid_algorithms:
            raise ValueError(f"Invalid algorithm: {v}. Must be one of {valid_algorithms}")
        return v


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    enabled: bool = Field(default=True, description="Enable rate limiting")
    store_url: str = Field(
        default="redis://localhost:6379/1", description="Rate limit store connection URL"
    )
    fail_mode: str = Field(
        default="open", description="Fail mode (open or closed) when store unavailable"
    )
    rules: list[RateLimitRule] = Field(default_factory=list, description="Rate limiting rules")

    @field_validator("fail_mode")
    @classmethod
    def validate_fail_mode(cls, v: str) -> str:
        """Validate fail mode is valid."""
        valid_modes = ["open", "closed"]
        if v not in valid_modes:
            raise ValueError(f"Invalid fail_mode: {v}. Must be one of {valid_modes}")
        return v


class UpstreamConfig(BaseModel):
    """Upstream proxy configuration."""

    connection_timeout: int = Field(default=5, ge=1, description="Connection timeout in seconds")
    request_timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    pool_size: int = Field(default=100, ge=1, description="Connection pool size per host")
    retry_enabled: bool = Field(default=False, description="Enable retry on failures")
    retry_attempts: int = Field(default=2, ge=1, description="Maximum retry attempts")


class MetricsConfig(BaseModel):
    """Metrics and observability configuration."""

    enabled: bool = Field(default=True, description="Enable metrics collection")
    endpoint: str = Field(default="/metrics", description="Metrics endpoint path")
    health_endpoint: str = Field(default="/health", description="Health check endpoint path")
    liveness_endpoint: str = Field(default="/health/live", description="Liveness endpoint path")
    readiness_endpoint: str = Field(default="/health/ready", description="Readiness endpoint path")


class GatewayConfig(BaseModel):
    """Main gateway configuration."""

    environment: str = Field(default="development", description="Environment name")
    server: ServerConfig = Field(default_factory=ServerConfig)
    routes: list[RouteConfig] = Field(default_factory=list)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    rate_limiting: RateLimitConfig = Field(default_factory=RateLimitConfig)
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)


class ConfigLoader:
    """Loads and validates configuration from multiple sources."""

    def __init__(self, config_path: str | None = None):
        """Initialize the configuration loader.

        Args:
            config_path: Path to configuration file. If None, uses environment variable
                        GATEWAY_CONFIG_PATH or defaults to config/gateway.yaml
        """
        self.config_path = self._resolve_config_path(config_path)

    def _resolve_config_path(self, config_path: str | None) -> Path:
        """Resolve configuration file path."""
        if config_path:
            return Path(config_path)

        env_path = os.getenv("GATEWAY_CONFIG_PATH")
        if env_path:
            return Path(env_path)

        # Try environment-specific config first
        env = os.getenv("GATEWAY_ENV", "development")
        env_specific = Path(f"config/gateway.{env}.yaml")
        if env_specific.exists():
            return env_specific

        return Path("config/gateway.yaml")

    def load(self) -> GatewayConfig:
        """Load and validate configuration.

        Returns:
            Validated GatewayConfig instance

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
        """
        # Load from file
        config_dict = self._load_from_file()

        # Override with environment variables
        config_dict = self._override_from_env(config_dict)

        # Validate and create config object
        try:
            config = GatewayConfig(**config_dict)
        except Exception as e:
            raise ValueError(f"Configuration validation failed: {e}") from e

        return config

    def _load_from_file(self) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            # Return empty dict if file doesn't exist, will use defaults
            return {}

        with open(self.config_path) as f:
            config_dict = yaml.safe_load(f) or {}

        return config_dict

    def _override_from_env(self, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Override configuration with environment variables.

        Environment variables follow the pattern: GATEWAY_<SECTION>_<KEY>
        For example: GATEWAY_SERVER_PORT=8080
        """
        # Server config
        if host := os.getenv("GATEWAY_SERVER_HOST"):
            config_dict.setdefault("server", {})["host"] = host
        if port := os.getenv("GATEWAY_SERVER_PORT"):
            config_dict.setdefault("server", {})["port"] = int(port)
        if tls := os.getenv("GATEWAY_SERVER_TLS_ENABLED"):
            config_dict.setdefault("server", {})["tls_enabled"] = tls.lower() == "true"

        # Logging config
        if log_level := os.getenv("GATEWAY_LOG_LEVEL"):
            config_dict.setdefault("logging", {})["level"] = log_level
        if log_format := os.getenv("GATEWAY_LOG_FORMAT"):
            config_dict.setdefault("logging", {})["format"] = log_format

        # Session config
        if session_store := os.getenv("GATEWAY_SESSION_STORE_URL"):
            config_dict.setdefault("session", {})["session_store_url"] = session_store
        if token_secret := os.getenv("GATEWAY_TOKEN_SIGNING_SECRET"):
            config_dict.setdefault("session", {})["token_signing_secret"] = token_secret

        # Rate limiting config
        if rl_store := os.getenv("GATEWAY_RATELIMIT_STORE_URL"):
            config_dict.setdefault("rate_limiting", {})["store_url"] = rl_store
        if rl_enabled := os.getenv("GATEWAY_RATELIMIT_ENABLED"):
            config_dict.setdefault("rate_limiting", {})["enabled"] = rl_enabled.lower() == "true"

        # Environment
        if env := os.getenv("GATEWAY_ENV"):
            config_dict["environment"] = env

        return config_dict


def load_config(config_path: str | None = None) -> GatewayConfig:
    """Load configuration (convenience function).

    Args:
        config_path: Optional path to configuration file

    Returns:
        Validated GatewayConfig instance
    """
    loader = ConfigLoader(config_path)
    return loader.load()
