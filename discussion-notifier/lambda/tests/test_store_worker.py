import json

import app
import boto3
import pytest
import worker
from conftest import comment, payload
from notifications import DEFAULT_EVENTS
from store import DeliveryBusy


def job(delivery="delivery-1"):
    return {"delivery": delivery, "event": "discussion", "payload": payload()}


def test_existing_channel_is_initialized_once_and_can_be_deleted(store):
    rules = store.rules("channel", "C1")
    assert rules[0]["events"] == sorted(DEFAULT_EVENTS)
    store.remove(rules[0]["sk"])
    assert store.rules() == []


def test_scope_save_updates_existing_rule_without_duplicates(store):
    store.save("dm", "U1", "category", "설계", ["body_edited"])
    store.save("dm", "U1", "category", "설계", ["comment_edited"])
    assert len(store.rules("dm", "U1")) == 1
    assert store.rules("dm", "U1")[0]["events"] == ["comment_edited"]
    store.save("dm", "U1", "category", "설계", [])
    assert store.rules("dm", "U1")[0]["events"] == []


def test_delivery_claim_handles_overlap_completed_and_expired_lease(store, monkeypatch):
    destination = ("dm", "U1")
    monkeypatch.setattr("store.time.time", lambda: 1000)
    assert store.claim("d1", destination)
    with pytest.raises(DeliveryBusy):
        store.claim("d1", destination)
    monkeypatch.setattr("store.time.time", lambda: 1121)
    assert store.claim("d1", destination)
    store.complete("d1", destination)
    assert not store.claim("d1", destination)
    assert store.claim("d2", destination)


def test_partial_failure_retries_only_failed_destination(store, monkeypatch):
    store.save("dm", "U1", "all", "", ["created"])
    messages = []
    failed = False

    def post(token, method, **message):
        nonlocal failed
        if message["channel"] == "U1" and not failed:
            failed = True
            raise RuntimeError("slack-unavailable")
        messages.append(message["channel"])

    monkeypatch.setattr(worker, "call", post)
    monkeypatch.setattr("store.time.time", lambda: 1000)
    with pytest.raises(RuntimeError):
        worker.dispatch(job(), store, "token")
    assert messages == ["C1"]
    monkeypatch.setattr("store.time.time", lambda: 1121)
    worker.dispatch(job(), store, "token")
    worker.dispatch(job(), store, "token")
    assert messages == ["C1", "U1"]


def test_worker_reports_failed_record_for_sqs_retry(store, monkeypatch):
    monkeypatch.setattr(worker, "Store", lambda: store)
    monkeypatch.setattr(worker, "secret", lambda key: "token")
    monkeypatch.setattr(
        worker,
        "call",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    result = worker.handler({"Records": [{"messageId": "m1", "body": json.dumps(job())}]}, None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m1"}]}


def test_receiver_uses_real_sqs_client(store, monkeypatch):
    queue = boto3.client("sqs").create_queue(QueueName="notifications")["QueueUrl"]
    monkeypatch.setenv("NOTIFICATION_QUEUE_URL", queue)
    app.enqueue(job())
    messages = boto3.client("sqs").receive_message(QueueUrl=queue)["Messages"]
    assert json.loads(messages[0]["Body"])["delivery"] == "delivery-1"


def test_rules_query_all_pages(store, monkeypatch):
    original = store.table.query
    calls = []

    def paged(**args):
        calls.append(args)
        return original(**args, Limit=1)

    monkeypatch.setattr(store.table, "query", paged)
    store.save("dm", "U1", "all", "", ["created"])
    assert len(store.rules()) == 2
    assert len(calls) >= 3
    assert any("ExclusiveStartKey" in call for call in calls)


def test_channel_setting_button_is_only_added_to_channel_messages(store, monkeypatch):
    store.save("dm", "U1", "all", "", ["created"])
    messages = []
    monkeypatch.setattr(worker, "call", lambda token, method, **message: messages.append(message))
    worker.dispatch(job(), store, "token")
    channel_message = next(message for message in messages if message["channel"] == "C1")
    dm_message = next(message for message in messages if message["channel"] == "U1")
    assert (
        channel_message["attachments"][0]["blocks"][-1]["elements"][-1]["action_id"]
        == "notify_manage_channel"
    )
    assert channel_message["attachments"][0]["blocks"][-1]["elements"][-1]["value"] == "C1"
    assert all(
        button["action_id"] != "notify_manage_channel"
        for button in dm_message["attachments"][0]["blocks"][-1]["elements"]
    )


@pytest.mark.parametrize("action", ["closed", "reopened", "unanswered"])
def test_default_subscriptions_do_not_receive_status_events(store, monkeypatch, action):
    store.save("dm", "U1", "all", "", DEFAULT_EVENTS)
    messages = []
    monkeypatch.setattr(worker, "call", lambda token, method, **message: messages.append(message))
    event = {
        "delivery": "status-event",
        "event": "discussion",
        "payload": payload(action, old_answer=comment()),
    }
    worker.dispatch(event, store, "token")
    assert messages == []
