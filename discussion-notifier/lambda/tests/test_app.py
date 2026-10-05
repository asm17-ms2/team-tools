import base64
import json

import app
import pytest
import worker
from conftest import SECRET, comment, github_request, payload, slack_request
from settings import metadata


@pytest.fixture
def queued(monkeypatch):
    jobs = []
    monkeypatch.setattr(app, "enqueue", jobs.append)
    return jobs


def test_signed_event_is_queued_before_sending(queued):
    response = app.handler(github_request("discussion", payload()), None)
    assert response["statusCode"] == 200
    assert queued[0]["delivery"] == "delivery-1"
    assert queued[0]["payload"]["discussion"]["number"] == 1


@pytest.mark.parametrize("signature", ["", "sha256=00"])
def test_invalid_signature_cannot_enqueue(queued, signature):
    request = github_request("discussion", payload())
    request["headers"]["X-Hub-Signature-256"] = signature
    assert app.handler(request, None)["statusCode"] == 401
    assert not queued


def test_base64_preserves_signature(queued):
    request = github_request("discussion", payload())
    request["body"] = base64.b64encode(request["body"].encode()).decode()
    request["isBase64Encoded"] = True
    assert app.handler(request, None)["statusCode"] == 200
    assert len(queued) == 1


@pytest.mark.parametrize(
    "event_name,data",
    [
        ("issues", payload()),
        ("discussion", payload("deleted")),
        ("discussion", payload(sender={"type": "Bot"})),
        ("discussion", payload(repository={"full_name": "other/repo"})),
        ("discussion", payload("edited", changes={})),
    ],
)
def test_unsupported_events_are_not_queued(queued, event_name, data):
    assert app.handler(github_request(event_name, data), None)["statusCode"] == 204
    assert not queued


def test_ping_needs_no_discussion(queued):
    assert app.handler(github_request("ping", {"zen": "hi"}), None)["statusCode"] == 200
    assert not queued


def test_missing_delivery_is_rejected(queued):
    assert (
        app.handler(github_request("discussion", payload(), delivery=""), None)["statusCode"] == 400
    )
    assert not queued


def test_queue_failure_is_retryable(monkeypatch):
    def fail(job):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(app, "enqueue", fail)
    assert app.handler(github_request("discussion", payload()), None)["statusCode"] == 503


def test_github_signature_official_example():
    assert app.verify_signature(
        b"It's a Secret to Everybody",
        b"Hello, World!",
        "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17",
    )


@pytest.mark.parametrize("timestamp", [699, 1301, "invalid"])
def test_old_or_invalid_slack_request_is_rejected(monkeypatch, timestamp):
    monkeypatch.setattr(app.time, "time", lambda: 1000)
    assert not app.verify_slack_signature(
        SECRET,
        b"test",
        {"x-slack-request-timestamp": str(timestamp), "x-slack-signature": "v0=00"},
    )


def test_slash_command_returns_private_launcher(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 1000)
    request = slack_request(
        {
            "command": "/discussion-notify",
            "team_id": "T1",
            "channel_id": "C1",
            "user_id": "U1",
        }
    )
    response = app.handler(request, None)
    message = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert message["response_type"] == "ephemeral"
    assert len(message["blocks"][-1]["elements"]) == 2


def test_other_workspace_is_rejected(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 1000)
    request = slack_request({"command": "/discussion-notify", "team_id": "T2", "channel_id": "C1"})
    assert app.handler(request, None)["statusCode"] == 403


def test_tampered_slack_body_is_rejected(monkeypatch):
    monkeypatch.setattr(app.time, "time", lambda: 1000)
    request = slack_request({"team_id": "T1"})
    request["body"] += "&user_id=U2"
    assert app.handler(request, None)["statusCode"] == 401


def test_signed_settings_to_edited_comment_delivery(monkeypatch, store, queued):
    monkeypatch.setattr(app.time, "time", lambda: 1000)
    monkeypatch.setattr(app, "Store", lambda: store)
    submission = {
        "type": "view_submission",
        "team": {"id": "T1"},
        "user": {"id": "U1"},
        "view": {
            "callback_id": "notify_save",
            "private_metadata": metadata("dm", "U1"),
            "state": {
                "values": {
                    "scope": {"scope": {"selected_option": {"value": "discussion"}}},
                    "selector": {"selector": {"value": "https://github.com/o/r/discussions/1"}},
                    "events": {"events": {"selected_options": [{"value": "comment_edited"}]}},
                }
            },
        },
    }
    response = app.handler(slack_request({"payload": json.dumps(submission)}), None)
    assert json.loads(response["body"])["response_action"] == "update"
    data = payload("edited", comment=comment(body="수정한 댓글"))
    app.handler(github_request("discussion_comment", data), None)
    messages = []
    monkeypatch.setattr(worker, "call", lambda token, method, **message: messages.append(message))
    worker.dispatch(queued[0], store, "token")
    assert [message["channel"] for message in messages] == ["U1"]
    assert "수정한 댓글" in messages[0]["text"]
