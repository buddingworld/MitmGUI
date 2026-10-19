"""Text conversions used by the "Convert Selection" context menu.

The semantics follow the Tools window (``ToolsDialog`` in ``main_window``) so a
conversion applied to a selection produces what the matching tool would; the
HTML group follows Burp's HTML options instead, since the Tools window has no
HTML tab.

Every converter takes the selected text and returns the converted text. On
input it cannot handle it raises ``ValueError`` with a short reason, which the
caller shows to the user.
"""

import base64
import binascii
import html
import urllib.parse

#: Characters the URL encoders leave alone — the same set the Tools window's
#: URL encoder keeps (its ``quote(..., safe="-._~")`` mode).
_URL_SAFE = "-._~"

#: The characters Burp treats as significant in HTML markup, with the entity
#: names used for them by the "encode all characters" converter.
_HTML_KEY_ENTITIES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


# ── URL ──


def url_decode(text: str) -> str:
    """URL-decode, treating ``+`` as a space (as the Tools window does)."""
    return urllib.parse.unquote_plus(text)


def url_encode_key(text: str) -> str:
    """Percent-encode everything that is not an unreserved URL character."""
    return urllib.parse.quote(text, safe=_URL_SAFE)


def url_encode_all(text: str) -> str:
    """Percent-encode every byte of the UTF-8 encoding, ASCII included."""
    return "".join(f"%{byte:02X}" for byte in text.encode("utf-8"))


def _unicode_escape(ch: str) -> str:
    """``%uXXXX`` for one character, using a surrogate pair above the BMP."""
    code = ord(ch)
    if code <= 0xFFFF:
        return f"%u{code:04X}"
    code -= 0x10000
    return f"%u{0xD800 + (code >> 10):04X}%u{0xDC00 + (code & 0x3FF):04X}"


def _is_url_unreserved(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in _URL_SAFE)


def url_encode_key_unicode(text: str) -> str:
    """Like :func:`url_encode_key`, but encoded characters become ``%uXXXX``."""
    return "".join(
        ch if _is_url_unreserved(ch) else _unicode_escape(ch) for ch in text
    )


def url_encode_all_unicode(text: str) -> str:
    """Encode every character as ``%uXXXX``, ASCII included."""
    return "".join(_unicode_escape(ch) for ch in text)


# ── HTML ──


def html_decode(text: str) -> str:
    """Decode named, numeric and hex HTML entities."""
    return html.unescape(text)


def html_encode_key(text: str) -> str:
    """Encode only the markup-significant characters."""
    return html.escape(text, quote=True)


def html_encode_all(text: str) -> str:
    """Encode every character, preferring a named entity when one exists."""
    out = []
    for ch in text:
        named = _HTML_KEY_ENTITIES.get(ch)
        if named is not None:
            out.append(named)
            continue
        name = html.entities.codepoint2name.get(ord(ch))
        out.append(f"&{name};" if name else f"&#{ord(ch)};")
    return "".join(out)


def html_encode_all_numeric(text: str) -> str:
    """Encode every character as a decimal numeric entity."""
    return "".join(f"&#{ord(ch)};" for ch in text)


def html_encode_all_hex(text: str) -> str:
    """Encode every character as a hexadecimal numeric entity."""
    return "".join(f"&#x{ord(ch):X};" for ch in text)


# ── Base64 ──


def _base64_bytes(text: str) -> bytes:
    """Decode base64 text to bytes, ignoring whitespace from wrapped input."""
    compact = "".join(text.split())
    if not compact:
        raise ValueError("nothing to decode")
    compact += "=" * (-len(compact) % 4)
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"not valid base64 ({exc})") from exc


def base64_decode(text: str) -> str:
    """Decode base64 back to UTF-8 text."""
    return _base64_bytes(text).decode("utf-8", errors="replace")


