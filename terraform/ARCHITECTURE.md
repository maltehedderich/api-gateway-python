# AWS Serverless Architecture for API Gateway

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Internet / Clients                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ HTTPS
                                 ▼
                    ┌────────────────────────┐
                    │   Route53 (Optional)   │
                    │  api.example.com       │
                    └────────────┬───────────┘
                                 │
                                 │ DNS
                                 ▼
                    ┌────────────────────────┐
                    │    ACM Certificate     │
                    │    (Optional)          │
                    └────────────┬───────────┘
                                 │
                                 │ TLS
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                     AWS API Gateway HTTP API                       │
│                                                                    │
│  • HTTP API (v2) - 70% cheaper than REST API                     │
│  • Built-in throttling & rate limiting                           │
│  • CORS support                                                  │
│  • Request validation                                            │
│  • CloudWatch access logs                                        │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             │ AWS_PROXY
                             │ (Payload 2.0)
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                         AWS Lambda Function                        │
│                                                                    │
│  Runtime: Python 3.12                                             │
│  Handler: gateway.lambda_handler.handler                          │
│  Memory: 512 MB (configurable)                                    │
│  Timeout: 30 seconds (configurable)                               │
│  Concurrency: Unlimited (configurable)                            │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               API Gateway Application                    │   │
│  │                                                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐       │   │
│  │  │  Request   │→ │    Auth    │→ │ Rate Limit │       │   │
│  │  │  Logging   │  │ Middleware │  │ Middleware │       │   │
│  │  └────────────┘  └────────────┘  └────────────┘       │   │
│  │                        ↓                                │   │
│  │                  ┌────────────┐                        │   │
│  │                  │   Proxy    │                        │   │
│  │                  │ Middleware │                        │   │
│  │                  └────────────┘                        │   │
│  │                        ↓                                │   │
│  │                  ┌────────────┐                        │   │
│  │                  │  Response  │                        │   │
│  │                  │  Logging   │                        │   │
│  │                  └────────────┘                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Environment Variables:                                           │
│  • GATEWAY_ENV, GATEWAY_LOG_LEVEL                                │
│  • GATEWAY_SESSION_TABLE_NAME                                    │
│  • GATEWAY_RATELIMIT_TABLE_NAME                                  │
│  • GATEWAY_TOKEN_SIGNING_SECRET                                  │
│  • UPSTREAM_*_SERVICE_URL                                        │
└─────┬────────────────────────┬─────────────────────┬──────────────┘
      │                        │                     │
      │                        │                     │ Proxy requests
      ▼                        ▼                     ▼
┌─────────────┐      ┌──────────────────┐    ┌──────────────┐
│  DynamoDB   │      │    DynamoDB      │    │   Upstream   │
│  Sessions   │      │  Rate Limits     │    │   Services   │
│             │      │                  │    │              │
│ • On-demand │      │  • On-demand     │    │ • User API   │
│ • TTL: 1hr  │      │  • TTL: 60s      │    │ • Product API│
│ • Encrypted │      │  • Encrypted     │    │ • Admin API  │
└─────────────┘      └──────────────────┘    └──────────────┘

                             ↓
                  ┌──────────────────────┐
                  │   CloudWatch Logs    │
                  │                      │
                  │ • Lambda logs        │
                  │ • API Gateway logs   │
                  │ • Retention: 7 days  │
                  │                      │
                  │   CloudWatch Metrics │
                  │                      │
                  │ • Invocations        │
                  │ • Errors             │
                  │ • Duration           │
                  │ • Throttles          │
                  └──────────────────────┘

                             ↓
                  ┌──────────────────────┐
                  │  CloudWatch Alarms   │
                  │      (Optional)      │
                  │                      │
                  │ • Lambda errors      │
                  │ • API 5xx errors     │
                  │ • Throttles          │
                  └──────────────────────┘
```

## Component Details

### 1. API Gateway HTTP API

**Purpose**: Entry point for all HTTP requests

**Features**:
- HTTP API v2 (cheaper than REST API)
- Built-in throttling (configurable)
- CORS support
- CloudWatch access logs
- Custom domain support (optional)

**Cost**: ~$1.00 per million requests

**Configuration**:
- Stage: `v1` (configurable)
- Throttling: 50 req/s steady, 100 burst
- Integration: AWS_PROXY to Lambda
- Timeout: 30 seconds

### 2. Lambda Function

**Purpose**: Runs the API Gateway application logic

**Runtime**: Python 3.12

**Memory**: 512 MB (configurable, 128-10240 MB)
- More memory = more CPU power
- More memory = higher cost per ms

**Timeout**: 30 seconds (configurable, max 900s)

**Concurrency**:
- Default: Unlimited
- Configurable: Reserved concurrency for cost control

**Cold Start**:
- ~1-3 seconds for first invocation
- Subsequent invocations: ~10-50ms
- Mitigations: Provisioned concurrency (adds cost)

**Cost**: ~$0.20 per million requests @ 512MB, 100ms avg duration

**IAM Permissions**:
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` (CloudWatch)
- `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:DeleteItem`, `dynamodb:Query`, `dynamodb:Scan` (DynamoDB tables)

