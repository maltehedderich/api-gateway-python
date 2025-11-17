variable "prefix" {
  description = "Resource name prefix (e.g., 'api-gateway-dev')"
  type        = string
}

variable "enable_pitr" {
  description = "Enable point-in-time recovery for DynamoDB tables"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
