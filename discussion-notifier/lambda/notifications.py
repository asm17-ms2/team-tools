import re

EVENTS = {
    "created": "새 글",
    "body_edited": "본문 수정",
    "title_edited": "제목 수정",
    "comment_created": "새 댓글",
    "reply_created": "새 답글",
    "comment_edited": "댓글과 답글 수정",
    "answered": "답변 채택",
}
DEFAULT_EVENTS = ["created", "comment_created", "reply_created", "answered"]
SCOPES = {"all": "저장소 전체", "category": "카테고리", "discussion": "특정 글"}


def event_types(event_name, payload):
    if payload.get("sender", {}).get("type") == "Bot":
        return set()
    action = payload.get("action")
    if event_name == "discussion":
        if action in ("created", "answered"):
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


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def excerpt(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= 200 else text[:200] + "..."


def build_message(event_name, payload):
    types = event_types(event_name, payload)
    if not types:
        return None
    discussion = payload["discussion"]
    headline = ", ".join(label for key, label in EVENTS.items() if key in types)
    if "created" in types:
        headline = "새 Discussion"
    author = discussion["user"]["login"]
    body = discussion.get("body")
    link = discussion["html_url"]
    prefix = ""
    if "answered" in types:
        answer = payload["answer"]
        author, body, link = (
            answer["user"]["login"],
            answer.get("body"),
            answer["html_url"],
        )
        prefix = f"{escape(payload['sender']['login'])} 님이 <{link}|답변>을 채택\n"
    elif event_name == "discussion_comment":
        comment = payload["comment"]
        author, body, link = (
            comment["user"]["login"],
            comment.get("body"),
            comment["html_url"],
        )
    if payload["action"] == "edited":
        author = payload["sender"]["login"]
    category = escape(discussion["category"]["name"])
    title = f"<{discussion['html_url']}|{escape(excerpt(discussion['title']))}>"
    author_link = f"<{link}|{escape(author)}>" if link != discussion["html_url"] else escape(author)
    detail = prefix + f"{author_link}: {escape(excerpt(body))}"
    return {
        "text": f"[{category}] {headline}: {title}\n{detail}",
        "unfurl_links": False,
        "unfurl_media": False,
        "blocks": [
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"{category} | {headline}"}],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": detail}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "notify_follow",
                        "text": {"type": "plain_text", "text": "이 글 DM 알림 설정"},
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
