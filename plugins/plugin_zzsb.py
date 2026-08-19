"""plugin_zzsb.py

对 POST 且 URL 包含 ``?zzsb`` 的请求进行处理:
1. multipart/form-data -> key=value 形式(value 做 url 编码),文件上传字段忽略;
   application/x-www-form-urlencoded -> 原样保留;
   两者统一得到 post_string。
2. 将 post_string 与字符串 "2019" 逐字节循环异或,结果 base64 编码后再 url 编码。
3. 新请求体为: commentText={url编码后的结果}
4. 处理完成后移除 URL 中的 ``?zzsb``,并把该会话标为 #ffc2fd(不写日志)。
"""

import base64
import re
import urllib.parse
from urllib.parse import parse_qsl, urlencode, urlparse

XOR_KEY = b"2019"
PLUGIN_COLOR = "#ffc2fd"


def info():
    return {
        "description": "ZZSB"
    }


def _parse_multipart(content_type: str, body: bytes) -> list[tuple[str, str | None, bytes]]:
    """Parse multipart/form-data. Returns [(name, filename, value)].

    ``filename`` is None for ordinary fields, so file uploads can be ignored.
    """
    m = re.search(r'boundary="?([^";]+)"?', content_type)
    if not m:
        return []
    boundary = m.group(1).encode("utf-8")
    parts: list[tuple[str, str | None, bytes]] = []
    for raw in body.split(b"--" + boundary):
        header_end = raw.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        header = raw[:header_end].decode("utf-8", "replace")
        value = raw[header_end + 4:]
        if value.endswith(b"\r\n"):
            value = value[:-2]
        name = None
        filename = None
        for line in header.split("\r\n"):
            if line.lower().startswith("content-disposition"):
                nm = re.search(r'name="([^"]*)"', line)
                fm = re.search(r'filename="([^"]*)"', line)
                if nm:
                    name = nm.group(1)
                if fm:
                    filename = fm.group(1)
        parts.append((name, filename, value))
    return parts


def _strip_marker(req, marker: str) -> None:
    """Remove the marker query parameter (and the ``?`` if it was the only one)."""
    parsed = urlparse(req.path)
    if not parsed.query:
        return
    kept = [
        kv for kv in parse_qsl(parsed.query, keep_blank_values=True) if kv[0] != marker
    ]
    new_query = urlencode(kept)
    new_path = parsed.path
    if new_query:
        new_path += "?" + new_query
    if parsed.fragment:
        new_path += "#" + parsed.fragment
    req.path = new_path


def _rewrite_aspx_64string(post_string: str) -> str:
    def replace_match(match: re.Match[str]) -> str:
        encoded = match.group(1)
        decoded = urllib.parse.unquote_plus(encoded)
        decoded += "=" * (-len(decoded) % 4)
        text = base64.b64decode(decoded).decode("utf-8", "replace")
        text = text.replace("Request.Item", "req.item")
        rewritten = base64.b64encode(text.encode("utf-8")).decode("ascii")
        rewritten = urllib.parse.quote(rewritten, safe="")
        return f'64String("{rewritten}")'

    return re.sub(r'64String\("([^"]*)"\)', replace_match, post_string)


def request(flow, api):
    req = flow.request
    if req.method.upper() != "POST":
        return
    has_zzsb = "?zzsb" in req.pretty_url
    has_zzs = "?zzs" in req.pretty_url
    if not has_zzsb and not has_zzs:
        return
    marker = "zzsb" if has_zzsb else "zzs"

    # Keep the original header for parsing (the boundary is case-sensitive),
    # lowercase only for the MIME type check.
    content_type_raw = req.headers.get("content-type", "")
    content_type = content_type_raw.lower()

    if "multipart/form-data" in content_type:
        # multipart -> key=value, values url-encoded, file uploads ignored
        pairs = []
        for name, filename, value in _parse_multipart(content_type_raw, req.content or b""):
            if name is None or filename is not None:
                continue
            encoded_value = urllib.parse.quote(value.decode("utf-8", "replace"), safe="")
            pairs.append(f"{name}={encoded_value}")
        post_string = "&".join(pairs)
    else:
        # urlencoded (and anything else) -> keep the body as-is
        post_string = req.get_text() or ""

    if ".aspx" in req.pretty_url.lower():
        post_string = _rewrite_aspx_64string(post_string)

    if has_zzs and not has_zzsb:
        enc = post_string.encode("utf-8").hex()
    else:
        # XOR with "2019"
        data = post_string.encode("utf-8")
        xored = bytes(b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(data))
        b64 = base64.b64encode(xored).decode("ascii")
        enc = urllib.parse.quote(b64, safe="")

    req.content = f"commentText={enc}".encode("utf-8")
    req.headers["content-type"] = "application/x-www-form-urlencoded"

    # Remove the marker from the URL and highlight the session.
    _strip_marker(req, marker)
    api.view.set_bgcolor(flow, PLUGIN_COLOR)
