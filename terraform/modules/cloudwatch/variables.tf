variable "prefix" {
  description = "Resource name prefix (e.g., 'api-gateway-dev')"
  type        = string
}

variable "retention_in_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 7
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.retention_in_days)
    error_message = "Retention must be a valid CloudWatch Logs retention period."
  }
}

# Alarm configuration
variable "enable_alarms" {
  description = "Enable CloudWatch metric alarms"
  type        = bool
  default     = false
}

variable "lambda_function_name" {
  description = "Lambda function name for alarms"
  type        = string
  default     = ""
}

variable "api_gateway_id" {
  description = "API Gateway ID for alarms"
  type        = string
  default     = ""
}

variable "stage_name" {
  description = "API Gateway stage name for alarms"
  type        = string
  default     = ""
}

variable "error_threshold" {
  description = "Lambda error threshold for alarms"
  type        = number
  default     = 5
}

variable "throttle_threshold" {
  description = "Lambda throttle threshold for alarms"
  type        = number
  default     = 10
}

variable "api_5xx_threshold" {
  description = "API Gateway 5xx error threshold"
  type        = number
  default     = 5
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
