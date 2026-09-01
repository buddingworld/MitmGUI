import asyncio
import logging
import os
import threading
import time

from mitmproxy import addons
from mitmproxy import hooks
from mitmproxy import master
from mitmproxy import options
from mitmproxy.net.http import url
from mitmproxy.addons import eventstore
from mitmproxy.addons import intercept
from mitmproxy.addons import readfile
from mitmproxy.addons import view
from mitmproxy.addons.proxyserver import Proxyserver
from mitmproxy.tools.mitmgui.plugins_manager import _PluginsAddon

logger = logging.getLogger(__name__)


class _ResponseIntercept:
    """Intercepts only the RESPONSE phase for specific flow IDs.

    Unlike flow.intercept() which pauses both request *and* response,
    this addon only intercepts the response, letting the request
    proceed to the server normally.
    """

    def __init__(self):
        self.intercept_ids: set[str] = set()

    def response(self, flow):
        fid = str(flow.id)
        if fid in self.intercept_ids:
            flow.intercept()
            self.intercept_ids.discard(fid)


class _HostsRemappingAddon:
    """Remaps request targets based on a hosts.txt file.

    Format (one rule per line):
        NewIP Hostname
        NewHostname Hostname
        NewHost:NewPort Hostname[:OriginalPort]
    Blank lines and lines starting with # are ignored.
    """

    def __init__(self):
        self._rules: list[tuple[str, int | None, str, int | None]] = []
        self._hosts_file = os.path.join(os.getcwd(), "hosts.txt")
        self.reload()

    @staticmethod
    def _split_host_port(value: str) -> tuple[str, int | None]:
        value = value.strip()
        if value.startswith("["):
            end = value.find("]")
            if end != -1:
                host = value[1:end]
                rest = value[end + 1:]
                if rest.startswith(":") and rest[1:].isdigit():
                    return host, int(rest[1:])
                return host, None
        if value.count(":") == 1:
            host, port = value.rsplit(":", 1)
            if port.isdigit():
                return host, int(port)
        return value, None

    def reload(self) -> None:
        """Reload hosts rules from hosts.txt."""
        rules = []
        try:
            if os.path.isfile(self._hosts_file):
                with open(self._hosts_file, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if not s or s.startswith("#"):
                            continue
                        parts = s.split(None, 1)
                        if len(parts) == 2:
                            new_host, new_port = self._split_host_port(parts[0])
                            match_host, match_port = self._split_host_port(parts[1])
                            rules.append((new_host, new_port, match_host, match_port))
        except OSError:
            pass
        self._rules = rules

    def _map_target(self, host: str, port: int) -> tuple[str, int] | None:
        for new_host, new_port, match_host, match_port in self._rules:
            if host == match_host and (match_port is None or port == match_port):
                return new_host, new_port if new_port is not None else port
        return None

    def server_connect(self, data) -> None:
        if not data.server.address:
            return
        mapped = self._map_target(*data.server.address)
        if mapped is not None:
            data.server.address = mapped

    def _remap_flow_request_target(self, flow) -> None:
        request = flow.request
        mapped = self._map_target(request.pretty_host, request.port)
        if mapped is None:
            return
        new_host, new_port = mapped
        # Save the original host_header (the Host header value from the request)
        # so the GUI can always display the original hostname.
        flow._original_host = request.host_header or request.pretty_host
        # Set data.host/data.port directly to bypass property setters, which
        # overwrite the Host header and authority. This keeps the original Host
        # header while changing the request target fields for display/replay.
        request.data.host = new_host
        request.data.port = new_port
        flow._hosts_remapped = True

    def requestheaders(self, flow) -> None:
        self._remap_flow_request_target(flow)

    def request(self, flow) -> None:
        self._remap_flow_request_target(flow)


class _AutoRulesAddon:
    """Applies Auto Rules (autos.json) to matching flows.

    Rule format:
        {
          "enabled": true,
          "item": "Request.Url" | "Request.Header"
                  | "Response.Header" | "Response.Body",   # match location
          "match_type": "String" | "Regex",
          "match_value": "...",                            # match condition
          "action": "Color" | "Response With" | "Response With File"
                    | "SaveToFile" | "Replace",
          "value": ...                                     # action payload
        }
    - ``Color`` is applied by the GUI (session list), not by this addon.
    - ``Response With`` answers the request directly with the configured
      payload (matched on the request side), without contacting the web
      server; rules matched on the response side overwrite the body. The
      payload is either a plain body text or a full raw HTTP response
      packet (starting with "HTTP/") which is replayed verbatim.
    - ``Response With File`` works like ``Response With`` but the payload
      comes from a file (``value`` is the file path). If the file starts
      with "HTTP/" it is parsed as a raw response packet and replayed
      verbatim; otherwise a 200 OK response is built with a Content-Type
      guessed from the file extension (unknown -> application/octet-stream).
    - ``SaveToFile`` saves the matching flow to ``value`` (a directory) as
      ``Session_{timestamp}.txt`` once its response is available.
    - ``Replace`` rewrites the location selected by ``value.in``:
        value = {
          "in": "URL" | "Request.Headers" | "Request.Body"
                | "Response.Headers" | "Response.Body"
                | "WebSocket.C2S" | "WebSocket.S2C" | "WebSocket.Both",
          "type": "String" | "Regex",
          "source": "...",
          "destination": "..."
        }
      ``WebSocket.*`` targets rewrite the content of WebSocket messages
      (C2S = client -> server, S2C = server -> client, Both = either
      direction). They are applied in the ``websocket_message`` hook.
    """

    AUTO_FILE = os.path.join(os.getcwd(), "autos.json")

    def __init__(self):
        self._rules: list[dict] = []
        self._last_mtime: float | None = None
        self._save_pending: dict[str, str] = {}  # flow id -> save directory
        self.reload()

    def reload(self) -> None:
        """Reload rules from autos.json."""
        import json
        try:
            self._last_mtime = os.path.getmtime(self.AUTO_FILE)
        except OSError:
            self._last_mtime = None
        try:
            if os.path.isfile(self.AUTO_FILE):
                with open(self.AUTO_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._rules = data if isinstance(data, list) else []
            else:
                self._rules = []
        except (OSError, json.JSONDecodeError):
            self._rules = []

    def _refresh_rules_if_changed(self) -> None:
        """Reload rules from autos.json if the file changed on disk."""
        try:
            mtime = os.path.getmtime(self.AUTO_FILE)
        except OSError:
            return
        if mtime != self._last_mtime:
            self.reload()

    # ── Matching ──

    @staticmethod
    def _target_text(flow, item: str) -> str:
        """Return the text of ``item`` on a flow for matching purposes.

        Strings are used as-is (no automatic URL encoding/decoding): users
        paste percent-encoded values themselves when they need to match them.
        """
        if item == "Request.Url":
            if not flow.request:
                return ""
            return flow.request.url
        if item == "Request.Header":
            if not flow.request:
                return ""
            try:
                return str(flow.request.headers)
            except Exception:
                return ""
        if item == "Response.Header":
            if not flow.response:
                return ""
            try:
                return str(flow.response.headers)
            except Exception:
                return ""
        if item == "Response.Body":
            if not flow.response:
                return ""
            content = flow.response.get_text(strict=False)
            return content or ""
        return ""

    @staticmethod
    def _match_rule(rule: dict, text: str) -> bool:
        """Check whether ``text`` satisfies the rule's match condition."""
        match_type = rule.get("match_type", "String")
        match_value = rule.get("match_value", "")
        if not match_value:
            return False
        if match_type == "Regex":
            import re
            try:
                return re.search(match_value, text) is not None
            except re.error:
                return False
        return match_value in text

    def _first_rule(self, flow, items: tuple[str, ...]):
        """Return the first enabled rule whose item is in ``items`` and matches."""
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("item", "") not in items:
                continue
            text = self._target_text(flow, rule.get("item", ""))
            if self._match_rule(rule, text):
                return rule
        return None

    # ── Replace helpers ──

    @staticmethod
    def _apply_replace_text(text: str, source: str, destination: str, rtype: str) -> str:
        if not source:
            return text
        if rtype == "Regex":
            import re
            try:
                return re.sub(source, destination, text)
            except re.error:
                return text
        return text.replace(source, destination)

    @staticmethod
    def _set_request_target_url_preserve_host_header(request, new_url: str) -> None:
        scheme, host, port, path = url.parse(new_url)
        request.data.scheme = scheme
        request.data.host = host.decode("idna")
        request.data.port = port
        request.data.path = path

    @staticmethod
    def _apply_replace_to_headers(headers, source: str, destination: str, rtype: str) -> bool:
        """Apply replacement to header names and values. Returns True if any change."""
        changed = False
        new_fields = []
        for name, value in headers.fields:
            s_name = name.decode("utf-8", "replace")
            s_value = value.decode("utf-8", "replace")
            new_name = _AutoRulesAddon._apply_replace_text(s_name, source, destination, rtype)
            new_value = _AutoRulesAddon._apply_replace_text(s_value, source, destination, rtype)
            if new_name != s_name or new_value != s_value:
                changed = True
            new_fields.append((new_name.encode("utf-8"), new_value.encode("utf-8")))
        if changed:
            headers.fields = tuple(new_fields)
        return changed

    @staticmethod
    def _apply_replace_to_body(msg, source: str, destination: str, rtype: str) -> bool:
        if msg is None or msg.content is None:
            return False
        content = msg.get_text(strict=False)
        if content is None:
            return False
        new_content = _AutoRulesAddon._apply_replace_text(content, source, destination, rtype)
        if new_content != content:
            msg.set_text(new_content)
            return True
        return False

    @staticmethod
    def _apply_replace_to_ws(message, source: str, destination: str, rtype: str) -> bool:
        """Apply replacement to a WebSocket message's content."""
        if message is None or message.content is None:
            return False
        text = message.content.decode("utf-8", "replace")
        new_text = _AutoRulesAddon._apply_replace_text(text, source, destination, rtype)
        if new_text != text:
            message.content = new_text.encode("utf-8")
            return True
        return False

    def _apply_replace_rule(self, flow, rule: dict, message=None) -> bool:
        """Apply one Replace rule. Returns True if anything changed.

        ``message`` is the current WebSocket message when the rule targets
        ``value.in`` in (WebSocket.C2S, WebSocket.S2C, WebSocket.Both).
        """
        value = rule.get("value")
        if not isinstance(value, dict):
            return False
        replace_in = value.get("in", "URL")
        rtype = value.get("type", "String")
        source = value.get("source", "")
        destination = value.get("destination", "")
        if not source:
            return False

        if replace_in in ("WebSocket.C2S", "WebSocket.S2C", "WebSocket.Both"):
            return message is not None and self._apply_replace_to_ws(
                message, source, destination, rtype
            )
        if replace_in == "URL":
            if flow.request and flow.request.url:
                # No automatic URL encoding: Source/Destination are applied
                # as-is. Users paste percent-encoded values when needed.
                new_url = self._apply_replace_text(
                    flow.request.url, source, destination, rtype
                )
                if new_url != flow.request.url:
                    self._set_request_target_url_preserve_host_header(flow.request, new_url)
                    return True
            return False
        if replace_in == "Request.Headers":
            return bool(flow.request) and self._apply_replace_to_headers(
                flow.request.headers, source, destination, rtype
            )
        if replace_in == "Request.Body":
            return self._apply_replace_to_body(flow.request, source, destination, rtype)
        if replace_in == "Response.Headers":
            return bool(flow.response) and self._apply_replace_to_headers(
                flow.response.headers, source, destination, rtype
            )
        if replace_in == "Response.Body":
            return self._apply_replace_to_body(flow.response, source, destination, rtype)
        return False

    # ── Hooks ──

    @staticmethod
    def _replace_rule_in(value) -> str:
        """The replace target location of a rule's value, defaulting to URL."""
        if isinstance(value, dict):
            return value.get("in", "URL")
        return "URL"

    def _apply_replace_matching(self, flow, target_ins: set[str]) -> None:
        """Apply every enabled Replace rule whose target is in ``target_ins``.

        The match condition (``item``/``match_type``/``match_value``) is
        evaluated independently of the replace target (``value.in``), so a rule
        may match e.g. a Request.Header but replace inside Response.Body.
        """
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("action") != "Replace":
                continue
            if self._replace_rule_in(rule.get("value")) not in target_ins:
                continue
            text = self._target_text(flow, rule.get("item", ""))
            if self._match_rule(rule, text):
                self._apply_replace_rule(flow, rule)

    def _apply_websocket_replace(self, flow, message) -> None:
        """Apply every enabled Replace rule targeting WebSocket message
        contents. The direction is selected by ``value.in``:
        ``WebSocket.C2S`` (client -> server), ``WebSocket.S2C``
        (server -> client) or ``WebSocket.Both``."""
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("action") != "Replace":
                continue
            replace_in = self._replace_rule_in(rule.get("value"))
            if replace_in == "WebSocket.C2S":
                if not message.from_client:
                    continue
            elif replace_in == "WebSocket.S2C":
                if message.from_client:
                    continue
            elif replace_in == "WebSocket.Both":
                pass
            else:
                continue
            text = self._target_text(flow, rule.get("item", ""))
            if self._match_rule(rule, text):
                self._apply_replace_rule(flow, rule, message)

    def _apply_response_with(self, flow) -> None:
        """Answer the first matching Response With / Response With File rule
        directly with the configured payload, without contacting the web
        server.

        Only rules whose match location lives on the request side
        (Request.Url / Request.Header) can be evaluated here, since the
        response is not available yet.
        """
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            action = rule.get("action")
            if action not in ("Response With", "Response With File"):
                continue
            text = self._target_text(flow, rule.get("item", ""))
            if not self._match_rule(rule, text):
                continue
            value = rule.get("value")
            if not isinstance(value, str) or not value:
                return
            if action == "Response With File":
                flow.response = self._response_from_file(value)
            else:
                flow.response = self._response_with_value(value)
            return

    @staticmethod
    def _response_with_value(value: str):
        """Build the response object for a Response With rule.

        If ``value`` looks like a raw HTTP response packet (starts with
        "HTTP/"), it is parsed and replayed verbatim: the status line,
        headers and body are taken from the pasted packet. Otherwise the
        value is returned as a plain-text body with status 200.
        """
        from mitmproxy import http
        from mitmproxy.net.http import http1

        if not value.lstrip("\ufeff \t\r\n").startswith("HTTP/"):
            return http.Response.make(
                200,
                value.encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8"},
            )
        try:
            # Normalize line endings so CRLF and LF packets both parse.
            raw = value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
            lines = raw.split(b"\n")
            sep = len(lines)
            for i, line in enumerate(lines):
                if line == b"":
                    sep = i
                    break
            resp = http1.read_response_head(lines[:sep])
            body = b"\r\n".join(lines[sep + 1:])
            resp.content = body
            # Framing headers must match the actual body we serve.
            resp.headers.pop("Content-Length", None)
            resp.headers.pop("Transfer-Encoding", None)
            resp.headers["Content-Length"] = str(len(body))
            return resp
        except (ValueError, IndexError, TypeError):
            # Fall back to plain text if the packet cannot be parsed.
            return http.Response.make(
                200,
                value.encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8"},
            )

    # Content types guessed from the file extension for "Response With File".
    _FILE_CONTENT_TYPES = {
        ".json": "application/json",
        ".html": "text/html",
        ".htm": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".xml": "application/xml",
        ".txt": "text/plain",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".pdf": "application/pdf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".zip": "application/zip",
        ".mp4": "video/mp4",
    }

    def _response_from_file(self, path: str):
        """Build the response object for a Response With File rule.

        If the file starts with "HTTP/", it is parsed as a raw response
        packet and replayed verbatim (status line, headers and body are
        taken from the file). Otherwise a 200 OK response is built with a
        Content-Type guessed from the file extension; unknown extensions
        get "application/octet-stream".
        """
        from mitmproxy import http
        from mitmproxy.net.http import http1

        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            return http.Response.make(
                500,
                f"AutoRule: cannot read file '{path}' ({e})".encode("utf-8"),
                {"Content-Type": "text/plain; charset=utf-8"},
            )

        head = data.lstrip(b"\xef\xbb\xbf \t\r\n")
        if not head.startswith(b"HTTP/"):
            ext = os.path.splitext(path)[1].lower()
            ct = self._FILE_CONTENT_TYPES.get(ext, "application/octet-stream")
            return http.Response.make(200, data, {"Content-Type": ct})

        try:
            # Split head/body at the first empty line (CRLF or LF); the raw
            # body bytes are kept verbatim so binary payloads survive.
            i_crlf = data.find(b"\r\n\r\n")
            i_lf = data.find(b"\n\n")
            candidates = [(i, 4) for i in (i_crlf,) if i != -1]
            candidates += [(i, 2) for i in (i_lf,) if i != -1]
            if candidates:
                sep, skip = min(candidates)
                head_lines = data[:sep].splitlines()
                body = data[sep + skip:]
            else:
                head_lines, body = data.splitlines(), b""
            resp = http1.read_response_head(head_lines)
            resp.content = body
            # Framing headers must match the actual body we serve.
            resp.headers.pop("Content-Length", None)
            resp.headers.pop("Transfer-Encoding", None)
            resp.headers["Content-Length"] = str(len(body))
            return resp
        except (ValueError, IndexError, TypeError):
            ext = os.path.splitext(path)[1].lower()
            ct = self._FILE_CONTENT_TYPES.get(ext, "application/octet-stream")
            return http.Response.make(200, data, {"Content-Type": ct})

    def _save_flow_to_file(self, flow, directory: str) -> None:
        """Save a matching flow to ``directory`` as Session_{timestamp}.txt."""
        try:
            os.makedirs(directory, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
            path = os.path.join(directory, f"Session_{ts}.txt")
            lines = []

            req = getattr(flow, "request", None)
            if req is not None:
                lines.append("================ Request ================")
                lines.append(f"{req.method} {req.url} {req.http_version}")
                lines.extend(f"{k}: {v}" for k, v in req.headers.items())
                lines.append("")
                try:
                    lines.append(req.get_text(strict=False) or "")
                except ValueError:
                    lines.append(f"<binary body, {len(req.raw_content or b'')} bytes>")

            resp = getattr(flow, "response", None)
            if resp is not None:
                lines.append("================ Response ================")
                lines.append(f"{resp.http_version} {resp.status_code} {resp.reason}")
                lines.extend(f"{k}: {v}" for k, v in resp.headers.items())
                lines.append("")
                try:
                    lines.append(resp.get_text(strict=False) or "")
                except ValueError:
                    lines.append(f"<binary body, {len(resp.raw_content or b'')} bytes>")

            with open(path, "w", encoding="utf-8", errors="replace") as f:
                f.write("\n".join(lines))
        except OSError:
            # Never break proxying because of a save failure.
            pass

    def request(self, flow) -> None:
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        self._refresh_rules_if_changed()
        # Response With / Response With File: return the configured payload
        # without contacting the web server.
        self._apply_response_with(flow)
        # SaveToFile rules matching on the request side: if the flow was
        # short-circuited above (response already present) save it now,
        # otherwise remember the directory and save in the response hook.
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("action") != "SaveToFile":
                continue
            if rule.get("item") not in ("Request.Url", "Request.Header"):
                continue
            text = self._target_text(flow, rule.get("item", ""))
            if self._match_rule(rule, text):
                value = rule.get("value")
                if isinstance(value, str) and value:
                    if flow.response is not None:
                        self._save_flow_to_file(flow, value)
                    else:
                        self._save_pending[str(getattr(flow, "id", ""))] = value
                break
        # Replace rules targeting the request side (URL / Request.*)
        self._apply_replace_matching(flow, {"URL", "Request.Headers", "Request.Body"})

    def response(self, flow) -> None:
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        self._refresh_rules_if_changed()
        # Response With / Response With File: first matching rule whose item
        # is a response location
        rule = self._first_rule(flow, ("Response.Header", "Response.Body"))
        if rule is not None and rule.get("action") in ("Response With", "Response With File"):
            value = rule.get("value")
            if isinstance(value, str) and value and flow.response is not None:
                if rule.get("action") == "Response With File":
                    flow.response = self._response_from_file(value)
                elif value.lstrip("\ufeff \t\r\n").startswith("HTTP/"):
                    flow.response = self._response_with_value(value)
                else:
                    flow.response.set_text(value)
        # SaveToFile: request-side pending match or response-side match; the
        # response is now available so the full exchange can be written.
        save_dir = self._save_pending.pop(str(getattr(flow, "id", "")), None)
        if save_dir is None:
            for r in self._rules:
                if not r.get("enabled", True):
                    continue
                if r.get("action") != "SaveToFile":
                    continue
                if r.get("item") not in ("Response.Header", "Response.Body"):
                    continue
                text = self._target_text(flow, r.get("item", ""))
                if self._match_rule(r, text):
                    value = r.get("value")
                    if isinstance(value, str):
                        save_dir = value
                    break
        if save_dir and flow.response is not None:
            self._save_flow_to_file(flow, save_dir)
        # Replace rules targeting the response side (Response.Headers/Body);
        # the match item may live on either side of the flow.
        self._apply_replace_matching(
            flow, {"Response.Headers", "Response.Body"}
        )

    def websocket_message(self, flow) -> None:
        """Apply Replace rules targeting WebSocket message contents
        (``value.in`` in WebSocket.C2S / WebSocket.S2C / WebSocket.Both)."""
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        if flow.websocket is None or not flow.websocket.messages:
            return
        self._refresh_rules_if_changed()
        self._apply_websocket_replace(flow, flow.websocket.messages[-1])


class _BreakpointRequestIntercept:
    """Addon that intercepts incoming requests based on breakpoint rules.

    Bypasses the mitmproxy flowfilter/options mechanism to ensure reliable
    cross-thread breakpoint enforcement directly on the proxy event loop.
    Requests matching the GUI filter rules (filter.json) are never
    intercepted - they behave as if BreakPoint was off for those sessions.
    """

    def __init__(self):
        self.breakpoint_mode: bool = False
        self.breakpoint_rules: list[dict] = []
        # Flow IDs that should bypass request interception because they are
        # being replayed specifically for response-only interception (Break On
        # Response in Replay And Edit mode while breakpoint mode is active).
        self.response_only_ids: set[str] = set()
        # GUI filter rules: matching sessions skip breakpoint interception.
        self.filter_rules: list[dict] = self._load_filter_rules()
        # Flows this addon has intercepted (id -> flow). Used to release every
        # pending flow when breakpoint mode/rules are turned off so that no
        # traffic is left stuck in the "one request at a time" state.
        self.intercepted_flows: dict[str, object] = {}

    @staticmethod
    def _load_filter_rules() -> list[dict]:
        import json
        import os
        try:
            with open(
                os.path.join(os.getcwd(), "filter.json"), "r", encoding="utf-8"
            ) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _matches_filter(self, flow) -> bool:
        """Return True if the flow matches any GUI filter rule.

        Must match MitmGuiMainWindow._match_filter_rule() exactly.
        """
        if not flow.request:
            return False
        for rule in self.filter_rules:
            rule_type = rule.get("type", "")
            rule_value = rule.get("value", "")
            if rule_type == "hostname":
                if (flow.request.host or "") == rule_value:
                    return True
            elif rule_type == "path":
                # Ignore a leading slash and optionally the query string.
                rule_value = rule_value.lstrip("/")
                full = (flow.request.path or "").lstrip("/")
                bare = full.split("?", 1)[0]
                if full == rule_value or bare == rule_value:
                    return True
        return False

    def request(self, flow) -> None:
        from mitmproxy import http
        if not isinstance(flow, http.HTTPFlow):
            return
        # Filtered sessions bypass BreakPoint entirely and complete normally.
        if self._matches_filter(flow):
            return
        fid = str(flow.id)
        if fid in self.response_only_ids:
            return
        if self.breakpoint_mode:
            flow.intercept()
            self.intercepted_flows[fid] = flow
            return
        if self.breakpoint_rules and self._match_rules(flow):
            flow.intercept()
            self.intercepted_flows[fid] = flow

    def response(self, flow) -> None:
        # A resumed breakpoint flow finally got its response - forget it so the
        # bookkeeping does not grow unbounded.
        self.intercepted_flows.pop(str(flow.id), None)

    def release_all(self) -> None:
        """Resume every flow intercepted by this addon.

        Must be called on the proxy event loop (e.g. via
        master._loop.call_soon_threadsafe) so that flow.resume() is safe.
        This is invoked whenever BreakPoint mode/rules are switched off so
        that no traffic remains stuck in the intercepted state.
        """
        for flow in list(self.intercepted_flows.values()):
            flow.resume()
        self.intercepted_flows.clear()

    def _match_rules(self, flow) -> bool:
        import re
        for rule in self.breakpoint_rules:
            prop = rule.get("property", "host")
            value = rule.get("value", "")
            match_type = rule.get("match_type", "contains")
            if prop == "host":
                host = flow.request.host if flow.request else ""
                if match_type == "regex":
                    try:
                        if re.search(value, host, re.IGNORECASE):
                            return True
                    except re.error:
                        pass
                else:  # contains
                    if value.lower() in host.lower():
                        return True
        return False


class MitmGuiMaster(master.Master):
    """Master class that bridges mitmproxy with the PyQt6 GUI.

    Unlike CLI tools (mitmdump/mitmproxy), we do NOT use ErrorCheck here.
    ErrorCheck calls sys.exit(1) on any ERROR-level log during startup,
    which would kill the entire GUI.  Instead we store errors so the
    GUI can surface them in a dialog or status bar.
    """

    def __init__(self, opts: options.Options):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        super().__init__(opts, event_loop=self._loop)

        self.view = view.View()
        self.startup_errors: list[str] = []

        # EventStore's CallbackLogger calls asyncio.get_running_loop() in
        # __init__, so we need to create it inside a running event loop.
        self._loop.run_until_complete(self._init_addons())

        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    async def _init_addons(self) -> None:
        self.events = eventstore.EventStore()
        self.addons.add(*addons.default_addons())
        self.response_intercept = _ResponseIntercept()
        self.breakpoint_req_intercept = _BreakpointRequestIntercept()
        self.hosts_remapping = _HostsRemappingAddon()
        self.auto_rules_addon = _AutoRulesAddon()
        self.plugins_addon = _PluginsAddon()
        self.plugins_addon.master = self  # expose session list (api.view)
        self.addons.add(
            self.breakpoint_req_intercept,
            intercept.Intercept(),
            readfile.ReadFileStdin(),
            self.view,
            self.events,
            self.response_intercept,
            self.hosts_remapping,
            self.auto_rules_addon,
            self.plugins_addon,  # last: plugin hooks run after Auto Rules
        )
        self.proxyserver: Proxyserver = self.addons.get("proxyserver")

        # Auto-load rules.py from current directory (like mitmproxy -s ./rules.py)
        import os
        from mitmproxy.addons.script import Script
        rules_path = os.path.join(os.getcwd(), "rules.py")
        if os.path.isfile(rules_path):
            try:
                script_addon = Script(rules_path, reload=True)
                self.addons.add(script_addon)
                logger.info(f"Loaded rules script: {rules_path}")
            except Exception as e:
                logger.warning(f"Failed to load rules script: {e}")

        # Load plugins registered in plugins.json (enabled ones get on_load).
        self.plugins_addon.load_from_file()

    def start(self) -> None:
        """Start the proxy in a background thread."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()

    def stop(self) -> None:
        """Stop the proxy."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self.shutdown)
        if self._thread:
            self._thread.join(timeout=5)

    def replay_flow(self, flow, on_error=None) -> None:
        """Schedule a flow for replay on the proxy event loop.

        This must be called from any thread. The replay will execute on
        the proxy's asyncio event loop, avoiding synchronous hook triggers
        on the calling thread.
        """
        if self._loop:
            def _do_replay():
                try:
                    playback = self.addons.get("clientplayback")
                    if playback:
                        error = playback.check(flow)
                        if error:
                            if on_error:
                                on_error(error)
                            return
                    self.commands.execute(f"replay.client @{flow.id}")
                except Exception as e:
                    logger.exception("Failed to replay flow %s", flow.id)
                    if on_error:
                        on_error(str(e))
            self._loop.call_soon_threadsafe(_do_replay)

    def _run_loop(self) -> None:
        """Run the asyncio event loop in a background thread."""
        asyncio.set_event_loop(self._loop)
        try:
            self._ready.set()
            self._loop.run_until_complete(self._run_mitmgui())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            msg = f"Proxy error: {e}"
            logger.error(msg)
            self.startup_errors.append(msg)

    async def _run_mitmgui(self) -> None:
        """Wrapper around Master.run() that tolerates errors during startup.

        The base Master.run() treats any OptionsError during running() as
        fatal and shuts down the event loop.  For a GUI application, a
        non-critical error (e.g. broken user cert) should not prevent
        basic HTTP proxying.
        """
        from mitmproxy.utils import asyncio_utils as au

        with (
            au.install_exception_handler(self._asyncio_exception_handler),
            au.set_eager_task_factory(),
        ):
            self.should_exit.clear()

            if ps := self.addons.get("proxyserver"):
                await asyncio.wait(
                    [
                        asyncio.create_task(
                            ps.setup_servers(), name="setup_servers"
                        ),
                        asyncio.create_task(
                            self.should_exit.wait(), name="should_exit"
                        ),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if self.should_exit.is_set():
                    return

            # Check if any servers actually started
            if ps := self.addons.get("proxyserver"):
                if not ps.listen_addrs():
                    msg = "Proxy failed to start — port may be in use or network unavailable."
                    logger.error(msg)
                    self.startup_errors.append(msg)

            try:
                await self.running()
            except Exception as e:
                msg = f"Certificate error: {e}"
                logger.warning(msg)
                self.startup_errors.append(msg)

            await self.should_exit.wait()
