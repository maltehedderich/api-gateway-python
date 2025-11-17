# API Gateway outputs
output "api_gateway_url" {
  description = "API Gateway invoke URL"
  value       = module.api_gateway.stage_invoke_url
}

output "api_gateway_id" {
  description = "API Gateway ID"
  value       = module.api_gateway.api_id
}

output "custom_domain_url" {
  description = "Custom domain URL (if configured)"
  value       = var.custom_domain_name != null ? "https://${var.custom_domain_name}" : null
}

# Lambda outputs
output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.lambda.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = module.lambda.function_arn
}

# DynamoDB outputs
output "sessions_table_name" {
  description = "Sessions DynamoDB table name"
  value       = module.dynamodb.sessions_table_name
}

output "rate_limits_table_name" {
  description = "Rate limits DynamoDB table name"
  value       = module.dynamodb.rate_limits_table_name
}

# CloudWatch outputs
output "log_group_name" {
  description = "Lambda CloudWatch Log Group name"
  value       = module.lambda.log_group_name
}

output "api_access_log_group_name" {
  description = "API Gateway access logs group name"
  value       = module.cloudwatch.access_log_group_name
}

# Deployment information
output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    environment   = var.environment
    region        = var.aws_region
    api_url       = module.api_gateway.stage_invoke_url
    custom_domain = var.custom_domain_name
    lambda_name   = module.lambda.function_name
  }
}
