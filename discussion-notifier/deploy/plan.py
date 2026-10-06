import json
import os
import sys
from pathlib import Path


def require_existing_state(state):
    resources = {
        f"{resource['type']}.{resource['name']}"
        for resource in state.get("resources", [])
        if resource.get("mode") == "managed"
    }
    required = {
        "aws_lambda_function.notifier",
        "aws_lambda_function.worker",
        "aws_lambda_function_url.notifier",
        "aws_sqs_queue.notifications",
        "aws_sqs_queue.failed",
        "aws_dynamodb_table.settings",
        "aws_iam_role.lambda",
    }
    if not required.issubset(resources):
        raise ValueError("Existing production state is missing; stop before planning")


def plan_summary(plan, commit):
    changes = [
        resource
        for resource in plan.get("resource_changes", [])
        if resource["change"]["actions"] not in (["no-op"], ["read"])
    ]
    if any("delete" in resource["change"]["actions"] for resource in changes):
        raise ValueError("Deletion or replacement requires a separate deployment")
    lines = [
        "# Discussion notifier deployment",
        "",
        f"Commit: `{commit}`",
        "",
        "| Resource | Action |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| `{resource['address']}` | {', '.join(resource['change']['actions'])} |"
        for resource in changes
    )
    if not changes:
        lines.append("| No changes | Deployment skipped |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    content = json.loads(Path(sys.argv[2]).read_text())
    if sys.argv[1] == "state":
        require_existing_state(content)
    else:
        summary = plan_summary(content, os.environ["GITHUB_SHA"])
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write(summary)
