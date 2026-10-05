import io
import json
import urllib.error

import pytest
import slack_api


def test_slack_http_success_with_api_error_is_failure(monkeypatch):
    monkeypatch.setattr(
        slack_api.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(b'{"ok":false,"error":"not_in_channel"}'),
    )
    with pytest.raises(slack_api.SlackError, match="not_in_channel"):
        slack_api.call("token", "chat.postMessage", channel="C1", text="test")


def test_failed_http_does_not_expose_tokens(monkeypatch):
    def fail(request, **kwargs):
        raise urllib.error.URLError("secret-token-in-error")

    monkeypatch.setattr(slack_api.urllib.request, "urlopen", fail)
    with pytest.raises(slack_api.SlackError, match="^connection-failed$"):
        slack_api.call("secret-token", "views.open")


def test_posts_structured_message_to_fixed_slack_api_host(monkeypatch):
    requests = []

    def post(request, **kwargs):
        requests.append(request)
        return io.BytesIO(b'{"ok":true,"ts":"1.2"}')

    monkeypatch.setattr(slack_api.urllib.request, "urlopen", post)
    response = slack_api.call("token", "chat.postMessage", channel="U1", text="test")
    assert response["ts"] == "1.2"
    assert requests[0].full_url == "https://slack.com/api/chat.postMessage"
    assert json.loads(requests[0].data)["channel"] == "U1"
