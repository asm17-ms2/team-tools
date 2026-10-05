import json

import pytest
import settings
from settings import editor_view, handle_action, metadata, save_view


def submission(kind="dm", owner="U1", user="U1", scope="all", selector="", events=None, key=None):
    events = ["created"] if events is None else events
    return {
        "user": {"id": user},
        "view": {
            "private_metadata": metadata(kind, owner, key),
            "state": {
                "values": {
                    "scope": {"scope": {"selected_option": {"value": scope}}},
                    "selector": {"selector": {"value": selector}},
                    "events": {
                        "events": {"selected_options": [{"value": event} for event in events]}
                    },
                }
            },
        },
    }


def test_any_member_can_change_channel_settings(store):
    result = save_view(
        submission(kind="channel", owner="C1", user="U2", events=["comment_edited"]),
        store,
    )
    assert result["response_action"] == "update"
    assert store.rules("channel", "C1")[0]["events"] == ["comment_edited"]


def test_dm_owner_cannot_be_forged(store):
    with pytest.raises(ValueError):
        save_view(submission(owner="U2", user="U1"), store)
    assert store.rules("dm", "U2") == []


def test_empty_selection_disables_only_this_rule(store):
    store.save("dm", "U1", "all", "", ["created"])
    save_view(submission(scope="category", selector="설계", events=[]), store)
    rules = store.rules("dm", "U1")
    assert len(rules) == 2
    assert next(rule for rule in rules if rule["scope"] == "all")["events"] == ["created"]
    assert next(rule for rule in rules if rule["scope"] == "category")["events"] == []


def test_wrong_repository_link_shows_field_error(store):
    result = save_view(
        submission(scope="discussion", selector="https://github.com/other/r/discussions/1"),
        store,
    )
    assert result["response_action"] == "errors"
    assert "selector" in result["errors"]
    assert not store.rules("dm", "U1")


def test_unsupported_event_shows_field_error(store):
    result = save_view(submission(events=["deleted"]), store)
    assert result["response_action"] == "errors"
    assert not store.rules("dm", "U1")


def test_existing_rule_changes_events_without_changing_scope(store):
    rule = store.save("dm", "U1", "category", "설계", ["created"])
    save_view(submission(scope="all", key=rule["sk"], events=["body_edited"]), store)
    assert store.rules("dm", "U1")[0]["scope"] == "category"
    assert store.rules("dm", "U1")[0]["events"] == ["body_edited"]


def test_follow_on_shared_message_uses_clicking_user(store, monkeypatch):
    opened = []
    monkeypatch.setattr(
        settings, "call", lambda token, method, **args: opened.append((method, args))
    )
    handle_action(
        {
            "user": {"id": "U2"},
            "trigger_id": "trigger",
            "actions": [{"action_id": "notify_follow", "value": "1"}],
        },
        store,
        "token",
    )
    method, args = opened[0]
    assert method == "views.open"
    assert json.loads(args["view"]["private_metadata"])["owner"] == "U2"
    assert args["view"]["blocks"][2]["element"]["initial_value"] == "1"
    assert store.rules("dm", "U2") == []


def test_delete_frees_scope_without_restoring_defaults(store, monkeypatch):
    rule = store.rules("channel", "C1")[0]
    monkeypatch.setattr(settings, "call", lambda *args, **kwargs: {})
    handle_action(
        {
            "user": {"id": "U2"},
            "actions": [{"action_id": "notify_delete", "value": rule["sk"]}],
            "view": {
                "private_metadata": metadata("channel", "C1", rule["sk"]),
                "id": "V1",
                "hash": "hash",
            },
        },
        store,
        "token",
    )
    assert store.rules("channel", "C1") == []


def test_duplicate_scope_is_editable_at_limit(store):
    for i in range(24):
        store.save("dm", "U1", "discussion", str(i + 1), ["created"])
    rejected = save_view(submission(scope="discussion", selector="25"), store)
    assert rejected["response_action"] == "errors"
    updated = save_view(submission(scope="discussion", selector="1", events=[]), store)
    assert updated["response_action"] == "update"


def test_optional_checkboxes_allow_turning_all_events_off():
    view = editor_view("dm", "U1")
    events = next(block for block in view["blocks"] if block.get("block_id") == "events")
    assert events["optional"] is True
    assert len(events["element"]["options"]) == 7