def base64_encode(text: str, padding: bool = True) -> str:
    """Base64-encode the UTF-8 bytes, optionally without ``=`` padding."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return encoded if padding else encoded.rstrip("=")


# ── Base64 URL ──


def base64_encode_urlencode(text: str, padding: bool = True) -> str:
    """Base64-encode, then percent-encode the whole result for use in a URL."""
    return urllib.parse.quote(base64_encode(text, padding), safe="")


def urldecode_base64_decode(text: str) -> str:
    """URL-decode, then base64-decode.

    Plain ``unquote`` rather than ``unquote_plus`` is used because a literal
    ``+`` is meaningful inside base64 and must survive; an encoded ``%2B``
    still decodes to ``+``.
    """
    return base64_decode(urllib.parse.unquote(text))


# ── Native (Unicode escapes) ──


def native_to_string(text: str) -> str:
    r"""Turn ``\uXXXX`` / ``\UXXXXXXXX`` / ``\xNN`` escapes into characters.

    Literal non-ASCII text is protected first: ``unicode_escape`` would
    otherwise read the UTF-8 bytes of e.g. ``中`` as latin-1 and mangle them.
    """
    guarded = []
    for ch in text:
        code = ord(ch)
        if code < 0x80:
            guarded.append(ch)
        elif code <= 0xFFFF:
            guarded.append(f"\\u{code:04x}")
        else:
            guarded.append(f"\\U{code:08x}")
    try:
        return bytes("".join(guarded), "utf-8").decode("unicode_escape")
    except UnicodeError as exc:
        raise ValueError(f"not a valid escape sequence ({exc})") from exc


def string_to_native(text: str, ignore_latin: bool = False) -> str:
    r"""Turn characters into ``\uXXXX`` / ``\UXXXXXXXX`` escapes.

    With ``ignore_latin`` the ASCII characters are kept as-is, as the Tools
    window's "Ignore latin characters" option does.
    """
    out = []
    for ch in text:
        code = ord(ch)
        if ignore_latin and code <= 0x7F:
            out.append(ch)
        elif code <= 0xFFFF:
            out.append(f"\\u{code:04x}")
        else:
            out.append(f"\\U{code:08x}")
    return "".join(out)


#: The "Convert Selection" menu, as (group, ((label, converter), ...)) pairs.
#: Kept as data so the menu and this module cannot drift apart.
MENU: tuple[tuple[str, tuple[tuple[str, object], ...]], ...] = (
    (
        "URL",
        (
            ("URL DECODE", url_decode),
            ("URL ENCODE Key Characters", url_encode_key),
            ("URL ENCODE Key Characters(Unicode)", url_encode_key_unicode),
            ("URL ENCODE All", url_encode_all),
            ("URL ENCODE All(Unicode)", url_encode_all_unicode),
        ),
    ),
    (
        "HTML",
        (
            ("HTML DECODE", html_decode),
            ("HTML ENCODE Key Characters", html_encode_key),
            ("HTML ENCODE All Characters", html_encode_all),
            ("HTML ENCODE All Characters (numeric entities)", html_encode_all_numeric),
            ("HTML ENCODE All Characters (hex entities)", html_encode_all_hex),
        ),
    ),
    (
        "BASE64",
        (
            ("BASE64 Decode", base64_decode),
            ("BASE64 Encode With Padding", lambda t: base64_encode(t, True)),
            ("BASE64 Encode", lambda t: base64_encode(t, False)),
        ),
    ),
    (
        "BASE64 URL",
        (
            (
                "BASE64 Encode With Padding+URLENCODE",
                lambda t: base64_encode_urlencode(t, True),
            ),
            ("BASE64 Encode +URLENCODE", lambda t: base64_encode_urlencode(t, False)),
            ("URLDECODE + BASE64DECODE", urldecode_base64_decode),
        ),
    ),
    (
        "Native",
        (
            ("Native -> String", native_to_string),
            ("ASCII -> Native (All)", lambda t: string_to_native(t, False)),
            (
                "ASCII -> Native (Ignore Latin Characters)",
                lambda t: string_to_native(t, True),
            ),
        ),
    ),
)
