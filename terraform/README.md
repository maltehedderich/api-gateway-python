# API Gateway - Terraform Infrastructure

This directory contains Terraform infrastructure as code (IaC) for deploying the API Gateway to AWS as a serverless application.

## Architecture Overview

The infrastructure deploys a fully serverless, cost-optimized API Gateway on AWS:

```
┌──────────────┐      ┌──────────────────┐      ┌────────────────┐
│   Internet   │─────▶│  API Gateway     │─────▶│  Lambda        │
│              │      │  (HTTP API)      │      │  (Python 3.12) │
└──────────────┘      └──────────────────┘      └────────────────┘
                              │                         │
                              │                         ├─────▶ DynamoDB
                              │                         │       (Sessions)
                              ▼                         │
                      ┌──────────────────┐              ├─────▶ DynamoDB
                      │  CloudWatch      │              │       (Rate Limits)
                      │  Logs            │◀─────────────┘
                      └──────────────────┘              └─────▶ Upstream APIs
```

### Components

- **API Gateway HTTP API**: Entry point with built-in throttling, CORS, and request validation
- **Lambda Function**: Runs the API Gateway application (Python 3.12)
- **DynamoDB Tables**:
  - `sessions`: Session storage with TTL (replaces Redis)
  - `rate_limits`: Rate limiting state with TTL (replaces Redis)
- **CloudWatch Logs**: Centralized logging for Lambda and API Gateway
- **IAM Roles**: Least-privilege execution roles
- **Optional**: Custom domain with ACM certificate and Route53 DNS

### Cost Optimization

- **On-demand pricing**: No fixed costs, pay only for usage
- **No VPC**: Lambda runs outside VPC to avoid NAT gateway costs ($32+/month)
- **DynamoDB on-demand**: No provisioned capacity charges
- **HTTP API**: ~70% cheaper than REST API
- **Configurable limits**: Reserved concurrency and throttling to prevent runaway costs

