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
        ("discussion", payload("unanswered"), {"unanswered"}),
        ("discussion", payload("closed"), {"closed"}),
        ("discussion", payload("reopened"), {"reopened"}),
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
        payload(discussion=discussion(title="<b> & </b>", body="<!channel>\n" + "나" * 3000)),
    )
    assert "<!channel>" not in message["text"]
    assert "&lt;!channel&gt;" in message["text"]
    assert "..." in message["text"]
    assert message["unfurl_links"] is False
    assert message["attachments"][0]["blocks"][-1]["elements"][0]["value"] == "1"


def test_answer_links_to_accepted_comment():
    message = build_message(
        "discussion", payload("answered", answer=comment(user={"login": "answerer"}))
    )
    assert "답변 채택" in message["text"]
    assert "#discussioncomment-9|답변>" in message["text"]


def test_edited_message_uses_editor():
    message = build_message("discussion_comment", payload("edited", comment=comment()))
    assert "댓글 수정: <https://github.com/editor|editor>" in message["text"]
    assert "작성자: commenter" in message["text"]


@pytest.mark.parametrize(
    "name,data,label,color,author",
    [
        ("discussion", payload(), "새 글", "#2DA44E", "author"),
        ("discussion_comment", payload(comment=comment()), "새 댓글", "#0969DA", "commenter"),
        (
            "discussion_comment",
            payload(comment=comment(parent_id=9)),
            "새 답글",
            "#0969DA",
            "commenter",
        ),
        (
            "discussion",
            payload("edited", changes={"body": {}, "title": {}}),
            "본문 수정, 제목 수정",
            "#BF8700",
            "editor",
        ),
        (
            "discussion_comment",
            payload("edited", comment=comment(parent_id=9)),
            "답글 수정",
            "#BF8700",
            "editor",
        ),
        ("discussion", payload("answered", answer=comment()), "답변 채택", "#8250DF", "editor"),
    ],
)
def test_card_identifies_event_actor_and_original_link(name, data, label, color, author):
    message = build_message(name, data)
    assert (
        f"{label}: <https://github.com/{author}|{author}>" in message["blocks"][0]["text"]["text"]
    )
    card = message["attachments"][0]
    assert card["color"] == color
    assert "|#1 롤백 기준이 뭔가요>" in card["blocks"][0]["text"]["text"]
    assert "o/r | 설계" in card["blocks"][2]["elements"][0]["text"]
    assert "|GitHub에서 보기>" in card["blocks"][2]["elements"][0]["text"]
    assert message["parse"] == "none"
    for block in message["blocks"] + card["blocks"]:
        text = block.get("text", {})
        if text.get("type") == "mrkdwn":
            assert text["verbatim"] is True


def test_empty_body_still_has_a_valid_section():
    message = build_message("discussion", payload(discussion=discussion(body=None)))
    assert message["attachments"][0]["blocks"][1]["text"]["text"] == "본문이 없습니다."


@pytest.mark.parametrize(
    "action,label,color,status",
    [
        ("closed", "닫힘", "#6E7781", "토의가 종료되었습니다."),
        ("reopened", "재열림", "#2DA44E", "토의가 다시 열렸습니다."),
    ],
)
def test_status_card_shows_actor_and_state_instead_of_repeating_proposal(
    action, label, color, status
):
    message = build_message("discussion", payload(action))
    assert f"{label}: <https://github.com/editor|editor>" in message["text"]
    assert "작성자: author" in message["text"]
    card = message["attachments"][0]
    assert card["color"] == color
    assert card["blocks"][1]["text"]["text"] == status
    assert "본문" not in card["blocks"][1]["text"]["text"]


def test_unanswered_card_links_to_old_answer_and_distinguishes_actor_from_author():
    message = build_message(
        "discussion", payload("unanswered", old_answer=comment(body="이전 합의 내용"))
    )
    assert "채택 취소: <https://github.com/editor|editor>" in message["text"]
    assert "#discussioncomment-9|이전 답변>의 채택을 취소" in message["text"]
    assert "이전 합의 내용" in message["text"]
    assert "작성자: commenter" in message["text"]
    assert message["attachments"][0]["color"] == "#BF8700"
