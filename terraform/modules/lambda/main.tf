# Lambda function for API Gateway

# IAM role for Lambda execution
resource "aws_iam_role" "lambda_execution" {
  name               = "${var.prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(
    var.tags,
    {
      Name = "${var.prefix}-lambda-role"
    }
  )
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# CloudWatch Logs policy
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access policy (least privilege)
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name   = "${var.prefix}-lambda-dynamodb"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_dynamodb.json
}

data "aws_iam_policy_document" "lambda_dynamodb" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan"
    ]
    resources = [
      var.sessions_table_arn,
      var.rate_limits_table_arn
    ]
  }
}

# Lambda function
resource "aws_lambda_function" "gateway" {
  function_name = "${var.prefix}-gateway"
  role          = aws_iam_role.lambda_execution.arn

  # Package configuration - user must provide this
  filename         = var.lambda_package_path
  source_code_hash = fileexists(var.lambda_package_path) ? filebase64sha256(var.lambda_package_path) : null
  handler          = var.lambda_handler
  runtime          = var.lambda_runtime

  # Alternative: Docker image
  # image_uri    = var.lambda_image_uri
  # package_type = "Image"

  # Resource configuration
  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  # Environment variables
  environment {
    variables = merge(
      {
        GATEWAY_ENV                  = var.environment
        GATEWAY_LOG_LEVEL            = var.log_level
        GATEWAY_LOG_FORMAT           = "json"
        GATEWAY_SESSION_STORE_TYPE   = "dynamodb"
        GATEWAY_SESSION_TABLE_NAME   = var.sessions_table_name
        GATEWAY_RATELIMIT_STORE_TYPE = "dynamodb"
        GATEWAY_RATELIMIT_TABLE_NAME = var.rate_limits_table_name
        GATEWAY_RATELIMIT_ENABLED    = tostring(var.rate_limiting_enabled)
        GATEWAY_TOKEN_SIGNING_SECRET = var.token_signing_secret
        AWS_REGION_NAME              = var.aws_region
      },
      var.additional_env_vars
    )
  }

  # Reserved concurrent executions (optional, helps control costs)
  reserved_concurrent_executions = var.reserved_concurrency

  tags = merge(
    var.tags,
    {
      Name = "${var.prefix}-gateway"
    }
  )

  depends_on = [
    aws_iam_role_policy_attachment.lambda_logs,
    aws_iam_role_policy.lambda_dynamodb
  ]
}

# CloudWatch Log Group with retention
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.prefix}-gateway"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name = "${var.prefix}-gateway-logs"
    }
  )
}

# Lambda permission for API Gateway to invoke
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.gateway.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.api_gateway_execution_arn}/*/*"
}
