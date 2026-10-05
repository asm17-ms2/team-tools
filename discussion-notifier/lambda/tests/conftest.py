import hashlib
import hmac
import json
import urllib.parse

import app
import boto3
import pytest
from moto import mock_aws
from store import Store

SECRET = b"test-secret"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for key, value in {
        "AWS_DEFAULT_REGION": "ap-northeast-2",
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "GITHUB_REPOSITORY": "o/r",
        "SLACK_TEAM_ID": "T1",
        "DEFAULT_CHANNEL_ID": "C1",
        "SETTINGS_TABLE": "settings",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(app, "secret", lambda key: SECRET.decode())


@pytest.fixture
def store():
    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="settings",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        store = Store(table)
        store.rules()
        yield store


def discussion(**overrides):
    return {
        "number": 1,
        "title": "롤백 기준이 뭔가요",
        "html_url": "https://github.com/o/r/discussions/1",
        "body": "본문",
        "user": {"login": "author"},
        "category": {"name": "설계"},
        **overrides,
    }


def comment(**overrides):
    return {
        "html_url": "https://github.com/o/r/discussions/1#discussioncomment-9",
        "body": "댓글 본문",
        "user": {"login": "commenter"},
        "parent_id": None,
        **overrides,
    }


def payload(action="created", **overrides):
    return {
        "action": action,
        "discussion": discussion(),
        "repository": {"full_name": "o/r"},
        "sender": {"type": "User", "login": "editor"},
        **overrides,
    }


def github_request(event_name, data, delivery="delivery-1"):
    body = json.dumps(data).encode()
    return {
        "body": body.decode(),
        "headers": {
            "X-GitHub-Event": event_name,
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest(),
        },
    }


def slack_request(data, now=1000):
    body = urllib.parse.urlencode(data).encode()
    signature = (
        "v0="
        + hmac.new(SECRET, b"v0:" + str(now).encode() + b":" + body, hashlib.sha256).hexdigest()
    )
    return {
        "body": body.decode(),
        "headers": {
            "X-Slack-Signature": signature,
            "X-Slack-Request-Timestamp": str(now),
        },
    }
