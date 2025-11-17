# Kubernetes Manifests for API Gateway

This directory contains Kubernetes manifests for deploying the API Gateway.

## Directory Structure

```
k8s/
├── base/                    # Base manifests
│   ├── deployment.yaml      # Gateway deployment
│   ├── service.yaml         # Service and RBAC
│   ├── configmap.yaml       # Configuration
│   ├── secret.yaml.template # Secrets template
│   ├── hpa.yaml            # Horizontal Pod Autoscaler
│   ├── ingress.yaml        # Ingress with TLS
│   └── kustomization.yaml  # Kustomize configuration
├── monitoring/             # Monitoring resources
│   ├── servicemonitor.yaml    # Prometheus ServiceMonitor
│   ├── grafana-dashboard.json # Grafana dashboard
│   └── prometheus-rules.yaml  # Prometheus alert rules
└── overlays/               # Environment-specific overlays
    └── production/         # Production overrides
```

## Deployment Methods

### Method 1: Using kubectl directly

```bash
# Create namespace (optional)
kubectl create namespace api-gateway

# Create secrets first
kubectl create secret generic api-gateway-secrets \
  --from-literal=SESSION_SECRET="$(openssl rand -base64 32)" \
  --from-literal=REDIS_PASSWORD="your-redis-password" \
  --from-literal=SIGNING_KEY="$(openssl rand -base64 64)"

# Apply manifests
kubectl apply -f base/configmap.yaml
kubectl apply -f base/deployment.yaml
kubectl apply -f base/service.yaml
kubectl apply -f base/hpa.yaml
kubectl apply -f base/ingress.yaml
```

### Method 2: Using Kustomize

```bash
# Deploy using kustomize
kubectl apply -k base/

# Or build first to preview
kubectl kustomize base/
```

### Method 3: Using Helm (if you create a chart)

```bash
helm install api-gateway ./helm/api-gateway \
  --set image.tag=v0.1.0 \
  --set redis.password=your-password
```

## Monitoring Setup

```bash
# Deploy Prometheus ServiceMonitor
kubectl apply -f monitoring/servicemonitor.yaml

# Deploy Prometheus alert rules
kubectl apply -f monitoring/prometheus-rules.yaml

# Import Grafana dashboard
# Upload monitoring/grafana-dashboard.json to Grafana UI
```

## Configuration

### Required Secrets

Before deploying, create the following secrets:

```bash
kubectl create secret generic api-gateway-secrets \
  --from-literal=SESSION_SECRET="<generated-secret>" \
  --from-literal=REDIS_PASSWORD="<redis-password>" \
  --from-literal=SIGNING_KEY="<generated-key>"
```

### ConfigMap

Edit `base/configmap.yaml` to configure:
- Routes and upstream services
- Rate limiting rules
- Session settings
- Redis connection

### Ingress

Edit `base/ingress.yaml` to set:
- Your domain names
- TLS certificate settings
- Ingress annotations

## Customization

### Environment Overlays

Create environment-specific overlays:

```bash
mkdir -p overlays/production
cat > overlays/production/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

bases:
  - ../../base

namespace: production

images:
  - name: api-gateway
    newTag: v1.0.0

replicas:
  - name: api-gateway
    count: 5

patchesStrategicMerge:
  - deployment-patch.yaml
EOF
```

### Resource Limits

Adjust in `base/deployment.yaml`:

```yaml
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

### Autoscaling

Adjust in `base/hpa.yaml`:

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

## Verification

After deployment:

```bash
# Check pod status
kubectl get pods -l app=api-gateway

# Check service
kubectl get svc api-gateway

# Check ingress
kubectl get ingress api-gateway

# Test health endpoint
kubectl port-forward svc/api-gateway 8080:80
curl http://localhost:8080/health/live
```

## Troubleshooting

See [RUNBOOK.md](../RUNBOOK.md) for operational procedures and incident response.

## Additional Resources

- [DEPLOYMENT.md](../DEPLOYMENT.md) - Complete deployment guide
- [RUNBOOK.md](../RUNBOOK.md) - Operational runbook
- [CLAUDE.md](../CLAUDE.md) - Development guide
