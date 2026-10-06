variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "AWS 계정 ID는 12자리 숫자입니다."
  }
}

variable "state_bucket" {
  type = string
}

variable "event_source_mapping_id" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9-]{36}$", var.event_source_mapping_id))
    error_message = "운영 Lambda 큐 연결의 UUID를 입력합니다."
  }
}

locals {
  account      = var.aws_account_id
  region       = "ap-northeast-2"
  name         = "discussion-notifier"
  state_key    = "${local.name}/terraform.tfstate"
  bucket_arn   = "arn:aws:s3:::${var.state_bucket}"
  role_arn     = "arn:aws:iam::${local.account}:role/${local.name}"
  boundary_arn = "arn:aws:iam::${local.account}:policy/${local.name}-runtime-boundary"
  mapping_arn  = "arn:aws:lambda:${local.region}:${local.account}:event-source-mapping:${var.event_source_mapping_id}"
  functions = [
    "arn:aws:lambda:${local.region}:${local.account}:function:${local.name}",
    "arn:aws:lambda:${local.region}:${local.account}:function:${local.name}-worker",
  ]
  queues = [
    "arn:aws:sqs:${local.region}:${local.account}:${local.name}-notifications",
    "arn:aws:sqs:${local.region}:${local.account}:${local.name}-failed",
  ]
  table = "arn:aws:dynamodb:${local.region}:${local.account}:table/${local.name}-settings"
  logs = flatten([
    for suffix in ["", "-worker"] : [
      "arn:aws:logs:${local.region}:${local.account}:log-group:/aws/lambda/${local.name}${suffix}",
      "arn:aws:logs:${local.region}:${local.account}:log-group:/aws/lambda/${local.name}${suffix}:*",
    ]
  ])
  common_statements = [
    {
      Effect   = "Allow"
      Action   = ["s3:ListBucket"]
      Resource = local.bucket_arn
      Condition = {
        StringLike = { "s3:prefix" = ["${local.name}/*", "env:/*"] }
      }
    },
    {
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "${local.bucket_arn}/${local.state_key}"
    },
    {
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = [
        "${local.bucket_arn}/${local.state_key}.tflock",
        "${local.bucket_arn}/${local.name}/deploy-plans/*",
      ]
    },
    {
      Effect   = "Allow"
      Action   = ["lambda:Get*", "lambda:ListTags", "lambda:ListVersionsByFunction"]
      Resource = concat(local.functions, [local.mapping_arn])
    },
    {
      Effect   = "Allow"
      Action   = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"]
      Resource = local.role_arn
    },
    {
      Effect   = "Allow"
      Action   = ["sqs:GetQueueAttributes", "sqs:ListQueueTags"]
      Resource = local.queues
    },
    {
      Effect   = "Allow"
      Action   = ["dynamodb:DescribeTable", "dynamodb:DescribeContinuousBackups", "dynamodb:DescribeTimeToLive", "dynamodb:ListTagsOfResource"]
      Resource = local.table
    },
    {
      Effect   = "Allow"
      Action   = ["logs:DescribeLogGroups"]
      Resource = "*"
    },
    {
      Effect   = "Allow"
      Action   = ["logs:ListTagsForResource", "logs:ListTagsLogGroup"]
      Resource = local.logs
    },
  ]
  deploy_statements = [
    {
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${local.bucket_arn}/${local.state_key}"
    },
    {
      Effect = "Allow"
      Action = [
        "lambda:CreateFunction", "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
        "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency",
        "lambda:CreateFunctionUrlConfig", "lambda:UpdateFunctionUrlConfig",
        "lambda:AddPermission", "lambda:RemovePermission", "lambda:TagResource", "lambda:UntagResource",
      ]
      Resource = local.functions
    },
    {
      Effect   = "Allow"
      Action   = ["lambda:UpdateEventSourceMapping", "lambda:TagResource", "lambda:UntagResource"]
      Resource = local.mapping_arn
    },
    {
      Effect   = "Allow"
      Action   = ["iam:CreateRole", "iam:PutRolePolicy", "iam:PutRolePermissionsBoundary"]
      Resource = local.role_arn
      Condition = {
        StringEquals = { "iam:PermissionsBoundary" = local.boundary_arn }
      }
    },
    {
      Effect   = "Allow"
      Action   = ["iam:TagRole", "iam:UntagRole"]
      Resource = local.role_arn
    },
    {
      Effect    = "Allow"
      Action    = ["iam:PassRole"]
      Resource  = local.role_arn
      Condition = { StringEquals = { "iam:PassedToService" = "lambda.amazonaws.com" } }
    },
    {
      Effect   = "Allow"
      Action   = ["sqs:CreateQueue", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:UntagQueue"]
      Resource = local.queues
    },
    {
      Effect   = "Allow"
      Action   = ["dynamodb:CreateTable", "dynamodb:UpdateTable", "dynamodb:UpdateTimeToLive", "dynamodb:UpdateContinuousBackups", "dynamodb:TagResource", "dynamodb:UntagResource"]
      Resource = local.table
    },
    {
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource"]
      Resource = local.logs
    },
  ]
}

data "aws_iam_openid_connect_provider" "github" {
  arn = "arn:aws:iam::${local.account}:oidc-provider/token.actions.githubusercontent.com"
}

resource "aws_iam_role" "actions" {
  for_each = {
    plan   = "repo:asm17-ms2@293532363/team-tools@1405328493:ref:refs/heads/main"
    deploy = "repo:asm17-ms2@293532363/team-tools@1405328493:environment:production"
  }
  name = "team-tools-discussion-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = each.value
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "actions" {
  for_each = aws_iam_role.actions
  name     = "discussion-notifier"
  role     = each.value.id
  policy = each.key == "deploy" ? jsonencode({
    Version   = "2012-10-17"
    Statement = concat(local.common_statements, local.deploy_statements, local.boundary_protection_statements)
    }) : jsonencode({
    Version   = "2012-10-17"
    Statement = concat(local.common_statements, local.boundary_protection_statements)
  })
}

output "plan_role_arn" {
  value = aws_iam_role.actions["plan"].arn
}

output "deploy_role_arn" {
  value = aws_iam_role.actions["deploy"].arn
}
