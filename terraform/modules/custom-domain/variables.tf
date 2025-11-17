variable "domain_name" {
  description = "Custom domain name (e.g., api.example.com)"
  type        = string
}

variable "create_certificate" {
  description = "Create ACM certificate (set false if using existing certificate)"
  type        = bool
  default     = true
}

variable "subject_alternative_names" {
  description = "Subject alternative names for the certificate"
  type        = list(string)
  default     = []
}

variable "create_dns_record" {
  description = "Create Route53 DNS record"
  type        = bool
  default     = true
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
  default     = null
}

# API Gateway custom domain info
variable "api_gateway_domain_name" {
  description = "API Gateway custom domain name (target for DNS)"
  type        = string
}

variable "api_gateway_domain_zone_id" {
  description = "API Gateway custom domain hosted zone ID"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
