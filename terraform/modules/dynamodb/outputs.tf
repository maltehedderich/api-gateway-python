output "sessions_table_name" {
  description = "Name of the sessions DynamoDB table"
  value       = aws_dynamodb_table.sessions.name
}

output "sessions_table_arn" {
  description = "ARN of the sessions DynamoDB table"
  value       = aws_dynamodb_table.sessions.arn
}

output "rate_limits_table_name" {
  description = "Name of the rate limits DynamoDB table"
  value       = aws_dynamodb_table.rate_limits.name
}

output "rate_limits_table_arn" {
  description = "ARN of the rate limits DynamoDB table"
  value       = aws_dynamodb_table.rate_limits.arn
}
