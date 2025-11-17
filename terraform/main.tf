terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration - can be customized
  # Example for S3 backend:
  # backend "s3" {
  #   bucket         = "my-terraform-state-bucket"
  #   key            = "api-gateway/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "api-gateway"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Local variables
locals {
  prefix = "${var.project_name}-${var.environment}"
  common_tags = merge(
    var.tags,
    {
      Project     = var.project_name
      Environment = var.environment
    }
  )
}

# DynamoDB tables for session and rate limiting
module "dynamodb" {
  source = "./modules/dynamodb"

  prefix      = local.prefix
  enable_pitr = var.enable_pitr
  tags        = local.common_tags
}

# CloudWatch Logs
module "cloudwatch" {
  source = "./modules/cloudwatch"

  prefix            = local.prefix
  retention_in_days = var.log_retention_days

  # Optional alarms
  enable_alarms        = var.enable_cloudwatch_alarms
  lambda_function_name = var.enable_cloudwatch_alarms ? module.lambda.function_name : ""
  api_gateway_id       = var.enable_cloudwatch_alarms ? module.api_gateway.api_id : ""
  stage_name           = var.enable_cloudwatch_alarms ? var.stage_name : ""

  tags = local.common_tags
}

# API Gateway HTTP API (created before Lambda to get execution ARN)
module "api_gateway" {
  source = "./modules/api-gateway"

  prefix      = local.prefix
  environment = var.environment
  stage_name  = var.stage_name

  lambda_invoke_arn      = module.lambda.function_invoke_arn
  integration_timeout_ms = var.lambda_timeout * 1000

  # Access logs
  enable_access_logs         = var.enable_access_logs
  access_log_destination_arn = module.cloudwatch.access_log_group_arn

  # CORS
  cors_allow_origins = var.cors_allow_origins
  cors_allow_methods = var.cors_allow_methods
  cors_allow_headers = var.cors_allow_headers

  # Throttling
  enable_throttling      = var.enable_api_throttling
  throttling_burst_limit = var.throttling_burst_limit
  throttling_rate_limit  = var.throttling_rate_limit

  # Custom domain (optional)
  custom_domain_name  = var.custom_domain_name
  acm_certificate_arn = var.custom_domain_name != null ? module.custom_domain[0].certificate_arn : null

  tags = local.common_tags

  depends_on = [module.custom_domain]
}

# Lambda function
module "lambda" {
  source = "./modules/lambda"

  prefix      = local.prefix
  environment = var.environment
  aws_region  = var.aws_region

  # DynamoDB tables
  sessions_table_name   = module.dynamodb.sessions_table_name
  sessions_table_arn    = module.dynamodb.sessions_table_arn
  rate_limits_table_name = module.dynamodb.rate_limits_table_name
  rate_limits_table_arn  = module.dynamodb.rate_limits_table_arn

  # Lambda configuration
  lambda_package_path = var.lambda_package_path
  lambda_handler      = var.lambda_handler
  lambda_runtime      = var.lambda_runtime
  lambda_memory_size  = var.lambda_memory_size
  lambda_timeout      = var.lambda_timeout
  reserved_concurrency = var.lambda_reserved_concurrency

  # Application configuration
  token_signing_secret  = var.token_signing_secret
  rate_limiting_enabled = var.rate_limiting_enabled
  log_level             = var.log_level
  log_retention_days    = var.log_retention_days

  # Additional environment variables (for upstream URLs, etc.)
  additional_env_vars = var.additional_lambda_env_vars

  # API Gateway execution ARN
  api_gateway_execution_arn = module.api_gateway.api_execution_arn

  tags = local.common_tags

  depends_on = [module.dynamodb]
}

# Custom domain (optional)
module "custom_domain" {
  count  = var.custom_domain_name != null ? 1 : 0
  source = "./modules/custom-domain"

  domain_name               = var.custom_domain_name
  create_certificate        = var.create_acm_certificate
  subject_alternative_names = var.certificate_san_list
  create_dns_record         = var.create_route53_record
  route53_zone_id           = var.route53_zone_id

  # These will be null initially, need to be added after API Gateway is created
  api_gateway_domain_name        = ""
  api_gateway_domain_zone_id     = ""

  tags = local.common_tags
}
