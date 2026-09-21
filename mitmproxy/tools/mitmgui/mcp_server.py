"""MCP (Model Context Protocol) server for mitmgui.

Speaks MCP over the "Streamable HTTP" transport: JSON-RPC 2.0 messages are
POSTed to a single endpoint (``/mcp``).  Only the standard library is used,
so enabling the server does not require any extra dependency.

Three tools are exposed: ``get_sessions``, ``get_session`` and
``new_session``.  They read from / write to the running proxy through the
``MitmGuiMaster`` event loop, so all flow access happens on that loop.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mitmproxy import http
from mitmproxy.connection import Client, Server

MCP_HOST = "127.0.0.1"
MCP_PORT = 7290
MCP_PATH = "/mcp"
MCP_URL = f"http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}"

SERVER_NAME = "mitmgui"
SERVER_VERSION = "1.0.0"

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

DEFAULT_PAGE_NO = 1
DEFAULT_PAGE_SIZE = 20

# Upper bound for the body text returned by get_session, so that a single
# large download cannot blow up the caller's context window.
MAX_BODY_CHARS = 200_000

TOOLS = [
    {
        "name": "get_sessions",
        "description": (
            "List captured HTTP sessions ordered by request start time "
            "(oldest first). Every filter is optional and they are combined "
            "with AND. begin_id / end_id refer to the 1-based index of a "
            "session in the whole session store (the '#' column of the "
            "MitmGUI session list). Returns the main fields of each matching "
            "session together with pagination information."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Case-insensitive substring match on the request host.",
                },
                "url": {
                    "type": "string",
                    "description": "Case-insensitive substring match on the full request URL.",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method, e.g. GET or POST (case-insensitive).",
                },
                "begin_time": {
                    "type": "string",
                    "description": (
                        "Only sessions started at or after this time. Either "
                        "ISO-8601 (e.g. 2026-09-21T10:00:00) or Unix epoch seconds."
                    ),
                },
                "end_time": {
                    "type": "string",
                    "description": "Only sessions started at or before this time (same formats).",
                },
                "begin_id": {
                    "type": "integer",
                    "description": "First session index to include (1-based, inclusive).",
                },
                "end_id": {
                    "type": "integer",
                    "description": "Last session index to include (1-based, inclusive).",
                },
                "page_no": {
                    "type": "integer",
                    "description": "Page number, starting at 1.",
                    "default": DEFAULT_PAGE_NO,
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of sessions per page.",
                    "default": DEFAULT_PAGE_SIZE,
                },
            },
        },
    },
    {
        "name": "get_session",
        "description": (
            "Get the details of a single captured session by its session_id. "
            "The result is grouped into three sections: 'request' (method, "
            "url, host, headers, body, ...), 'response' (status_code, reason, "
            "headers, body, ...) and 'info' (timing, comment, addresses, ...). "
            "Use `fields` to limit which of them are returned."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session_id returned by get_sessions / new_session.",
                },
                "fields": {
                    "type": ["string", "array"],
                    "items": {"type": "string"},
                    "description": (
                        "Which fields to return. Defaults to '*' (everything). "
                        "Accepts a comma-separated string or an array. Valid "
                        "entries: '*' for all; 'request' / 'request.*' / "
                        "'response' / 'response.*' / 'info' / 'info.*' for a "
                        "whole section; or a dotted path such as 'request.host', "
                        "'request.url', 'request.body', 'response.headers', "
                        "'response.body', 'info.comment'."
                    ),
                    "default": "*",
                },
                "body_limit": {
                    "type": "integer",
                    "description": "Maximum number of characters returned for each body.",
                    "default": MAX_BODY_CHARS,
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "new_session",
        "description": (
            "Send a new HTTP request through MitmGUI and return its "
            "session_id. Provide either `raw` (a complete raw HTTP request) "
            "or `method` / `url` / `headers` / `body`. The response arrives "
            "asynchronously and can be fetched with get_session afterwards."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "raw": {
                    "type": "string",
                    "description": (
                        "Complete raw HTTP request text: request line, "
                        "headers, a blank line, then the body."
                    ),
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method, e.g. GET or POST.",
                },
                "url": {
                    "type": "string",
                    "description": "Absolute URL, e.g. https://example.com/api.",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers as a name/value object.",
                    "additionalProperties": {"type": "string"},
                },
                "body": {
                    "type": "string",
                    "description": "Request body sent as UTF-8 text.",
                },
            },
        },
    },
]


# ── helpers ──


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _result(mid, result) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _parse_time(value) -> float | None:
    """Accept Unix epoch seconds or an ISO-8601 string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        raise ValueError(
            f"Invalid time value {value!r}: use ISO-8601 (2026-09-21T10:00:00) "
            "or Unix epoch seconds"
        )