### 3. DynamoDB Tables

#### Sessions Table

**Purpose**: Store session data (replaces Redis)

**Schema**:
```
Primary Key: session_id (String)
Attributes:
  - data (String): JSON-encoded session data
  - ttl (Number): TTL timestamp for auto-deletion
```

**Capacity**: On-demand (pay per request)

**TTL**: Enabled, auto-deletes expired sessions

**Encryption**: Server-side encryption enabled

**Cost**: ~$1.25 per million write requests, ~$0.25 per million read requests

#### Rate Limits Table

**Purpose**: Store rate limiting counters (replaces Redis)

**Schema**:
```
Primary Key: rate_limit_key (String)
Attributes:
  - count (Number): Current request count
  - state (String): JSON-encoded rate limit state
  - ttl (Number): TTL timestamp for auto-deletion
```

**Capacity**: On-demand (pay per request)

**TTL**: Enabled, auto-deletes expired counters

**Encryption**: Server-side encryption enabled

**Cost**: ~$1.25 per million write requests, ~$0.25 per million read requests

### 4. CloudWatch Logs

**Purpose**: Centralized logging for Lambda and API Gateway

**Log Groups**:
- `/aws/lambda/{function-name}` - Lambda function logs
- `/aws/apigateway/{prefix}-access-logs` - API Gateway access logs

**Retention**: 7 days (configurable: 1, 3, 5, 7, 14, 30, 60, 90, ...)

**Cost**: ~$0.50 per GB ingested, ~$0.03 per GB stored

### 5. CloudWatch Alarms (Optional)

**Purpose**: Alert on operational issues

**Alarms**:
- Lambda errors threshold
- Lambda throttles threshold
- API Gateway 5xx errors

**Actions**: Can be configured to send SNS notifications

### 6. IAM Roles

#### Lambda Execution Role

**Trust Policy**: Lambda service can assume role

**Managed Policies**:
- `AWSLambdaBasicExecutionRole` (CloudWatch Logs)

**Inline Policies**:
- DynamoDB access to sessions and rate_limits tables

**Principle of Least Privilege**: Only grants necessary permissions

## Traffic Flow

### Typical Request Flow

1. **Client Request**
   - Client sends HTTPS request to API Gateway
   - Optional: Custom domain resolves via Route53

2. **API Gateway**
   - Validates request format
   - Checks throttling limits
   - Logs request to CloudWatch
   - Invokes Lambda function with API Gateway v2 payload

3. **Lambda Function**
   - Mangum adapter converts API Gateway event to ASGI
   - Request logging middleware logs request details
   - Authentication middleware validates session token
     - Queries DynamoDB sessions table
     - Validates token signature and expiration
   - Rate limiting middleware checks limits
     - Queries/updates DynamoDB rate_limits table
     - Uses token bucket algorithm
   - Proxy middleware forwards request to upstream service
   - Response logging middleware logs response details
   - Returns response to API Gateway

4. **API Gateway Response**
   - Logs response to CloudWatch
   - Returns response to client

### Session Validation Flow

```
Lambda → DynamoDB Sessions Table
  │
  ├→ GetItem(session_id)
  │   └→ Check TTL not expired
  │   └→ Parse session data (user_id, roles, etc.)
  │
  └→ Attach user context to request
```

### Rate Limiting Flow

```
Lambda → DynamoDB Rate Limits Table
  │
  ├→ GetItem(rate_limit_key)
  │   └→ Get current count and last_update
  │
  ├→ Calculate tokens to add (token bucket)
  │   └→ elapsed_time * refill_rate
  │
  ├→ Check if request can be allowed
  │   └→ available_tokens >= 1
  │
  └→ UpdateItem (atomic increment)
      └→ Set TTL for auto-cleanup
```

## Scalability

### Horizontal Scaling

- **Lambda**: Auto-scales to 1000 concurrent executions by default
- **DynamoDB**: On-demand scales automatically
- **API Gateway**: Handles any request rate (with throttling)

### Limits

- **Lambda**: 1000 concurrent executions (soft limit, can be increased)
- **API Gateway**: 10,000 requests/second (soft limit, can be increased)
- **DynamoDB**: No throughput limits with on-demand mode

### Performance Tuning

1. **Increase Lambda memory**: More CPU for faster processing
2. **Use provisioned concurrency**: Eliminate cold starts (adds cost)
3. **Optimize Lambda package size**: Faster cold starts
4. **Use DynamoDB DAX**: Cache for DynamoDB (adds cost)
5. **Add CloudFront CDN**: Cache responses, reduce Lambda invocations

## Security

### Network Security

- **No VPC**: Lambda runs outside VPC for cost optimization
  - No NAT Gateway costs (~$32/month)
  - Faster cold starts
  - Still secure via IAM

- **Encryption**: All data encrypted in transit and at rest
  - TLS 1.2+ for API Gateway
  - Server-side encryption for DynamoDB

