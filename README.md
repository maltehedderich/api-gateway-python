# API Gateway

> [!WARNING]
> **EXPERIMENTAL CODE - NOT PRODUCTION READY**
>
> All code in this repository was generated as an experiment with Claude Code Web and **MUST BE CAREFULLY REVIEWED** before any use in production environments. This is a proof-of-concept and has not undergone the necessary security audits, testing, and validation required for production deployment.

A Python-based API Gateway that serves as a unified entry point for backend services. The gateway provides essential cross-cutting concerns including:

- Request/response logging with structured JSON format
- OAuth2-based session authentication and authorization
- Rate limiting to protect upstream services from abuse
- Reverse proxy functionality for backend services
- Comprehensive observability and metrics

## Architecture

The API Gateway is structured as a layered application with a middleware-based request processing pipeline:

- **HTTP Server Layer**: Handles TCP connections and HTTP protocol parsing
- **Routing Engine**: Maps requests to route configurations
- **Middleware Chain**: Composes authentication, authorization, rate limiting, and proxy stages
- **Logging Module**: Captures structured request/response metadata
- **Authentication & Authorization**: Validates session tokens and enforces access control
- **Rate Limiting**: Tracks and enforces request rate quotas
- **Upstream Proxy**: Forwards validated requests to backend services
- **Observability**: Exposes metrics and health check endpoints

## Project Structure

```
api-gateway-python/
├── src/
│   └── gateway/
│       ├── core/           # Core components (config, logging, metrics)
│       ├── middleware/     # Middleware implementations
│       └── utils/          # Utility functions
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── config/                # Configuration files
├── docs/                  # Documentation
├── pyproject.toml         # Project dependencies and configuration
└── README.md
```

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Poetry (for dependency management)

### Installation

1. Install Poetry if you haven't already:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:

```bash
poetry install
```

3. Activate the virtual environment:

```bash
poetry shell
```

### Code Quality Tools

The project uses several tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **Flake8**: Linting
- **mypy**: Type checking

Run all checks:

```bash
# Format code
poetry run black src tests

# Sort imports
poetry run isort src tests

# Lint
poetry run flake8 src tests

# Type check
poetry run mypy src
```

### Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html
```

## Configuration

Configuration is loaded from:

1. Configuration files (YAML/JSON) in the `config/` directory
2. Environment variables (override file-based config)
3. Command-line arguments (for specific overrides)

See `config/` directory for example configurations.

## Running the Gateway

```bash
poetry run python -m gateway.main
```

## License

[License information to be added]
