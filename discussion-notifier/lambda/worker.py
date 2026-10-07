import json
import os
from copy import deepcopy

from app import log
from botocore.exceptions import BotoCoreError, ClientError
from config import secret
from notifications import build_message, destinations
from settings import button
from slack_api import SlackError, call
from store import Store


def handler(event, context):
    failures = []
    store = Store()
    token = secret("SLACK_BOT_TOKEN_PARAM")
    for record in event["Records"]:
        try:
            dispatch(json.loads(record["body"]), store, token)
        except (
            BotoCoreError,
            ClientError,
            RuntimeError,
            KeyError,
            ValueError,
            TypeError,
        ) as error:
            log("delivery-failed", type(error).__name__)
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def dispatch(job, store, token):
    payload = job["payload"]
    if payload["repository"]["full_name"].casefold() != os.environ["GITHUB_REPOSITORY"].casefold():
        return
    message = build_message(job["event"], payload)
    if message is None:
        return
    failures = []
    for destination in destinations(store.rules(), job["event"], payload):
        try:
            if not store.claim(job["delivery"], destination):
                continue
            outgoing = message
            if destination[0] == "channel":
                outgoing = deepcopy(message)
                outgoing["attachments"][0]["blocks"][-1]["elements"].append(
                    button("notify_manage_channel", "채널 설정", destination[1])
                )
            call(token, "chat.postMessage", channel=destination[1], **outgoing)
            store.complete(job["delivery"], destination)
        except (BotoCoreError, ClientError, RuntimeError) as error:
            detail = str(error) if isinstance(error, SlackError) else type(error).__name__
            log("destination-failed", f"{destination[0]}:{destination[1]}:{detail}")
            failures.append(type(error).__name__)
    if failures:
        raise RuntimeError(",".join(failures))
    log("delivered", job["delivery"])
