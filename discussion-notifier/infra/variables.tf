variable "aws_account_id" {
  type        = string
  description = "배포를 허용할 AWS 계정 ID"
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "AWS 계정 ID는 12자리 숫자입니다."
  }
}

variable "slack_team_id" {
  type        = string
  description = "알림 봇을 설치할 Slack 워크스페이스 ID"
  validation {
    condition     = can(regex("^T[A-Z0-9]+$", var.slack_team_id))
    error_message = "Slack 워크스페이스 ID는 T로 시작합니다."
  }
}

variable "default_channel_id" {
  type        = string
  description = "기존 알림을 유지할 Slack 채널 ID"
  validation {
    condition     = can(regex("^[CG][A-Z0-9]+$", var.default_channel_id))
    error_message = "Slack 채널 ID는 C 또는 G로 시작합니다."
  }
}
