output "function_url" {
  value = aws_lambda_function_url.notifier.function_url
}

output "log_group" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "worker_log_group" {
  value = aws_cloudwatch_log_group.worker.name
}

output "failed_queue_url" {
  value = aws_sqs_queue.failed.url
}