**Estimated Monthly Cost (Low Traffic):**
- API Gateway: $1-3/month (1M requests ~$1)
- Lambda: $0-5/month (128,000 seconds free tier)
- DynamoDB: $0-2/month (25GB + 25 WCU/RCU free tier)
- CloudWatch Logs: $0-1/month (5GB free tier)
- **Total**: ~$2-11/month for low-traffic MVP

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** >= 1.5.0 ([Install](https://developer.hashicorp.com/terraform/downloads))
3. **AWS CLI** configured with credentials ([Setup](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html))
4. **Python 3.12** and **uv** for building Lambda package

### AWS Permissions Required

The AWS user/role running Terraform needs these permissions:
- `lambda:*` (Lambda functions)
- `apigateway:*` (API Gateway)
- `dynamodb:*` (DynamoDB tables)
- `logs:*` (CloudWatch Logs)
- `iam:*` (IAM roles and policies)
- `acm:*` (ACM certificates - if using custom domain)
- `route53:*` (Route53 DNS - if using custom domain)

## Quick Start

### 1. Configure Backend (Optional but Recommended)

For production, use S3 backend for remote state:

```bash
# Create S3 bucket for Terraform state
aws s3 mb s3://my-terraform-state-bucket --region us-east-1

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Uncomment and configure the backend in `main.tf`:

```hcl
backend "s3" {
  bucket         = "my-terraform-state-bucket"
  key            = "api-gateway/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "terraform-state-lock"
}
```

### 2. Build Lambda Deployment Package

The Lambda function needs to be packaged with dependencies:

```bash
# Navigate to project root
cd /path/to/api-gateway-python

# Build Lambda package
./scripts/build-lambda.sh

# This creates: lambda-package.zip
```

**Note**: The build script is not included yet. See section below on creating the Lambda adapter.

### 3. Configure Variables

Copy the example variables file and customize:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and configure:

```hcl
# Required variables
token_signing_secret = "your-secure-secret-at-least-32-chars"

# Optional: Configure upstream service URLs
additional_lambda_env_vars = {
  UPSTREAM_USER_SERVICE_URL    = "https://users-api.example.com"
  UPSTREAM_PRODUCT_SERVICE_URL = "https://products-api.example.com"
}
```

**Security Note**: Never commit `terraform.tfvars` with secrets! Use environment variables or AWS Secrets Manager for production.

### 4. Initialize Terraform

```bash
terraform init
```

### 5. Preview Changes

```bash
terraform plan
```

Review the planned changes carefully.

### 6. Deploy Infrastructure

```bash
terraform apply
```

Type `yes` to confirm and deploy.

### 7. Test the Deployment

```bash
# Get the API Gateway URL
API_URL=$(terraform output -raw api_gateway_url)

# Test health endpoint
curl $API_URL/health

# Expected response:
# {"status":"healthy","environment":"dev","version":"0.1.0"}
```

## Configuration

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `token_signing_secret` | Secret for signing session tokens (min 32 chars) | `"your-secret-key"` |
| `lambda_package_path` | Path to Lambda ZIP package | `"./lambda-package.zip"` |

### Important Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `environment` | `"dev"` | Environment name (dev/staging/prod) |
| `aws_region` | `"us-east-1"` | AWS region (us-east-1 is cheapest) |
| `lambda_memory_size` | `512` | Lambda memory in MB (128-10240) |
| `lambda_timeout` | `30` | Lambda timeout in seconds |
| `log_retention_days` | `7` | CloudWatch Logs retention |
| `enable_pitr` | `false` | Enable DynamoDB point-in-time recovery |
| `enable_cloudwatch_alarms` | `false` | Enable CloudWatch metric alarms |
| `cors_allow_origins` | `["*"]` | CORS allowed origins |

### Custom Domain Configuration

To use a custom domain (e.g., `api.example.com`):

1. Add to `terraform.tfvars`:

```hcl
custom_domain_name     = "api.example.com"
create_acm_certificate = true
create_route53_record  = true
route53_zone_id        = "Z1234567890ABC"  # Your Route53 zone ID
```

2. Apply Terraform:

```bash
terraform apply
```

3. Wait for ACM certificate validation (DNS-based, takes 5-10 minutes)

## Module Structure

```
terraform/
├── main.tf                    # Root configuration
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── terraform.tfvars.example   # Example variables
├── README.md                  # This file
└── modules/
    ├── dynamodb/             # DynamoDB tables
    ├── lambda/               # Lambda function and IAM
    ├── api-gateway/          # API Gateway HTTP API
    ├── cloudwatch/           # CloudWatch Logs and alarms
    └── custom-domain/        # ACM certificate and Route53
```

## Outputs

After successful deployment, Terraform provides these outputs:

```bash
# API Gateway URL
terraform output api_gateway_url

# Lambda function name
terraform output lambda_function_name

# DynamoDB table names
terraform output sessions_table_name
terraform output rate_limits_table_name

# Summary of all resources
terraform output deployment_summary
```

## Updating the Deployment

### Update Lambda Code

1. Make changes to the application code
2. Rebuild the Lambda package:

```bash
./scripts/build-lambda.sh
```

3. Update Lambda function:

```bash
cd terraform
terraform apply -target=module.lambda
```

### Update Configuration

1. Edit `terraform.tfvars`
2. Apply changes:

```bash
terraform apply
```

## Monitoring and Debugging

### View Lambda Logs

```bash
# Get function name
FUNCTION_NAME=$(terraform output -raw lambda_function_name)

# Stream logs
aws logs tail "/aws/lambda/$FUNCTION_NAME" --follow
```

### View API Gateway Logs

```bash
# Get log group name
LOG_GROUP=$(terraform output -raw api_access_log_group_name)

# Stream logs
aws logs tail "$LOG_GROUP" --follow
```

### Check DynamoDB Tables

```bash
# Get table names
SESSIONS_TABLE=$(terraform output -raw sessions_table_name)
RATE_LIMITS_TABLE=$(terraform output -raw rate_limits_table_name)

# Scan sessions table (development only!)
aws dynamodb scan --table-name $SESSIONS_TABLE --max-items 10
```

### Invoke Lambda Directly (Testing)

```bash
FUNCTION_NAME=$(terraform output -raw lambda_function_name)

aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --payload '{"rawPath":"/health","requestContext":{"http":{"method":"GET"}}}' \
  response.json

cat response.json
```

## Cost Management

### Set Budget Alerts

Create a budget in AWS Console:
1. Navigate to AWS Billing → Budgets
2. Create a budget for your account
3. Set threshold (e.g., $20/month)
4. Add email alerts

### Monitor Costs

```bash
# Check current month costs (requires AWS CLI)
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

### Cost Control Features

- **Lambda reserved concurrency**: Limits max concurrent executions
- **API Gateway throttling**: Rate limits (burst/steady)
- **DynamoDB on-demand**: No minimum charges
- **CloudWatch Logs retention**: Auto-delete old logs

## Troubleshooting

### Issue: Lambda function not found

**Cause**: Lambda package doesn't exist or path is incorrect

**Solution**:
```bash
# Build the package
./scripts/build-lambda.sh

# Verify it exists
ls -lh lambda-package.zip

# Update terraform.tfvars with correct path
lambda_package_path = "./lambda-package.zip"
```

### Issue: Permission denied errors

**Cause**: IAM permissions missing

**Solution**: Check that your AWS user/role has the required permissions listed in Prerequisites.

### Issue: Certificate validation timeout

**Cause**: Route53 zone misconfiguration or DNS propagation delay

**Solution**:
1. Verify `route53_zone_id` is correct
2. Check Route53 for validation CNAME records
3. Wait 5-10 minutes for DNS propagation

### Issue: Lambda cold starts are slow

**Cause**: Large deployment package or VPC configuration

**Solution**:
1. Reduce package size (exclude unnecessary dependencies)
2. Increase Lambda memory (more memory = more CPU)
3. Consider provisioned concurrency for production (adds cost)

## Production Recommendations

Before deploying to production:

- [ ] Enable DynamoDB point-in-time recovery: `enable_pitr = true`
- [ ] Enable CloudWatch alarms: `enable_cloudwatch_alarms = true`
- [ ] Increase log retention: `log_retention_days = 30` or higher
- [ ] Use S3 backend for Terraform state
- [ ] Store secrets in AWS Secrets Manager (not terraform.tfvars)
- [ ] Configure specific CORS origins (not `["*"]`)
- [ ] Set up AWS Organizations for multi-account strategy
- [ ] Enable AWS CloudTrail for audit logging
- [ ] Configure Lambda reserved concurrency for cost control
- [ ] Set up CI/CD pipeline for automated deployments
- [ ] Add WAF rules to API Gateway (for DDoS protection)

## Cleanup

To destroy all resources and avoid charges:

```bash
terraform destroy
```

**Warning**: This deletes all data in DynamoDB tables! Backup important data first.

## Next Steps

1. **Adapt the application**: The current application uses aiohttp (long-running server). You need to create a Lambda adapter. See `src/gateway/lambda_handler.py` (to be created).

2. **Configure upstream services**: Update `additional_lambda_env_vars` with your backend service URLs.

3. **Set up CI/CD**: Automate builds and deployments using GitHub Actions, GitLab CI, or AWS CodePipeline.

4. **Add monitoring**: Configure CloudWatch dashboards and alarms.

5. **Implement caching**: Add CloudFront CDN in front of API Gateway for improved performance and reduced costs.

## Support

For issues or questions:
1. Check the main project README
2. Review Terraform documentation: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
3. AWS API Gateway docs: https://docs.aws.amazon.com/apigateway/
4. AWS Lambda docs: https://docs.aws.amazon.com/lambda/
