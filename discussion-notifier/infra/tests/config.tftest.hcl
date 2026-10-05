mock_provider "aws" {
  mock_data "aws_region" {
    defaults = { region = "ap-northeast-2" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/discussion-notifier" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:ap-northeast-2:123456789012:notifications" }
  }
}

variables {
  aws_account_id     = "123456789012"
  slack_team_id      = "T123"
  default_channel_id = "C123"
}

run "notification_infrastructure" {
  command = plan

  assert {
    condition     = aws_sqs_queue.notifications.visibility_timeout_seconds >= 6 * aws_lambda_function.worker.timeout
    error_message = "SQS visibility timeout must leave time for Lambda retries."
  }
  assert {
    condition     = aws_lambda_function.notifier.environment[0].variables.DEFAULT_CHANNEL_ID == "C123"
    error_message = "The existing notification channel must be preserved."
  }
  assert {
    condition     = aws_lambda_function.notifier.timeout < 10
    error_message = "GitHub webhook requests must finish within ten seconds."
  }
  assert {
    condition     = aws_lambda_event_source_mapping.notifications.function_response_types == toset(["ReportBatchItemFailures"])
    error_message = "Only failed SQS records should be retried."
  }
  assert {
    condition     = aws_dynamodb_table.settings.ttl[0].attribute_name == "expires_at"
    error_message = "Delivery receipts must expire separately from subscription rules."
  }
}
