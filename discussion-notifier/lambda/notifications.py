import re

from formatting import body_preview, escaped_excerpt

EVENTS = {
    "created": "새 글",
    "body_edited": "본문 수정",
    "title_edited": "제목 수정",
    "comment_created": "새 댓글",
    "reply_created": "새 답글",
    "comment_edited": "댓글과 답글 수정",
    "answered": "답변 채택",
    "unanswered": "채택 취소",
    "closed": "닫힘",
    "reopened": "재열림",
}
DEFAULT_EVENTS = ["created", "comment_created", "reply_created", "answered"]
SCOPES = {"all": "저장소 전체", "category": "카테고리", "discussion": "특정 글"}


def event_types(event_name, payload):
    if payload.get("sender", {}).get("type") == "Bot":
        return set()
    action = payload.get("action")
    if event_name == "discussion":
        if action in ("created", "answered", "unanswered", "closed", "reopened"):
            return {action}
        if action == "edited":
            changes = payload.get("changes", {})
            return {f"{field}_edited" for field in ("body", "title") if field in changes}
    if event_name == "discussion_comment":
        if action == "created":
            return {"reply_created" if payload["comment"].get("parent_id") else "comment_created"}
        if action == "edited":
            return {"comment_edited"}
    return set()


def normalize_selector(scope, selector, repository):
    selector = selector.strip()
    if scope == "all":
        return ""
    if scope == "category" and selector and len(selector) <= 100:
        return selector.casefold()
    if scope == "discussion":
        match = re.fullmatch(
            rf"https://github\.com/{re.escape(repository)}/discussions/([1-9]\d*)/?(?:#[^\s]*)?",
            selector,
            re.IGNORECASE,
        )
        number = match[1] if match else selector.removeprefix("#")
        if re.fullmatch(r"[1-9]\d{0,19}", number):
            return number
    raise ValueError("카테고리 이름, 글 번호 또는 이 저장소의 Discussion 링크를 입력하세요.")


def destinations(rules, event_name, payload):
    types = event_types(event_name, payload)
    discussion = payload["discussion"]
    category = discussion["category"]["name"].casefold()
    number = str(discussion["number"])
    matched = set()
    for rule in rules:
        scope = rule["scope"]
        matches = (
            scope == "all"
            or (scope == "category" and rule["selector"] == category)
            or (scope == "discussion" and rule["selector"] == number)
        )
        if matches and types.intersection(rule["events"]):
            matched.add((rule["kind"], rule["owner"]))
    return sorted(matched)


def mrkdwn(text):
    return {"type": "mrkdwn", "text": text, "verbatim": True}


def build_message(event_name, payload):
    types = event_types(event_name, payload)
    if not types:
        return None
    discussion = payload["discussion"]
    headline = ", ".join(label for key, label in EVENTS.items() if key in types)
    content = discussion
    if "answered" in types:
        content = payload["answer"]
    elif "unanswered" in types:
        content = payload["old_answer"]
    elif event_name == "discussion_comment":
        content = payload["comment"]
        if "comment_edited" in types:
            headline = "답글 수정" if content.get("parent_id") else "댓글 수정"
    actor = content["user"] if payload["action"] == "created" else payload["sender"]
    author = escaped_excerpt(actor["login"], 100)
    actor_link = f"<https://github.com/{actor['login']}|{author}>"
    event_line = f"{headline}: {actor_link}"
    if "answered" in types:
        event_line += f" 님이 <{content['html_url']}|답변>을 채택"
    elif "unanswered" in types:
        event_line += f" 님이 <{content['html_url']}|이전 답변>의 채택을 취소"
    title = escaped_excerpt(discussion["title"].replace("|", " / "), 250)
    title_link = f"<{discussion['html_url']}|#{discussion['number']} {title}>"
    status_text = {"closed": "토의가 종료되었습니다.", "reopened": "토의가 다시 열렸습니다."}
    body = status_text.get(payload["action"]) or body_preview(content.get("body"))
    repository = escaped_excerpt(payload["repository"]["full_name"], 200)
    category = escaped_excerpt(discussion["category"]["name"], 100)
    metadata = f"{repository} | {category} | <{content['html_url']}|GitHub에서 보기>"
    if content["user"]["login"] != actor["login"]:
        metadata += f" | 작성자: {escaped_excerpt(content['user']['login'], 100)}"
    color = "#2DA44E" if "created" in types else "#0969DA"
    if payload["action"] == "edited":
        color = "#BF8700"
    elif "answered" in types:
        color = "#8250DF"
    elif "unanswered" in types:
        color = "#BF8700"
    elif "closed" in types:
        color = "#6E7781"
    elif "reopened" in types:
        color = "#2DA44E"
    return {
        "text": f"{event_line}\n{title_link}\n{body}\n{metadata}",
        "unfurl_links": False,
        "unfurl_media": False,
        "parse": "none",
        "blocks": [{"type": "section", "text": mrkdwn(event_line)}],
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {"type": "section", "text": mrkdwn(f"*{title_link}*")},
                    {"type": "section", "text": mrkdwn(body)},
                    {"type": "context", "elements": [mrkdwn(metadata)]},
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "action_id": "notify_follow",
                                "text": {"type": "plain_text", "text": "이 글 DM 알림"},
                                "value": str(discussion["number"]),
                            },
                            {
                                "type": "button",
                                "action_id": "notify_manage_dm",
                                "text": {"type": "plain_text", "text": "내 DM 설정"},
                            },
                        ],
                    },
                ],
            }
        ],
    }
