locals {
  name               = "discussion-notifier"
  parameter_prefix   = "/meterengine/discussion-notifier"
  secret_parameter   = "${local.parameter_prefix}/github-webhook-secret"
  signing_parameter  = "${local.parameter_prefix}/slack-signing-secret"
  token_parameter    = "${local.parameter_prefix}/slack-bot-token"
  parameter_arn_base = "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter"
  environment = {
    GITHUB_WEBHOOK_SECRET_PARAM = local.secret_parameter
    SLACK_SIGNING_SECRET_PARAM  = local.signing_parameter
    SLACK_BOT_TOKEN_PARAM       = local.token_parameter
    SETTINGS_TABLE              = aws_dynamodb_table.settings.name
    NOTIFICATION_QUEUE_URL      = aws_sqs_queue.notifications.url
    GITHUB_REPOSITORY           = "asm17-ms2/meterengine"
    SLACK_TEAM_ID               = var.slack_team_id
    DEFAULT_CHANNEL_ID          = var.default_channel_id
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda"
  excludes    = ["tests", "__pycache__", ".pytest_cache", "requirements-test.txt"]
  output_path = "${path.module}/build/lambda.zip"
}

resource "aws_iam_role" "lambda" {
  name = local.name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = local.name
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
      },
      {
        Effect = "Allow"
        Action = "ssm:GetParameters"
        Resource = [
          "${local.parameter_arn_base}${local.secret_parameter}",
          "${local.parameter_arn_base}${local.signing_parameter}",
          "${local.parameter_arn_base}${local.token_parameter}",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.settings.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.notifications.arn
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "notifier" {
  function_name                  = local.name
  role                           = aws_iam_role.lambda.arn
  runtime                        = "python3.14"
  architectures                  = ["arm64"]
  handler                        = "app.handler"
  filename                       = data.archive_file.lambda.output_path
  source_code_hash               = data.archive_file.lambda.output_base64sha256
  timeout                        = 8
  memory_size                    = 512
  reserved_concurrent_executions = 2

  environment {
    variables = local.environment
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [aws_iam_role_policy.lambda]
}

resource "aws_lambda_function_url" "notifier" {
  function_name      = aws_lambda_function.notifier.function_name
  authorization_type = "NONE"
}

resource "aws_dynamodb_table" "settings" {
  name         = "${local.name}-settings"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_sqs_queue" "failed" {
  name                      = "${local.name}-failed"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "notifications" {
  name                       = "${local.name}-notifications"
  visibility_timeout_seconds = 360
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.failed.arn
    maxReceiveCount     = 5
  })
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.name}-worker"
  retention_in_days = 14
}

resource "aws_iam_role_policy" "worker_logs" {
  name = "${local.name}-worker-logs"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.worker.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "worker" {
  function_name                  = "${local.name}-worker"
  role                           = aws_iam_role.lambda.arn
  runtime                        = "python3.14"
  architectures                  = ["arm64"]
  handler                        = "worker.handler"
  filename                       = data.archive_file.lambda.output_path
  source_code_hash               = data.archive_file.lambda.output_base64sha256
  timeout                        = 60
  memory_size                    = 256
  reserved_concurrent_executions = 2

  environment {
    variables = local.environment
  }
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.worker.name
  }
  depends_on = [aws_iam_role_policy.lambda, aws_iam_role_policy.worker_logs]
}

resource "aws_lambda_event_source_mapping" "notifications" {
  event_source_arn        = aws_sqs_queue.notifications.arn
  function_name           = aws_lambda_function.worker.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
}
