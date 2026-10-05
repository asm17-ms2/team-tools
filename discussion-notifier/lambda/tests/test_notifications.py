import pytest
from conftest import comment, discussion, payload
from notifications import build_message, destinations, event_types, normalize_selector


@pytest.mark.parametrize(
    "name,data,expected",
    [
        ("discussion", payload(), {"created"}),
        (
            "discussion",
            payload("edited", changes={"body": {"from": "old"}}),
            {"body_edited"},
        ),
        (
            "discussion",
            payload("edited", changes={"title": {"from": "old"}}),
            {"title_edited"},
        ),
        (
            "discussion",
            payload("edited", changes={"body": {}, "title": {}}),
            {"body_edited", "title_edited"},
        ),
        ("discussion_comment", payload(comment=comment()), {"comment_created"}),
        (
            "discussion_comment",
            payload(comment=comment(parent_id=9)),
            {"reply_created"},
        ),
        (
            "discussion_comment",
            payload("edited", comment=comment()),
            {"comment_edited"},
        ),
        (
            "discussion_comment",
            payload("edited", comment=comment(parent_id=9)),
            {"comment_edited"},
        ),
        ("discussion", payload("answered"), {"answered"}),
    ],
)
def test_event_classification(name, data, expected):
    assert event_types(name, data) == expected


def test_overlapping_scopes_send_once_and_disabled_rules_do_not_match():
    rules = [
        {
            "kind": "dm",
            "owner": "U1",
            "scope": "all",
            "selector": "",
            "events": ["body_edited"],
        },
        {
            "kind": "dm",
            "owner": "U1",
            "scope": "category",
            "selector": "설계",
            "events": ["body_edited"],
        },
        {
            "kind": "dm",
            "owner": "U1",
            "scope": "discussion",
            "selector": "1",
            "events": ["body_edited"],
        },
        {
            "kind": "dm",
            "owner": "U2",
            "scope": "discussion",
            "selector": "2",
            "events": ["body_edited"],
        },
        {
            "kind": "channel",
            "owner": "C1",
            "scope": "all",
            "selector": "",
            "events": [],
        },
    ]
    assert destinations(rules, "discussion", payload("edited", changes={"body": {}})) == [
        ("dm", "U1")
    ]
    assert destinations(rules, "discussion_comment", payload("edited", comment=comment())) == []


@pytest.mark.parametrize(
    "value,expected",
    [
        ("#12", "12"),
        ("12", "12"),
        ("https://github.com/o/r/discussions/12#discussioncomment-9", "12"),
    ],
)
def test_normalizes_discussion_selector(value, expected):
    assert normalize_selector("discussion", value, "o/r") == expected


@pytest.mark.parametrize(
    "scope,value",
    [
        ("discussion", "0"),
        ("discussion", "-1"),
        ("discussion", "https://github.com/other/repo/discussions/1"),
        ("category", " "),
        ("invalid", ""),
    ],
)
def test_invalid_scope_cannot_subscribe(scope, value):
    with pytest.raises(ValueError):
        normalize_selector(scope, value, "o/r")


def test_message_escapes_mentions_and_limits_preview():
    message = build_message(
        "discussion",
        payload(discussion=discussion(title="<b> & </b>", body="<!channel>\n" + "나" * 300)),
    )
    assert "<!channel>" not in message["text"]
    assert "&lt;!channel&gt;" in message["text"]
    assert "..." in message["text"]
    assert message["unfurl_links"] is False
    assert message["blocks"][-1]["elements"][0]["value"] == "1"


def test_answer_links_to_accepted_comment():
    message = build_message(
        "discussion", payload("answered", answer=comment(user={"login": "answerer"}))
    )
    assert "답변 채택" in message["text"]
    assert "#discussioncomment-9|답변>" in message["text"]


def test_edited_message_uses_editor():
    message = build_message("discussion_comment", payload("edited", comment=comment()))
    assert "|editor>:" in message["text"]
    assert "댓글과 답글 수정" in message["text"]
