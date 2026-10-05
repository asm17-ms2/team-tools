import json
import urllib.error
import urllib.request


class SlackError(RuntimeError):
    pass


def call(token, method, **payload):
    request = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise SlackError(f"http-{error.code}") from None
    except urllib.error.URLError, TimeoutError:
        raise SlackError("connection-failed") from None
    if not result.get("ok"):
        raise SlackError(result.get("error", "unknown-error"))
    return result
