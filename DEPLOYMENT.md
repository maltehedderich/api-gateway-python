# API Gateway - Deployment Guide

This guide covers deploying the API Gateway to production and other environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Building the Container Image](#building-the-container-image)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration](#configuration)
- [TLS/SSL Setup](#tlsssl-setup)
- [Scaling](#scaling)
- [Monitoring Setup](#monitoring-setup)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

- **Docker** (v20.10+) or **Podman** for building container images
- **kubectl** (v1.25+) for Kubernetes deployment
- **Kubernetes cluster** (v1.25+) with:
  - Ingress controller (nginx-ingress recommended)
  - Metrics server (for HPA)
  - Prometheus Operator (optional, for monitoring)
  - cert-manager (optional, for TLS certificate management)

### Required Services

- **Redis** (v7.0+) for session storage and rate limiting
  - Must be accessible from the gateway pods
  - Recommended: Redis with persistence enabled
  - Recommended: Redis cluster for high availability

### Access Requirements

- Container registry credentials (for pushing/pulling images)
- Kubernetes cluster access with appropriate RBAC permissions
- DNS access for configuring ingress hostnames

---

## Building the Container Image

### 1. Build the Image

```bash
# Build using Docker
docker build -t api-gateway:latest .

# Or build with a specific tag
docker build -t api-gateway:v0.1.0 .

# Build for multiple architectures (optional)
docker buildx build --platform linux/amd64,linux/arm64 -t api-gateway:v0.1.0 .
```

### 2. Tag and Push to Registry

```bash
# Tag for your container registry
docker tag api-gateway:latest your-registry.example.com/api-gateway:v0.1.0

# Push to registry
docker push your-registry.example.com/api-gateway:v0.1.0
```

### 3. Verify the Image

```bash
# Test the image locally
docker run -p 8080:8080 \
  -e REDIS_HOST=localhost \
  -e SESSION_SECRET=test-secret \
  api-gateway:latest

# Check health
curl http://localhost:8080/health/live
```

---

## Kubernetes Deployment

### Directory Structure

The Kubernetes manifests are organized as follows:

```
k8s/
├── base/
│   ├── deployment.yaml      # Main deployment
│   ├── service.yaml         # Service and RBAC
│   ├── configmap.yaml       # Configuration
│   ├── secret.yaml.template # Secrets template
│   ├── hpa.yaml            # Horizontal Pod Autoscaler
│   └── ingress.yaml        # Ingress with TLS
├── monitoring/
│   ├── servicemonitor.yaml    # Prometheus ServiceMonitor
│   ├── grafana-dashboard.json # Grafana dashboard
│   └── prometheus-rules.yaml  # Alert rules
└── overlays/
    └── production/          # Production-specific overrides
```

### Step-by-Step Deployment

#### 1. Create Namespace (Optional)

```bash
kubectl create namespace api-gateway
kubectl config set-context --current --namespace=api-gateway
```

#### 2. Create Secrets

**Option A: Using kubectl directly**

```bash
# Generate session secret
SESSION_SECRET=$(openssl rand -base64 32)

# Create the secret
kubectl create secret generic api-gateway-secrets \
  --from-literal=SESSION_SECRET="${SESSION_SECRET}" \
  --from-literal=REDIS_PASSWORD="your-redis-password" \
  --from-literal=SIGNING_KEY="$(openssl rand -base64 64)"
```

**Option B: Using the template**

```bash
# Copy and edit the template
cp k8s/base/secret.yaml.template k8s/base/secret.yaml

# Generate and base64 encode secrets
echo -n "your-secret-value" | base64

# Edit secret.yaml with your values
vim k8s/base/secret.yaml

# Apply the secret
kubectl apply -f k8s/base/secret.yaml

# Delete the file (don't commit it!)
rm k8s/base/secret.yaml
```

#### 3. Deploy Redis (if not already deployed)

```bash
# Simple Redis deployment (development only)
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
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
  name: redis-service
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
EOF
```

**Production**: Use a managed Redis service or Redis cluster with persistence.

#### 4. Apply ConfigMaps

```bash
kubectl apply -f k8s/base/configmap.yaml
```

#### 5. Deploy the Gateway

```bash
# Apply all base manifests
kubectl apply -f k8s/base/deployment.yaml
kubectl apply -f k8s/base/service.yaml
kubectl apply -f k8s/base/hpa.yaml
```

#### 6. Verify Deployment

```bash
# Check pod status
kubectl get pods -l app=api-gateway

# Check logs
kubectl logs -l app=api-gateway --tail=50

# Check events
kubectl get events --sort-by='.lastTimestamp'

# Test health endpoint
kubectl port-forward svc/api-gateway 8080:80
curl http://localhost:8080/health/live
```

#### 7. Configure Ingress

**Edit ingress.yaml** to set your domain names:

```yaml
spec:
  tls:
  - hosts:
    - api.yourdomain.com
    secretName: api-gateway-tls
  rules:
  - host: api.yourdomain.com
```

**Apply ingress**:

```bash
kubectl apply -f k8s/base/ingress.yaml
```

**Verify ingress**:

```bash
kubectl get ingress api-gateway
curl https://api.yourdomain.com/health/live
```

---

## Configuration

### Environment Variables

Key environment variables (configured in ConfigMap and Secrets):

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GATEWAY_HOST` | Bind address | `0.0.0.0` | No |
| `GATEWAY_PORT` | HTTP port | `8080` | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `LOG_FORMAT` | Log format (json/text) | `json` | No |
| `REDIS_HOST` | Redis hostname | - | Yes |
| `REDIS_PORT` | Redis port | `6379` | No |
| `REDIS_PASSWORD` | Redis password | - | If auth enabled |
| `SESSION_SECRET` | Session signing secret | - | Yes |
| `SESSION_TTL` | Session TTL (seconds) | `3600` | No |
| `RATELIMIT_ENABLED` | Enable rate limiting | `true` | No |

### Gateway Configuration File

Edit `k8s/base/configmap.yaml` to customize routes, rate limits, and other settings:

```yaml
data:
  gateway.yml: |
    routes:
      - path: /api/v1/users
        methods: [GET, POST]
        upstream: http://user-service:8080
        auth_required: true
        permissions: [read:users]
        ratelimit:
          requests: 100
          window: 60
```

After editing, reapply:

```bash
kubectl apply -f k8s/base/configmap.yaml
kubectl rollout restart deployment/api-gateway
```

---

## TLS/SSL Setup

### Using cert-manager (Recommended)

1. **Install cert-manager**:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

2. **Create ClusterIssuer**:

```bash
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

3. **Certificate is auto-created** by the ingress (see `k8s/base/ingress.yaml`).

### Manual TLS Certificate

```bash
# Create TLS secret from certificate files
kubectl create secret tls api-gateway-tls \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key
```

---

## Scaling

### Horizontal Pod Autoscaling

The HPA automatically scales based on CPU and memory:

```bash
# Check HPA status
kubectl get hpa api-gateway

# Describe HPA for details
kubectl describe hpa api-gateway
```

**Adjust scaling parameters** in `k8s/base/hpa.yaml`:

```yaml
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        averageUtilization: 70
```

### Manual Scaling

```bash
# Scale to specific replica count
kubectl scale deployment api-gateway --replicas=5

# Verify
kubectl get deployment api-gateway
```

### Vertical Scaling

Adjust resource requests/limits in `k8s/base/deployment.yaml`:

```yaml
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

---

## Monitoring Setup

### 1. Deploy Prometheus ServiceMonitor

```bash
kubectl apply -f k8s/monitoring/servicemonitor.yaml
```

### 2. Import Grafana Dashboard

1. Open Grafana UI
2. Go to **Dashboards** → **Import**
3. Upload `k8s/monitoring/grafana-dashboard.json`
4. Select Prometheus data source
5. Click **Import**

### 3. Configure Alerts

```bash
kubectl apply -f k8s/monitoring/prometheus-rules.yaml
```

### 4. Verify Metrics

```bash
# Port-forward to gateway
kubectl port-forward svc/api-gateway 8080:80

# Fetch metrics
curl http://localhost:8080/metrics
```

---

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name>

# Common issues:
# - Missing secrets
# - Redis not accessible
# - Image pull errors
```

### Health Checks Failing

```bash
# Test health endpoint directly
kubectl exec -it <pod-name> -- curl localhost:8080/health/live

# Check readiness probe
kubectl get pod <pod-name> -o jsonpath='{.status.conditions[?(@.type=="Ready")]}'
```

### High Memory/CPU Usage

```bash
# Check resource usage
kubectl top pods -l app=api-gateway

# Increase resource limits
kubectl edit deployment api-gateway
```

### Connection Issues

```bash
# Test service connectivity
kubectl run -it --rm debug --image=busybox --restart=Never -- sh
wget -qO- http://api-gateway/health/live

# Check service endpoints
kubectl get endpoints api-gateway
```

### Configuration Issues

```bash
# View current config
kubectl get configmap api-gateway-config -o yaml

# Check environment variables
kubectl exec -it <pod-name> -- env | grep GATEWAY
```

---

## Rolling Updates

### Update the Image

```bash
# Update deployment image
kubectl set image deployment/api-gateway \
  gateway=your-registry.example.com/api-gateway:v0.2.0

# Monitor rollout
kubectl rollout status deployment/api-gateway

# Rollback if needed
kubectl rollout undo deployment/api-gateway
```

### Update Configuration

```bash
# Edit configmap
kubectl edit configmap api-gateway-config

# Restart pods to pick up changes
kubectl rollout restart deployment/api-gateway
```

---

## Production Checklist

Before deploying to production:

- [ ] Secrets are stored securely (not in version control)
- [ ] TLS certificates are configured and valid
- [ ] Redis is highly available with persistence
- [ ] Resource limits are set appropriately
- [ ] HPA is configured for expected load
- [ ] Monitoring and alerting are configured
- [ ] Logs are being collected and aggregated
- [ ] Backup and disaster recovery plan is in place
- [ ] Security scanning is performed on images
- [ ] Network policies are configured (if required)
- [ ] PodDisruptionBudget is configured
- [ ] Rate limiting is properly tuned
- [ ] Upstream service URLs are correct

---

## Additional Resources

- [RUNBOOK.md](RUNBOOK.md) - Operational runbook
- [CLAUDE.md](CLAUDE.md) - Development guide
- [API_GATEWAY_DESIGN_SPEC.md](API_GATEWAY_DESIGN_SPEC.md) - Design specification
- [README.md](README.md) - Project overview
