mock_provider "aws" {}

variables {
  aws_account_id          = "123456789012"
  state_bucket            = "example-terraform-state-123456789012"
  event_source_mapping_id = "00000000-0000-0000-0000-000000000000"
}

run "bounded_deployment" {
  command = plan

  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.actions["deploy"].policy).Statement :
      try(statement.Condition.StringEquals["iam:PermissionsBoundary"], "") == "arn:aws:iam::123456789012:policy/discussion-notifier-runtime-boundary"
      if statement.Effect == "Allow" && anytrue([
        for action in statement.Action : contains(["iam:CreateRole", "iam:PutRolePolicy", "iam:PutRolePermissionsBoundary"], action)
      ])
    ])
    error_message = "IAM role creation and policy changes require the fixed boundary."
  }
  assert {
    condition = anytrue([
      for statement in jsondecode(aws_iam_role_policy.actions["deploy"].policy).Statement :
      statement.Effect == "Deny" && contains(statement.Action, "iam:DeleteRolePermissionsBoundary")
    ])
    error_message = "Deployment must explicitly deny removing the Lambda boundary."
  }
  assert {
    condition = anytrue([
      for statement in jsondecode(aws_iam_role_policy.actions["deploy"].policy).Statement :
      statement.Effect == "Deny" && contains(statement.Action, "iam:CreatePolicyVersion") && statement.Resource == "arn:aws:iam::123456789012:policy/discussion-notifier-runtime-boundary"
    ])
    error_message = "Deployment must not modify the boundary policy itself."
  }
  assert {
    condition = anytrue([
      for statement in jsondecode(aws_iam_policy.runtime_boundary.policy).Statement :
      statement.Effect == "Deny" && !contains(try(statement.NotAction, []), "iam:CreateUser") && can(statement.NotAction)
    ])
    error_message = "The runtime boundary must explicitly deny IAM administration."
  }
  assert {
    condition     = jsondecode(aws_iam_role.actions["plan"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:asm17-ms2@293532363/team-tools@1405328493:ref:refs/heads/main"
    error_message = "GitHub trust must use the immutable subject for the main branch."
  }
}
