variable "prefix" {
  description = "Resource name prefix (e.g., 'api-gateway-dev')"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "v1"
}

# Lambda integration
variable "lambda_invoke_arn" {
  description = "Lambda function invoke ARN"
  type        = string
}

variable "integration_timeout_ms" {
  description = "Integration timeout in milliseconds (max 30000)"
  type        = number
  default     = 30000
}

# CORS configuration
variable "cors_allow_origins" {
  description = "CORS allowed origins"
  type        = list(string)
  default     = ["*"]
}

variable "cors_allow_methods" {
  description = "CORS allowed methods"
  type        = list(string)
  default     = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
}

variable "cors_allow_headers" {
  description = "CORS allowed headers"
  type        = list(string)
  default     = ["Content-Type", "Authorization", "X-Request-ID"]
}

variable "cors_max_age" {
  description = "CORS max age in seconds"
  type        = number
  default     = 300
}

# Access logging
variable "enable_access_logs" {
  description = "Enable API Gateway access logs"
  type        = bool
  default     = true
}

variable "access_log_destination_arn" {
  description = "CloudWatch Logs ARN for access logs"
  type        = string
  default     = null
}

# Throttling
variable "enable_throttling" {
  description = "Enable API Gateway throttling"
  type        = bool
  default     = true
}

variable "throttling_burst_limit" {
  description = "Throttling burst limit (requests)"
  type        = number
  default     = 100
}

variable "throttling_rate_limit" {
  description = "Throttling rate limit (requests per second)"
  type        = number
  default     = 50
}

# Custom domain (optional)
variable "custom_domain_name" {
  description = "Custom domain name for API Gateway (optional)"
  type        = string
  default     = null
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for custom domain (required if custom_domain_name is set)"
  type        = string
  default     = null
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
