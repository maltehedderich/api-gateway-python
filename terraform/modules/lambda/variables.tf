variable "prefix" {
  description = "Resource name prefix (e.g., 'api-gateway-dev')"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

# DynamoDB table references
variable "sessions_table_name" {
  description = "Name of the sessions DynamoDB table"
  type        = string
}

variable "sessions_table_arn" {
  description = "ARN of the sessions DynamoDB table"
  type        = string
}

variable "rate_limits_table_name" {
  description = "Name of the rate limits DynamoDB table"
  type        = string
}

variable "rate_limits_table_arn" {
  description = "ARN of the rate limits DynamoDB table"
  type        = string
}

# Lambda configuration
variable "lambda_package_path" {
  description = "Path to Lambda deployment package (ZIP file)"
  type        = string
  default     = "../lambda-package.zip"
}

variable "lambda_handler" {
  description = "Lambda handler function"
  type        = string
  default     = "gateway.lambda_handler.handler"
}

variable "lambda_runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 30
}

variable "reserved_concurrency" {
  description = "Reserved concurrent executions (-1 for unlimited)"
  type        = number
  default     = -1
}

# Application configuration
variable "token_signing_secret" {
  description = "Secret for signing session tokens"
  type        = string
  sensitive   = true
}

variable "rate_limiting_enabled" {
  description = "Enable rate limiting"
  type        = bool
  default     = true
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 7
}

variable "additional_env_vars" {
  description = "Additional environment variables for Lambda"
  type        = map(string)
  default     = {}
}

# API Gateway reference
variable "api_gateway_execution_arn" {
  description = "API Gateway execution ARN for Lambda permissions"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