def _as_int(value, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer value {value!r}")


def _content_type(message) -> str:
    return message.headers.get("content-type", "") or ""


def _body_size(message) -> int:
    raw = message.raw_content
    return len(raw) if raw else 0


def _flow_start(flow: http.HTTPFlow) -> float:
    if flow.request is not None and flow.request.timestamp_start is not None:
        return flow.request.timestamp_start
    return flow.timestamp_created


def _summary(session_index: int, flow: http.HTTPFlow) -> dict:
    """The main fields shared by get_sessions and get_session."""
    request = flow.request
    response = flow.response
    return {
        "session_index": session_index,
        "session_id": flow.id,
        "host": request.host,
        "url": request.url,
        "method": request.method,
        "request_content_type": _content_type(request),
        "request_body_length": _body_size(request),
        "status_code": response.status_code if response else None,
        "response_body_length": _body_size(response) if response else 0,
        "response_content_type": _content_type(response) if response else "",
    }


def _headers_to_dict(headers) -> dict:
    return {key: value for key, value in headers.items()}


def _cookies_to_dict(cookies) -> dict:
    """Cookie name -> value. Response cookies are (value, attributes) tuples."""
    result = {}
    for name, value in cookies.items():
        if isinstance(value, tuple):
            value = value[0]
        result[name] = value
    return result


def _body_text(message, limit: int) -> tuple[str | None, bool]:
    """Decoded body plus a truncated flag."""
    content = message.get_content(strict=False)
    if content is None:
        return None, False
    text = content.decode("utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit], True
    return text, False


def _time_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="milliseconds")


# ── flow access (runs on the proxy event loop) ──


def _all_flows(master) -> list[http.HTTPFlow]:
    flows = [f for f in list(master.view) if isinstance(f, http.HTTPFlow)]
    flows.sort(key=_flow_start)
    return flows


def _matches(flow: http.HTTPFlow, host, url, method, begin_ts, end_ts) -> bool:
    request = flow.request
    if host and host.lower() not in request.host.lower():
        return False
    if url and url.lower() not in request.url.lower():
        return False
    if method and method.lower() != request.method.lower():
        return False
    start = _flow_start(flow)
    if begin_ts is not None and start < begin_ts:
        return False
    if end_ts is not None and start > end_ts:
        return False
    return True


async def _query_sessions(master, args: dict) -> dict:
    host = (args.get("host") or "").strip() or None
    url = (args.get("url") or "").strip() or None
    method = (args.get("method") or "").strip() or None
    begin_ts = _parse_time(args.get("begin_time"))
    end_ts = _parse_time(args.get("end_time"))
    begin_id = _as_int(args.get("begin_id"), None)
    end_id = _as_int(args.get("end_id"), None)
    page_no = _as_int(args.get("page_no"), DEFAULT_PAGE_NO)
    page_size = _as_int(args.get("page_size"), DEFAULT_PAGE_SIZE)

    if page_no < 1:
        page_no = 1
    if page_size < 1:
        page_size = DEFAULT_PAGE_SIZE

    flows = _all_flows(master)

    matched = []
    for index, flow in enumerate(flows, start=1):
        if begin_id is not None and index < begin_id:
            continue
        if end_id is not None and index > end_id:
            continue
        if _matches(flow, host, url, method, begin_ts, end_ts):
            matched.append(_summary(index, flow))

    total_count = len(matched)
    total_page = (total_count + page_size - 1) // page_size
    start = (page_no - 1) * page_size
    return {
        "current_page": page_no,
        "total_page": total_page,
        "total_count": total_count,
        "page_size": page_size,
        "sessions": matched[start:start + page_size],
    }


async def _get_session(master, args: dict) -> dict:
    session_id = str(args.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    limit = _as_int(args.get("body_limit"), MAX_BODY_CHARS)
    specs = _normalize_fields(args.get("fields"))

    flows = _all_flows(master)
    for index, flow in enumerate(flows, start=1):
        if flow.id == session_id:
            return _select_fields(_session_detail(index, flow, limit), specs)

    raise ValueError(f"session not found: {session_id}")


def _session_detail(index: int, flow: http.HTTPFlow, limit: int) -> dict:
    """One session, normalized into request / response / info sections."""
    request = flow.request
    response = flow.response

    request_body, request_truncated = _body_text(request, limit)
    if response is not None:
        response_body, response_truncated = _body_text(response, limit)
    else:
        response_body, response_truncated = None, False

    start_ts = _flow_start(flow)
    resp_start = response.timestamp_start if response else None
    resp_end = response.timestamp_end if response else None
    end_ts = resp_end or resp_start

    return {
        "session_id": flow.id,
        "request": {
            "method": request.method,
            "url": request.url,
            "host": request.host,
            "scheme": request.scheme,
            "authority": request.authority,
            "path": request.path,
            "query": dict(request.query),
            "http_version": request.http_version,
            "content_type": _content_type(request),
            "body_length": _body_size(request),
            "body": request_body,
            "body_truncated": request_truncated,
            "headers": _headers_to_dict(request.headers),
            "cookies": _cookies_to_dict(request.cookies),
        },
        "response": {
            "status_code": response.status_code if response else None,
            "reason": response.reason if response else None,
            "http_version": response.http_version if response else None,
            "content_type": _content_type(response) if response else "",
            "body_length": _body_size(response) if response else 0,
            "body": response_body,
            "body_truncated": response_truncated,
            "headers": _headers_to_dict(response.headers) if response else {},
            "cookies": _cookies_to_dict(response.cookies) if response else {},
        },
        "info": {
            "session_index": index,
            "message": f"Request Failed: {flow.error.msg}" if flow.error else "Request OK",
            "type": flow.type,
            "client_request_time": _time_iso(start_ts),
            "server_response_time": _time_iso(resp_start),
            "request_end_time": _time_iso(resp_end),
            "total_duration_ms": (
                int((end_ts - start_ts) * 1000) if end_ts is not None else None
            ),
            "intercepted": bool(flow.intercepted),
            "marked": bool(getattr(flow, "marked", False)),
            "comment": flow.comment or "",
            "client_address": _peer(flow.client_conn),
            "server_address": _peer(flow.server_conn),
            "metadata": {
                key: value
                for key, value in (flow.metadata or {}).items()
                if not key.startswith("_")
            },
        },
    }


def _normalize_fields(value) -> list[str]:
    """Accept '*', 'request.host,response.body' or an array of the same."""
    if value is None:
        return ["*"]
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, (list, tuple)):
        raw = []
        for entry in value:
            raw.extend(str(entry).split(","))
    else:
        raise ValueError("fields must be a string or an array of strings")
    specs = [part.strip() for part in raw if part.strip()]
    return specs or ["*"]


def _select_fields(data: dict, specs: list[str]) -> dict:
    """Keep only the requested parts, preserving the section order."""
    if "*" in specs:
        return data

    valid = set()
    for spec in specs:
        if spec in data:
            valid.add(spec)
        elif "." in spec:
            section, _, key = spec.partition(".")
            values = data.get(section)
            if isinstance(values, dict) and (key == "*" or key in values):
                valid.add(spec)
    if not valid:
        raise ValueError(
            f"no valid fields: {', '.join(specs)}. Use '*' for everything, a "
            "section name (request / response / info), or a dotted path such "
            "as request.host or response.body."
        )

    selected = {}
    for key, values in data.items():
        if isinstance(values, dict):
            sub = {s.split(".", 1)[1] for s in valid if s.startswith(key + ".")}
            if key in valid or "*" in sub:
                selected[key] = values
            elif sub:
                selected[key] = {k: v for k, v in values.items() if k in sub}
        elif key in valid:
            selected[key] = values
    return selected


def _peer(conn) -> str | None:
    address = getattr(conn, "peername", None) or getattr(conn, "address", None)
    if not address:
        return None
    return f"{address[0]}:{address[1]}"


def _apply_headers(request, headers) -> None:
    if not headers:
        return
    items = []
    if isinstance(headers, dict):
        items = list(headers.items())
    elif isinstance(headers, list):
        for entry in headers:
            if isinstance(entry, dict):
                items.append((entry.get("name", ""), entry.get("value", "")))
            elif isinstance(entry, str) and ":" in entry:
                name, value = entry.split(":", 1)
                items.append((name.strip(), value.strip()))
    for name, value in items:
        if name:
            request.headers[str(name)] = str(value)


def _build_flow(args: dict) -> http.HTTPFlow:
    raw = args.get("raw")
    if raw:
        # Reuse the exact parser used by the New Session dialog so that both
        # entry points accept the same raw format.
        from mitmproxy.tools.mitmgui.main_window import NewSessionDialog

        return NewSessionDialog._parse_raw_to_flow(str(raw))

    method = (args.get("method") or "").strip()
    url = (args.get("url") or "").strip()
    if not method or not url:
        raise ValueError("provide either 'raw' or both 'method' and 'url'")

    body = args.get("body")
    content = body.encode("utf-8") if isinstance(body, str) else b""

    request = http.Request.make(method.upper(), url, content, http.Headers())
    _apply_headers(request, args.get("headers"))
    if not content:
        # Request.make() always sets Content-Length; drop it for a bodyless request.
        request.headers.pop("content-length", None)

    client_conn = Client(peername=("127.0.0.1", 0), sockname=("127.0.0.1", 0))
    server_conn = Server(address=(request.host, request.port))
    flow = http.HTTPFlow(client_conn, server_conn)
    flow.request = request
    return flow


async def _send_flow(master, flow: http.HTTPFlow) -> None:
    flow.metadata["_mcp"] = True  # shown as "MCP" in the session list Info column
    master.view.add([flow])
    master.replay_flow(flow)


# ── MCP server ──


class McpServer:
    """MCP Streamable HTTP server exposing the captured sessions."""

    def __init__(self, master):
        self._master = master
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started_at: str | None = None
        self._request_count = 0
        self._error: str | None = None
        self._session_id: str | None = None

    # ── lifecycle ──

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    @property
    def error(self) -> str | None:
        return self._error

    def start(self) -> bool:
        """Bind the listening socket. Returns True on success."""
        with self._lock:
            if self._httpd is not None:
                return True
            try:
                httpd = ThreadingHTTPServer((MCP_HOST, MCP_PORT), _McpRequestHandler)
            except OSError as e:
                self._error = f"Cannot listen on {MCP_HOST}:{MCP_PORT} - {e}"
                return False
            httpd.daemon_threads = True
            httpd.mcp_server = self
            self._httpd = httpd
            self._error = None
            self._request_count = 0
            self._started_at = datetime.datetime.now().isoformat(
                sep=" ", timespec="seconds"
            )
            self._thread = threading.Thread(
                target=httpd.serve_forever, name="mitmgui-mcp", daemon=True
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            httpd, self._httpd = self._httpd, None
            thread = self._thread
            self._thread = None
            self._started_at = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)

    def status(self) -> dict:
        return {
            "running": self.is_running,
            "url": MCP_URL,
            "host": MCP_HOST,
            "port": MCP_PORT,
            "path": MCP_PATH,
            "transport": "streamable-http",
            "tools": [t["name"] for t in TOOLS],
            "started_at": self._started_at,
            "request_count": self._request_count,
            "error": self._error,
        }

    @staticmethod
    def client_config() -> str:
        return json.dumps(
            {"mcpServers": {SERVER_NAME: {"url": MCP_URL}}}, indent=2
        )

    def _count_request(self) -> None:
        with self._lock:
            self._request_count += 1

    # ── tool dispatch ──

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name == "get_sessions":
            coro = _query_sessions(self._master, arguments)
        elif name == "get_session":
            coro = _get_session(self._master, arguments)
        elif name == "new_session":
            return self._new_session(arguments)
        else:
            raise ValueError(f"unknown tool: {name}")
        return self._run(coro)

    def _new_session(self, arguments: dict) -> dict:
        flow = _build_flow(arguments)
        self._run(_send_flow(self._master, flow))
        return {
            "session_id": flow.id,
            "url": flow.request.url,
            "method": flow.request.method,
        }

    def _run(self, coro):
        """Run a coroutine on the proxy event loop and wait for the result."""
        loop = getattr(self._master, "_loop", None)
        if loop is None or not loop.is_running():
            raise RuntimeError("MitmGUI proxy is not running")
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=30)

    # ── JSON-RPC ──

    def handle_message(self, message, session_id: str | None):
        """Handle one JSON-RPC message. Returns (response|None, session_id)."""
        if not isinstance(message, dict):
            return _error(None, -32600, "Invalid Request"), session_id

        mid = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            if mid is None:
                return None, session_id
            return _error(mid, -32600, "Invalid Request"), session_id

        # Notifications carry no id and never get a response.
        if method == "initialize":
            params = message.get("params") or {}
            requested = params.get("protocolVersion")
            version = (
                requested
                if requested in SUPPORTED_PROTOCOL_VERSIONS
                else DEFAULT_PROTOCOL_VERSION
            )
            session_id = session_id or uuid.uuid4().hex
            return (
                _result(mid, {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": (
                        "MitmGUI session tools: use get_sessions to browse "
                        "captured traffic, get_session for the full details of "
                        "one session, and new_session to send a request."
                    ),
                }),
                session_id,
            )

        if method.startswith("notifications/"):
            return None, session_id

        if method == "ping":
            return _result(mid, {}), session_id

        if method == "tools/list":
            return _result(mid, {"tools": TOOLS}), session_id

        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or name not in {t["name"] for t in TOOLS}:
                return (
                    _error(mid, -32602, f"Unknown tool: {name!r}"),
                    session_id,
                )
            try:
                data = self.call_tool(name, arguments)
            except Exception as e:
                return (
                    _result(mid, {
                        "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                        "isError": True,
                    }),
                    session_id,
                )
            return (
                _result(mid, {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(data, ensure_ascii=False, indent=2),
                    }],
                    "isError": False,
                }),
                session_id,
            )

        if mid is None:
            return None, session_id
        return _error(mid, -32601, f"Method not found: {method}"), session_id


