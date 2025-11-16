># Performance and Load Testing

This directory contains performance and load tests for the API Gateway using Locust.

## Prerequisites

Install dependencies:

```bash
poetry install
```

## Running Load Tests

### Interactive Mode (with Web UI)

Start Locust with the web interface:

```bash
poetry run locust -f tests/performance/locustfile.py --host=http://localhost:8080
```

Then open your browser to http://localhost:8089 to configure and run tests.

### Headless Mode

Run tests without the web UI:

```bash
# Basic load test: 100 users, 10 users spawned per second, run for 1 minute
poetry run locust -f tests/performance/locustfile.py --host=http://localhost:8080 \
    --users 100 --spawn-rate 10 --run-time 60s --headless

# Generate HTML report
poetry run locust -f tests/performance/locustfile.py --host=http://localhost:8080 \
    --users 100 --spawn-rate 10 --run-time 60s --headless \
    --html=reports/load_test_report.html
```

### Quick Test Scenarios

Use the provided scripts to run predefined scenarios:

```bash
# Light load test (validate basic functionality)
./scripts/run_load_test.sh light

# Medium load test (simulate normal traffic)
./scripts/run_load_test.sh medium

# Heavy load test (stress test)
./scripts/run_load_test.sh heavy

# Rate limit test (specifically test rate limiting)
./scripts/run_load_test.sh ratelimit
```

## User Types

The load tests include different user types to simulate various scenarios:

### PublicRouteUser
- Simulates unauthenticated users
- Accesses public endpoints
- Wait time: 1-3 seconds between requests
- Tasks: GET /api/hello, POST /api/echo, query parameters

### AuthenticatedUser
- Simulates authenticated users
- Uses session tokens
- Wait time: 0.5-2 seconds between requests
- Tasks: GET /api/users/{id}, POST/PUT to protected endpoints

### RateLimitTestUser
- Specifically tests rate limiting
- Very aggressive request pattern (0.1s pacing)
- Expects and handles 429 Too Many Requests responses

### HighThroughputUser
- Simulates high-throughput scenarios
- Minimal wait time (0.1-0.5s)
- Tests gateway under sustained load

### MixedWorkloadUser
- Realistic mixed workload
- 50% authenticated, 50% unauthenticated
- Mix of read/write operations with varying payload sizes

### StressTestUser
- Stress testing with extreme load
- Very aggressive timing (0.01-0.1s)
- Large payloads (up to 100KB)

### HealthCheckMonitor
- Continuously monitors health endpoints
- 5-second intervals
- Verifies gateway health during load

## Test Scenarios

### Baseline Performance Test
Validate performance targets under normal load:

```bash
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 50 \
    --spawn-rate 5 \
    --run-time 5m \
    --headless \
    --only-summary \
    --html=reports/baseline_performance.html
```

**Expected Results:**
- **Throughput**: ≥ 1000 requests/second
- **Latency (p50)**: ≤ 50ms
- **Latency (p95)**: ≤ 200ms
- **Latency (p99)**: ≤ 500ms
- **Error Rate**: < 0.1%

### Rate Limiting Test
Test rate limiting behavior:

```bash
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 20 \
    --spawn-rate 5 \
    --run-time 2m \
    --headless \
    --user-classes RateLimitTestUser \
    --html=reports/rate_limit_test.html
```

**Expected Results:**
- **429 Responses**: Present when limits exceeded
- **Rate Limit Headers**: X-RateLimit-* headers in responses
- **Recovery**: System recovers after rate limit window resets

### Stress Test
Find breaking points and maximum capacity:

```bash
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 500 \
    --spawn-rate 50 \
    --run-time 10m \
    --headless \
    --user-classes StressTestUser \
    --html=reports/stress_test.html
```

**Expected Results:**
- **Graceful Degradation**: System slows but doesn't crash
- **Error Handling**: Errors are handled gracefully
- **Recovery**: System recovers when load decreases

### Endurance Test
Test stability over extended period:

