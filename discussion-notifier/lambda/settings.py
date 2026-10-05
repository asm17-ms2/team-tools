import json
import os

from notifications import DEFAULT_EVENTS, EVENTS, SCOPES, escape, normalize_selector
from slack_api import call

MAX_RULES = 24


def plain(text):
    return {"type": "plain_text", "text": text}


def option(value, label):
    return {"text": plain(label), "value": value}


def button(action, label, value=""):
    return {
        "type": "button",
        "action_id": action,
        "text": plain(label),
        "value": value or action,
    }


def launcher(channel):
    buttons = [button("notify_manage_dm", "내 DM 설정")]
    if channel.startswith(("C", "G")):
        buttons.append(button("notify_manage_channel", "이 채널 설정", channel))
    return {
        "response_type": "ephemeral",
        "text": "Discussion 알림 설정",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Discussion 알림 설정*\n받을 범위와 이벤트를 선택하세요. 채널 설정은 팀원 누구나 변경할 수 있습니다.",
                },
            },
            {"type": "actions", "elements": buttons},
        ],
    }


def metadata(kind, owner, key=None):
    return json.dumps({"kind": kind, "owner": owner, "key": key})


def manage_view(store, kind, owner):
    rules = store.rules(kind, owner)
    destination = "개인 DM" if kind == "dm" else f"채널 <#{owner}>"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{destination} 알림*\n{os.environ['GITHUB_REPOSITORY']}\n여러 범위가 겹치면 하나라도 켜진 이벤트를 한 번만 받습니다.",
            },
        }
    ]
    for rule in rules:
        scope = SCOPES[rule["scope"]]
        selector = escape(rule["selector"])
        label = scope if not selector else f"{scope}: {selector}"
        events = ", ".join(EVENTS[key] for key in EVENTS if key in rule["events"]) or "알림 꺼짐"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{label}*\n{events}"},
                "accessory": button("notify_edit", "설정 변경", rule["sk"]),
            }
        )
    if not rules:
        blocks.append(
            {
                "type": "section",
                "text": plain("등록한 알림이 없습니다. 범위를 추가하면 알림을 받습니다."),
            }
        )
    if len(rules) < MAX_RULES:
        blocks.append({"type": "actions", "elements": [button("notify_add", "범위 추가")]})
    return {
        "type": "modal",
        "callback_id": "notify_manage",
        "title": plain("Discussion 알림 설정"),
        "close": plain("닫기"),
        "private_metadata": metadata(kind, owner),
        "blocks": blocks,
    }


def input_block(name, label, element, optional=False):
    return {
        "type": "input",
        "block_id": name,
        "label": plain(label),
        "element": {"action_id": name, **element},
        "optional": optional,
    }


def editor_view(kind, owner, rule=None, number=None):
    events = rule["events"] if rule else DEFAULT_EVENTS
    blocks = [
        {
            "type": "section",
            "text": plain("받을 이벤트만 선택하세요. 모두 해제하면 이 범위의 알림이 꺼집니다."),
        }
    ]
    if rule:
        label = SCOPES[rule["scope"]] + (f": {rule['selector']}" if rule["selector"] else "")
        blocks.append({"type": "section", "text": plain(label)})
    else:
        scope = "discussion" if number else "all"
        blocks.extend(
            [
                input_block(
                    "scope",
                    "받을 범위",
                    {
                        "type": "static_select",
                        "options": [option(key, value) for key, value in SCOPES.items()],
                        "initial_option": option(scope, SCOPES[scope]),
                    },
                ),
                input_block(
                    "selector",
                    "카테고리 이름 또는 글 번호 / 링크",
                    {
                        "type": "plain_text_input",
                        "max_length": 200,
                        "placeholder": plain(
                            "전체는 비워 두세요. 예: 설계, #123 또는 Discussion 링크"
                        ),
                        **({"initial_value": number} if number else {}),
                    },
                    optional=True,
                ),
            ]
        )
    choices = [option(key, value) for key, value in EVENTS.items()]
    blocks.append(
        input_block(
            "events",
            "받을 이벤트",
            {
                "type": "checkboxes",
                "options": choices,
                **(
                    {"initial_options": [item for item in choices if item["value"] in events]}
                    if events
                    else {}
                ),
            },
            optional=True,
        )
    )
    if rule:
        blocks.append(
            {
                "type": "actions",
                "elements": [button("notify_delete", "이 범위 삭제", rule["sk"])],
            }
        )
    return {
        "type": "modal",
        "callback_id": "notify_save",
        "title": plain("알림 범위 설정"),
        "submit": plain("저장"),
        "close": plain("취소"),
        "private_metadata": metadata(kind, owner, rule["sk"] if rule else None),
        "blocks": blocks,
    }


