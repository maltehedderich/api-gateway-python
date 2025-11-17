output "access_log_group_name" {
  description = "Name of the API Gateway access logs group"
  value       = aws_cloudwatch_log_group.api_gateway_access_logs.name
}

output "access_log_group_arn" {
  description = "ARN of the API Gateway access logs group"
  value       = aws_cloudwatch_log_group.api_gateway_access_logs.arn
}

output "lambda_errors_alarm_arn" {
  description = "ARN of the Lambda errors alarm (if enabled)"
  value       = var.enable_alarms ? aws_cloudwatch_metric_alarm.lambda_errors[0].arn : null
}

output "lambda_throttles_alarm_arn" {
  description = "ARN of the Lambda throttles alarm (if enabled)"
  value       = var.enable_alarms ? aws_cloudwatch_metric_alarm.lambda_throttles[0].arn : null
}

output "api_5xx_alarm_arn" {
  description = "ARN of the API Gateway 5xx errors alarm (if enabled)"
  value       = var.enable_alarms ? aws_cloudwatch_metric_alarm.api_gateway_5xx[0].arn : null
}