class _McpRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MitmGUI-MCP/" + SERVER_VERSION
    sys_version = ""

    @property
    def _mcp(self) -> McpServer:
        return self.server.mcp_server

    def log_message(self, fmt, *args):  # silence the default stderr logging
        pass

    # ── HTTP verbs ──

    def do_POST(self) -> None:
        if self.path.split("?")[0] != MCP_PATH:
            self._send_json(404, {"error": "not found"})
            return
        if self._origin_rejected():
            return

        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""
        try:
            message = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, _error(None, -32700, "Parse error"))
            return

        self._mcp._count_request()
        session_id = self.headers.get("mcp-session-id")

        messages = message if isinstance(message, list) else [message]
        responses = []
        for item in messages:
            try:
                response, session_id = self._mcp.handle_message(item, session_id)
            except Exception as e:
                response = _error(
                    item.get("id") if isinstance(item, dict) else None,
                    -32603,
                    f"{type(e).__name__}: {e}",
                )
            if response is not None:
                responses.append(response)

        if not responses:
            # Only notifications: acknowledge without a body.
            self._send_json(202, None, session_id)
            return

        payload = responses if isinstance(message, list) else responses[0]
        self._send_json(200, payload, session_id)

    def do_GET(self) -> None:
        # The server never pushes unsolicited messages, so no SSE stream.
        self._send_json(
            405, {"error": "use POST for MCP requests"}, extra={"Allow": "POST, DELETE"}
        )

    def do_DELETE(self) -> None:
        if self.path.split("?")[0] != MCP_PATH:
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(204, None)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "POST, GET, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── helpers ──

    def _origin_rejected(self) -> bool:
        """Reject browser requests from foreign origins (DNS rebinding)."""
        origin = self.headers.get("origin")
        if not origin:
            return False
        allowed = (
            f"http://{MCP_HOST}:{MCP_PORT}",
            f"http://localhost:{MCP_PORT}",
        )
        if origin.rstrip("/") in allowed:
            return False
        self._send_json(403, {"error": "origin not allowed"})
        return True

    def _send_json(self, code: int, payload, session_id: str | None = None,
                   extra: dict | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        if code not in (204, 304):
            self.send_header("Content-Length", str(len(body)))
        if session_id:
            self.send_header("Mcp-Session-Id", session_id)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)
