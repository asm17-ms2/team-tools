import re
from urllib.parse import quote, urlsplit

INLINE = re.compile(r"(`[^`\n]+`|!?\[([^]\n]+)\]\(([^\s)]+)\)|\*\*([^\n]+?)\*\*|~~([^\n]+?)~~)")


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escaped_excerpt(text, limit):
    result = []
    size = 0
    for character in text:
        encoded = escape(character)
        if size + len(encoded) > limit:
            break
        result.append(encoded)
        size += len(encoded)
    return "".join(result)


def inline_parts(text):
    position = 0
    for match in INLINE.finditer(text):
        yield "", text[position : match.start()], ""
        token, label, url, bold, strike = match.groups()
        if token.startswith("`"):
            yield "`", token[1:-1], "`"
        elif label is not None:
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme in ("http", "https") and bool(parsed.netloc)
            except ValueError:
                valid = False
            if valid:
                safe_url = quote(url, safe=":/?#[]@!$&'()*+,;=%")
                yield f"<{escape(safe_url)}|", label.replace("|", " / "), ">"
            else:
                yield "", label, ""
        elif bold is not None:
            yield "*", bold, "*"
        else:
            yield "~", strike, "~"
        position = match.end()
    yield "", text[position:], ""


def markdown_parts(text):
    lines = (text or "").replace("\r\n", "\n").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence:
            marker = fence[1]
            code = []
            index += 1
            while index < len(lines) and not re.fullmatch(
                rf"\s*{re.escape(marker[0])}{{{len(marker)},}}\s*", lines[index]
            ):
                code.append(lines[index])
                index += 1
            yield "```\n", "\n".join(code).replace("```", "` ` `"), "\n```"
        elif (
            index + 1 < len(lines)
            and "|" in line
            and re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*", lines[index + 1])
        ):
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                row = "; ".join(
                    f"{headers[column]}: {cell}" if column < len(headers) else cell
                    for column, cell in enumerate(cells)
                )
                yield from inline_parts("- " + row)
                yield "", "\n", ""
                index += 1
            continue
        else:
            heading = re.match(r"^#{1,6}\s+(.+?)(?:\s+#+)?$", line)
            if heading:
                yield "*", heading[1].replace("**", ""), "*"
            else:
                line = re.sub(r"^([ \t]*)[*+]\s+", r"\1- ", line)
                line = re.sub(r"^([ \t]*)- \[([ xX])\]\s+", r"\1- (\2) ", line)
                yield from inline_parts(line)
        yield "", "\n", ""
        index += 1


def body_preview(text, limit=2800):
    parts = []
    remaining = limit - 4
    truncated = False
    for prefix, content, suffix in markdown_parts(text):
        encoded = escape(content)
        size = len(prefix) + len(encoded) + len(suffix)
        if size > remaining:
            available = remaining - len(prefix) - len(suffix)
            if available > 0:
                parts.append(prefix + escaped_excerpt(content, available) + suffix)
            truncated = True
            break
        parts.append(prefix + encoded + suffix)
        remaining -= size
    result = "".join(parts).strip()
    if truncated:
        result += "\n..."
    return result or "본문이 없습니다."