def context(payload):
    meta = json.loads(payload["view"]["private_metadata"])
    if meta["kind"] == "dm":
        if meta["owner"] != payload["user"]["id"]:
            raise ValueError("다른 사용자의 DM 설정은 변경할 수 없습니다.")
    elif meta["kind"] != "channel" or not meta["owner"].startswith(("C", "G")):
        raise ValueError("채널에서 설정 명령을 실행하세요.")
    return meta


def selected_rule(store, meta):
    if meta.get("key"):
        for rule in store.rules(meta["kind"], meta["owner"]):
            if rule["sk"] == meta["key"]:
                return rule
        raise ValueError("설정이 변경되었습니다. 창을 다시 열어 주세요.")
    return None


def handle_action(payload, store, token):
    action = payload["actions"][0]
    action_id = action["action_id"]
    user = payload["user"]["id"]
    if action_id in ("notify_manage_dm", "notify_manage_channel", "notify_follow"):
        kind, owner = "dm", user
        if action_id == "notify_manage_channel":
            kind, owner = "channel", action["value"]
            if not owner.startswith(("C", "G")):
                raise ValueError("채널에서 설정 명령을 실행하세요.")
        if action_id == "notify_follow":
            number = normalize_selector(
                "discussion", action["value"], os.environ["GITHUB_REPOSITORY"]
            )
            rules = store.rules(kind, owner)
            rule = next(
                (r for r in rules if r["scope"] == "discussion" and r["selector"] == number),
                None,
            )
            if rule is None and len(rules) >= MAX_RULES:
                view = manage_view(store, kind, owner)
            else:
                view = editor_view(kind, owner, rule, number)
        else:
            view = manage_view(store, kind, owner)
        call(token, "views.open", trigger_id=payload["trigger_id"], view=view)
    elif action_id in ("notify_add", "notify_edit"):
        meta = context(payload)
        rule = (
            selected_rule(store, {**meta, "key": action["value"]})
            if action_id == "notify_edit"
            else None
        )
        view = editor_view(meta["kind"], meta["owner"], rule)
        call(
            token,
            "views.update",
            view_id=payload["view"]["id"],
            hash=payload["view"]["hash"],
            view=view,
        )
    elif action_id == "notify_delete":
        meta = context(payload)
        rule = selected_rule(store, meta)
        if rule is None or rule["sk"] != action["value"]:
            raise ValueError("삭제할 설정을 다시 선택하세요.")
        store.remove(rule["sk"])
        call(
            token,
            "views.update",
            view_id=payload["view"]["id"],
            hash=payload["view"]["hash"],
            view=manage_view(store, meta["kind"], meta["owner"]),
        )


def save_view(payload, store):
    meta = context(payload)
    state = payload["view"]["state"]["values"]
    rule = selected_rule(store, meta)
    if rule:
        scope, selector = rule["scope"], rule["selector"]
    else:
        scope = state["scope"]["scope"]["selected_option"]["value"]
        try:
            selector = normalize_selector(
                scope,
                state["selector"]["selector"].get("value") or "",
                os.environ["GITHUB_REPOSITORY"],
            )
        except ValueError as error:
            return {"response_action": "errors", "errors": {"selector": str(error)}}
    events = [item["value"] for item in (state["events"]["events"].get("selected_options") or [])]
    if any(key not in EVENTS for key in events):
        return {
            "response_action": "errors",
            "errors": {"events": "목록에 있는 이벤트를 선택하세요."},
        }
    existing = store.rules(meta["kind"], meta["owner"])
    replaces = any(r["scope"] == scope and r["selector"] == selector for r in existing)
    if not replaces and len(existing) >= MAX_RULES:
        return {
            "response_action": "errors",
            "errors": {"events": "등록할 수 있는 범위는 최대 24개입니다."},
        }
    store.save(meta["kind"], meta["owner"], scope, selector, events)
    return {
        "response_action": "update",
        "view": manage_view(store, meta["kind"], meta["owner"]),
    }
