# API Gateway

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

### Local Development

```bash
# With Poetry
poetry run python -m gateway

# Or using Make
make run-local

# With Docker
make docker-build
make docker-run
```

### Using Docker Compose

```bash
docker-compose up -d
```

## Deployment

### Kubernetes Deployment

The gateway is designed for production deployment on Kubernetes with comprehensive monitoring and auto-scaling.

**Quick Deploy:**

```bash
# Using Make (recommended)
make deploy-all

# Or manually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

**Prerequisites:**
- Kubernetes cluster (1.24+)
- Redis instance
- kubectl configured

**Documentation:**
- [Deployment Guide](docs/DEPLOYMENT.md) - Complete deployment instructions
- [Operational Runbook](docs/RUNBOOK.md) - Day-to-day operations and troubleshooting
- [Kubernetes README](k8s/README.md) - Kubernetes manifests documentation

### Monitoring and Observability

The gateway exposes Prometheus metrics and includes:
- Pre-configured Grafana dashboards
- Alerting rules for critical issues
- Health check endpoints
- Structured JSON logging

**Metrics endpoint:** `http://localhost:9090/metrics`

**Health checks:**
- Liveness: `/health/live`
- Readiness: `/health/ready`
- Detailed: `/health`

## Available Make Commands

Run `make help` to see all available commands:

```bash
make help              # Show all available commands
make install           # Install dependencies
make test              # Run tests
make lint              # Run linters
make docker-build      # Build Docker image
make deploy-all        # Deploy to Kubernetes
make k8s-status        # Check deployment status
```

## Design and Architecture

For detailed information about the architecture, components, and design decisions, see the [API Gateway Design Specification](API_GATEWAY_DESIGN_SPEC.md).

Key features:
- Middleware-based request processing pipeline
- Pluggable authentication and authorization
- Flexible rate limiting with multiple algorithms
- Connection pooling for upstream services
- Horizontal scaling with stateless design
- Comprehensive error handling and logging

## Performance

- **Throughput**: Designed to handle 10,000+ requests/second per instance
- **Latency**: p95 < 50ms (excluding upstream latency)
- **Availability**: 99.9% SLA with proper deployment
- **Auto-scaling**: HorizontalPodAutoscaler for automatic scaling

## Contributing

1. Ensure all tests pass: `make test`
2. Run linters and formatters: `make lint format`
3. Update documentation as needed
4. Follow the existing code style

## License

[License information to be added]
