import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse

from botocore.exceptions import BotoCoreError, ClientError
from config import secret
from notifications import event_types
from settings import handle_action, launcher, save_view
from slack_api import SlackError
from store import Store


def handler(event, context):
    headers = {name.lower(): value for name, value in (event.get("headers") or {}).items()}
    raw_body = (
        base64.b64decode(event["body"])
        if event.get("isBase64Encoded")
        else (event.get("body") or "").encode()
    )
    try:
        if "x-github-event" in headers:
            return github_request(raw_body, headers)
        if "x-slack-signature" in headers:
            return slack_request(raw_body, headers)
        return respond(401)
    except KeyError, ValueError, TypeError:
        return respond(400)
    except (BotoCoreError, ClientError, RuntimeError, OSError) as error:
        log("request-failed", type(error).__name__)
        return respond(503)


def verify_signature(secret_value, raw_body, signature_header):
    expected = "sha256=" + hmac.new(secret_value, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def verify_slack_signature(secret_value, raw_body, headers):
    timestamp = headers.get("x-slack-request-timestamp", "")
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    signed = b"v0:" + timestamp.encode() + b":" + raw_body
    expected = "v0=" + hmac.new(secret_value, signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers.get("x-slack-signature", ""))


def github_request(raw_body, headers):
    if not verify_signature(
        secret("GITHUB_WEBHOOK_SECRET_PARAM").encode(),
        raw_body,
        headers.get("x-hub-signature-256", ""),
    ):
        return respond(401)
    name = headers["x-github-event"]
    if name == "ping":
        return respond(200)
    payload = json.loads(raw_body)
    if (
        payload.get("repository", {}).get("full_name", "").casefold()
        != os.environ["GITHUB_REPOSITORY"].casefold()
    ):
        return respond(204)
    if not event_types(name, payload):
        return respond(204)
    delivery = headers.get("x-github-delivery")
    if not delivery:
        return respond(400)
    enqueue({"delivery": delivery, "event": name, "payload": payload})
    log("queued", delivery)
    return respond(200)


def enqueue(job):
    import boto3

    boto3.client("sqs").send_message(
        QueueUrl=os.environ["NOTIFICATION_QUEUE_URL"], MessageBody=json.dumps(job)
    )


def slack_request(raw_body, headers):
    if not verify_slack_signature(secret("SLACK_SIGNING_SECRET_PARAM").encode(), raw_body, headers):
        return respond(401)
    form = {
        key: values[0]
        for key, values in urllib.parse.parse_qs(raw_body.decode(), keep_blank_values=True).items()
    }
    payload = json.loads(form["payload"]) if "payload" in form else form
    team = payload.get("team", {}).get("id") or payload.get("team_id")
    if team != os.environ["SLACK_TEAM_ID"]:
        return respond(403)
    if "command" in form:
        if form["command"] != "/discussion-notify":
            return respond(400)
        return respond(200, launcher(form["channel_id"]))
    if payload.get("type") == "view_submission" and payload["view"]["callback_id"] == "notify_save":
        return respond(200, save_view(payload, Store()))
    if payload.get("type") == "block_actions":
        try:
            handle_action(payload, Store(), secret("SLACK_BOT_TOKEN_PARAM"))
        except SlackError as error:
            log("slack-action-failed", str(error))
            return respond(
                200,
                {
                    "response_type": "ephemeral",
                    "text": "설정 창을 열지 못했습니다. 명령을 다시 실행해 주세요.",
                },
            )
    return respond(200)


def respond(status, payload=None):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(payload, ensure_ascii=False) if payload is not None else "",
    }


def log(outcome, identifier):
    print(json.dumps({"outcome": outcome, "id": identifier}))
