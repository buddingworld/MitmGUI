"""WebSocket viewer window for mitmgui.

Lists every WebSocket connection mitmproxy is tracking in a chat-style session
list. Right-clicking a session allows inspecting the handshake (``Base``),
watching and extending the exchanged messages (``View``), disconnecting the
connection (``Disconnect``) or dropping it from this list (``Remove``).
"""

import time

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Avatar background colors, picked per host so a session keeps its color.
_AVATAR_COLORS = (
    "#00838F",
    "#5E35B1",
    "#EF6C00",
    "#2E7D32",
    "#AD1457",
    "#0277BD",
    "#6D4C41",
)

# Backslash escapes accepted in the manual send boxes.
_ESCAPES = {
    "0": 0x00,
    "b": 0x08,
    "f": 0x0C,
    "n": 0x0A,
    "r": 0x0D,
    "t": 0x09,
    "\\": 0x5C,
    "\"": 0x22,
    "'": 0x27,
    "/": 0x2F,
}

_HEX_DIGITS = set("0123456789abcdefABCDEF")


def decode_escapes(text: str) -> bytes:
    r"""Decode a manually typed payload into bytes.

    Follows the JSON style escapes so that invisible characters can be sent:
    ``\x23`` for ``#``, ``\u0027`` for a single quote, plus the usual ``\n``,
    ``\r``, ``\t``, ``\0``, ``\b``, ``\f``, ``\\``, ``\"``, ``\'`` and ``\/``.
    Anything else after a backslash is kept verbatim.
    """
    out = bytearray()
    i = 0
    size = len(text)
    while i < size:
        ch = text[i]
        if ch != "\\" or i + 1 >= size:
            out += ch.encode("utf-8")
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "x" and i + 3 < size and set(text[i + 2 : i + 4]) <= _HEX_DIGITS:
            out.append(int(text[i + 2 : i + 4], 16))
            i += 4
            continue
        if nxt == "u" and i + 5 < size and set(text[i + 2 : i + 6]) <= _HEX_DIGITS:
            out += chr(int(text[i + 2 : i + 6], 16)).encode("utf-8")
            i += 6
            continue
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
            continue
        out += nxt.encode("utf-8")
        i += 2
    return bytes(out)


def _render(content: bytes, is_text: bool) -> str:
    """Render a message body for display, escaping invisible characters."""
    if is_text:
        return "".join(
            ch if ch.isprintable() else f"\\x{ord(ch):02x}"
            for ch in content.decode("utf-8", "replace")
        )
    return "".join(
        chr(b) if 0x20 <= b < 0x7F else f"\\x{b:02x}" for b in content
    )


