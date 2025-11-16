"""Unit tests for configuration module."""

import os
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from gateway.core.config import (
    ConfigLoader,
    GatewayConfig,
    LoggingConfig,
    RateLimitConfig,
    ServerConfig,
    SessionConfig,
    load_config,
)


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary configuration file."""
    config_data = {
        "environment": "test",
        "server": {"host": "localhost", "port": 9999},
        "logging": {"level": "DEBUG"},
    }
    config_file = tmp_path / "test_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    return config_file


def test_server_config_defaults() -> None:
    """Test ServerConfig with default values."""
    config = ServerConfig()
    assert config.host == "0.0.0.0"
    assert config.port == 8080
    assert config.tls_enabled is False


def test_server_config_validation() -> None:
    """Test ServerConfig validation."""
    # Valid port
    config = ServerConfig(port=8080)
    assert config.port == 8080

    # Invalid port (too low)
    with pytest.raises(ValueError):
        ServerConfig(port=0)

    # Invalid port (too high)
    with pytest.raises(ValueError):
        ServerConfig(port=70000)


def test_logging_config_defaults() -> None:
    """Test LoggingConfig with default values."""
    config = LoggingConfig()
    assert config.level == "INFO"
    assert config.format == "json"
    assert "Authorization" in config.redact_headers


def test_logging_config_level_validation() -> None:
    """Test LoggingConfig log level validation."""
    # Valid levels
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        config = LoggingConfig(level=level)
        assert config.level == level

    # Case insensitive
    config = LoggingConfig(level="debug")
    assert config.level == "DEBUG"

    # Invalid level
    with pytest.raises(ValueError, match="Invalid log level"):
        LoggingConfig(level="INVALID")


def test_session_config_defaults() -> None:
    """Test SessionConfig with default values."""
    config = SessionConfig()
    assert config.cookie_name == "session_token"
    assert config.token_ttl == 3600
    assert config.refresh_enabled is True


def test_rate_limit_config_validation() -> None:
    """Test RateLimitConfig validation."""
    config = RateLimitConfig(fail_mode="open")
    assert config.fail_mode == "open"

    config = RateLimitConfig(fail_mode="closed")
    assert config.fail_mode == "closed"

    with pytest.raises(ValueError, match="Invalid fail_mode"):
        RateLimitConfig(fail_mode="invalid")


def test_gateway_config_defaults() -> None:
    """Test GatewayConfig with all defaults."""
    config = GatewayConfig()
    assert config.environment == "development"
    assert config.server.port == 8080
    assert config.logging.level == "INFO"
    assert config.rate_limiting.enabled is True


def test_config_loader_file_loading(temp_config_file: Path) -> None:
    """Test ConfigLoader loads from file correctly."""
    loader = ConfigLoader(config_path=str(temp_config_file))
    config = loader.load()

    assert config.environment == "test"
    assert config.server.host == "localhost"
    assert config.server.port == 9999
    assert config.logging.level == "DEBUG"


def test_config_loader_missing_file() -> None:
    """Test ConfigLoader handles missing file gracefully."""
    loader = ConfigLoader(config_path="nonexistent.yaml")
    # Should not raise error, just use defaults
    config = loader.load()
    assert config.environment == "development"


def test_config_loader_env_override(
    temp_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test ConfigLoader overrides from environment variables."""
    # Set environment variables
    monkeypatch.setenv("GATEWAY_SERVER_PORT", "7777")
    monkeypatch.setenv("GATEWAY_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("GATEWAY_ENV", "production")

    loader = ConfigLoader(config_path=str(temp_config_file))
    config = loader.load()

    # Environment variables should override file values
    assert config.server.port == 7777
    assert config.logging.level == "ERROR"
    assert config.environment == "production"


def test_config_loader_env_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ConfigLoader resolves config path from environment."""
    config_data = {"environment": "env_test"}
    config_file = tmp_path / "from_env.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    monkeypatch.setenv("GATEWAY_CONFIG_PATH", str(config_file))

    loader = ConfigLoader()
    config = loader.load()
    assert config.environment == "env_test"


def test_load_config_convenience_function(temp_config_file: Path) -> None:
    """Test load_config convenience function."""
    config = load_config(config_path=str(temp_config_file))
    assert isinstance(config, GatewayConfig)
    assert config.environment == "test"


def test_config_validation_error() -> None:
    """Test configuration validation catches errors."""
    loader = ConfigLoader()
    # Create invalid config by directly modifying the loaded dict
    loader._load_from_file = lambda: {"server": {"port": "invalid"}}  # type: ignore

    with pytest.raises(ValueError, match="Configuration validation failed"):
        loader.load()
