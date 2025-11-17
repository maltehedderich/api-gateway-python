# API Gateway - Operational Runbook

This runbook provides step-by-step procedures for common operational tasks and incident response for the API Gateway.

## Table of Contents

- [Emergency Contacts](#emergency-contacts)
- [Service Overview](#service-overview)
- [Common Incidents](#common-incidents)
- [Operational Procedures](#operational-procedures)
- [Monitoring and Alerts](#monitoring-and-alerts)
- [Maintenance](#maintenance)
- [Disaster Recovery](#disaster-recovery)

---

## Emergency Contacts

| Role | Contact | Availability |
|------|---------|--------------|
| On-Call Engineer | PagerDuty rotation | 24/7 |
| Platform Team Lead | [Name/Email] | Business hours |
| DevOps Team | devops@example.com | 24/7 |
| Security Team | security@example.com | 24/7 (incidents) |

---

## Service Overview

### Architecture

- **Type**: Stateless API Gateway
- **Language**: Python 3.12
- **Framework**: aiohttp
- **Dependencies**:
  - Redis (session storage, rate limiting)
  - Upstream services (user-service, post-service, etc.)

### Key Metrics

| Metric | Normal Range | Alert Threshold |
|--------|--------------|-----------------|
| Request rate | 100-1000 req/s | - |
| P95 latency | < 100ms | > 1s |
| Error rate | < 1% | > 5% |
| Pod count | 3-10 | < 2 |
| CPU usage | 30-70% | > 90% |
| Memory usage | 40-80% | > 90% |

### SLA/SLO

- **Availability**: 99.9% uptime
- **Latency**: P95 < 200ms, P99 < 500ms
- **Error Budget**: 0.1% (43 minutes/month)

---

## Common Incidents

### 1. High Error Rate (5xx)

**Symptoms:**
- Alert: `APIGatewayHighServerErrorRate`
- Grafana dashboard shows spike in 5xx responses
- User reports of service unavailability

**Diagnosis:**

```bash
# Check recent logs for errors
kubectl logs -l app=api-gateway --tail=100 | grep ERROR

# Check pod status
kubectl get pods -l app=api-gateway

# Check upstream service health
kubectl get pods -l app=user-service
kubectl get pods -l app=post-service

# Check Redis connectivity
kubectl exec -it <gateway-pod> -- nc -zv redis-service 6379
```

**Resolution:**

1. **If gateway pods are unhealthy:**
   ```bash
   kubectl describe pod <pod-name>
   kubectl delete pod <pod-name>  # Restart unhealthy pod
   ```

2. **If Redis is down:**
   ```bash
   kubectl get pods -l app=redis
   kubectl logs -l app=redis
   # Escalate to platform team if Redis cluster issue
   ```

3. **If upstream services are down:**
   ```bash
   # Check upstream service status
   kubectl get pods -l app=<service-name>
   # Escalate to service owner team
   ```

4. **If configuration issue:**
   ```bash
   # Check recent config changes
   kubectl get configmap api-gateway-config -o yaml
   # Rollback if needed
   kubectl rollout undo deployment/api-gateway
   ```

**Escalation:**
- If issue persists > 10 minutes, escalate to Platform Team Lead
- If security-related, notify Security Team

---

### 2. High Latency

**Symptoms:**
- Alert: `APIGatewayHighLatency` or `APIGatewayCriticalLatency`
- Grafana shows P95/P99 latency spike
- User complaints of slow responses

**Diagnosis:**

```bash
# Check current latency metrics
kubectl port-forward svc/api-gateway 8080:80
curl http://localhost:8080/metrics | grep duration

# Check pod resource usage
kubectl top pods -l app=api-gateway

# Check upstream latency
curl http://localhost:8080/metrics | grep upstream_duration

# Check Redis latency
kubectl exec -it <gateway-pod> -- redis-cli -h redis-service ping
```

**Resolution:**

1. **If gateway CPU/memory is high:**
   ```bash
   # Check if HPA is scaling
   kubectl get hpa api-gateway

   # Manual scale if needed
   kubectl scale deployment api-gateway --replicas=10
   ```

2. **If upstream services are slow:**
   ```bash
   # Check upstream service metrics
   kubectl top pods -l app=<service-name>
   # Escalate to service owner
   ```

3. **If Redis is slow:**
   ```bash
   # Check Redis metrics
   kubectl exec -it redis-pod -- redis-cli info stats
   # Check for high key count or memory usage
   # Escalate to platform team
   ```

4. **If sudden traffic spike:**
   ```bash
   # Check request rate
   curl http://localhost:8080/metrics | grep requests_total

   # Check rate limiting
   curl http://localhost:8080/metrics | grep ratelimit

   # Consider tightening rate limits temporarily
   kubectl edit configmap api-gateway-config
   ```

**Escalation:**
- If P99 > 2s for > 10 minutes, escalate to Platform Team
- If caused by upstream, notify service owner team

---

### 3. Gateway Pods Down

**Symptoms:**
- Alert: `APIGatewayDown` or `APIGatewayInsufficientReplicas`
- No response from gateway endpoints
- Kubernetes shows pods in CrashLoopBackOff or Pending

**Diagnosis:**

```bash
# Check pod status
kubectl get pods -l app=api-gateway

# Check recent events
kubectl get events --sort-by='.lastTimestamp' | grep api-gateway

# Check pod details
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name> --previous  # Previous container logs if crashed
```

**Resolution:**

1. **If CrashLoopBackOff:**
   ```bash
   # Check logs for error
   kubectl logs <pod-name> --previous

   # Common causes:
   # - Missing/invalid secrets
   # - Redis unavailable
   # - Configuration error

   # Verify secrets exist
   kubectl get secret api-gateway-secrets

   # Verify Redis is accessible
   kubectl get svc redis-service
   kubectl get pods -l app=redis
   ```

2. **If Pending (resource constraints):**
   ```bash
   # Check node resources
   kubectl describe nodes

   # Check resource requests
   kubectl describe pod <pod-name> | grep -A 5 "Requests:"

   # Reduce resource requests if needed
   kubectl edit deployment api-gateway
   ```

3. **If ImagePullBackOff:**
   ```bash
   # Check image name and tag
   kubectl describe pod <pod-name> | grep Image

   # Verify registry credentials
   kubectl get secret <registry-secret>

   # Fix deployment image
   kubectl set image deployment/api-gateway \
     gateway=correct-registry.com/api-gateway:v0.1.0
   ```

**Escalation:**
- If all pods down > 5 minutes, page Platform Team Lead immediately
- Critical incident - this is a production outage

---

### 4. Authentication Failures Spike

**Symptoms:**
- Alert: `APIGatewayAuthFailureSpike` or `APIGatewayHighAuthFailureRate`
- Many 401 Unauthorized responses
- Possible security incident

**Diagnosis:**

```bash
# Check auth failure metrics
curl http://localhost:8080/metrics | grep auth_failures

# Check logs for auth failures
kubectl logs -l app=api-gateway --tail=200 | grep "auth.*fail"

# Look for patterns (IP addresses, user IDs)
kubectl logs -l app=api-gateway --tail=500 | grep 401 | cut -d' ' -f5 | sort | uniq -c
```

**Resolution:**

1. **If legitimate traffic (expired sessions):**
   ```bash
   # Check if session expiry recently changed
   kubectl get configmap api-gateway-config -o yaml | grep SESSION_TTL

   # No action needed if users just need to re-login
   ```

2. **If potential brute force attack:**
   ```bash
   # Check rate limiting status
   curl http://localhost:8080/metrics | grep ratelimit

   # Temporarily tighten rate limits
   kubectl edit configmap api-gateway-config
   # Reduce ratelimit.default.requests
   kubectl rollout restart deployment/api-gateway

   # Block source IPs at ingress level if needed
   kubectl annotate ingress api-gateway \
     nginx.ingress.kubernetes.io/whitelist-source-range="0.0.0.0/0,!<attacker-ip>/32"
   ```

3. **If Redis issue (sessions lost):**
   ```bash
   # Check Redis status
   kubectl logs -l app=redis

   # Check if Redis restarted recently
   kubectl get pods -l app=redis -o jsonpath='{.items[*].status.startTime}'

   # Escalate to platform team
   ```

**Escalation:**
- If suspected attack, notify Security Team immediately
- If Redis data loss, escalate to Platform Team Lead

---

### 5. Rate Limiting Too Aggressive

**Symptoms:**
- Alert: `APIGatewayHighRateLimitRate`
- Many 429 Too Many Requests responses
- User complaints about being blocked

**Diagnosis:**

```bash
# Check rate limit metrics
curl http://localhost:8080/metrics | grep ratelimit_exceeded

# Check current rate limit config
kubectl get configmap api-gateway-config -o yaml | grep -A 10 ratelimit

# Check which routes are rate limited
kubectl logs -l app=api-gateway | grep "429" | awk '{print $8}' | sort | uniq -c
```

**Resolution:**

1. **If legitimate traffic:**
   ```bash
   # Increase rate limits
   kubectl edit configmap api-gateway-config
   # Update ratelimit.default.requests or route-specific limits

   # Restart gateway to apply
   kubectl rollout restart deployment/api-gateway
   ```

2. **If temporary spike:**
   ```bash
   # Temporarily increase burst allowance
   kubectl edit configmap api-gateway-config
   # Update ratelimit.default.burst

   kubectl rollout restart deployment/api-gateway
   ```

3. **If specific user needs higher limit:**
   ```bash
   # Consider implementing user tier-based rate limiting
   # (requires code change - escalate to development team)
   ```

**Escalation:**
- Coordinate with product team for rate limit policy changes
- Document changes in runbook

---

## Operational Procedures

### Scaling the Gateway

**Manual Scale Up:**

```bash
# Increase replicas
kubectl scale deployment api-gateway --replicas=10

# Verify
kubectl get deployment api-gateway
kubectl get pods -l app=api-gateway
```

**Manual Scale Down:**

```bash
# Only scale down during low traffic periods
# Check current traffic first
curl http://localhost:8080/metrics | grep requests_total

# Scale down gradually
kubectl scale deployment api-gateway --replicas=5

# Monitor for 5 minutes before further reduction
```

**Adjust HPA Thresholds:**

```bash
# Edit HPA
kubectl edit hpa api-gateway

# Common adjustments:
# - minReplicas: minimum number of pods
# - maxReplicas: maximum number of pods
# - averageUtilization: CPU/memory target percentage
```

---

### Updating Configuration

**Update ConfigMap:**

```bash
# Edit config
kubectl edit configmap api-gateway-config

# Or apply from file
kubectl apply -f k8s/base/configmap.yaml

# Restart pods to pick up changes
kubectl rollout restart deployment/api-gateway

# Monitor rollout
kubectl rollout status deployment/api-gateway

# Verify config
kubectl exec -it <new-pod> -- cat /app/config/gateway.yml
```

**Update Secrets:**

```bash
# Rotate session secret
NEW_SECRET=$(openssl rand -base64 32)

kubectl create secret generic api-gateway-secrets-new \
  --from-literal=SESSION_SECRET="${NEW_SECRET}" \
  --from-literal=REDIS_PASSWORD="$(kubectl get secret api-gateway-secrets -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)" \
  --dry-run=client -o yaml | kubectl apply -f -

# Update deployment to use new secret
kubectl patch deployment api-gateway \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"gateway","envFrom":[{"secretRef":{"name":"api-gateway-secrets-new"}}]}]}}}}'

# Delete old secret after verification
kubectl delete secret api-gateway-secrets
```

---

### Deploying New Version

**Rolling Update:**

```bash
# Update image
kubectl set image deployment/api-gateway \
  gateway=your-registry.com/api-gateway:v0.2.0

# Watch rollout
kubectl rollout status deployment/api-gateway

# Verify new version
kubectl get pods -l app=api-gateway -o jsonpath='{.items[*].spec.containers[*].image}'
```

**Rollback:**

```bash
# Rollback to previous version
kubectl rollout undo deployment/api-gateway

# Rollback to specific revision
kubectl rollout history deployment/api-gateway
kubectl rollout undo deployment/api-gateway --to-revision=3
```

---

### Viewing Logs

**Real-time logs:**

```bash
# All pods
kubectl logs -l app=api-gateway -f

# Specific pod
kubectl logs <pod-name> -f

# With timestamps
kubectl logs <pod-name> -f --timestamps
```

**Historical logs:**

```bash
# Last 100 lines
kubectl logs -l app=api-gateway --tail=100

# Logs from previous container (if crashed)
kubectl logs <pod-name> --previous

# Search for errors
kubectl logs -l app=api-gateway --tail=1000 | grep ERROR

# Search for specific request
kubectl logs -l app=api-gateway --tail=5000 | grep "correlation_id.*abc123"
```

---

### Checking Health

**Health endpoints:**

```bash
# Liveness probe
curl http://localhost:8080/health/live

# Readiness probe
curl http://localhost:8080/health/ready

# Expected responses:
# 200 OK - healthy
# 503 Service Unavailable - not ready (check dependencies)
```

**Pod health:**

```bash
# Check pod conditions
kubectl get pods -l app=api-gateway \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'

# Describe pod for detailed health
kubectl describe pod <pod-name>
```

---

## Monitoring and Alerts

### Alert Priorities

| Alert | Severity | Response Time | Action |
|-------|----------|---------------|--------|
| APIGatewayDown | Critical | Immediate | Page on-call |
| APIGatewayHighServerErrorRate | Critical | 5 minutes | Investigate |
| APIGatewayHighLatency | Warning | 15 minutes | Monitor |
| APIGatewayAuthFailureSpike | Critical | 5 minutes | Security check |
| APIGatewayInsufficientReplicas | Critical | Immediate | Check HPA/nodes |

### Key Metrics to Monitor

**Request metrics:**
- `gateway_requests_total` - Total requests by route, method, status
- `gateway_request_duration_seconds` - Request latency histogram

**Error metrics:**
- `gateway_auth_failures_total` - Authentication failures
- `gateway_ratelimit_exceeded_total` - Rate limit rejections
- `gateway_upstream_errors_total` - Upstream service errors

**System metrics:**
- `gateway_active_connections` - Active HTTP connections
- `process_resident_memory_bytes` - Memory usage
- `process_cpu_seconds_total` - CPU usage

**Dependency metrics:**
- `gateway_redis_operation_duration_seconds` - Redis latency
- `gateway_upstream_duration_seconds` - Upstream latency

---

## Maintenance

### Scheduled Maintenance Window

**Before maintenance:**

1. Notify users via status page
2. Scale up replicas for redundancy:
   ```bash
   kubectl scale deployment api-gateway --replicas=10
   ```
3. Verify monitoring is active

**During maintenance:**

1. Perform updates with rolling strategy
2. Monitor error rates and latency continuously
3. Keep rollback plan ready

**After maintenance:**

1. Verify all pods healthy
2. Check metrics for anomalies
3. Scale back to normal replica count
4. Update status page

### Routine Tasks

**Weekly:**
- Review error logs for patterns
- Check disk usage on Redis
- Verify TLS certificates validity (> 30 days)
- Review and tune rate limiting rules

**Monthly:**
- Rotate secrets (session secret, signing key)
- Review and update alert thresholds
- Performance testing
- Update dependencies (security patches)

**Quarterly:**
- Disaster recovery drill
- Capacity planning review
- Security audit
- Update documentation

---

## Disaster Recovery

### Backup and Restore

**Redis backup:**

```bash
# Trigger Redis save
kubectl exec -it redis-pod -- redis-cli BGSAVE

# Copy RDB file
kubectl cp redis-pod:/data/dump.rdb ./backup/dump-$(date +%Y%m%d).rdb
```

**Configuration backup:**

```bash
# Export all manifests
kubectl get deployment api-gateway -o yaml > backup/deployment.yaml
kubectl get configmap api-gateway-config -o yaml > backup/configmap.yaml
kubectl get service api-gateway -o yaml > backup/service.yaml
```

### Complete Outage Recovery

1. **Verify cluster accessibility:**
   ```bash
   kubectl cluster-info
   kubectl get nodes
   ```

2. **Deploy Redis:**
   ```bash
   kubectl apply -f k8s/redis/  # Or restore from backup
   ```

3. **Create secrets:**
   ```bash
   kubectl apply -f backup/secrets.yaml
   ```

4. **Deploy gateway:**
   ```bash
   kubectl apply -f k8s/base/
   ```

5. **Verify deployment:**
   ```bash
   kubectl get pods -l app=api-gateway
   curl https://api.yourdomain.com/health/live
   ```

6. **Restore DNS (if needed):**
   ```bash
   kubectl get ingress api-gateway
   # Update DNS records to point to ingress IP
   ```

---

## Useful Commands Reference

```bash
# Quick health check
kubectl get pods -l app=api-gateway && kubectl get hpa api-gateway

# View recent errors
kubectl logs -l app=api-gateway --tail=100 --since=10m | grep ERROR

# Get metrics summary
kubectl port-forward svc/api-gateway 8080:80 &
curl -s http://localhost:8080/metrics | grep -E "(requests_total|duration_seconds)"

# Emergency scale up
kubectl scale deployment api-gateway --replicas=15

# Emergency rollback
kubectl rollout undo deployment/api-gateway

# Restart all pods
kubectl rollout restart deployment/api-gateway

# Check resource usage
kubectl top pods -l app=api-gateway

# Get pod IPs
kubectl get pods -l app=api-gateway -o wide
```

---

## Contact and Escalation

1. **First 5 minutes**: Self-service using this runbook
2. **5-15 minutes**: Consult with team members in Slack
3. **15+ minutes or critical issue**: Page Platform Team Lead
4. **Security incidents**: Notify Security Team immediately
5. **Data loss**: Page CTO/VP Engineering

**Incident Slack Channel**: `#incidents-api-gateway`
**Status Page**: https://status.example.com

---

*Last Updated: 2025-11-17*
*Maintained by: Platform Team*
