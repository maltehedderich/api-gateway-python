# General configuration
variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "api-gateway"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# DynamoDB configuration
variable "enable_pitr" {
  description = "Enable point-in-time recovery for DynamoDB tables (recommended for production)"
  type        = bool
  default     = false
}

# Lambda configuration
variable "lambda_package_path" {
  description = "Path to Lambda deployment package (ZIP file). Build with: scripts/build-lambda.sh"
  type        = string
  default     = "./lambda-package.zip"
}

variable "lambda_handler" {
  description = "Lambda handler function (module.function)"
  type        = string
  default     = "gateway.lambda_handler.handler"
}

variable "lambda_runtime" {
  description = "Lambda runtime version"
  type        = string
  default     = "python3.12"
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB (128-10240). More memory = more CPU."
  type        = number
  default     = 512
  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "Lambda memory size must be between 128 and 10240 MB."
  }
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds (1-900)"
  type        = number
  default     = 30
  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "Lambda timeout must be between 1 and 900 seconds."
  }
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrent executions (-1 for unlimited, 0 to disable, >0 to reserve)"
  type        = number
  default     = -1
}

# Application configuration
variable "token_signing_secret" {
  description = "Secret key for signing session tokens (min 32 characters)"
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.token_signing_secret) >= 32
    error_message = "Token signing secret must be at least 32 characters."
  }
}

variable "rate_limiting_enabled" {
  description = "Enable rate limiting middleware"
  type        = bool
  default     = true
}

variable "log_level" {
  description = "Application log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
  type        = string
  default     = "INFO"
  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], var.log_level)
    error_message = "Log level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days (1, 3, 5, 7, 14, 30, 60, 90, etc.)"
  type        = number
  default     = 7
}

variable "additional_lambda_env_vars" {
  description = "Additional environment variables for Lambda (e.g., upstream service URLs)"
  type        = map(string)
  default     = {}
  # Example:
  # {
  #   UPSTREAM_USER_SERVICE_URL    = "https://users.example.com"
  #   UPSTREAM_PRODUCT_SERVICE_URL = "https://products.example.com"
  # }
}

# API Gateway configuration
variable "stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "v1"
}

variable "enable_access_logs" {
  description = "Enable API Gateway access logs"
  type        = bool
  default     = true
}

variable "enable_api_throttling" {
  description = "Enable API Gateway throttling (recommended for cost control)"
  type        = bool
  default     = true
}

variable "throttling_burst_limit" {
  description = "API Gateway throttling burst limit (requests)"
  type        = number
  default     = 100
}

variable "throttling_rate_limit" {
  description = "API Gateway throttling rate limit (requests per second)"
  type        = number
  default     = 50
}

# CORS configuration
variable "cors_allow_origins" {
  description = "CORS allowed origins. Use ['*'] for development, specific domains for production."
  type        = list(string)
  default     = ["*"]
}

variable "cors_allow_methods" {
  description = "CORS allowed HTTP methods"
  type        = list(string)
  default     = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
}

variable "cors_allow_headers" {
  description = "CORS allowed headers"
  type        = list(string)
  default     = ["Content-Type", "Authorization", "X-Request-ID"]
}

# CloudWatch alarms (optional)
variable "enable_cloudwatch_alarms" {
  description = "Enable CloudWatch metric alarms (recommended for production)"
  type        = bool
  default     = false
}

# Custom domain configuration (optional)
variable "custom_domain_name" {
  description = "Custom domain name for API Gateway (e.g., api.example.com). Leave null to disable."
  type        = string
  default     = null
}

variable "create_acm_certificate" {
  description = "Create ACM certificate for custom domain (set false if using existing certificate)"
  type        = bool
  default     = true
}

variable "certificate_san_list" {
  description = "Subject alternative names for ACM certificate"
  type        = list(string)
  default     = []
}

variable "create_route53_record" {
  description = "Create Route53 DNS record for custom domain"
  type        = bool
  default     = true
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID (required if using custom domain)"
  type        = string
  default     = null
}
