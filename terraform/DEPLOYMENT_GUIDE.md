# AWS Serverless Deployment Guide

This guide walks you through deploying the API Gateway to AWS as a serverless application.

## Overview

This deployment creates:
- **AWS Lambda** function running the Python API Gateway
- **API Gateway HTTP API** as the entry point
- **DynamoDB** tables for session storage and rate limiting
- **CloudWatch Logs** for monitoring
- **IAM roles** with least-privilege permissions

**Estimated cost**: $2-11/month for low-traffic MVP workloads

## Prerequisites

Before you begin, ensure you have:

1. **AWS Account** with administrative access
2. **AWS CLI** installed and configured
3. **Terraform** >= 1.5.0 installed
4. **Python 3.12** installed
5. **uv** package manager installed

### 1. Configure AWS CLI

```bash
# Configure AWS credentials
aws configure

# Verify access
aws sts get-caller-identity
```

## Step-by-Step Deployment

### Step 1: Install Dependencies

```bash
# Install uv if not already installed
pip install uv

# Sync project dependencies
uv sync --all-extras
```

### Step 2: Build Lambda Package

The application needs to be packaged with dependencies for Lambda:

```bash
# From project root
./scripts/build-lambda.sh
```

This creates `lambda-package.zip` containing:
- Application code (`gateway/`)
- Python dependencies (aiohttp, pydantic, boto3, etc.)
- Optimized for size (removes tests, docs, cache files)

**Expected package size**: 10-25 MB

### Step 3: Configure Terraform Variables

```bash
cd terraform

# Copy example variables
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
# Required: Generate a secure secret
token_signing_secret = "your-very-secure-secret-at-least-32-characters-long"

# Environment
environment = "dev"
aws_region  = "us-east-1"  # Use us-east-1 for lowest costs

# Lambda configuration
lambda_package_path = "../lambda-package.zip"
lambda_memory_size  = 512  # Start with 512 MB
lambda_timeout      = 30   # 30 seconds

# Logging
log_level          = "INFO"
log_retention_days = 7  # Short retention for dev

# IMPORTANT: Configure your upstream services
additional_lambda_env_vars = {
  # Replace with your actual backend service URLs
  UPSTREAM_USER_SERVICE_URL    = "https://users-api.example.com"
  UPSTREAM_PRODUCT_SERVICE_URL = "https://products-api.example.com"
  UPSTREAM_ADMIN_SERVICE_URL   = "https://admin-api.example.com"
}
```

**Security Note**: Never commit `terraform.tfvars` with real secrets!

### Step 4: Configure Terraform Backend (Optional but Recommended)

For production, use S3 backend for remote state:

```bash
# Create S3 bucket for state
aws s3 mb s3://my-company-terraform-state --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket my-company-terraform-state \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Uncomment backend configuration in `main.tf`:

```hcl
backend "s3" {
  bucket         = "my-company-terraform-state"
  key            = "api-gateway/dev/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "terraform-state-lock"
}
```

### Step 5: Initialize Terraform

```bash
terraform init
```

This downloads the AWS provider and initializes the backend.

### Step 6: Review Planned Changes

```bash
terraform plan
```

Review the output carefully. You should see:
- 2 DynamoDB tables (sessions, rate-limits)
- 1 Lambda function
- 1 IAM role with 2 policies
- 1 API Gateway HTTP API
- 2 CloudWatch Log Groups
- Various supporting resources

### Step 7: Deploy Infrastructure

```bash
terraform apply
```

Type `yes` when prompted.

Deployment takes ~2-3 minutes.

### Step 8: Test the Deployment

```bash
# Get the API Gateway URL
API_URL=$(terraform output -raw api_gateway_url)

echo "API Gateway URL: $API_URL"

# Test health endpoint
curl $API_URL/health

# Expected response:
# {"status":"healthy","environment":"dev","version":"0.1.0"}

# Test liveness
curl $API_URL/health/live

# Test readiness (checks DynamoDB connectivity)
curl $API_URL/health/ready
```

### Step 9: View Logs

```bash
# Get Lambda function name
FUNCTION_NAME=$(terraform output -raw lambda_function_name)

# Stream Lambda logs
aws logs tail "/aws/lambda/$FUNCTION_NAME" --follow

# In another terminal, make test requests
curl $API_URL/health
```

## Configuration Details

### Required Customization

You **must** customize these for your deployment:

1. **Token Signing Secret**: Generate a secure random string
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Upstream Service URLs**: Configure backend services in `additional_lambda_env_vars`

3. **Route Configuration**: Update `src/gateway/lambda_handler.py:_load_routes()` with your actual routes

### Optional Customization

- **Custom Domain**: See Custom Domain Setup section below
- **CloudWatch Alarms**: Set `enable_cloudwatch_alarms = true` for production
- **DynamoDB PITR**: Set `enable_pitr = true` for production backups
- **CORS Origins**: Change from `["*"]` to specific domains in production
- **Lambda Memory**: Adjust `lambda_memory_size` based on performance needs
- **Log Retention**: Increase `log_retention_days` for production

## Custom Domain Setup

To use a custom domain (e.g., `api.example.com`):

### Prerequisites
- Own a domain registered in Route53
- Have the Route53 hosted zone ID

### Configuration

1. Update `terraform.tfvars`:

```hcl
custom_domain_name     = "api.example.com"
create_acm_certificate = true
create_route53_record  = true
route53_zone_id        = "Z1234567890ABC"  # Your zone ID
```

2. Apply Terraform:

```bash
terraform apply
```

3. Wait for certificate validation (5-10 minutes):

```bash
# Check certificate status
aws acm describe-certificate \
  --certificate-arn $(terraform output -raw certificate_arn) \
  --query 'Certificate.Status'
