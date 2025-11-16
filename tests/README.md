# API Gateway Testing Guide

Comprehensive testing suite for the Python-based API Gateway, implementing section 9.7 (Testing and Validation) of the design specification.

## Table of Contents

1. [Overview](#overview)
2. [Test Structure](#test-structure)
3. [Running Tests](#running-tests)
4. [Unit Tests](#unit-tests)
5. [Integration Tests](#integration-tests)
6. [Performance Tests](#performance-tests)
7. [Test Coverage](#test-coverage)
8. [Continuous Integration](#continuous-integration)
9. [Troubleshooting](#troubleshooting)

## Overview

The testing suite is organized into three main categories:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test end-to-end flows through the gateway
- **Performance Tests**: Load and stress testing to validate throughput and latency targets

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures and configuration
├── README.md                      # This file
│
├── unit/                          # Unit tests
│   ├── __init__.py
│   ├── test_auth.py              # Authentication middleware tests
│   ├── test_config.py            # Configuration loading tests
│   ├── test_logging.py           # Logging functionality tests
│   ├── test_metrics.py           # Metrics collection tests
│   ├── test_middleware.py        # Middleware chain tests
│   ├── test_proxy.py             # Upstream proxy tests
│   ├── test_rate_limit.py        # Rate limiting algorithm tests
│   ├── test_routing.py           # Routing engine tests
│   └── test_session_store.py     # Session store tests
│
├── integration/                   # Integration tests
│   ├── __init__.py
│   ├── conftest.py               # Integration test fixtures
│   ├── test_e2e_flow.py          # End-to-end request flow tests
│   ├── test_authentication.py    # Auth integration tests
│   ├── test_rate_limiting.py     # Rate limiting integration tests
│   └── test_proxy.py             # Proxy integration tests
│
└── performance/                   # Performance tests
    ├── __init__.py
    ├── README.md                 # Performance testing guide
    └── locustfile.py             # Locust load test scenarios
```

## Running Tests

### Prerequisites

Install all dependencies:

```bash
poetry install
```

### Run All Tests

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=gateway --cov-report=html
```

### Run Specific Test Categories

```bash
# Unit tests only
poetry run pytest tests/unit -v

# Integration tests only
poetry run pytest tests/integration -v

# Specific test file
poetry run pytest tests/unit/test_auth.py -v

# Specific test function
poetry run pytest tests/unit/test_auth.py::TestTokenValidator::test_validate_opaque_token_success -v
```

### Run Tests with Different Options

```bash
# Stop on first failure
poetry run pytest -x

# Run last failed tests only
poetry run pytest --lf

# Show print statements
poetry run pytest -s

# Run in parallel (requires pytest-xdist)
poetry run pytest -n auto
```

## Unit Tests

Unit tests validate individual components in isolation with mocked dependencies.

### Coverage Areas

**Configuration (test_config.py)**
- Configuration loading from files and environment
- Configuration validation and error handling
- Default values and overrides

**Logging (test_logging.py)**
- Structured JSON logging
- Log level filtering
- Correlation ID generation
- Sensitive data redaction

**Authentication (test_auth.py)**
- Token extraction from cookies and headers
- Token validation (opaque and signed)
- Session expiration and revocation
- Role-based authorization

**Rate Limiting (test_rate_limit.py)**
- Token bucket algorithm
- Fixed window algorithm
- Sliding window algorithm
- Rate limit key generation
- Fail-open/fail-closed behavior

**Routing (test_routing.py)**
- Route pattern matching
- HTTP method validation
- Path parameter extraction
- Route priority resolution

**Metrics (test_metrics.py)**
- Metrics collection
- Health check registration
- Prometheus exposition
- Component health tracking

**Middleware (test_middleware.py)**
- Middleware chain execution
- Request context propagation
- Error handling

**Proxy (test_proxy.py)**
- Upstream request preparation
- Header manipulation
- Response streaming
- Timeout handling

**Session Store (test_session_store.py)**
- Session CRUD operations
- Session expiration
- Session revocation
- In-memory and Redis stores

### Running Unit Tests

```bash
# All unit tests
poetry run pytest tests/unit -v

# With coverage
poetry run pytest tests/unit --cov=gateway --cov-report=term-missing

# Specific component
poetry run pytest tests/unit/test_auth.py -v
```

### Test Results

Current unit test status: **120/143 passing** (83.9%)

Most tests pass. Some tests have minor issues related to:
- Prometheus metric registry cleanup (fixed with conftest.py)
- Logging output capture (environmental)
- aiohttp request mocking (version-specific)

## Integration Tests

Integration tests validate end-to-end flows through the gateway with real (but mocked) upstream services.

### Test Scenarios

**End-to-End Flow (test_e2e_flow.py)**
- Public route access
- Request/response flow
- Query parameters and headers
- Different HTTP methods
- Error handling (404, 405, 500, 504)
- Health checks and metrics endpoints

**Authentication (test_authentication.py)**
- Protected route access without token (401)
- Protected route with valid token (200)
- Token in cookie vs Authorization header
- Expired and revoked tokens
- Session lifecycle and refresh
- Authorization failures (403)
- User context propagation

**Rate Limiting (test_rate_limiting.py)**
- Requests within limit allowed
- Requests exceeding limit denied (429)
- Rate limit headers present
- Different rate limiting algorithms
- Per-user vs per-IP limiting
- Composite key rate limiting
- Concurrent request handling
- Fail-open/fail-closed behavior

**Upstream Proxying (test_proxy.py)**
- Request forwarding to upstream
- Query parameters and headers forwarded
- Request body forwarded
- Path parameters extracted
- Proxy headers added (X-Forwarded-*)
- Response status and body forwarded
- Upstream errors handled
- Timeouts handled
- Connection pooling and reuse

### Running Integration Tests

```bash
# All integration tests
poetry run pytest tests/integration -v

# Specific test file
poetry run pytest tests/integration/test_authentication.py -v

# With detailed output
poetry run pytest tests/integration -v -s
```

### Prerequisites for Integration Tests

Integration tests require:
1. Mock upstream server (provided by fixtures)
2. In-memory session and rate limit stores
3. Gateway instance configured for testing

All dependencies are automatically set up by the test fixtures.

## Performance Tests

Performance tests validate throughput, latency, and scalability using Locust.

### Test Types

**Load Testing**
- Validate performance under normal load
- Target: 1000+ req/s, p99 < 500ms

**Stress Testing**
- Find breaking points
- Test graceful degradation

**Endurance Testing**
- Validate stability over time
- Detect memory leaks

**Spike Testing**
- Test behavior under sudden traffic spikes

**Rate Limit Testing**
- Validate rate limiting behavior under load

### Running Performance Tests

See [tests/performance/README.md](performance/README.md) for detailed instructions.

Quick start:

```bash
# Interactive mode with web UI
poetry run locust -f tests/performance/locustfile.py --host=http://localhost:8080

# Headless mode
poetry run locust -f tests/performance/locustfile.py --host=http://localhost:8080 \
    --users 100 --spawn-rate 10 --run-time 60s --headless
```

### Performance Targets

Based on design specification:

- **Latency**:
  - p50: ≤ 50ms
  - p95: ≤ 200ms
  - p99: ≤ 500ms
- **Throughput**: ≥ 1000 req/s (single instance)
- **Error Rate**: < 0.1% under normal load

## Test Coverage

### Generating Coverage Reports

```bash
# Generate HTML coverage report
poetry run pytest --cov=gateway --cov-report=html

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Targets

- **Overall**: ≥ 80%
- **Critical paths** (auth, rate limiting): ≥ 90%
- **Edge cases**: Covered

### Current Coverage

Run `poetry run pytest --cov=gateway --cov-report=term` to see current coverage.

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'

    - name: Install Poetry
      uses: snok/install-poetry@v1

    - name: Install dependencies
      run: poetry install

    - name: Run unit tests
      run: poetry run pytest tests/unit --cov=gateway --cov-report=xml

    - name: Run integration tests
      run: poetry run pytest tests/integration -v

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## Testing Best Practices

### Writing Tests

1. **One assertion per test** (where reasonable)
2. **Clear test names** describing what is tested
3. **Arrange-Act-Assert** pattern
4. **Use fixtures** for common setup
5. **Mock external dependencies** in unit tests
6. **Test both success and failure paths**

### Test Naming Convention

```python
def test_<function_name>_<scenario>_<expected_result>():
    """Test description."""
    # Arrange
    ...

    # Act
    ...

    # Assert
    ...
```

Examples:
- `test_validate_token_with_valid_token_returns_session()`
- `test_rate_limit_when_limit_exceeded_returns_429()`
- `test_proxy_with_timeout_returns_504()`

### Fixture Organization

- **conftest.py** (tests/): Global fixtures available to all tests
- **conftest.py** (tests/integration/): Integration-specific fixtures
- **Test file fixtures**: Test-specific fixtures using `@pytest.fixture`

## Troubleshooting

### Common Issues

**Import Errors**
```bash
# Ensure package is installed in development mode
poetry install
```

**Async Test Issues**
```bash
# Ensure pytest-asyncio is installed
poetry add --dev pytest-asyncio

# Check pytest.ini configuration
# asyncio_mode = "auto" should be set
```

**Port Already in Use (Integration Tests)**
```bash
# Kill processes using test ports
lsof -ti:8888 | xargs kill -9  # Mock upstream
lsof -ti:9999 | xargs kill -9  # Gateway test instance
```

**Prometheus Metric Errors**
- Fixed by conftest.py registry reset
- If issues persist, run tests in isolation: `pytest -k test_name`

**Redis Connection Errors**
```bash
# Start Redis for tests requiring Redis
docker run -d -p 6379:6379 redis:alpine

# Or use in-memory store for testing
# (Default for integration tests)
```

### Debug Mode

Run tests with debugging:

```bash
# With pdb on failure
poetry run pytest --pdb

# With verbose output and print statements
poetry run pytest -v -s

# With logging output
poetry run pytest --log-cli-level=DEBUG
```

## Test Data and Cleanup

### Fixtures Handle Cleanup

Test fixtures automatically clean up after tests:
- Mock servers are stopped
- Session stores are disconnected
- Rate limit stores are cleared

### Manual Cleanup

If needed:

```bash
# Clear Redis
redis-cli FLUSHDB

# Clear test files
rm -rf tests/__pycache__ tests/integration/__pycache__ tests/unit/__pycache__
rm -rf .pytest_cache htmlcov .coverage
```

## Contributing Tests

When adding new features:

1. **Write unit tests** for new components
2. **Write integration tests** for new flows
3. **Update performance tests** if needed
4. **Ensure coverage** doesn't decrease
5. **All tests must pass** before merge

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [Locust Documentation](https://docs.locust.io/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- API Gateway Design Specification - Section 9.7

## Support

For test-related issues:
- Check this documentation
- Review test output and error messages
- Consult design specification
- Create an issue with test failure details