### IAM Security

- **Least Privilege**: Lambda role only has necessary permissions
- **No Long-Term Credentials**: Uses IAM role, no access keys
- **Resource-Based Policies**: API Gateway can invoke Lambda

### Application Security

- **Session Token Validation**: Cryptographic signature verification
- **Rate Limiting**: Prevents abuse and DDoS
- **Input Validation**: Pydantic models validate all inputs
- **Security Headers**: HSTS, CSP, X-Frame-Options, etc.

## Cost Analysis

### Example: Low-Traffic API (1M requests/month)

| Component | Usage | Cost |
|-----------|-------|------|
| API Gateway | 1M requests | $1.00 |
| Lambda | 1M requests × 100ms × 512MB | $2.08 |
| DynamoDB | 1M reads + 100K writes | $0.38 |
| CloudWatch Logs | 1GB | $0.50 |
| Data Transfer | 1GB out | $0.09 |
| **Total** | | **$4.05/month** |

### Example: Medium-Traffic API (10M requests/month)

| Component | Usage | Cost |
|-----------|-------|------|
| API Gateway | 10M requests | $10.00 |
| Lambda | 10M requests × 100ms × 512MB | $20.83 |
| DynamoDB | 10M reads + 1M writes | $3.75 |
| CloudWatch Logs | 10GB | $5.00 |
| Data Transfer | 10GB out | $0.90 |
| **Total** | | **$40.48/month** |

### Cost Optimization Tips

1. **Reduce Lambda memory**: If CPU-light workload
2. **Reduce log retention**: 3-7 days instead of 30+
3. **Use reserved concurrency**: Prevent runaway costs
4. **Enable DynamoDB auto-scaling**: For predictable workloads (cheaper than on-demand)
5. **Add CloudFront**: Cache responses, reduce Lambda invocations

## Monitoring and Observability

### CloudWatch Metrics

**Lambda Metrics**:
- Invocations
- Errors
- Duration
- Throttles
- ConcurrentExecutions
- IteratorAge (for streams)

**API Gateway Metrics**:
- Count (requests)
- IntegrationLatency
- Latency
- 4XXError
- 5XXError

**DynamoDB Metrics**:
- ConsumedReadCapacityUnits
- ConsumedWriteCapacityUnits
- UserErrors
- SystemErrors

### Logging

**Structured JSON Logs**:
```json
{
  "timestamp": "2025-11-17T12:34:56.789Z",
  "level": "INFO",
  "message": "Request processed",
  "correlation_id": "req-abc123",
  "user_id": "user-456",
  "method": "GET",
  "path": "/api/v1/users",
  "status_code": 200,
  "duration_ms": 45
}
```

**Log Insights Queries**:
- Error rate
- P50/P90/P99 latency
- Top error messages
- Requests by user/IP

### Tracing (Optional)

- **AWS X-Ray**: Distributed tracing
  - Add `aws-xray-sdk` to Lambda
  - Enable in API Gateway
  - Visualize request flow

## Disaster Recovery

### Backup

- **DynamoDB**: Point-in-time recovery (optional, adds cost)
- **Terraform State**: S3 with versioning enabled
- **Lambda Code**: Stored in S3 automatically

### Recovery

- **RTO** (Recovery Time Objective): ~5-10 minutes
  - Recreate from Terraform state
  - Lambda code automatically available

- **RPO** (Recovery Point Objective):
  - DynamoDB: 5 minutes with PITR
  - Session data: Acceptable loss (users re-authenticate)

### Multi-Region (Optional)

For high availability, deploy to multiple regions:
- Route53 health checks and failover
- DynamoDB global tables
- Replicate Lambda and API Gateway to secondary region

## Limitations and Considerations

### Known Limitations

1. **Cold Starts**: First request ~1-3s latency
2. **Maximum Timeout**: Lambda limited to 15 minutes
3. **Package Size**: Lambda deployment package max 250 MB unzipped
4. **DynamoDB Latency**: Single-digit milliseconds (slower than Redis)
5. **No VPC Integration**: Can't directly access VPC resources

### When NOT to Use This Architecture

- **High-frequency trading**: Cold starts unacceptable
- **Long-running tasks**: Use ECS/Fargate or Step Functions
- **Very large payloads**: Use S3 with Lambda triggers
- **Sub-millisecond latency**: Use dedicated servers
- **Legacy protocols**: Lambda only supports HTTP(S)

## Future Enhancements

### Potential Improvements

1. **Add API caching**: CloudFront or API Gateway cache
2. **Use DynamoDB DAX**: In-memory cache for DynamoDB
3. **Implement Circuit Breaker**: Protect upstream services
4. **Add Request Tracing**: AWS X-Ray integration
5. **Use Secrets Manager**: Store token signing secret
6. **Add WAF**: Web Application Firewall for security
7. **Implement API versioning**: Multiple API versions
8. **Add GraphQL support**: Apollo Server on Lambda
9. **Use EventBridge**: Event-driven architecture
10. **Add Cognito**: User authentication and authorization
