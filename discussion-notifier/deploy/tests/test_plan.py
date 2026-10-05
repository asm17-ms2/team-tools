import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("plan", Path(__file__).parents[1] / "plan.py")
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


def test_missing_state_cannot_plan_duplicate_infrastructure():
    with pytest.raises(ValueError, match="Existing production state"):
        plan.require_existing_state({"resources": []})


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["create", "delete"]])
def test_destructive_changes_are_rejected(actions):
    with pytest.raises(ValueError, match="Deletion or replacement"):
        plan.plan_summary({"resource_changes": [{"change": {"actions": actions}}]}, "commit")


def test_summary_never_includes_resource_values():
    summary = plan.plan_summary(
        {
            "resource_changes": [
                {
                    "address": "aws_lambda_function.notifier",
                    "change": {
                        "actions": ["update"],
                        "before": {"secret": "private-value"},
                        "after": {"secret": "private-value"},
                    },
                }
            ]
        },
        "commit",
    )
    assert "aws_lambda_function.notifier" in summary
    assert "private-value" not in summary


def test_unchanged_resources_do_not_need_deployment():
    summary = plan.plan_summary(
        {"resource_changes": [{"change": {"actions": ["no-op"]}}]}, "commit"
    )
    assert "Deployment skipped" in summary