```

4. Once validated, test custom domain:

```bash
curl https://api.example.com/health
```

## Monitoring and Operations

### View CloudWatch Metrics

```bash
# Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=$FUNCTION_NAME \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=$FUNCTION_NAME \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

### View DynamoDB Tables

```bash
# List sessions
SESSIONS_TABLE=$(terraform output -raw sessions_table_name)
aws dynamodb scan --table-name $SESSIONS_TABLE --max-items 10

# List rate limits
RATE_LIMITS_TABLE=$(terraform output -raw rate_limits_table_name)
aws dynamodb scan --table-name $RATE_LIMITS_TABLE --max-items 10
```

### Invoke Lambda Directly (Testing)

```bash
# Create test event
cat > test-event.json << 'EOF'
{
  "version": "2.0",
  "routeKey": "$default",
  "rawPath": "/health",
  "rawQueryString": "",
  "headers": {
    "accept": "application/json"
  },
  "requestContext": {
    "http": {
      "method": "GET",
      "path": "/health"
    },
    "requestId": "test-123"
  }
}
EOF

# Invoke Lambda
aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --payload file://test-event.json \
  response.json

# View response
cat response.json | jq .
```

## Updating the Deployment

### Update Lambda Code

1. Make changes to application code
2. Rebuild package:
   ```bash
   ./scripts/build-lambda.sh
   ```
3. Update Lambda:
   ```bash
   cd terraform
   terraform apply -target=module.lambda
   ```

### Update Infrastructure

```bash
# Make changes to terraform files
# Then apply
terraform apply
```

## Cost Optimization

### Current Cost Estimates (us-east-1, low traffic)

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| API Gateway | 1M requests | ~$1.00 |
| Lambda | 1M requests @ 512MB, 100ms avg | ~$2.00 |
| DynamoDB | 1M reads, 100K writes | ~$0.50 |
| CloudWatch Logs | 1GB logs | ~$0.50 |
| **Total** | | **~$4.00/month** |

### Cost Control Measures

1. **Set reserved concurrency** to prevent runaway costs:
   ```hcl
   lambda_reserved_concurrency = 10  # Max 10 concurrent executions
   ```

2. **Enable API throttling**:
   ```hcl
   throttling_rate_limit  = 50   # 50 requests/second max
   throttling_burst_limit = 100  # 100 burst
   ```

3. **Set AWS budgets**:
   ```bash
   aws budgets create-budget \
     --account-id $(aws sts get-caller-identity --query Account --output text) \
     --budget file://budget.json
   ```

4. **Reduce log retention**:
   ```hcl
   log_retention_days = 3  # Minimum
   ```

## Troubleshooting

### Lambda Package Too Large

If package exceeds 50 MB:

```bash
# Check package size
ls -lh lambda-package.zip

# Optimize further
cd build/lambda
du -sh *  # Find large dependencies

# Remove unnecessary packages
# Edit scripts/build-lambda.sh to exclude them
```

### DynamoDB Connection Errors

Check IAM permissions:

```bash
# Test DynamoDB access
aws dynamodb describe-table --table-name $SESSIONS_TABLE
```

Ensure Lambda execution role has DynamoDB permissions.

### Cold Start Latency

Lambda cold starts can take 1-3 seconds. To reduce:

1. **Increase memory** (more CPU):
   ```hcl
   lambda_memory_size = 1024
   ```

2. **Use provisioned concurrency** (adds cost):
   ```hcl
   provisioned_concurrent_executions = 2
   ```

3. **Optimize package size** (faster cold starts)

### API Gateway 502/504 Errors

Check Lambda timeout:

```bash
# Increase timeout
lambda_timeout = 60  # Max 900 seconds
```

Check Lambda logs for errors:

```bash
aws logs tail "/aws/lambda/$FUNCTION_NAME" --since 10m
```

## Production Checklist

Before deploying to production:

- [ ] Use S3 backend for Terraform state
- [ ] Store secrets in AWS Secrets Manager (not terraform.tfvars)
- [ ] Enable DynamoDB point-in-time recovery: `enable_pitr = true`
- [ ] Enable CloudWatch alarms: `enable_cloudwatch_alarms = true`
- [ ] Increase log retention: `log_retention_days = 30`
- [ ] Configure specific CORS origins (not `["*"]`)
- [ ] Set up custom domain with ACM certificate
- [ ] Enable AWS WAF for DDoS protection
- [ ] Configure AWS CloudTrail for audit logging
- [ ] Set up AWS Budgets and billing alerts
- [ ] Test disaster recovery procedures
- [ ] Document runbooks for common operations
- [ ] Set up CI/CD pipeline for automated deployments
- [ ] Configure Lambda reserved concurrency
- [ ] Review and harden IAM policies

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Build Lambda package
        run: ./scripts/build-lambda.sh

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.5.0

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Apply
        run: terraform apply -auto-approve
        working-directory: terraform
        env:
          TF_VAR_token_signing_secret: ${{ secrets.TOKEN_SIGNING_SECRET }}
```

## Cleanup

To destroy all resources:

```bash
cd terraform
terraform destroy
```

**Warning**: This permanently deletes all data in DynamoDB tables!

## Next Steps

1. **Configure authentication**: Implement session token validation
2. **Set up monitoring**: Create CloudWatch dashboards
3. **Load testing**: Use Locust or Apache Bench to test performance
4. **Security audit**: Review IAM policies and security groups
5. **Documentation**: Document API endpoints and usage

## Support

For issues:
1. Check CloudWatch Logs for error details
2. Review Terraform documentation
3. Check AWS service health dashboard
4. Contact your AWS support team (if applicable)
