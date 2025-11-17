output "certificate_arn" {
  description = "ARN of the ACM certificate"
  value       = var.create_certificate ? aws_acm_certificate.api[0].arn : null
}

output "domain_name" {
  description = "Custom domain name"
  value       = var.domain_name
}

output "dns_record_name" {
  description = "DNS record name"
  value       = var.create_dns_record ? aws_route53_record.api[0].name : null
}
