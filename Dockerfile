# Multi-stage Dockerfile for API Gateway
# Stage 1: Build stage with uv for dependency installation
FROM python:3.12-slim AS builder

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv==0.5.0

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# We sync production dependencies only (no dev extras)
RUN uv sync --no-dev --frozen

# Stage 2: Runtime stage
FROM python:3.12-slim

# Set metadata labels
LABEL maintainer="API Gateway Team"
LABEL description="Python-based API Gateway with OAuth2 and rate limiting"
LABEL version="0.1.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=8080

# Create non-root user for security
RUN groupadd -r gateway && useradd -r -g gateway -u 1000 gateway

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source code
COPY src/ /app/src/
COPY config/ /app/config/

# Create directories for logs and temporary files
RUN mkdir -p /app/logs /app/tmp && \
    chown -R gateway:gateway /app

# Switch to non-root user
USER gateway

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${GATEWAY_PORT}/health/live')"

# Expose the gateway port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "gateway"]
