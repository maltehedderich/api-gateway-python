output "api_id" {
  description = "ID of the API Gateway"
  value       = aws_apigatewayv2_api.gateway.id
}

output "api_endpoint" {
  description = "Default endpoint URL of the API Gateway"
  value       = aws_apigatewayv2_api.gateway.api_endpoint
}

output "api_execution_arn" {
  description = "Execution ARN of the API Gateway"
  value       = aws_apigatewayv2_api.gateway.execution_arn
}

output "stage_name" {
  description = "Name of the deployment stage"
  value       = aws_apigatewayv2_stage.default.name
}

output "stage_invoke_url" {
  description = "Invoke URL for the deployment stage"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "custom_domain_name" {
  description = "Custom domain name (if configured)"
  value       = var.custom_domain_name != null ? aws_apigatewayv2_domain_name.custom[0].domain_name : null
}

output "custom_domain_target" {
  description = "Custom domain target for DNS configuration"
  value       = var.custom_domain_name != null ? aws_apigatewayv2_domain_name.custom[0].domain_name_configuration[0].target_domain_name : null
}
