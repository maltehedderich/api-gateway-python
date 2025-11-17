# DynamoDB tables for session storage and rate limiting

# Session storage table
resource "aws_dynamodb_table" "sessions" {
  name         = "${var.prefix}-sessions"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  # Enable TTL for automatic session expiration
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Enable point-in-time recovery for production
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.prefix}-sessions"
      Description = "Session storage for API Gateway"
    }
  )
}

# Rate limiting table
resource "aws_dynamodb_table" "rate_limits" {
  name         = "${var.prefix}-rate-limits"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing
  hash_key     = "rate_limit_key"

  attribute {
    name = "rate_limit_key"
    type = "S"
  }

  # Enable TTL for automatic cleanup
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Enable point-in-time recovery for production
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.prefix}-rate-limits"
      Description = "Rate limiting storage for API Gateway"
    }
  )
}