def _looks_like_text(data: bytes) -> bool:
    """True if the payload can be sent as a WebSocket TEXT frame."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _fmt_time(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def _session_last_time(flow) -> str:
    """Timestamp shown on the right of a session row (last message or close)."""
    data = flow.websocket
    if data is None:
        return ""
    if data.timestamp_end:
        return _fmt_time(data.timestamp_end)
    if data.messages:
        return _fmt_time(data.messages[-1].timestamp)
    return ""


def _session_title(flow, max_chars: int = 0) -> str:
    """Host (plus non-default port) and path of the WebSocket handshake.

    With ``max_chars`` set, anything beyond that many characters is replaced
    with an ellipsis (used for window titles and session list rows).
    """
    request = flow.request
    host = request.host or "?"
    if request.port not in (80, 443):
        host = f"{host}:{request.port}"
    path = request.path or "/"
    title = host if path == "/" else f"{host}{path}"
    if max_chars and len(title) > max_chars:
        title = title[:max_chars] + "…"
    return title


def _session_preview(flow) -> str:
    """One-line preview of the most recent message of a session."""
    data = flow.websocket
    if data is None:
        return ""
    prefix = "" if flow.live else "[closed] "
    if not data.messages:
        return f"{prefix}Handshake only"
    message = data.messages[-1]
    arrow = "→" if message.from_client else "←"
    text = _render(message.content, message.is_text)
    if len(text) > 56:
        text = text[:53] + "..."
    return f"{prefix}{arrow} {text}"


def _avatar_text(flow) -> str:
    host = flow.request.host or "?"
    return host[0].upper()


def _avatar_color(flow) -> str:
    host = flow.request.host or "?"
    return _AVATAR_COLORS[sum(host.encode("utf-8")) % len(_AVATAR_COLORS)]


def _ws_icon():
    # Imported lazily: main_window imports this module at import time.
    from mitmproxy.tools.mitmgui.main_window import _make_icon

    return _make_icon("websocket", "#00838F")


class _SessionRow(QWidget):
    """Chat-contact style row: avatar, session title, preview and last time."""

    def __init__(self, flow, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        avatar = QLabel(_avatar_text(flow))
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {_avatar_color(flow)}; color: white;"
            " border-radius: 18px; font-weight: bold;"
        )
        layout.addWidget(avatar)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        title_font = self.title.font()
        title_font.setBold(True)
        self.title.setFont(title_font)
        column.addWidget(self.title)

        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setStyleSheet("color: rgba(128, 128, 128, 0.95);")
        column.addWidget(self.preview)

        layout.addLayout(column, 1)

        self.time = QLabel()
        self.time.setTextFormat(Qt.TextFormat.PlainText)
        self.time.setStyleSheet("color: rgba(128, 128, 128, 0.95);")
        self.time.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self.time)

        self.update_flow(flow)

    def update_flow(self, flow) -> None:
        self.title.setText(_session_title(flow, max_chars=80))
        self.preview.setText(_session_preview(flow))
        self.time.setText(_session_last_time(flow))


class WebSocketWindow(QDialog):
    """Chat-style list of every WebSocket session mitmproxy has seen.

    Sessions are polled from the proxy view, so connections that were already
    established before the window was opened show up as well.
    """

    REFRESH_MS = 400

    def __init__(self, master, parent=None):
        super().__init__(parent)
        self._master = master
        self._flows: dict[str, object] = {}
        self._rows: dict[str, _SessionRow] = {}
        self._items: dict[str, QListWidgetItem] = {}
        self._removed: set[str] = set()  # sessions dropped via "Remove"
        self._views: list = []  # keep child windows alive

        self.setWindowTitle("WebSocket Sessions")
        self.setWindowIcon(_ws_icon())
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        header = QLabel("WebSocket Sessions")
        header_font = header.font()
        header_font.setPointSize(header_font.pointSize() + 3)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, 1)

        self._status = QLabel("No WebSocket sessions captured yet.")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setStyleSheet("color: rgba(128, 128, 128, 0.95);")
        layout.addWidget(self._status)

        self._timer = QTimer(self)
        self._timer.setInterval(self.REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    # ── session list ──

    def _refresh(self) -> None:
        """Sync the list with the WebSocket flows the proxy is tracking."""
        try:
            flows = [
                f
                for f in self._master.view._store.values()
                if getattr(f, "websocket", None) is not None
            ]
        except RuntimeError:
            return  # the store changed while iterating; retry on the next tick

        seen: set[str] = set()
        for flow in flows:
            fid = str(flow.id)
            if fid in self._removed:
                continue
            seen.add(fid)
            row = self._rows.get(fid)
            if row is None:
                self._add_row(flow, fid)
            else:
                row.update_flow(flow)

        # Forget sessions the proxy no longer keeps (e.g. list cleared).
        for fid in list(self._rows):
            if fid not in seen:
                self._remove_row(fid)

        count = len(self._rows)
        if count:
            self._status.setText(
                f"{count} session(s) - double-click to view the chat, "
                "right-click for more actions."
            )
        else:
            self._status.setText("No WebSocket sessions captured yet.")

    def _add_row(self, flow, fid: str) -> None:
        row = _SessionRow(flow)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, fid)
        item.setSizeHint(QSize(0, max(52, row.sizeHint().height())))
        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        self._flows[fid] = flow
        self._rows[fid] = row
        self._items[fid] = item

    def _remove_row(self, fid: str) -> None:
        item = self._items.pop(fid, None)
        self._rows.pop(fid, None)
        self._flows.pop(fid, None)
        if item is not None:
            self._list.takeItem(self._list.row(item))

    def _flow_at(self, item: QListWidgetItem | None):
        if item is None:
            return None
        return self._flows.get(item.data(Qt.ItemDataRole.UserRole))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        flow = self._flow_at(item)
        if flow is not None:
            self._open_view(flow)

    # ── right-click menu ──

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        flow = self._flow_at(item)
        if flow is None:
            return
        self._list.setCurrentItem(item)

        menu = QMenu(self)
        base_action = menu.addAction("Base")
        base_action.triggered.connect(lambda _=False, f=flow: self._open_base(f))
        view_action = menu.addAction("View")
        view_action.triggered.connect(lambda _=False, f=flow: self._open_view(f))
        menu.addSeparator()
        disconnect_action = menu.addAction("Disconnect")
        disconnect_action.setEnabled(bool(flow.live))
        disconnect_action.triggered.connect(
            lambda _=False, f=flow: self._disconnect(f)
        )
        remove_action = menu.addAction("Remove")
        remove_action.triggered.connect(
            lambda _=False, f=flow: self._remove_session(f)
        )
        menu.exec(self._list.mapToGlobal(pos))

    def _open_base(self, flow) -> None:
        """Show the session that established the WebSocket (request/response)."""
        # Imported lazily: main_window imports this module at import time.
        from mitmproxy.tools.mitmgui.main_window import FlowDetailDialog

        dialog = FlowDetailDialog(flow, self)
        dialog.setWindowTitle(
            f"WebSocket Handshake - {_session_title(flow, max_chars=80)}"
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_view(self, flow) -> None:
        """Chat-style message log with the manual send boxes."""
        dialog = _MessageViewDialog(self._master, flow, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._views.append(dialog)
        dialog.destroyed.connect(
            lambda _=None, d=dialog: d in self._views and self._views.remove(d)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _disconnect(self, flow) -> None:
        """Abort the WebSocket connection on the proxy event loop."""
        if not flow.live:
            self._status.setText("Connection is already closed.")
            return
        if self._master._loop is not None:
            self._master._loop.call_soon_threadsafe(
                self._master.proxyserver.abort_flow, flow
            )
            self._status.setText("Closing the connection...")

    def _remove_session(self, flow) -> None:
        """Drop the session from this window (the proxy keeps capturing it)."""
        fid = str(flow.id)
        self._removed.add(fid)
        self._remove_row(fid)
        self._status.setText("Session removed from this list.")


class _MessageViewDialog(QDialog):
    """Chat-style log of one WebSocket session with two manual send boxes.

    The upper box injects a message from the server to the browser, the lower
    one from the browser to the server. Payloads accept JSON style escapes
    (``\x23``, ``\u0027``, ``\n``, ...) so invisible characters can be sent.
    """

    REFRESH_MS = 400
    MAX_BUBBLE_WIDTH = 520
    #: messages taller than this many lines collapse behind a "Show more" link
    PREVIEW_LINES = 3

    def __init__(self, master, flow, parent=None):
        super().__init__(parent)
        self._master = master
        self._flow = flow
        self._shown = 0  # number of messages already rendered as bubbles

        self.setWindowTitle(f"WebSocket - {_session_title(flow, max_chars=80)}")
        self.setWindowIcon(_ws_icon())
        self.resize(760, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Session URL: a read-only, wrapping, selectable text box. A QLabel
        # either forces the window wide (an URL is one long "word" and sets
        # the minimum width) or cannot be copied from, so QTextEdit is used.
        self._header = QTextEdit()
        self._header.setReadOnly(True)
        self._header.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        layout.addWidget(self._header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._bubbles = QVBoxLayout(container)
        self._bubbles.setContentsMargins(6, 6, 6, 6)
        self._bubbles.setSpacing(8)
        self._bubbles.addStretch(1)
        scroll.setWidget(container)
        self._scroll = scroll
        layout.addWidget(scroll, 1)

        layout.addWidget(self._build_send_row("Server → Browser", True))
        layout.addWidget(self._build_send_row("Browser → Server", False))

        self._status = QLabel("Ready.")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setStyleSheet("color: rgba(128, 128, 128, 0.95);")
        layout.addWidget(self._status)

        self._timer = QTimer(self)
        self._timer.setInterval(self.REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _build_send_row(self, caption: str, to_client: bool) -> QWidget:
        """One [line edit + send button] pair, target chosen by ``to_client``."""
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)

        label = QLabel(caption)
        label.setFixedWidth(130)

        edit = QLineEdit()
        edit.setFont(QFont("Consolas", 10))
        edit.setPlaceholderText(
            r"Payload, e.g. {\"type\":\"ping\"}\x23  (\xNN and \uNNNN are decoded)"
        )

        send = QPushButton("Send")
        send.clicked.connect(lambda: self._send(to_client, edit))
        edit.returnPressed.connect(lambda: self._send(to_client, edit))

        line.addWidget(label)
        line.addWidget(edit, 1)
        line.addWidget(send)
        return row

    # ── message log ──

    def _refresh(self) -> None:
        data = self._flow.websocket
        messages = list(data.messages) if data is not None else []
        self._update_header()

        if len(messages) < self._shown:
            self._rebuild(messages)
            return
        if len(messages) == self._shown:
            return

        at_bottom = self._at_bottom()
        for message in messages[self._shown :]:
            self._add_bubble(message)
        self._shown = len(messages)
        if at_bottom:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _rebuild(self, messages: list) -> None:
        while self._bubbles.count() > 1:  # keep the trailing stretch
            item = self._bubbles.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._shown = 0
        for message in messages:
            self._add_bubble(message)
        self._shown = len(messages)

    def _add_bubble(self, message) -> None:
        """Append one chat bubble: right for browser→server, left for server."""
        from_client = message.from_client
        direction = "Browser → Server" if from_client else "Server → Browser"
        kind = "TEXT" if message.is_text else "BINARY"
        header = (
            f"{_fmt_time(message.timestamp)} · {direction} · {kind}"
            f" · {len(message.content)} B"
        )
        if message.injected:
            header += " · injected"
        if message.dropped:
            header += " · dropped"

        body = _render(message.content, message.is_text)

        bubble = QWidget()
        bubble.setMaximumWidth(self.MAX_BUBBLE_WIDTH)
        column = QVBoxLayout(bubble)
        column.setContentsMargins(10, 7, 10, 7)
        column.setSpacing(3)
        shade = "rgba(0, 122, 255, 0.16)" if from_client else "rgba(128, 128, 128, 0.18)"
        bubble.setStyleSheet(f"background: {shade}; border-radius: 10px;")

        caption = QLabel(header)
        caption.setTextFormat(Qt.TextFormat.PlainText)
        caption.setStyleSheet(
            "background: transparent; color: rgba(128, 128, 128, 0.95);"
            " font-size: 10px;"
        )
        column.addWidget(caption)

        content = QLabel(body or "(empty)")
        content.setTextFormat(Qt.TextFormat.PlainText)
        content.setFont(QFont("Consolas", 10))
        content.setWordWrap(True)
        content.setMaximumWidth(self.MAX_BUBBLE_WIDTH - 20)
        content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        content.setStyleSheet("background: transparent;")
        column.addWidget(content)

        width = self.MAX_BUBBLE_WIDTH - 20
        preview_h = content.fontMetrics().lineSpacing() * self.PREVIEW_LINES
        if content.heightForWidth(width) > preview_h + 2:
            # Trim the preview until it fits PREVIEW_LINES lines (wide glyphs
            # such as CJK wrap differently than a plain char estimate), clamp
            # the label height, and offer a tail link that restores the full
            # selectable text.
            char_w = content.fontMetrics().horizontalAdvance("0") or 1
            preview = body[: width // char_w * self.PREVIEW_LINES]
            while preview:
                content.setText(preview.rstrip() + "…")
                if content.heightForWidth(width) <= preview_h + 2:
                    break
                preview = preview[: len(preview) * 9 // 10]
            else:
                content.setText("…")
            content.setMaximumHeight(preview_h)
            more = QLabel('<a href="#more">Show more</a>')
            more.setTextFormat(Qt.TextFormat.RichText)
            more.setTextInteractionFlags(
                Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            more.setStyleSheet("background: transparent; font-size: 10px;")
            more.linkActivated.connect(
                lambda _=None, m=message, c=content, w=more:
                    self._expand_bubble(m, c, w)
            )
            column.addWidget(more)

        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        if from_client:
            line.addStretch(1)
            line.addWidget(bubble)
        else:
            line.addWidget(bubble)
            line.addStretch(1)
        self._bubbles.insertWidget(self._bubbles.count() - 1, row)

    def _expand_bubble(self, message, content: QLabel, more: QLabel) -> None:
        """Replace a collapsed 3-line preview with the full message text."""
        content.setText(_render(message.content, message.is_text) or "(empty)")
        content.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX: undo the clamp
        more.deleteLater()

    def _update_header(self) -> None:
        data = self._flow.websocket
        if self._flow.live:
            text = f"{_session_title(self._flow)} · open"
        else:
            text = f"{_session_title(self._flow)} · closed"
            if data is not None and data.close_code is not None:
                sender = "client" if data.closed_by_client else "server"
                reason = f" {data.close_reason}" if data.close_reason else ""
                text += f" (by {sender}, {data.close_code}{reason})"
        self._header.setPlainText(text)
        # Auto-fit the box to the wrapped URL, capped at ~5 lines; longer
        # URLs get a vertical scrollbar instead of eating the window.
        fm = self._header.fontMetrics()
        doc_h = int(self._header.document().size().height())
        self._header.setFixedHeight(min(doc_h + 10, fm.lineSpacing() * 5 + 10))

    # ── manual sending ──

    def _send(self, to_client: bool, edit: QLineEdit) -> None:
        text = edit.text()
        if not text:
            self._set_status("Type a payload first.")
            return
        if not self._flow.live:
            self._set_status("Connection is closed - cannot send.")
            return
        if self._master._loop is None:
            self._set_status("Proxy is not running.")
            return

        payload = decode_escapes(text)
        is_text = _looks_like_text(payload)
        self._master._loop.call_soon_threadsafe(
            self._master.proxyserver.inject_websocket,
            self._flow,
            to_client,
            payload,
            is_text,
        )
        edit.clear()
        self._set_status(
            f"Sent {len(payload)} byte(s) as {'TEXT' if is_text else 'BINARY'} "
            f"{'to the browser' if to_client else 'to the server'}."
        )
        QTimer.singleShot(self.REFRESH_MS, self._refresh)

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    # ── scrolling ──

    def _at_bottom(self) -> bool:
        bar = self._scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())