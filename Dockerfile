# Multi-stage build for optimized Python API Gateway container
# Stage 1: Builder - Install dependencies and build application
FROM python:3.10-slim as builder

# Install poetry and build dependencies
RUN pip install --no-cache-dir poetry==1.7.1

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure poetry to not create virtual environment (we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy application source code
COPY src ./src
COPY config ./config

# Stage 2: Runtime - Minimal production image
FROM python:3.10-slim

# Create non-root user for security
RUN groupadd -r gateway && useradd -r -g gateway gateway

# Install runtime dependencies only
RUN pip install --no-cache-dir poetry==1.7.1

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files
COPY --from=builder --chown=gateway:gateway /app/src ./src
COPY --from=builder --chown=gateway:gateway /app/config ./config

# Copy dependency files for reference
COPY --chown=gateway:gateway pyproject.toml poetry.lock ./

# Environment variables with defaults
ENV GATEWAY_ENV=production \
    GATEWAY_LOG_LEVEL=INFO \
    GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose HTTP port
EXPOSE 8080

# Expose metrics port (Prometheus)
EXPOSE 9090

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/live').read()" || exit 1

# Switch to non-root user
USER gateway

# Run the gateway application
CMD ["python", "-m", "gateway"]