```bash
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 100 \
    --spawn-rate 10 \
    --run-time 1h \
    --headless \
    --user-classes MixedWorkloadUser \
    --html=reports/endurance_test.html
```

**Expected Results:**
- **Stable Performance**: No degradation over time
- **No Memory Leaks**: Memory usage remains stable
- **No Resource Exhaustion**: Connection pools, file descriptors stable

### Spike Test
Test behavior under sudden traffic spikes:

```bash
# Start with low load
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 10 \
    --spawn-rate 10 \
    --run-time 1m \
    --headless

# Then spike to high load
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 500 \
    --spawn-rate 100 \
    --run-time 2m \
    --headless
```

### Authentication & Authorization Load Test
Test auth-specific performance:

```bash
poetry run locust -f tests/performance/locustfile.py \
    --host=http://localhost:8080 \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --headless \
    --user-classes AuthenticatedUser \
    --html=reports/auth_load_test.html
```

## Performance Targets

Based on the design specification, the API Gateway should meet these targets:

### Latency Targets
- **p50 (median)**: ≤ 50ms
- **p90**: ≤ 100ms
- **p95**: ≤ 200ms
- **p99**: ≤ 500ms

### Throughput Targets
- **Minimum**: 1,000 requests/second (single instance)
- **Recommended**: 5,000 requests/second (with scaling)

### Error Rates
- **Target**: < 0.1% under normal load
- **Maximum**: < 1% under stress

### Resource Utilization
- **CPU**: < 80% under normal load
- **Memory**: Stable, no leaks
- **Connections**: Efficient pooling and reuse

## Monitoring During Tests

### Watch Metrics
```bash
# In another terminal, watch metrics during load test
watch -n 1 'curl -s http://localhost:8080/metrics | grep -E "(gateway_requests_total|gateway_request_duration)"'
```

### Watch Health
```bash
# Monitor health status
watch -n 5 'curl -s http://localhost:8080/health | jq .'
```

### System Resources
```bash
# Monitor system resources
docker stats  # If running in Docker
# or
htop  # If running locally
```

## Analyzing Results

### Key Metrics to Review

1. **Request Rate**: Requests per second handled
2. **Response Times**: p50, p90, p95, p99 latencies
3. **Error Rate**: Percentage of failed requests
4. **Throughput**: Total requests and data transferred
5. **Resource Usage**: CPU, memory, connections

### Interpreting Results

**Good Performance:**
- Response times within targets
- Low error rate (< 0.1%)
- Stable resource usage
- No timeouts or connection errors

**Performance Issues:**
- High latency (p99 > 500ms)
- Increasing error rates
- Resource exhaustion (CPU > 90%)
- Connection pool exhaustion

**Rate Limiting Working:**
- 429 responses when limits exceeded
- Rate limit headers present
- System recovers after window reset

## Troubleshooting

### High Latency
- Check upstream service performance
- Review database/cache query times
- Check for connection pool saturation
- Review middleware overhead

### High Error Rates
- Check gateway logs for errors
- Verify upstream service health
- Check rate limiting configuration
- Review session store availability

### Low Throughput
- Increase number of workers/threads
- Optimize database connection pooling
- Check for blocking I/O operations
- Review async operation efficiency

## Test Data Cleanup

After load tests, you may need to clean up test data:

```bash
# Clear rate limiting state
redis-cli FLUSHDB  # If using Redis

# Clear test sessions
# (Method depends on session store implementation)
```

## Continuous Performance Testing

Integrate performance tests into CI/CD:

```yaml
# Example GitHub Actions workflow
- name: Run Performance Tests
  run: |
    poetry run locust -f tests/performance/locustfile.py \
        --host=http://localhost:8080 \
        --users 50 \
        --spawn-rate 5 \
        --run-time 60s \
        --headless \
        --only-summary
```

## References

- [Locust Documentation](https://docs.locust.io/)
- [Performance Testing Best Practices](https://docs.locust.io/en/stable/writing-a-locustfile.html)
- API Gateway Design Specification - Section 8 (Scalability and Performance)
