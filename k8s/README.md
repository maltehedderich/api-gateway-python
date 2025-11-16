# Kubernetes Deployment Manifests

This directory contains Kubernetes manifests for deploying the API Gateway.

## Files

- **namespace.yaml**: Namespace, ServiceAccount, and RBAC resources
- **configmap.yaml**: Application configuration
- **secrets.yaml.template**: Template for secrets (DO NOT commit actual secrets!)
- **deployment.yaml**: Deployment, HorizontalPodAutoscaler, and PodDisruptionBudget
- **service.yaml**: Service definitions (ClusterIP, LoadBalancer, Metrics)
- **ingress.yaml**: Ingress resources for external access

## Quick Start

### Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured
- Redis deployed or available

### Basic Deployment

```bash
# 1. Create namespace
kubectl apply -f namespace.yaml

# 2. Create secrets (customize first!)
# See secrets.yaml.template for instructions
kubectl create secret generic api-gateway-secrets \
  --from-literal=redis_url='redis://redis:6379/0' \
  --from-literal=session_secret='YOUR_SECRET' \
  --namespace=api-gateway

# 3. Deploy configuration
kubectl apply -f configmap.yaml

# 4. Deploy application
kubectl apply -f deployment.yaml

# 5. Deploy services
kubectl apply -f service.yaml

# 6. Deploy ingress (update hostnames first!)
kubectl apply -f ingress.yaml

# 7. Verify deployment
kubectl get all -n api-gateway
```

## Customization

### Update Routes

Edit `configmap.yaml` and modify the `routes` section:

```yaml
routes:
  - id: "my-service"
    path: "/api/v1/myservice/*"
    methods: ["GET", "POST"]
    upstream: "http://my-service:8080"
    auth_required: true
```

Apply changes:

```bash
kubectl apply -f configmap.yaml
kubectl rollout restart deployment/api-gateway -n api-gateway
```

### Update Ingress Hostnames

Edit `ingress.yaml` and update:

```yaml
spec:
  tls:
    - hosts:
        - api.yourdomain.com  # Change this
  rules:
    - host: api.yourdomain.com  # Change this
```

### Adjust Resource Limits

Edit `deployment.yaml`:

```yaml
resources:
  requests:
    cpu: 500m      # Adjust based on load
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 1Gi
```

### Configure Auto-scaling

Edit `deployment.yaml` HorizontalPodAutoscaler section:

```yaml
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70  # Scale when CPU > 70%
```

## Monitoring

Deploy monitoring resources:

```bash
cd ../monitoring
kubectl apply -f servicemonitor.yaml
kubectl apply -f alerts.yaml
kubectl apply -f grafana-dashboard-configmap.yaml
```

## Troubleshooting

### Pods not starting

```bash
kubectl describe pod -n api-gateway <pod-name>
kubectl logs -n api-gateway <pod-name>
```

### Check secrets

```bash
kubectl get secret api-gateway-secrets -n api-gateway
```

### View configuration

```bash
kubectl get configmap api-gateway-config -n api-gateway -o yaml
```

### Test connectivity

```bash
# Port-forward to test locally
kubectl port-forward -n api-gateway svc/api-gateway 8080:80

# Test
curl http://localhost:8080/health/live
```

## Security Notes

1. **Never commit secrets to version control**
2. Use `secrets.yaml.template` as reference only
3. Use external secret management for production (Vault, AWS Secrets Manager, etc.)
4. Rotate secrets regularly
5. Enable network policies in production
6. Use TLS/HTTPS for all external traffic
7. Restrict access to metrics endpoint

## See Also

- [Deployment Guide](../docs/DEPLOYMENT.md) - Full deployment documentation
- [Operational Runbook](../docs/RUNBOOK.md) - Day-to-day operations
- [Design Specification](../API_GATEWAY_DESIGN_SPEC.md) - Architecture details
