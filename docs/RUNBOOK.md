# API Gateway Operational Runbook

This runbook provides procedures for common operational tasks, incident response, and troubleshooting.

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Health Checks](#health-checks)
3. [Incident Response](#incident-response)
4. [Common Issues and Solutions](#common-issues-and-solutions)
5. [Maintenance Procedures](#maintenance-procedures)
6. [Performance Tuning](#performance-tuning)
7. [Disaster Recovery](#disaster-recovery)

## Daily Operations

### Morning Checks

**Check System Health**

```bash
# Check pod status
kubectl get pods -n api-gateway

# Expected: All pods Running, READY 1/1

# Check recent logs for errors
kubectl logs --tail=100 deployment/api-gateway -n api-gateway | grep -i error

# Check metrics endpoint
kubectl port-forward -n api-gateway svc/api-gateway-metrics 9090:9090 &
curl -s http://localhost:9090/metrics | grep -E "http_requests_total|error"
```

**Review Grafana Dashboard**

1. Access Grafana dashboard: "API Gateway - Operations Dashboard"
2. Check for anomalies in:
   - Request rate (should be within normal range)
   - Error rate (should be < 1%)
   - Latency (p95 should be < 500ms)
   - Rate limiting (check for spikes)

**Review Active Alerts**

```bash
# Check Prometheus alerts
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &
# Navigate to http://localhost:9090/alerts

# Check for firing alerts
# Investigate any critical alerts immediately
```

### Monitoring Key Metrics

**Request Metrics**

```bash
# Total request rate
kubectl port-forward -n api-gateway svc/api-gateway-metrics 9090:9090 &
curl -s http://localhost:9090/metrics | grep "http_requests_total"

# Error rate
curl -s http://localhost:9090/metrics | grep "http_requests_total" | grep "status=\"5"
```

**Performance Metrics**

```bash
# Latency percentiles
curl -s http://localhost:9090/metrics | grep "http_request_duration_seconds"

# Active connections
curl -s http://localhost:9090/metrics | grep "active_connections"
```

**Resource Utilization**

```bash
# CPU and memory usage
kubectl top pods -n api-gateway

# Expected: CPU < 70%, Memory < 80%
```

## Health Checks

### Application Health

```bash
# Liveness check (is the process alive?)
curl -i http://<gateway-url>/health/live

# Expected: 200 OK

# Readiness check (is it ready to serve traffic?)
curl -i http://<gateway-url>/health/ready

# Expected: 200 OK

# Detailed health check
curl -s http://<gateway-url>/health | jq .

# Expected: All components showing "healthy"
```

### Dependency Health

**Redis Connection**

```bash
# Test Redis connectivity from gateway pod
kubectl exec -it deployment/api-gateway -n api-gateway -- \
  python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print('Redis OK' if r.ping() else 'Redis FAILED')"

# Check Redis directly
kubectl exec -it -n api-gateway redis-0 -- redis-cli ping

# Expected: PONG
```

**Upstream Services**

```bash
# Test connectivity to upstream services
kubectl exec -it deployment/api-gateway -n api-gateway -- \
  curl -I http://user-service.default.svc.cluster.local:8080/health

# Check each configured upstream service
```

## Incident Response

### High Error Rate (> 5%)

**Severity**: Critical

**Investigation Steps**:

1. Check current error rate:
   ```bash
   kubectl logs --tail=200 deployment/api-gateway -n api-gateway | grep "ERROR"
   ```

2. Identify error types:
   ```bash
   kubectl logs deployment/api-gateway -n api-gateway | grep "status_code" | sort | uniq -c
   ```

3. Check upstream services:
   ```bash
   # Review upstream error metrics
   curl -s http://localhost:9090/metrics | grep "upstream_request_errors"
   ```

4. Check recent deployments:
   ```bash
   kubectl rollout history deployment/api-gateway -n api-gateway
   ```

**Resolution**:

- If caused by recent deployment: Rollback immediately
  ```bash
  kubectl rollout undo deployment/api-gateway -n api-gateway
  ```

- If caused by upstream failures: Investigate upstream services
- If rate limiting is too strict: Temporarily increase limits
  ```bash
  kubectl edit configmap api-gateway-config -n api-gateway
  # Update rate limits, then restart
  kubectl rollout restart deployment/api-gateway -n api-gateway
  ```

### High Latency (p95 > 1s)

**Severity**: High

**Investigation Steps**:

1. Check current latency:
   ```bash
   curl -s http://localhost:9090/metrics | grep "http_request_duration_seconds"
   ```

2. Identify slow endpoints:
   ```bash
   kubectl logs deployment/api-gateway -n api-gateway | grep "latency" | sort -k5 -n -r | head
   ```

3. Check upstream latency:
   ```bash
   curl -s http://localhost:9090/metrics | grep "upstream_request_duration"
   ```

4. Check resource usage:
   ```bash
   kubectl top pods -n api-gateway
   ```

**Resolution**:

- If CPU/Memory is high: Scale up
  ```bash
  kubectl scale deployment/api-gateway --replicas=5 -n api-gateway
  ```

- If upstream is slow: Investigate upstream services
- If Redis is slow: Check Redis performance, consider scaling Redis

### Gateway Pods Crashing

**Severity**: Critical

**Investigation Steps**:

1. Check pod status:
   ```bash
   kubectl get pods -n api-gateway
   kubectl describe pod <pod-name> -n api-gateway
   ```

2. Check recent logs:
   ```bash
   kubectl logs <pod-name> -n api-gateway --previous
   ```

3. Check events:
   ```bash
   kubectl get events -n api-gateway --sort-by='.lastTimestamp'
   ```

**Common Causes and Resolutions**:

- **OOMKilled**: Increase memory limits
  ```bash
  kubectl edit deployment/api-gateway -n api-gateway
  # Increase resources.limits.memory
  ```

- **CrashLoopBackOff**: Check configuration and secrets
  ```bash
  kubectl get configmap api-gateway-config -n api-gateway -o yaml
  kubectl get secret api-gateway-secrets -n api-gateway
  ```

- **ImagePullBackOff**: Check image name and registry credentials

### Authentication Failures Spike

**Severity**: High

**Investigation Steps**:

1. Check auth failure rate:
   ```bash
   curl -s http://localhost:9090/metrics | grep "auth_failures_total"
   ```

2. Review logs:
   ```bash
   kubectl logs deployment/api-gateway -n api-gateway | grep "authentication failed"
   ```

3. Check Redis connectivity:
   ```bash
   kubectl exec -it deployment/api-gateway -n api-gateway -- \
     python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"
   ```

**Resolution**:

- If Redis is down: Investigate and restore Redis service
- If token expiration is too aggressive: Review and adjust token TTL
- If legitimate spike: May indicate security issue, review access logs

### Rate Limiting Too Aggressive

**Severity**: Medium

**Investigation Steps**:

1. Check rate limiting metrics:
   ```bash
   curl -s http://localhost:9090/metrics | grep "rate_limit_exceeded"
   ```

2. Identify affected keys/users:
   ```bash
   kubectl logs deployment/api-gateway -n api-gateway | grep "rate_limit_exceeded"
   ```

**Resolution**:

1. Temporarily increase limits if legitimate traffic:
   ```bash
   kubectl edit configmap api-gateway-config -n api-gateway
   # Increase rate limits in configuration
   ```

2. Restart deployment:
   ```bash
   kubectl rollout restart deployment/api-gateway -n api-gateway
   ```

3. For permanent changes, update configuration in version control

## Common Issues and Solutions

### Issue: Unable to connect to Redis

**Symptoms**:
- Authentication failures
- Rate limiting not working
- 503 errors

**Diagnosis**:
```bash
kubectl get pods -n api-gateway | grep redis
kubectl logs redis-0 -n api-gateway
```

**Solution**:
```bash
# Restart Redis
kubectl rollout restart statefulset/redis -n api-gateway

# Or scale down and up
kubectl scale statefulset/redis --replicas=0 -n api-gateway
kubectl scale statefulset/redis --replicas=1 -n api-gateway
```

### Issue: Configuration changes not taking effect

**Symptoms**:
- ConfigMap updated but behavior unchanged

**Diagnosis**:
```bash
kubectl get configmap api-gateway-config -n api-gateway -o yaml
kubectl describe pod <pod-name> -n api-gateway | grep "Config"
```

**Solution**:
```bash
# Force pod restart to pick up new config
kubectl rollout restart deployment/api-gateway -n api-gateway

# Verify new config is loaded
kubectl logs deployment/api-gateway -n api-gateway | grep "Configuration loaded"
```

### Issue: Ingress not routing traffic

**Symptoms**:
- External requests not reaching gateway
- 404 or 503 from ingress

**Diagnosis**:
```bash
kubectl get ingress -n api-gateway
kubectl describe ingress api-gateway -n api-gateway
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller
```

**Solution**:
```bash
# Check ingress controller
kubectl get pods -n ingress-nginx

# Verify service endpoints
kubectl get endpoints -n api-gateway

# Update ingress if needed
kubectl apply -f k8s/ingress.yaml
```

## Maintenance Procedures

### Updating the Gateway

**Zero-downtime deployment**:

1. Build and push new image:
   ```bash
   docker build -t api-gateway:v1.1.0 .
   docker push your-registry/api-gateway:v1.1.0
   ```

2. Update deployment:
   ```bash
   kubectl set image deployment/api-gateway \
     gateway=your-registry/api-gateway:v1.1.0 \
     -n api-gateway
   ```

3. Monitor rollout:
   ```bash
   kubectl rollout status deployment/api-gateway -n api-gateway
   ```

4. Verify health:
   ```bash
   kubectl get pods -n api-gateway
   curl http://<gateway-url>/health/ready
   ```

5. Rollback if issues:
   ```bash
   kubectl rollout undo deployment/api-gateway -n api-gateway
   ```

### Updating Configuration

1. Update ConfigMap:
   ```bash
   kubectl edit configmap api-gateway-config -n api-gateway
   # Or apply from file
   kubectl apply -f k8s/configmap.yaml
   ```

2. Restart deployment:
   ```bash
   kubectl rollout restart deployment/api-gateway -n api-gateway
   ```

3. Verify changes:
   ```bash
   kubectl logs -f deployment/api-gateway -n api-gateway
   ```

### Rotating Secrets

**Session Secret Rotation**:

1. Generate new secret:
   ```bash
   NEW_SECRET=$(openssl rand -base64 32)
   ```

2. Update secret:
   ```bash
   kubectl create secret generic api-gateway-secrets-new \
     --from-literal=redis_url='redis://redis:6379/0' \
     --from-literal=session_secret="$NEW_SECRET" \
     --namespace=api-gateway \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

3. Update deployment to use new secret

4. Rolling restart to pick up new secret

5. Delete old secret after verification

### Certificate Renewal

**If using cert-manager**:
- Automatic renewal, monitor cert-manager logs

**Manual renewal**:

1. Obtain new certificate

2. Update secret:
   ```bash
   kubectl create secret tls api-gateway-tls \
     --cert=new-tls.crt \
     --key=new-tls.key \
     --namespace=api-gateway \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

3. Restart deployment if needed

## Performance Tuning

### Scaling Guidelines

**Horizontal Scaling**:

```bash
# Manual scaling
kubectl scale deployment/api-gateway --replicas=5 -n api-gateway

# Check HPA
kubectl get hpa -n api-gateway

# Adjust HPA limits
kubectl edit hpa api-gateway -n api-gateway
```

**Vertical Scaling**:

```bash
# Update resource limits
kubectl edit deployment/api-gateway -n api-gateway

# Recommended limits for high-load:
# CPU: 2000m (2 cores)
# Memory: 1Gi
```

### Optimizing Redis

**Connection Pooling**:
- Adjust max connections in configuration
- Monitor Redis connection count

**Redis Persistence**:
```bash
# Check Redis persistence settings
kubectl exec -it redis-0 -n api-gateway -- redis-cli CONFIG GET save

# Adjust for performance vs durability trade-off
```

### Rate Limiting Tuning

- Review rate limit metrics regularly
- Adjust limits based on observed traffic patterns
- Consider different limits for different user tiers
- Use composite keys for fine-grained control

## Disaster Recovery

### Backup Procedures

**Configuration Backup**:

```bash
# Backup all configurations
kubectl get configmap,secret,deployment,service,ingress -n api-gateway -o yaml > backup-$(date +%Y%m%d).yaml
```

**Redis Backup**:

```bash
# Trigger Redis SAVE
kubectl exec -it redis-0 -n api-gateway -- redis-cli SAVE

# Copy RDB file
kubectl cp api-gateway/redis-0:/data/dump.rdb ./redis-backup-$(date +%Y%m%d).rdb
```

### Recovery Procedures

**Full Cluster Recovery**:

1. Restore namespace and RBAC:
   ```bash
   kubectl apply -f k8s/namespace.yaml
   ```

2. Restore secrets:
   ```bash
   # Restore from backup or recreate
   kubectl apply -f backup-secrets.yaml
   ```

3. Restore Redis (if using persistent volumes, PVCs should restore automatically):
   ```bash
   kubectl apply -f redis-deployment.yaml
   # Wait for Redis to be ready
   ```

4. Restore ConfigMap:
   ```bash
   kubectl apply -f k8s/configmap.yaml
   ```

5. Restore gateway deployment:
   ```bash
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   kubectl apply -f k8s/ingress.yaml
   ```

6. Verify all services:
   ```bash
   kubectl get all -n api-gateway
   curl http://<gateway-url>/health/ready
   ```

### Emergency Contacts

**Escalation Path**:
1. On-call engineer (check PagerDuty)
2. Team lead: [contact info]
3. Platform team: [contact info]

**External Dependencies**:
- Cloud provider support
- DNS provider support
- Certificate authority

## Best Practices

1. **Always test in staging first** before production changes
2. **Use kubectl apply** instead of edit for reproducibility
3. **Monitor after every change** for at least 15 minutes
4. **Keep runbook updated** with lessons learned from incidents
5. **Document all manual interventions** in incident reports
6. **Regular backup verification** - test restore procedures quarterly
7. **Practice disaster recovery** scenarios regularly

## Additional Resources

- [Deployment Guide](DEPLOYMENT.md)
- [API Gateway Design Specification](../API_GATEWAY_DESIGN_SPEC.md)
- Grafana Dashboard: http://grafana.example.com/d/api-gateway
- Prometheus: http://prometheus.example.com
- Alert Manager: http://alertmanager.example.com
