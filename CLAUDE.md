# API Gateway - Claude Development Guide

## Project Overview

This is a Python-based API Gateway that provides:
- **Request/Response Logging**: Comprehensive structured logging with correlation IDs
- **OAuth2 Session-Based Authorization**: Session token validation and user authorization
- **Rate Limiting**: Token bucket algorithm with Redis backend
- **Upstream Proxying**: Efficient request forwarding to backend services

## Architecture

The gateway follows a layered middleware-based architecture:

```
src/gateway/
├── core/           # Core components
│   ├── config.py       # Configuration management
│   ├── gateway.py      # Main gateway application
│   ├── handler.py      # Request handler
│   ├── logging.py      # Structured logging
│   ├── metrics.py      # Prometheus metrics
│   ├── middleware.py   # Middleware framework
│   ├── rate_limit.py   # Rate limiting logic
│   ├── routing.py      # Route matching
│   ├── server.py       # HTTP server
│   └── session_store.py # Session management
├── middleware/     # Middleware implementations
│   ├── auth.py         # Authentication middleware
│   ├── proxy.py        # Upstream proxy middleware
│   └── ratelimit.py    # Rate limiting middleware
└── utils/          # Utility functions
```

## Key Design Principles

### 1. Middleware Pipeline
The gateway processes requests through an ordered middleware chain:
1. Request logging
2. Authentication (session token validation)
3. Authorization (permission checks)
4. Rate limiting
5. Upstream proxy
6. Response logging

### 2. Stateless Design
- Gateway instances are stateless
- Session state stored in Redis
- Rate limiting state stored in Redis
- Enables horizontal scaling

### 3. Security First
- All session tokens transmitted over HTTPS only
- Cookies marked with `Secure`, `HttpOnly`, and `SameSite` flags
- No sensitive data in logs (tokens, passwords, PII)
- Input validation and sanitization

### 4. Observability
- Structured JSON logging with correlation IDs
- Prometheus metrics exposed at `/metrics`
- Health check endpoints: `/health/live` and `/health/ready`

## Development Requirements

### Python Version
- **Python 3.12** is required
- Uses modern Python features (type hints, async/await)

### Package Manager
- **uv** is used for dependency management
- Install: `pip install uv`
- Sync dependencies: `uv sync --all-extras`

### Code Quality Tools

#### 1. Ruff (Linting & Formatting)
**Configuration**: `pyproject.toml` - `[tool.ruff]`

**Formatting**:
```bash
# Check formatting
uv run ruff format --check src tests

# Auto-fix formatting
uv run ruff format src tests
```

**Linting**:
```bash
# Check for issues
uv run ruff check src tests

# Auto-fix issues
uv run ruff check --fix src tests
```

**Important Rules**:
- Line length: 100 characters
- Import sorting (isort)
- pycodestyle (E, W)
- pyflakes (F)
- pep8-naming (N)
- pyupgrade (UP)
- flake8-bugbear (B)
- flake8-comprehensions (C4)
- flake8-simplify (SIM)
- flake8-type-checking (TCH)

#### 2. mypy (Type Checking)
**Configuration**: `pyproject.toml` - `[tool.mypy]`

```bash
# Type check the codebase
uv run mypy src
```

**Requirements**:
- All functions must have type hints
- `disallow_untyped_defs = true`
- Use proper type annotations for async functions
- Import type-checking types under `TYPE_CHECKING` when needed

**Example**:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import web

async def handler(request: "web.Request") -> "web.Response":
    ...
```

#### 3. pytest (Testing)
**Configuration**: `pyproject.toml` - `[tool.pytest.ini_options]`

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=xml --cov-report=term-missing

# Run specific test
uv run pytest tests/test_auth.py::test_session_validation
```

**Requirements**:
- All tests in `tests/` directory
- Use `async` test functions with `pytest-asyncio`
- Mock external dependencies (Redis, upstream services)
- Aim for high coverage of core logic

### Redis Dependency
Tests and the application require Redis:
```bash
# Local development
docker run -d -p 6379:6379 redis:7-alpine

# Environment variables
export REDIS_HOST=localhost
export REDIS_PORT=6379
```

## GitHub Actions CI Pipeline

The CI pipeline runs on all PRs and must pass before merging:

### 1. Formatting Check
```bash
uv run ruff format --check src tests
```
**Fix**: `uv run ruff format src tests`

### 2. Linting Check
```bash
uv run ruff check src tests
```
**Fix**: `uv run ruff check --fix src tests`

### 3. Type Check
```bash
uv run mypy src
```
**Fix**: Add proper type hints to functions and fix type errors

### 4. Tests with Coverage
```bash
uv run pytest --cov=src --cov-report=xml --cov-report=term-missing
```
**Fix**: Ensure all tests pass and maintain good coverage

### 5. Security Scanning
- `pip-audit` checks for vulnerable dependencies
- CodeQL analyzes code for security issues

## Common Development Tasks

### Adding New Middleware

1. Create file in `src/gateway/middleware/`
2. Implement middleware function:
```python
from aiohttp import web
from gateway.core.middleware import Middleware

async def my_middleware(
    request: web.Request,
    handler: Middleware
) -> web.Response:
    # Pre-processing
    try:
        response = await handler(request)
        # Post-processing
        return response
    except Exception as e:
        # Error handling
        raise
```

