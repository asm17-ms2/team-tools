locals {
  secret_parameters = [
    for name in ["github-webhook-secret", "slack-signing-secret", "slack-bot-token"] :
    "arn:aws:ssm:${local.region}:${local.account}:parameter/meterengine/${local.name}/${name}"
  ]
  runtime_permissions = [
    {
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = [for suffix in ["", "-worker"] : "arn:aws:logs:${local.region}:${local.account}:log-group:/aws/lambda/${local.name}${suffix}:*"]
    },
    {
      Action   = ["ssm:GetParameters"]
      Resource = local.secret_parameters
    },
    {
      Action   = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
      Resource = [local.table]
    },
    {
      Action   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
      Resource = [local.queues[0]]
    },
    {
      Action   = ["kms:Decrypt"]
      Resource = ["arn:aws:kms:${local.region}:${local.account}:key/*"]
    },
  ]
  decryption_context = {
    "kms:ViaService"                      = ["ssm.${local.region}.amazonaws.com"]
    "kms:EncryptionContext:PARAMETER_ARN" = local.secret_parameters
  }
  boundary_protection_statements = [
    {
      Effect   = "Deny"
      Action   = ["iam:CreatePolicy", "iam:CreatePolicyVersion", "iam:SetDefaultPolicyVersion", "iam:DeletePolicyVersion", "iam:DeletePolicy"]
      Resource = local.boundary_arn
    },
    {
      Effect   = "Deny"
      Action   = ["iam:DeleteRolePermissionsBoundary", "iam:UpdateAssumeRolePolicy"]
      Resource = local.role_arn
    },
    {
      Effect   = "Deny"
      Action   = ["iam:CreateRole", "iam:PutRolePermissionsBoundary", "iam:PutRolePolicy"]
      Resource = local.role_arn
      Condition = {
        StringNotEquals = { "iam:PermissionsBoundary" = local.boundary_arn }
      }
    },
    {
      Effect   = "Deny"
      Action   = ["iam:*"]
      Resource = "arn:aws:iam::${local.account}:role/team-tools-discussion-*"
    },
  ]
}

resource "aws_iam_policy" "runtime_boundary" {
  name = "${local.name}-runtime-boundary"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [for permission in local.runtime_permissions : merge(permission, { Effect = "Allow" }, contains(permission.Action, "kms:Decrypt") ? {
        Condition                                                               = { StringEquals = local.decryption_context }
      } : {})],
      [{
        Effect    = "Deny"
        NotAction = flatten([for permission in local.runtime_permissions : permission.Action])
        Resource  = "*"
      }],
      [for permission in local.runtime_permissions : {
        Effect      = "Deny"
        Action      = permission.Action
        NotResource = permission.Resource
      }],
      [for key, values in local.decryption_context : {
        Effect    = "Deny"
        Action    = ["kms:Decrypt"]
        Resource  = "*"
        Condition = { StringNotEquals = { (key) = values } }
      }],
    )
  })
}
