import pytest
from formatting import body_preview


def test_paragraphs_headings_lists_and_tables_stay_readable():
    text = """## 최종 합의안

**기준**을 확인합니다.
- 첫 항목
+ 둘째 항목

| 번호 | 결정 | 이유 |
| --- | --- | --- |
| 1 | 비활성화 | 사용 종료 |
| 2 | 보관 | 감사 기록 |
"""
    preview = body_preview(text)
    assert preview.startswith("*최종 합의안*\n\n*기준*을 확인합니다.")
    assert "- 첫 항목\n- 둘째 항목" in preview
    assert "- 번호: 1; 결정: 비활성화; 이유: 사용 종료" in preview
    assert "- 번호: 2; 결정: 보관; 이유: 감사 기록" in preview
    assert "| ---" not in preview


def test_code_is_not_reformatted_as_headings_lists_or_links():
    text = (
        "`**literal**`\n```python\n## literal\n* item\n[link](https://example.com)\n<!channel>\n```"
    )
    preview = body_preview(text)
    assert preview.startswith("`**literal**`")
    assert "```\n## literal\n* item\n[link](https://example.com)\n&lt;!channel&gt;\n```" in preview


def test_links_are_converted_without_allowing_slack_control_markup():
    preview = body_preview(
        "[원문](https://example.com?a=1&b=2) <!channel> <@U123> [a|b](https://example.com/<@U123>)"
    )
    assert "<https://example.com?a=1&amp;b=2|원문>" in preview
    assert "&lt;!channel&gt; &lt;@U123&gt;" in preview
    assert "<https://example.com/%3C@U123%3E|a / b>" in preview


@pytest.mark.parametrize(
    "url", ["javascript:alert", "slack://open", "https://[bad", "file:///etc/passwd"]
)
def test_non_http_or_malformed_links_are_plain_labels(url):
    assert body_preview(f"[설명]({url})") == "설명"


@pytest.mark.parametrize(
    "text",
    [
        "&<>" * 3000,
        "**" + "가" * 4000 + "**",
        "```\n" + "가" * 4000 + "\n```",
        "[" + "가" * 4000 + "](https://example.com)",
    ],
)
def test_truncation_respects_encoded_limit_and_closes_formatting(text):
    preview = body_preview(text)
    assert len(preview) <= 2800
    assert preview.endswith("\n...")
    if text.startswith("**"):
        assert preview.count("*") == 2
    if text.startswith("```"):
        assert preview.count("```") == 2
    if text.startswith("["):
        assert preview.removesuffix("\n...").endswith(">")
    if text.startswith("&"):
        assert preview.removesuffix("\n...").endswith(("&amp;", "&lt;", "&gt;"))


def test_short_reply_is_not_truncated_or_flattened():
    assert body_preview("확인했습니다.\n감사합니다.") == "확인했습니다.\n감사합니다."