3. Register in middleware chain (see `gateway.py`)
4. Add tests in `tests/middleware/test_my_middleware.py`
5. Update configuration schema if needed

### Adding New Routes

Routes are configured in `config/gateway.yml`:
```yaml
routes:
  - path: /api/users
    methods: [GET, POST]
    upstream: http://user-service:8080
    middleware: [auth, ratelimit]
    auth_required: true
    permissions: [read:users]
```

### Adding Metrics

```python
from prometheus_client import Counter, Histogram

my_counter = Counter(
    'my_operation_total',
    'Description of operation',
    ['label1', 'label2']
)

my_counter.labels(label1='value', label2='other').inc()
```

### Adding Logging

```python
import logging
from gateway.core.logging import get_logger

logger = get_logger(__name__)

# Structured logging
logger.info(
    "Operation completed",
    extra={
        "correlation_id": request.correlation_id,
        "user_id": request.user.id,
        "latency_ms": latency,
    }
)
```

## Critical Implementation Details

### Session Token Validation Flow
1. Extract token from Cookie header (`session_token`)
2. Validate token format and signature
3. Check expiration timestamp
4. Query Redis for session state
5. Verify session not revoked
6. Load user roles/permissions
7. Attach user context to request

### Rate Limiting Algorithm (Token Bucket)
1. Generate rate limit key (e.g., `user:{user_id}:route:{route}`)
2. Retrieve current token count from Redis
3. Calculate tokens to add based on elapsed time
4. Check if request can be allowed
5. Decrement token count atomically
6. Return rate limit headers

### Error Response Format
All errors return consistent JSON:
```json
{
  "error": "error_code",
  "message": "Human-readable description",
  "correlation_id": "req-abc123",
  "timestamp": "2025-11-17T12:34:56.789Z"
}
```

### Security Headers
Always include:
- `Strict-Transport-Security`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`

## Testing Strategy

### Unit Tests
- Test individual components in isolation
- Mock external dependencies (Redis, upstream services)
- Cover edge cases and error conditions

### Integration Tests
- Test end-to-end request flow
- Use real Redis instance (test container)
- Mock upstream services with aiohttp test server

### Test Structure
```python
import pytest
from aiohttp import web
from gateway.middleware.auth import auth_middleware

@pytest.mark.asyncio
async def test_auth_middleware_valid_token(
    aiohttp_client,
    redis_client,
    mock_session
):
    # Arrange
    app = web.Application()
    # ... setup

    # Act
    resp = await client.get("/api/resource")

    # Assert
    assert resp.status == 200
```

## Performance Considerations

### Async/Await
- All I/O operations must be async
- Use `aiohttp` for HTTP client/server
- Use `aioredis` for Redis operations
- Avoid blocking operations in request handlers

### Connection Pooling
- Redis: Connection pool configured in session_store.py
- Upstream services: aiohttp ClientSession with connection pooling
- Reuse connections to minimize overhead

### Caching
- Session data cached in Redis with TTL
- User permissions cached for session duration
- Configuration loaded at startup and cached in memory

## Troubleshooting

### Common Issues

**Mypy Errors**:
- Ensure all function signatures have type hints
- Use `from typing import TYPE_CHECKING` for circular imports
- Check `ignore_missing_imports` for third-party libraries

**Ruff Format Issues**:
- Line too long: Break into multiple lines or use implicit string concatenation
- Import sorting: Let ruff auto-fix with `--fix`

**Test Failures**:
- Redis not running: Start Redis container
- Async issues: Ensure `@pytest.mark.asyncio` decorator
- Timing issues: Use `await asyncio.sleep(0)` to yield control

**Rate Limiting Issues**:
- Clock skew: Use server time, not client time
- Redis key expiration: Ensure TTL set correctly
- Atomic operations: Use Redis Lua scripts for consistency

## Pre-Commit Checklist

Before committing code:
- [ ] Run `uv run ruff format src tests`
- [ ] Run `uv run ruff check --fix src tests`
- [ ] Run `uv run mypy src` (no errors)
- [ ] Run `uv run pytest` (all tests pass)
- [ ] Add/update tests for new functionality
- [ ] Update CLAUDE.md if architecture changes
- [ ] Check no sensitive data in logs or code
- [ ] Verify error messages are user-friendly

## Environment Variables

Required for production:
```bash
# Server
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8080

# Redis
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_PASSWORD=secret

# Security
SESSION_SECRET=your-secret-key-here
COOKIE_SECURE=true
COOKIE_DOMAIN=.example.com

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## Additional Resources

- **Design Spec**: See `API_GATEWAY_DESIGN_SPEC.md` for detailed architecture
- **README**: See `README.md` for project overview and setup
- **Configuration**: See `config/gateway.yml` for route configuration
- **Tests**: See `tests/` for examples of testing patterns

## Questions or Issues?

When working on this codebase:
1. Review the design spec for architectural context
2. Check existing tests for usage patterns
3. Maintain consistency with established patterns
4. Prioritize security, observability, and performance
5. Ensure all CI checks pass before submitting PR
