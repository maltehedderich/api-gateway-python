# API Gateway Deployment Guide

This guide provides detailed instructions for deploying the API Gateway to various environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Deployment](#docker-deployment)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Configuration](#configuration)
5. [Monitoring Setup](#monitoring-setup)
6. [Security Considerations](#security-considerations)
7. [Scaling and High Availability](#scaling-and-high-availability)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- Docker 20.10+ or compatible container runtime
- Kubernetes 1.24+ (for Kubernetes deployment)
- kubectl 1.24+ (for Kubernetes deployment)
- Helm 3.0+ (optional, for Prometheus/Grafana)
- Redis 6.0+ (for session and rate limiting storage)

### Required Resources

**Minimum per instance:**
- CPU: 250m (0.25 cores)
- Memory: 256Mi
- Disk: 100Mi

**Recommended for production:**
- CPU: 1 core
- Memory: 512Mi
- Disk: 1Gi

## Docker Deployment

### Building the Image

```bash
# Build the Docker image
docker build -t api-gateway:latest .

# Tag for registry
docker tag api-gateway:latest your-registry.io/api-gateway:v1.0.0

# Push to registry
docker push your-registry.io/api-gateway:v1.0.0
```

### Running Locally

```bash
# Create a network
docker network create gateway-network

# Run Redis
docker run -d \
  --name redis \
  --network gateway-network \
  redis:7-alpine

# Run the gateway
docker run -d \
  --name api-gateway \
  --network gateway-network \
  -p 8080:8080 \
  -p 9090:9090 \
  -e GATEWAY_ENV=development \
  -e GATEWAY_LOG_LEVEL=DEBUG \
  -e REDIS_URL=redis://redis:6379/0 \
  -e SESSION_SECRET=your-secret-key-here \
  -v $(pwd)/config:/app/config:ro \
  api-gateway:latest
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  api-gateway:
    build: .
    ports:
      - "8080:8080"
      - "9090:9090"
    environment:
      - GATEWAY_ENV=development
      - GATEWAY_LOG_LEVEL=DEBUG
      - REDIS_URL=redis://redis:6379/0
      - SESSION_SECRET=${SESSION_SECRET:-default-secret-change-me}
    volumes:
      - ./config:/app/config:ro
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health/live').read()"]
      interval: 30s
      timeout: 3s
      retries: 3

volumes:
  redis-data:
```

Run with:

```bash
docker-compose up -d
```

## Kubernetes Deployment

### Step 1: Prepare the Cluster

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Verify namespace
kubectl get namespace api-gateway
```

### Step 2: Deploy Redis (if not already available)

```bash
# Using Helm (recommended)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install redis bitnami/redis \
  --namespace api-gateway \
  --set auth.enabled=false \
  --set master.persistence.enabled=true \
  --set replica.replicaCount=2

# Or deploy a simple Redis instance
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: api-gateway
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: api-gateway
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
EOF
```

### Step 3: Create Secrets

```bash
# Generate a strong session secret
SESSION_SECRET=$(openssl rand -base64 32)

# Create the secret
kubectl create secret generic api-gateway-secrets \
  --from-literal=redis_url='redis://redis.api-gateway.svc.cluster.local:6379/0' \
  --from-literal=session_secret="$SESSION_SECRET" \
  --namespace=api-gateway

# Create TLS secret (if you have certificates)
kubectl create secret tls api-gateway-tls \
  --cert=/path/to/tls.crt \
  --key=/path/to/tls.key \
  --namespace=api-gateway

# Or use cert-manager for automatic certificate management
```

### Step 4: Deploy ConfigMap

```bash
# Review and customize the configuration
kubectl apply -f k8s/configmap.yaml

# Verify
kubectl get configmap -n api-gateway
```

### Step 5: Deploy the Application

```bash
# Deploy the gateway
kubectl apply -f k8s/deployment.yaml

# Verify pods are running
kubectl get pods -n api-gateway -w

# Check logs
kubectl logs -f deployment/api-gateway -n api-gateway
```

### Step 6: Deploy Services and Ingress

```bash
# Deploy services
kubectl apply -f k8s/service.yaml

# Deploy ingress (update hostnames first!)
kubectl apply -f k8s/ingress.yaml

# Verify
kubectl get svc,ingress -n api-gateway
```

### Step 7: Deploy Monitoring

```bash
# Deploy ServiceMonitor (requires Prometheus Operator)
kubectl apply -f monitoring/servicemonitor.yaml

# Deploy alerting rules
kubectl apply -f monitoring/alerts.yaml

# Deploy Grafana dashboard
kubectl apply -f monitoring/grafana-dashboard-configmap.yaml
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GATEWAY_ENV` | Environment (development, staging, production) | `production` | No |
| `GATEWAY_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` | No |
| `GATEWAY_HOST` | Bind address | `0.0.0.0` | No |
| `GATEWAY_PORT` | HTTP port | `8080` | No |
| `GATEWAY_METRICS_PORT` | Metrics port | `9090` | No |
| `REDIS_URL` | Redis connection URL | - | Yes |
| `SESSION_SECRET` | Secret for token signing | - | Yes |

### Configuration File

The main configuration is in `/app/config/gateway.yaml`. See `k8s/configmap.yaml` for a complete example.

### Customizing Routes

Edit the `routes` section in the ConfigMap:

```yaml
routes:
  - id: "my-service"
    path: "/api/v1/myservice/*"
    methods: ["GET", "POST"]
    upstream: "http://my-service.default.svc.cluster.local:8080"
    auth_required: true
    rate_limit:
      enabled: true
      limit: 100
      window: 60
```

Apply changes:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl rollout restart deployment/api-gateway -n api-gateway
```

## Monitoring Setup

### Prometheus

If using Prometheus Operator:

```bash
# ServiceMonitor will be auto-discovered
kubectl apply -f monitoring/servicemonitor.yaml

# Verify metrics are being scraped
kubectl port-forward -n api-gateway svc/api-gateway-metrics 9090:9090
curl http://localhost:9090/metrics
```

### Grafana

1. Import the dashboard:
   ```bash
   kubectl apply -f monitoring/grafana-dashboard-configmap.yaml
   ```

2. Or manually import `monitoring/grafana-dashboard.json` into Grafana UI

3. Access Grafana and navigate to the "API Gateway - Operations Dashboard"

### Alerts

```bash
# Apply alert rules
kubectl apply -f monitoring/alerts.yaml

# Verify alerts are loaded in Prometheus
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# Navigate to http://localhost:9090/alerts
```

## Security Considerations

### TLS/HTTPS

**Option 1: Use cert-manager**

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

**Option 2: Provide your own certificates**

```bash
kubectl create secret tls api-gateway-tls \
  --cert=tls.crt \
  --key=tls.key \
  --namespace=api-gateway
```

### Network Policies

Create network policies to restrict traffic:

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-gateway-policy
  namespace: api-gateway
spec:
  podSelector:
    matchLabels:
      app: api-gateway
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 6379  # Redis
    - protocol: TCP
      port: 8080  # Upstream services
EOF
```

### Secret Management

For production, use external secret management:

- **AWS**: AWS Secrets Manager + External Secrets Operator
- **GCP**: Secret Manager + External Secrets Operator
- **Azure**: Key Vault + External Secrets Operator
- **HashiCorp Vault**: Vault + Vault Agent Injector

### Pod Security

The deployment uses:
- Non-root user
- Read-only root filesystem
- Dropped capabilities
- Security context constraints

## Scaling and High Availability

### Horizontal Scaling

The HorizontalPodAutoscaler is included in the deployment:

```bash
# Check HPA status
kubectl get hpa -n api-gateway

# Manual scaling
kubectl scale deployment/api-gateway --replicas=5 -n api-gateway
```

### Multi-Region Deployment

For global deployment:

1. Deploy to multiple regions
2. Use global load balancer (AWS Global Accelerator, GCP Cloud Load Balancing)
3. Configure DNS-based routing (Route 53, Cloud DNS)

### High Availability Checklist

- [ ] At least 3 replicas across multiple nodes/zones
- [ ] PodDisruptionBudget configured (min 2 available)
- [ ] Redis with replication and persistence
- [ ] Health checks configured
- [ ] Resource limits set
- [ ] Monitoring and alerting active

## Troubleshooting

### Pods not starting

```bash
# Check pod status
kubectl get pods -n api-gateway

# Describe pod
kubectl describe pod <pod-name> -n api-gateway

# Check logs
kubectl logs <pod-name> -n api-gateway

# Common issues:
# - Missing secrets: Check if api-gateway-secrets exists
# - Image pull errors: Check image name and registry credentials
# - Config errors: Check configmap syntax
```

### High latency

```bash
# Check metrics
kubectl port-forward -n api-gateway svc/api-gateway-metrics 9090:9090
curl http://localhost:9090/metrics | grep latency

# Check upstream services
# Check Redis performance
# Review resource limits
```

### Authentication failures

```bash
# Check Redis connectivity
kubectl exec -it deployment/api-gateway -n api-gateway -- \
  python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"

# Check session secret
kubectl get secret api-gateway-secrets -n api-gateway -o yaml

# Check logs for auth errors
kubectl logs -f deployment/api-gateway -n api-gateway | grep auth
```

### Rate limiting not working

```bash
# Verify Redis is accessible
# Check rate limiting configuration in configmap
# Review metrics for rate_limit_exceeded_total
```

## Rollback

To rollback a deployment:

```bash
# Check rollout history
kubectl rollout history deployment/api-gateway -n api-gateway

# Rollback to previous version
kubectl rollout undo deployment/api-gateway -n api-gateway

# Rollback to specific revision
kubectl rollout undo deployment/api-gateway --to-revision=2 -n api-gateway
```

## Next Steps

- Review the [Operational Runbook](RUNBOOK.md) for day-to-day operations
- Set up alerting notifications (PagerDuty, Slack, etc.)
- Configure log aggregation (ELK, Loki, CloudWatch)
- Implement backup strategies for Redis
- Plan disaster recovery procedures
