# API Gateway HTTP API (cheaper and simpler than REST API)

resource "aws_apigatewayv2_api" "gateway" {
  name          = "${var.prefix}-api"
  protocol_type = "HTTP"
  description   = "API Gateway for ${var.environment} environment"

  # CORS configuration (optional)
  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_methods = var.cors_allow_methods
    allow_headers = var.cors_allow_headers
    max_age       = var.cors_max_age
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.prefix}-api"
    }
  )
}

# Lambda integration
resource "aws_apigatewayv2_integration" "lambda" {
  api_id           = aws_apigatewayv2_api.gateway.id
  integration_type = "AWS_PROXY"

  connection_type      = "INTERNET"
  description          = "Lambda integration for API Gateway"
  integration_method   = "POST"
  integration_uri      = var.lambda_invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds = var.integration_timeout_ms
}

# Default route (catch-all)
resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.gateway.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Deployment stage
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.gateway.id
  name        = var.stage_name
  auto_deploy = true

  # Access logs (optional but recommended)
  dynamic "access_log_settings" {
    for_each = var.enable_access_logs ? [1] : []
    content {
      destination_arn = var.access_log_destination_arn
      format = jsonencode({
        requestId      = "$context.requestId"
        ip             = "$context.identity.sourceIp"
        requestTime    = "$context.requestTime"
        httpMethod     = "$context.httpMethod"
        routeKey       = "$context.routeKey"
        status         = "$context.status"
        protocol       = "$context.protocol"
        responseLength = "$context.responseLength"
        integrationErrorMessage = "$context.integrationErrorMessage"
      })
    }
  }

  # Throttling settings (cost control)
  dynamic "default_route_settings" {
    for_each = var.enable_throttling ? [1] : []
    content {
      throttling_burst_limit = var.throttling_burst_limit
      throttling_rate_limit  = var.throttling_rate_limit
    }
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.prefix}-${var.stage_name}"
    }
  )
}

# Custom domain mapping (optional)
resource "aws_apigatewayv2_domain_name" "custom" {
  count       = var.custom_domain_name != null ? 1 : 0
  domain_name = var.custom_domain_name

  domain_name_configuration {
    certificate_arn = var.acm_certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = merge(
    var.tags,
    {
      Name = var.custom_domain_name
    }
  )
}

resource "aws_apigatewayv2_api_mapping" "custom" {
  count       = var.custom_domain_name != null ? 1 : 0
  api_id      = aws_apigatewayv2_api.gateway.id
  domain_name = aws_apigatewayv2_domain_name.custom[0].id
  stage       = aws_apigatewayv2_stage.default.id
}
