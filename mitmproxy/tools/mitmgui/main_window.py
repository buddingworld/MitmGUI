import base64
import binascii
import ctypes
import fnmatch
import json as json_mod
import math
import os
import random
import re
import socket
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.dom.minidom
import zipfile
from collections.abc import Sequence
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QThread, pyqtSignal, QObject, QByteArray, QSortFilterProxyModel, QRegularExpression
from PyQt6.QtGui import QAction, QActionGroup, QBrush, QColor, QCursor, QFont, QFontMetrics, QIcon, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.Qsci import QsciScintilla, QsciScintillaBase

from mitmproxy import http, options
from mitmproxy.tools import cmdline
from mitmproxy.tools.mitmgui import themes
from mitmproxy.tools.mitmgui.config import AppConfig
from mitmproxy.tools.mitmgui.master import MitmGuiMaster
from mitmproxy.tools.mitmgui.session_list import SessionTableModel

ENCODINGS = ["utf-8", "gbk", "latin-1"]
DEFAULT_ENCODING = "utf-8"

# Themes with a dark chrome; the window frame adapts its colors accordingly
_DARK_THEMES = {"android", "pyqt_dark"}


def _glob_match(value: str, pattern: str, case_sensitive: bool) -> bool:
    """Match ``value`` against ``pattern`` supporting ``*`` / ``?`` wildcards
    (e.g. ``*.baidu.com``, ``*.baidu*.com``).  A pattern without wildcards
    behaves exactly like an equality test, so existing exact rules keep
    working unchanged."""
    if case_sensitive:
        return fnmatch.fnmatchcase(value, pattern)
    return fnmatch.fnmatchcase(value.lower(), pattern.lower())


def _make_icon(icon_type: str, bg_color: str, size: int = 64) -> QIcon:
    """Generate a minimalist shape icon on a colored background.

    icon_type: proxy, detail, filter, breakpoint, code, hosts, replace, options
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = 3  # margin

    # Background rounded rect
    p.setBrush(QColor(bg_color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(m, m, size - 2 * m, size - 2 * m, 12, 12)

    # Foreground pen for line-based shapes
    pen = QPen(QColor("white"))
    pen.setWidthF(2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    cx = cy = int(size / 2)

    if icon_type == "proxy":
        # Two opposing horizontal arrows (data transfer)
        # Top arrow → right
        p.drawLine(10, cy - 7, 54, cy - 7)
        p.drawLine(47, cy - 13, 54, cy - 7)
        p.drawLine(47, cy - 1, 54, cy - 7)
        # Bottom arrow ← left
        p.drawLine(54, cy + 7, 10, cy + 7)
        p.drawLine(17, cy + 1, 10, cy + 7)
        p.drawLine(17, cy + 13, 10, cy + 7)

    elif icon_type == "detail":
        # Document with folded corner and text lines
        p.drawRoundedRect(12, 8, 40, 48, 3, 3)
        # Fold corner
        p.drawLine(40, 8, 40, 22)
        p.drawLine(40, 22, 52, 22)
        path = QPainterPath()
        path.moveTo(40, 8)
        path.lineTo(40, 22)
        path.lineTo(52, 22)
        path.closeSubpath()
        p.fillPath(path, QColor("white"))
        # Text lines
        p.drawLine(20, 28, 44, 28)
        p.drawLine(20, 36, 44, 36)
        p.drawLine(20, 44, 34, 44)

    elif icon_type == "filter":
        # Funnel shape
        p.drawLine(16, 12, 48, 12)
        p.drawLine(48, 12, 40, 30)
        p.drawLine(40, 30, 40, 52)
        p.drawLine(40, 52, 24, 52)
        p.drawLine(24, 52, 24, 30)
        p.drawLine(24, 30, 16, 12)

    elif icon_type == "breakpoint":
        # Two vertical bars (pause)
        p.setBrush(QColor("white"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(18, 14, 9, 36, 3, 3)
        p.drawRoundedRect(37, 14, 9, 36, 3, 3)

    elif icon_type == "code":
        # </> angle brackets with slash
        pen2 = QPen(QColor("white"))
        pen2.setWidthF(2.5)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen2.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen2)
        # <
        p.drawLine(30, 18, 17, cy)
        p.drawLine(17, cy, 30, 46)
        # /
        p.drawLine(33, 46, 31, 18)
        # >
        p.drawLine(34, 18, 47, cy)
        p.drawLine(47, cy, 34, 46)

    elif icon_type == "hosts":
        # Monitor / screen
        p.drawRoundedRect(10, 8, 44, 32, 3, 3)
        # Stand
        p.drawLine(cx, 40, cx, 54)
        p.drawLine(20, 54, 44, 54)

    elif icon_type == "replace":
        # Two circular arrows forming a swap/refresh loop
        pen2 = QPen(QColor("white"))
        pen2.setWidthF(2.2)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen2)
        # Top arc: left to right
        path = QPainterPath()
        path.moveTo(18, 34)
        path.cubicTo(22, 14, 42, 14, 46, 30)
        p.drawPath(path)
        # Arrowhead top
        p.drawLine(38, 22, 46, 30)
        p.drawLine(42, 20, 46, 30)
        # Bottom arc: right to left
        path = QPainterPath()
        path.moveTo(46, 30)
        path.cubicTo(42, 50, 22, 50, 18, 34)
        p.drawPath(path)
        # Arrowhead bottom
        p.drawLine(26, 42, 18, 34)
        p.drawLine(22, 44, 18, 34)

    elif icon_type == "options":
        # Gear / cog
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r_outer = 11
        p.drawEllipse(QPointF(cx, cy), r_outer, r_outer)
        p.drawEllipse(QPointF(cx, cy), 4, 4)
        for i in range(6):
            angle = i * 60
            rad = math.radians(angle)
            x1 = cx + r_outer * math.cos(rad)
            y1 = cy + r_outer * math.sin(rad)
            x2 = cx + (r_outer + 6) * math.cos(rad)
            y2 = cy + (r_outer + 6) * math.sin(rad)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    elif icon_type == "new_session":
        # Document with a + symbol (new/compose)
        p.drawRoundedRect(10, 6, 44, 52, 3, 3)
        # Fold corner
        p.drawLine(40, 6, 40, 16)
        p.drawLine(40, 16, 54, 16)
        path = QPainterPath()
        path.moveTo(40, 6)
        path.lineTo(40, 16)
        path.lineTo(54, 16)
        path.closeSubpath()
        p.fillPath(path, QColor("white"))
        # Plus sign centered on the document
        p.drawLine(cx, cy - 10, cx, cy + 10)
        p.drawLine(cx - 10, cy, cx + 10, cy)

    elif icon_type == "plugins":
        # Three stacked blocks (extension modules), the middle one offset
        p.setBrush(QColor("white"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(12, 10, 22, 16, 3, 3)
        p.drawRoundedRect(30, 24, 22, 16, 3, 3)
        p.drawRoundedRect(12, 38, 22, 16, 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawLine(22, 34, 22, 38)

    elif icon_type == "logs":
        # Clipboard with text lines
        p.drawRoundedRect(16, 8, 32, 48, 3, 3)
        p.drawLine(28, 8, 28, 13)
        p.drawLine(36, 8, 36, 13)
        p.drawLine(22, 20, 42, 20)
        p.drawLine(22, 28, 42, 28)
        p.drawLine(22, 36, 42, 36)

    else:
        # Fallback: plain letter
        p.setPen(QColor("white"))
        f = QFont("Segoe UI", int(size * 0.45), QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, icon_type[0].upper())

    p.end()
    return QIcon(pixmap)


def _decode_bytes(content: bytes | None, encoding: str = DEFAULT_ENCODING) -> str:
    if not content:
        return ""
    return content.decode(encoding, errors="replace").replace("\ufffd", "??")


def _try_format_json(content: bytes | None) -> str:
    if not content:
        return ""
    try:
        s = content.decode("utf-8", errors="replace").replace("\ufffd", "??")
        obj = json_mod.loads(s)
        return json_mod.dumps(obj, indent=2, ensure_ascii=False)
    except (json_mod.JSONDecodeError, UnicodeDecodeError):
        return s


def _try_format_xml(content: bytes | None) -> str:
    if not content:
        return ""
    try:
        s = content.decode("utf-8", errors="replace").replace("\ufffd", "??")
        dom = xml.dom.minidom.parseString(s)
        return dom.toprettyxml(indent="  ")
    except Exception:
        return s


def _format_hex(content: bytes | None) -> str:
    if not content:
        return ""
    lines = []
    for i in range(0, len(content), 16):
        chunk = content[i : i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hex_part:<48}  {ascii_part}")
    return "\n".join(lines)


def _format_headers(h: http.Headers, encoding: str = DEFAULT_ENCODING) -> str:
    lines = []
    for k, v in h.fields:
        k_dec = k.decode("utf-8", errors="replace").replace("\ufffd", "??") if isinstance(k, bytes) else str(k)
        v_dec = v.decode(encoding, errors="replace").replace("\ufffd", "??") if isinstance(v, bytes) else str(v)
        lines.append(f"{k_dec}: {v_dec}")
    return "\n".join(lines)


def _format_webforms(request: http.Request) -> str:
    from urllib.parse import parse_qs

    if not request.content:
        return "(empty body)"
    try:
        body = request.content.decode("utf-8", errors="replace").replace("\ufffd", "??")
        params = parse_qs(body, keep_blank_values=True)
        if not params:
            return "(no form fields)"
        return "\n".join(f"{k}: {', '.join(v)}" for k, v in params.items())
    except Exception:
        return body


def _raw_target_to_path(target: str) -> str:
    if target == "*":
        return target
    if "://" in target:
        authority_start = target.find("://") + 3
        path_start = len(target)
        for sep in "/?#":
            pos = target.find(sep, authority_start)
            if pos != -1:
                path_start = min(path_start, pos)
        path = target[path_start:]
        return path or "/"
    return target or "/"


def _format_request_raw(flow, encoding: str = DEFAULT_ENCODING) -> str:
    r = flow.request
    if not r:
        return ""
    # For hosts-mapped flows, use the original host_header so the Raw view
    # shows the original hostname, not the remapped connection target.
    original_host = getattr(flow, "_original_host", None)
    if original_host:
        request_url = f"{r.scheme}://{original_host}{r.path}"
    else:
        request_url = r.url
    lines = [f"{r.method} {request_url} {r.http_version}"]
    for k, v in r.headers.fields:
        k_dec = k.decode("utf-8", errors="replace").replace("\ufffd", "??") if isinstance(k, bytes) else str(k)
        v_dec = v.decode(encoding, errors="replace").replace("\ufffd", "??") if isinstance(v, bytes) else str(v)
        lines.append(f"{k_dec}: {v_dec}")
    lines.append("")
    try:
        body = r.content
    except ValueError:
        body = None
    if body:
        lines.append(_decode_bytes(body, encoding))
    result = "\n".join(lines)
    return result


def _format_response_raw(flow, encoding: str = DEFAULT_ENCODING) -> str:
    resp = flow.response
    if not resp:
        return "(waiting for response...)"
    lines = [f"{resp.http_version} {resp.status_code} {resp.reason}"]
    for k, v in resp.headers.fields:
        k_dec = k.decode("utf-8", errors="replace").replace("\ufffd", "??") if isinstance(k, bytes) else str(k)
        v_dec = v.decode(encoding, errors="replace").replace("\ufffd", "??") if isinstance(v, bytes) else str(v)
        lines.append(f"{k_dec}: {v_dec}")
    lines.append("")
    try:
        body = resp.content
    except ValueError:
        body = None
    if body:
        lines.append(_decode_bytes(body, encoding))
    result = "\n".join(lines)
    return result


class _SignalBridge(QObject):
    flow_added = pyqtSignal(object)
    flow_updated = pyqtSignal(object)


# ── Frameless window chrome ─────────────────────────────────────────────────
# The native title bar is hidden; menus, the window title and the min/max/close
# buttons live in a single strip (see _setup_menu_bar).  Dragging, edge resizing
# and the double-click maximize/restore are all driven by the Qt-level mouse
# handlers in _FramelessMenuBar/_TitleBar/MitmGuiMainWindow on every platform -
# Windows native hit-test constants for the frameless resize border.

if sys.platform == "win32":
    _WM_GETMINMAXINFO = 0x0024

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class _MONITORINFO(ctypes.Structure):
        # ctypes.wintypes.MONITORINFO is not available on Python 3.14
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class _MINMAXINFO(ctypes.Structure):
        _fields_ = [
            ("ptReserved", _POINT),
            ("ptMaxSize", _POINT),
            ("ptMaxPosition", _POINT),
            ("ptMinTrackSize", _POINT),
            ("ptMaxTrackSize", _POINT),
        ]

    class _MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    # DWM frameless window constants.
    _WM_NCCALCSIZE = 0x0083
    _WM_NCHITTEST = 0x0084
    _HTCLIENT = 1
    _HTLEFT = 10
    _HTRIGHT = 11
    _HTTOP = 12
    _HTTOPLEFT = 13
    _HTTOPRIGHT = 14
    _HTBOTTOM = 15
    _HTBOTTOMLEFT = 16
    _HTBOTTOMRIGHT = 17
    _GWL_STYLE = -16
    _WS_THICKFRAME = 0x00040000
    _WS_CAPTION = 0x00C00000  # WS_BORDER | WS_DLGFRAME
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOZORDER = 0x0004
    _SWP_FRAMECHANGED = 0x0020

_EDGE_CURSORS = {
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "w": Qt.CursorShape.SizeHorCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
}

# Fallback styling for the "Default" theme (no global stylesheet is applied).
_DEFAULT_TITLE_BAR_QSS = """
QWidget#titleBar {
    background: #F0F0F0;
    border-bottom: 1px solid #D5D5D5;
}
QMenuBar#mainMenuBar {
    border-bottom: none;
}
QLabel#titleLabel {
    color: #333333;
    background: transparent;
}
QToolButton#titleMinBtn, QToolButton#titleMaxBtn, QToolButton#titleCloseBtn {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #333333;
    min-width: 46px;
    max-width: 46px;
    padding: 0;
}
QToolButton#titleMinBtn:hover, QToolButton#titleMaxBtn:hover {
    background: rgba(0, 0, 0, 0.08);
    color: #000000;
}
QToolButton#titleCloseBtn:hover {
    background: #E81123;
    color: #FFFFFF;
}
"""


class _WindowButton(QToolButton):
    """A window control button (minimize / maximize / close)."""

    def __init__(self, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName(f"title{kind.capitalize()}Btn")  # titleMinBtn ...
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setFixedWidth(46)
        if kind == "min":
            self.setText("\u2500")  # ─
            self.setToolTip("Minimize")
        elif kind == "max":
            self.setText("\u25a2")  # ▢
            self.setToolTip("Maximize")
        else:  # close
            self.setText("\u2715")  # ✕
            self.setToolTip("Close")


class _FramelessMenuBar(QMenuBar):
    """QMenuBar whose empty areas drag / double-click maximize the window.

    Menu items keep their normal behaviour; only the blank strip behind them
    acts as a title bar (used on non-Windows platforms, and as a fallback)."""

    def __init__(self, window: "MitmGuiMainWindow", parent: QWidget | None = None):
        super().__init__(parent)
        self._window = window
        self.setMouseTracking(True)  # hover feedback for edge resizing

    def _is_empty_area(self, pos: QPoint) -> bool:
        return self.actionAt(pos) is None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            local_pos = self.mapTo(self._window, event.position().toPoint())
            if self._window._begin_edge_resize(local_pos, event.globalPosition().toPoint()):
                event.accept()
                return
            if self._is_empty_area(event.position().toPoint()) and not self._window.isMaximized():
                self._window._begin_window_drag(event.globalPosition().toPoint())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._window._resize_edge is not None:
            self._window._do_manual_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._window._continue_window_drag(event.globalPosition().toPoint())
            event.accept()
            return
        self._window._update_edge_cursor(self.mapTo(self._window, event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._window._end_edge_resize()
        self._window._end_window_drag()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # The menu bar is fully covered by its menu items (File/Edit/...), so
        # there is no real "empty strip" to double-click - toggle on the whole
        # bar.  Single clicks on items still open the menus as usual.  A
        # double-click exactly on a resize edge is left to edge resizing.
        local_pos = self.mapTo(self._window, event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and not self._window._edge_at(local_pos):
            self._window._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        # Right-click anywhere on the menu bar opens the window system menu
        # (Restore/Move/Size/Minimize/Maximize/Close), like a native title bar.
        self._window._show_window_system_menu(event.globalPos())
        event.accept()


class _TitleBar(QWidget):
    """Strip that hosts the menu bar, the window title and window controls.

    Clicks on the label / gaps that are not consumed by a child widget drag
    the window (double-click maximizes).  These handlers run on every platform;
    the window itself also implements Qt-level edge resizing."""

    def __init__(self, window: "MitmGuiMainWindow", parent: QWidget | None = None):
        super().__init__(parent)
        self._window = window
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)  # hover feedback for edge resizing

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            local_pos = self.mapTo(self._window, event.position().toPoint())
            if self._window._begin_edge_resize(local_pos, event.globalPosition().toPoint()):
                event.accept()
                return
            if not self._window.isMaximized():
                self._window._begin_window_drag(event.globalPosition().toPoint())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._window._resize_edge is not None:
            self._window._do_manual_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._window._continue_window_drag(event.globalPosition().toPoint())
            event.accept()
            return
        self._window._update_edge_cursor(self.mapTo(self._window, event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._window._end_edge_resize()
        self._window._end_window_drag()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # Double-click on a resize edge is left to edge resizing.
        local_pos = self.mapTo(self._window, event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and not self._window._edge_at(local_pos):
            self._window._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        # Right-click anywhere on the title strip (menus/label/controls) opens
        # the window system menu, like a native title bar.
        self._window._show_window_system_menu(event.globalPos())
        event.accept()


class _DashedHeaderView(QHeaderView):
    """QHeaderView that draws a 10%-opaque dashed separator line at each
    column boundary in the header row (black on light themes, white on dark
    themes).  Themed section background/padding etc. stay untouched."""

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None):
        super().__init__(orientation, parent)
        self._dark = False

    def set_dark(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self.viewport().update()

    def paintSection(self, painter: QPainter, rect, logicalIndex: int) -> None:
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex >= self.count() - 1:
            return  # no separator after the last column
        color = QColor(255, 255, 255, 26) if self._dark else QColor(0, 0, 0, 26)
        pen = QPen(color, 1.0, Qt.PenStyle.DashLine)
        painter.save()
        painter.setPen(pen)
        x = rect.right()  # pixel-perfect column boundary
        painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.restore()


class _FrameOverlay(QWidget):
    """Mouse-transparent overlay that draws a thin 1px grey line at the window
    edge.  The real drop shadow + outside frame border are rendered by DWM
    (see _enable_dwm_shadow), so this overlay only paints the visible border.
    It never intercepts mouse input, so the Qt edge-resize hit zones below it
    keep working unchanged."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._dark = False

    def set_dark(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self.update()

    def paintEvent(self, event) -> None:
        parent = self.parentWidget()
        if parent is None or parent.isMaximized():
            return  # no frame when maximized (window fills the screen)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # 1px grey border inside the client edge (mainstream 1px look).  The
        # real drop shadow is drawn by DWM outside the window, so this overlay
        # only paints the thin line.
        color = QColor(75, 77, 83) if self._dark else QColor(150, 152, 158)
        p.setPen(QPen(color, 1.0))
        p.drawRect(r)


class _ScintillaTextEdit(QsciScintilla):
    """QsciScintilla-based editor used by the Raw tab and the New Session
    dialog.

    Unlike QPlainTextEdit, QScintilla preserves the line endings that were
    loaded into it (CRLF stays CRLF, LF stays LF), so editing a raw HTTP
    message never rewrites the untouched line breaks of the original packet.
    """

    def __init__(self, inspector_panel: "InspectorPanel | None" = None):
        super().__init__()
        self._inspector = inspector_panel
        self.setReadOnly(True)
        self.setUtf8(True)
        # Word Wrap is user-configurable and persisted in the config file
        # (enabled by default).
        config = AppConfig()
        self.setWrapMode(
            QsciScintilla.WrapMode.WrapWord
            if config.raw_word_wrap
            else QsciScintilla.WrapMode.WrapNone
        )
        # Hide the Scintilla margin strip (no line numbers / fold markers),
        # which otherwise shows as a gray block on the left.
        for margin in range(5):
            self.setMarginWidth(margin, 0)
        # Placeholder text (QScintilla has no native placeholder widget).
        self._placeholder_label = QLabel(self.viewport())
        self._placeholder_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self._placeholder_label.setStyleSheet(
            "color: #9AA0A6; background: transparent; border: none; padding: 4px;"
        )
        self._placeholder_label.hide()
        self.textChanged.connect(self._update_placeholder)
        # Persist the zoom level (changed via Ctrl + mouse wheel) so the
        # editor re-opens with the user's preferred font size.
        self.SCN_ZOOM.connect(self._save_zoom)
        # Colour the editor area to match the current application theme.
        self.apply_theme(AppConfig().theme)

    def apply_theme(self, theme_id: str) -> None:
        """Colour and font the Scintilla editor area to follow the active
        theme.

        QScintilla paints its own background and does not pick up fonts from
        the application QSS, so both the colours and the font are applied
        programmatically here.
        """
        bg, fg, sel_bg, sel_fg = themes.EDITOR_COLORS.get(
            theme_id, themes.EDITOR_COLORS[themes.DEFAULT_THEME]
        )
        self.setPaper(QColor(bg))
        self.setColor(QColor(fg))
        self.setSelectionBackgroundColor(QColor(sel_bg))
        self.setSelectionForegroundColor(QColor(sel_fg))
        self.setCaretForegroundColor(QColor(fg))
        family, size = themes.THEME_FONTS.get(
            theme_id, themes.THEME_FONTS[themes.DEFAULT_THEME]
        )
        if size > 0:
            font = QFont(family)
            # The themed QSS also sets the QsciScintilla font and QSS wins
            # over setFont(), so this point size only matters as a fallback
            # when a theme's stylesheet does not override the font.
            font.setPointSize(size)
        else:
            font = QFont(QApplication.font())
        self.setFont(font)
        # Apply the persisted zoom level (absolute, so re-applying the theme
        # does not stack with the previous zoom).
        self.SendScintilla(
            QsciScintillaBase.SCI_SETZOOM, AppConfig().raw_font_zoom
        )

    # ── QPlainTextEdit-compatible API used by InspectorPanel ──

    def toPlainText(self) -> str:
        return self.text()

    def setPlainText(self, text: str) -> None:
        self.setText(text)

    def document(self):
        """Return self so existing callers can use
        ``document().isModified()`` / ``document().setModified(...)``."""
        return self

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder_label.setText(text)
        self._update_placeholder()

    def find_first(self, pattern: str, use_regex: bool) -> bool:
        """Search forward from the current cursor position; when the end of
        the document is reached, wrap around to the top (mirrors the previous
        QPlainTextEdit-based find behaviour)."""
        line, index = self.getCursorPosition()
        if self.findFirst(
            pattern, use_regex, False, False, False, True, line, index, False
        ):
            return True
        self.setCursorPosition(0, 0)
        return self.findFirst(pattern, use_regex, False, False, False, True, 0, 0, False)

    # ── placeholder overlay ──

    def _update_placeholder(self) -> None:
        self._placeholder_label.setVisible(self.text() == "")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._placeholder_label.adjustSize()
        self._placeholder_label.move(4, 4)

    # ── right-click menu: encoding + Word Wrap ──

    def contextMenuEvent(self, event) -> None:
        menu = self.createStandardContextMenu()
        if self._inspector is not None:
            self._inspector.add_encoding_menu(menu)
        menu.addSeparator()
        wrap_action = menu.addAction("Word Wrap")
        wrap_action.setCheckable(True)
        wrap_action.setChecked(self.wrapMode() != QsciScintilla.WrapMode.WrapNone)
        wrap_action.triggered.connect(self._toggle_word_wrap)
        paste_action = menu.addAction("Paste From File")
        paste_action.setEnabled(not self.isReadOnly())
        paste_action.triggered.connect(self._paste_from_file)
        menu.exec(event.globalPos())

    def _toggle_word_wrap(self, checked: bool) -> None:
        self.setWrapMode(
            QsciScintilla.WrapMode.WrapWord
            if checked
            else QsciScintilla.WrapMode.WrapNone
        )
        config = AppConfig()
        config.raw_word_wrap = checked
        config.save()

    def _paste_from_file(self) -> None:
        """Read a file and replace the editor content with its decoded text
        (available while the editor is editable)."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Paste From File", "", "All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return
        encoding = (
            self._inspector._encoding
            if self._inspector is not None
            else DEFAULT_ENCODING
        )
        text = _decode_bytes(data, encoding)
        # Use length-aware Scintilla commands instead of the Qt string
        # helpers: the latter treat NUL as a C-string terminator.  Scintilla
        # positions are byte offsets when UTF-8 mode is enabled.
        payload = text.encode("utf-8")
        start = self.SendScintilla(QsciScintillaBase.SCI_GETSELECTIONSTART)
        end = self.SendScintilla(QsciScintillaBase.SCI_GETSELECTIONEND)
        self.SendScintilla(QsciScintillaBase.SCI_BEGINUNDOACTION)
        if end > start:
            self.SendScintilla(
                QsciScintillaBase.SCI_DELETERANGE, start, end - start
            )
        self.SendScintilla(QsciScintillaBase.SCI_GOTOPOS, start)
        self.SendScintilla(
            QsciScintillaBase.SCI_ADDTEXT, len(payload), payload
        )
        self.SendScintilla(QsciScintillaBase.SCI_ENDUNDOACTION)

    def _save_zoom(self) -> None:
        config = AppConfig()
        config.raw_font_zoom = int(
            self.SendScintilla(QsciScintillaBase.SCI_GETZOOM)
        )
        config.save()


class _RawSearchBar(QWidget):
    """Bottom bar for the Raw tab: keyword search with a Regex toggle,
    Find-next navigation from the current cursor, and occurrence counting."""

    def __init__(self, editor: _ScintillaTextEdit, parent: QWidget | None = None):
        super().__init__(parent)
        self._editor = editor

        self._keyword = QLineEdit()
        self._keyword.setPlaceholderText("Keyword")
        self._keyword.setClearButtonEnabled(True)
        self._regex = QCheckBox("Regex")
        self._find_btn = QPushButton("Find")
        self._count_btn = QPushButton("Count:__")
        self._find_btn.setFixedWidth(56)
        self._count_btn.setFixedWidth(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.addWidget(self._keyword, 1)
        layout.addWidget(self._regex)
        layout.addWidget(self._find_btn)
        layout.addWidget(self._count_btn)

        self._find_btn.clicked.connect(self._find_next)
        self._count_btn.clicked.connect(self._count_matches)
        self._keyword.returnPressed.connect(self._find_next)

    def _find_next(self) -> None:
        pattern = self._keyword.text()
        if not pattern:
            return
        editor = self._editor
        if self._regex.isChecked():
            rx = QRegularExpression(pattern)
            if not rx.isValid():
                QMessageBox.warning(self, "Error", f"Invalid regular expression: {pattern}")
                return
            found = editor.find_first(pattern, True)
        else:
            found = editor.find_first(pattern, False)
        if not found:
            self._count_btn.setText("Count:0")

    def _count_matches(self) -> None:
        pattern = self._keyword.text()
        if not pattern:
            return
        text = self._editor.text()
        if self._regex.isChecked():
            try:
                count = sum(1 for _ in re.finditer(pattern, text))
            except re.error:
                QMessageBox.warning(self, "Error", f"Invalid regular expression: {pattern}")
                return
        else:
            count = text.count(pattern)
        self._count_btn.setText(f"Count:{count}")


class _ImageViewWidget(QScrollArea):
    """Scrollable widget for displaying images in the ImageView tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setText("Select a session to view ImageView")
        self.setWidget(self._label)
        self.setWidgetResizable(False)

    def set_image(self, data: bytes | None) -> None:
        if not data:
            self._label.setText("(no image data)")
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(QByteArray(data)):
            self._label.setPixmap(pixmap)
            self._label.setFixedSize(pixmap.size() + pixmap.size() / 10)
        else:
            self._label.setText("(failed to decode image)")


class _WebFormsWidget(QWidget):
    """Widget with two tables (Query String + Body) for WebForms display."""

    NAME_WIDTH_RATIO = 0.25  # 25% for Name, 75% for Value

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._query_label = QLabel("Query String")
        self._query_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self._query_label)

        self._query_table = QTableWidget()
        self._query_table.setColumnCount(2)
        self._query_table.setHorizontalHeaderLabels(["Name", "Value"])
        self._query_table.horizontalHeader().setStretchLastSection(True)
        self._query_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._query_table.setColumnWidth(0, 150)
        self._query_table.verticalHeader().setVisible(False)
        self._query_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._query_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._query_table.setAlternatingRowColors(True)
        self._query_table.setWordWrap(True)
        self._query_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._query_table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._query_table)

        self._body_label = QLabel("Body")
        self._body_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self._body_label)

        self._body_table = QTableWidget()
        self._body_table.setColumnCount(2)
        self._body_table.setHorizontalHeaderLabels(["Name", "Value"])
        self._body_table.horizontalHeader().setStretchLastSection(True)
        self._body_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._body_table.setColumnWidth(0, 150)
        self._body_table.verticalHeader().setVisible(False)
        self._body_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._body_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._body_table.setAlternatingRowColors(True)
        self._body_table.setWordWrap(True)
        self._body_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._body_table)

        # Track whether user manually edited either table since last populate.
        self._modified = False
        self._query_table.cellChanged.connect(self._on_cell_changed)
        self._body_table.cellChanged.connect(self._on_cell_changed)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """When double-clicking a Value cell, show a multi-line editor dialog."""
        table = self.sender()
        if not isinstance(table, QTableWidget) or col != 1:
            return
        triggers = table.editTriggers()
        if triggers == QTableWidget.EditTrigger.NoEditTriggers:
            return  # read-only, no editing
        current = table.item(row, col)
        current_text = current.text() if current else ""

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Value")
        dialog.resize(500, 250)
        dl = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setPlainText(current_text)
        editor.setFont(QFont("Consolas", 10))
        dl.addWidget(editor)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dialog.accept)
        bb.rejected.connect(dialog.reject)
        dl.addWidget(bb)

        def _apply_value():
            new_text = editor.toPlainText()
            table.setItem(row, col, QTableWidgetItem(new_text))
            table.resizeRowToContents(row)

        dialog.accepted.connect(_apply_value)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

    def _on_cell_changed(self, row: int, col: int) -> None:
        self._modified = True

    def is_modified(self) -> bool:
        return self._modified

    def reset_modified(self) -> None:
        self._modified = False

    def set_params(self, query_params: list[tuple[str, str]], body_params: list[tuple[str, str]]):
        """Populate both tables and resize Name column to 35%."""
        self._populate_table(self._query_table, query_params, self._query_label)
        self._populate_table(self._body_table, body_params, self._body_label)
        self._modified = False

    def set_editable(self, editable: bool) -> None:
        """Toggle editability of both tables."""
        triggers = QTableWidget.EditTrigger.AllEditTriggers if editable else QTableWidget.EditTrigger.NoEditTriggers
        self._query_table.setEditTriggers(triggers)
        self._body_table.setEditTriggers(triggers)

    def get_query_params(self) -> list[tuple[str, str]]:
        """Read current query string params from the table.

        Note: whitespace is intentionally preserved (no strip), so a name or
        value that legitimately contains spaces round-trips through urlencode.
        """
        result: list[tuple[str, str]] = []
        for row in range(self._query_table.rowCount()):
            name_item = self._query_table.item(row, 0)
            value_item = self._query_table.item(row, 1)
            name = name_item.text() if name_item else ""
            value = value_item.text() if value_item else ""
            if name:
                result.append((name, value))
        return result

    def get_body_params(self) -> list[tuple[str, str]]:
        """Read current body form params from the table.

        Note: whitespace is intentionally preserved (no strip), so a name or
        value that legitimately contains spaces round-trips through urlencode.
        """
        result: list[tuple[str, str]] = []
        for row in range(self._body_table.rowCount()):
            name_item = self._body_table.item(row, 0)
            value_item = self._body_table.item(row, 1)
            name = name_item.text() if name_item else ""
            value = value_item.text() if value_item else ""
            if name:
                result.append((name, value))
        return result

    def _populate_table(self, table: QTableWidget, params: list[tuple[str, str]], label: QLabel):
        table.setRowCount(len(params))
        for row, (name, value) in enumerate(params):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(value))
        # Set Name column to 25% of table width
        total_w = table.viewport().width()
        if total_w > 0:
            table.setColumnWidth(0, int(total_w * self.NAME_WIDTH_RATIO))
        label.setVisible(len(params) > 0)
        table.setVisible(len(params) > 0)
        table.resizeRowsToContents()

    def resizeEvent(self, event):
        """Re-adjust Name column to 25% on resize."""
        super().resizeEvent(event)
        total_w = self._query_table.viewport().width()
        if total_w > 0:
            self._query_table.setColumnWidth(0, int(total_w * self.NAME_WIDTH_RATIO))
        total_w = self._body_table.viewport().width()
        if total_w > 0:
            self._body_table.setColumnWidth(0, int(total_w * self.NAME_WIDTH_RATIO))


class _SilentWebEnginePage(QWebEnginePage):
    """WebEngine page that silently ignores JavaScript console errors."""

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Suppress all JS console messages (e.g. localStorage SecurityError etc.)
        pass


class _NoWheelTabBar(QTabBar):
    """QTabBar that ignores mouse-wheel events (prevents accidental tab switches)."""

    def wheelEvent(self, e) -> None:
        e.ignore()


class _NoWheelTabWidget(QTabWidget):
    """QTabWidget whose tab bar is immune to mouse-wheel events."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(_NoWheelTabBar(self))


class InspectorPanel(QWidget):
    """A panel with tabs for inspecting request or response data."""

    def __init__(
        self,
        tab_labels: list[str],
        panel_type: str = "request",
        parent=None,
        ignore_wheel_tabs: bool = False,
    ):
        super().__init__(parent)
        self._panel_type = panel_type
        self._current_flow = None
        config = AppConfig()
        self._encoding = config.raw_encoding if config.raw_encoding in ENCODINGS else DEFAULT_ENCODING
        self._text_widgets: dict[str, _ScintillaTextEdit] = {}
        self._image_widget: _ImageViewWidget | None = None
        self._web_view: QWebEngineView | None = None
        self._webforms_widget: _WebFormsWidget | None = None
        self._previous_tab_index = -1
        # Tabs whose content no longer matches self._current_flow.  They are
        # rendered lazily when the user switches to them, so selecting large
        # flows never formats (or sets) big bodies on the GUI thread.
        self._stale_tabs: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if ignore_wheel_tabs:
            self._tabs = _NoWheelTabWidget(self)
        else:
            self._tabs = QTabWidget(self)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)

        for label in tab_labels:
            if label == "WebView":
                self._web_view = QWebEngineView()
                self._web_view.setPage(_SilentWebEnginePage(self._web_view))
                self._web_view.setHtml("<html><body></body></html>")
                self._tabs.addTab(self._web_view, label)
            elif label == "ImageView":
                self._image_widget = _ImageViewWidget()
                self._tabs.addTab(self._image_widget, label)
            elif label == "WebForms":
                self._webforms_widget = _WebFormsWidget()
                self._tabs.addTab(self._webforms_widget, label)
            elif label == "Raw":
                widget = _ScintillaTextEdit(self)
                widget.setPlaceholderText(f"Select a session to view {label}")
                self._text_widgets[label] = widget
                # Bottom search bar (keyword / Regex / Find / Count)
                container = QWidget()
                box = QVBoxLayout(container)
                box.setContentsMargins(0, 0, 0, 0)
                box.setSpacing(0)
                box.addWidget(widget)
                box.addWidget(_RawSearchBar(widget))
                self._tabs.addTab(container, label)
            else:
                # Text-based inspection tabs use the same themed Scintilla
                # editor as Raw, including persisted zoom and Word Wrap.
                widget = _ScintillaTextEdit(self)
                widget.setPlaceholderText(f"Select a session to view {label}")
                self._tabs.addTab(widget, label)
                self._text_widgets[label] = widget

        layout.addWidget(self._tabs)

        # Connect tab change signal for WebView lazy-render and WebForms↔Raw sync
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Save outgoing request-panel edits, then lazily render the incoming
        tab (big bodies are only formatted when their tab is shown)."""
        if self._panel_type == "request" and self._current_flow:
            prev_idx = self._previous_tab_index
            if prev_idx >= 0 and prev_idx != index:
                flow = self._current_flow
                prev_tab = self._tabs.tabText(prev_idx)

                # Save outgoing tab's edits — only when the panel is actually
                # editable (edit_mode or compose_mode).  In read-only mode the
                # Raw text matches the flow exactly; re-parsing it is
                # unnecessary and can corrupt data when the view hasn't caught
                # up yet.
                raw_widget = self._text_widgets.get("Raw")
                editable = raw_widget is not None and not raw_widget.isReadOnly()

                if prev_tab == "WebForms" and self._webforms_widget and self._webforms_widget.is_modified():
                    self.apply_webforms_edits(flow)
                    self._sync_content_length_inspector(flow, is_request=True)
                elif prev_tab == "Raw" and editable:
                    self.apply_request_edits(flow)

        self._previous_tab_index = index

        # Lazily render the incoming tab if its content is stale.
        cur_tab = self._tabs.tabText(index)
        if cur_tab in self._stale_tabs:
            self._render_tab(cur_tab)

    def _render_tab(self, tab_name: str) -> None:
        """Render a single content tab from the current flow (lazy path)."""
        self._stale_tabs.discard(tab_name)
        if tab_name not in self._text_widgets and tab_name not in ("WebView", "ImageView"):
            return
        if self._panel_type == "request":
            self._render_request_tab(tab_name)
        else:
            self._render_response_tab(tab_name)

    def _render_request_tab(self, tab_name: str) -> None:
        flow = self._current_flow
        if flow is None or not flow.request:
            return
        req = flow.request
        enc = self._encoding
        ct = req.headers.get("content-type", "").lower()
        try:
            safe_content = req.content
        except ValueError:
            safe_content = None

        if tab_name == "Raw":
            # QScintilla preserves the body's original line endings, so no
            # separate display-body bookkeeping is needed anymore.
            self.set_content("Raw", _format_request_raw(flow, enc))
        elif tab_name == "Headers":
            status_line = f"{req.method} {req.path} {req.http_version}"
            self.set_content("Headers", status_line + "\n" + _format_headers(req.headers, enc))
        elif tab_name == "Hex":
            self.set_content("Hex", _format_hex(safe_content))
        elif tab_name == "JSON":
            if "json" in ct:
                self.set_content("JSON", _try_format_json(safe_content))
            else:
                self.set_content("JSON", "(not JSON content)")
        elif tab_name == "XML":
            if "xml" in ct:
                self.set_content("XML", _try_format_xml(safe_content))
            else:
                self.set_content("XML", "(not XML content)")

    def _render_response_tab(self, tab_name: str) -> None:
        flow = self._current_flow
        if flow is None or not flow.response:
            return
        resp = flow.response
        enc = self._encoding
        ct = resp.headers.get("content-type", "").lower()
        try:
            safe_content = resp.content
        except ValueError:
            safe_content = None

        if tab_name == "Raw":
            # QScintilla preserves the body's original line endings, so no
            # separate display-body bookkeeping is needed anymore.
            self.set_content("Raw", _format_response_raw(flow, enc))
        elif tab_name == "Headers":
            status_line = f"{resp.http_version} {resp.status_code} {resp.reason}"
            self.set_content("Headers", status_line + "\n" + _format_headers(resp.headers, enc))
        elif tab_name == "Hex":
            self.set_content("Hex", _format_hex(safe_content))
        elif tab_name == "JSON":
            if "json" in ct:
                self.set_content("JSON", _try_format_json(safe_content))
            else:
                self.set_content("JSON", "(not JSON content)")
        elif tab_name == "XML":
            if "xml" in ct:
                self.set_content("XML", _try_format_xml(safe_content))
            else:
                self.set_content("XML", "(not XML content)")
        elif tab_name == "ImageView":
            if self._image_widget:
                if "image/" in ct:
                    self._image_widget.set_image(safe_content)
                else:
                    self._image_widget._label.setText("(not image content)")
        elif tab_name == "WebView":
            self._render_webview()

    def _sync_content_length_inspector(self, flow, is_request: bool) -> None:
        """Sync content-length header for inspector panel internal use."""
        msg = flow.request if is_request else flow.response
        if not msg:
            return
        cl_bytes = b"content-length"
        if not msg.content:
            # Never delete an existing Content-Length — only adjust to 0.
            # Do not add Content-Length if it was not already present.
            if cl_bytes in msg.headers:
                msg.headers[cl_bytes] = b"0"
            return
        body_len = len(msg.content)
        if cl_bytes in msg.headers:
            msg.headers[cl_bytes] = str(body_len).encode()
        else:
            msg.headers.add(cl_bytes, str(body_len).encode())

    def _render_webview(self) -> None:
        """Extract response content and render in WebView."""
        if not self._web_view or not self._current_flow:
            return
        resp = self._current_flow.response
        if not resp:
            return
        ct = resp.headers.get("content-type", "").lower()
        if "text/html" in ct and resp.content:
            html = resp.content.decode("utf-8", errors="replace")
        else:
            body = _decode_bytes(resp.content, self._encoding) if resp.content else "(no body)"
            html = f"<html><body><pre>{self._escape_html(body)}</pre></body></html>"
        self._web_view.setHtml(html)

    def add_encoding_menu(self, menu: QMenu) -> None:
        encoding_menu = menu.addMenu("Encoding")
        for enc in ENCODINGS:
            action = encoding_menu.addAction(enc)
            action.setCheckable(True)
            action.setChecked(enc == self._encoding)
            action.triggered.connect(lambda checked, e=enc: self._set_encoding(e))

    def _set_encoding(self, encoding: str) -> None:
        if encoding != self._encoding:
            self._encoding = encoding
            config = AppConfig()
            config.raw_encoding = encoding
            config.save()
            if self._current_flow:
                if self._panel_type == "request":
                    self.populate_request(self._current_flow)
                else:
                    self.populate_response(self._current_flow)

    def set_content(self, tab_name: str, text: str) -> None:
        if tab_name in self._text_widgets:
            w = self._text_widgets[tab_name]
            if w.toPlainText() != text:
                w.setPlainText(text)
            w.document().setModified(False)

    def set_editable(self, editable: bool) -> None:
        """Toggle read-only state for all text widgets and WebForms tables."""
        for w in self._text_widgets.values():
            w.setReadOnly(not editable)
        if self._webforms_widget:
            self._webforms_widget.set_editable(editable)

    def populate_request(self, flow) -> None:
        """Display the flow's request content in the text widgets.

        This method is read-only — it does NOT save edits.  Edits are only
        applied via explicit save paths (Send, Break On Response, F2 toggle,
        or switching away while edit mode is active).
        """
        req = flow.request
        self._current_flow = flow

        if not req:
            self.set_content("Raw", "(no request)")
            self.set_content("Headers", "(no request)")
            self.set_content("JSON", "")
            self.set_content("XML", "")
            self.set_content("Hex", "")
            if self._webforms_widget:
                self._webforms_widget.set_params([], [])
            self._stale_tabs.clear()
            return

        # WebForms is cheap and feeds edit sync — always refresh it.
        self._populate_webforms(req)

        # Heavy tabs are rendered lazily; only the visible one is rendered
        # now, the rest when the user switches to them.
        self._stale_tabs = {"Raw", "Headers", "XML", "JSON", "Hex"}
        self._render_tab(self._tabs.tabText(self._tabs.currentIndex()))

    def _populate_webforms(self, req) -> None:
        """Extract URL query params and body form params, show in tables."""
        from urllib.parse import parse_qs, urlsplit

        query_items: list[tuple[str, str]] = []
        body_items: list[tuple[str, str]] = []

        # Extract query string params from URL
        if req.path:
            parsed = urlsplit(req.path)
            if parsed.query:
                qs = parse_qs(parsed.query, keep_blank_values=True)
                for k, vals in qs.items():
                    for v in vals:
                        query_items.append((k, v))

        # Extract body params if content-type is x-www-form-urlencoded.
        # Access req.content carefully — it may raise ValueError when
        # content-encoding is invalid (get_content(strict=True)).
        try:
            raw_body = req.content
        except ValueError:
            raw_body = None
        if raw_body:
            ct = req.headers.get("content-type", "").lower()
            if "x-www-form-urlencoded" in ct:
                try:
                    body = raw_body.decode(self._encoding, errors="replace").replace("\ufffd", "??")
                    body_qs = parse_qs(body, keep_blank_values=True)
                    for k, vals in body_qs.items():
                        for v in vals:
                            body_items.append((k, v))
                except Exception:
                    pass

        if self._webforms_widget:
            self._webforms_widget.set_params(query_items, body_items)

    def apply_webforms_edits(self, flow) -> None:
        """Apply WebForms table edits back to the flow's request.

        Only applies when the user has actually modified the WebForms tables
        since the last populate.  Otherwise the stale table data would
        overwrite edits made in the Raw tab (e.g. URL query changes).
        """
        if not self._webforms_widget:
            return
        if not self._webforms_widget.is_modified():
            return
        req = flow.request
        if not req:
            return

        from urllib.parse import urlsplit, urlencode, urlunsplit

        query_pairs = self._webforms_widget.get_query_params()
        body_pairs = self._webforms_widget.get_body_params()

        # Update query string without treating semicolons as URL parameters.
        parsed = urlsplit(req.path)
        new_query = urlencode(query_pairs) if query_pairs else ""
        req.path = urlunsplit(("", "", parsed.path, new_query, parsed.fragment))

        # Update body — only touch it when the content is actually
        # form-encoded.  For JSON, XML, or other content types we must
        # not clear the body, otherwise non-form POST flows lose their
        # body when edits are saved (e.g. during Replay And Edit).
        current_ct = (req.headers.get("content-type", "") or "").lower()
        if body_pairs:
            body = urlencode(body_pairs).encode(self._encoding)
            req.content = body
            req.headers[b"content-type"] = b"application/x-www-form-urlencoded"
        elif "x-www-form-urlencoded" in current_ct:
            # Only clear the body when the original content was form-encoded.
            req.content = b""
            req.headers.pop(b"content-type", None)

        # Reset modified flag only after successful application, not on
        # early-return paths.
        if self._webforms_widget:
            self._webforms_widget.reset_modified()

    def apply_request_edits(self, flow) -> None:
        """Apply user edits from Raw and WebForms tabs back to the flow's request."""
        req = flow.request
        if not req:
            return
        from mitmproxy.net.http.url import hostport

        # ── 1. Apply Raw tab edits (method, URL, headers, body) ──
        raw_text = self._text_widgets.get("Raw")
        raw_modified = bool(raw_text and raw_text.document().isModified())
        if raw_modified:
            raw_str = raw_text.toPlainText()
            if raw_str:
                lines = raw_str.split("\n")
                try:
                    # The request line may carry a trailing "\r" when the user
                    # typed CRLF line endings; strip it before parsing.
                    parts = lines[0].rstrip("\r").split(" ", 2)
                    req.method = parts[0]
                    if len(parts) > 1:
                        from urllib.parse import urlsplit
                        parsed = urlsplit(parts[1])
                        req.path = _raw_target_to_path(parts[1])
                        if parsed.scheme:
                            req.scheme = parsed.scheme
                        if parsed.hostname:
                            raw_host = parsed.hostname
                            raw_port = parsed.port
                            original_host = getattr(flow, "_original_host", None)
                            raw_authority = raw_host
                            if raw_port is not None:
                                raw_authority = f"{raw_host}:{raw_port}"
                            if original_host and raw_authority == original_host:
                                pass
                            else:
                                # User edited the host – clear _original_host so
                                # the Raw display shows the edited URL, not the
                                # original (hosts-remapped) hostname.
                                flow._original_host = None
                                req.host = raw_host
                                if raw_port is not None:
                                    req.port = raw_port
                                else:
                                    # User removed the port from the URL — reset
                                    # to the scheme default so the old port does
                                    # not persist and reappear after regeneration.
                                    _s = (parsed.scheme or req.scheme).lower()
                                    req.port = 443 if _s == "https" else 80
                    if len(parts) > 2:
                        req.http_version = parts[2].rstrip("\r")
                except (IndexError, ValueError):
                    pass

                # Parse headers until empty line
                header_end = 0
                for i in range(1, len(lines)):
                    if lines[i] == "":
                        header_end = i
                        break
                    try:
                        k, v = lines[i].split(": ", 1)
                        v = v.rstrip("\r")
                        if i == 1:
                            req.headers.clear()
                        req.headers.add(k, v)
                    except ValueError:
                        pass

                # Keep authority/Host aligned with the edited Raw headers. For
                # hosts-remapped flows, the Raw request line shows the original
                # authority, while request.host/port hold the remapped target.
                explicit_host = req.headers.get("host", None)
                req.authority = (
                    explicit_host
                    or getattr(flow, "_original_host", None)
                    or hostport(req.scheme, req.host, req.port)
                )

                # Body is everything after the empty line.  QScintilla keeps the
                # body's original line endings (CRLF stays CRLF), so encoding
                # the text back preserves the packet's line breaks as-is.
                if header_end > 0 and header_end + 1 < len(lines):
                    body = "\n".join(lines[header_end + 1:])
                    req.content = body.encode(self._encoding, errors="replace")

        # ── 2. Apply WebForms tab edits only when Raw was not edited. Raw is
        # the source of truth for Edit And Replay; otherwise stale WebForms data
        # can overwrite manually appended POST body bytes.
        if not raw_modified:
            self.apply_webforms_edits(flow)

        # ── 3. Regenerate Raw text from the updated flow ──
        enc = self._encoding
        new_raw = _format_request_raw(flow, enc)
        self.set_content("Raw", new_raw)

        # ── 4. Refresh WebForms ──
        self._populate_webforms(req)

    def apply_response_edits(self, flow) -> None:
        """Apply user edits from the Raw tab back to the flow's response."""
        raw_text = self._text_widgets.get("Raw")
        if not raw_text:
            return
        raw_str = raw_text.toPlainText()
        if not raw_str:
            return

        lines = raw_str.split("\n")
        resp = flow.response
        if not resp:
            return
        try:
            # The status line may carry a trailing "\r" when the user typed
            # CRLF line endings; strip it before parsing.
            parts = lines[0].rstrip("\r").split(" ", 2)
            if len(parts) >= 1:
                resp.http_version = parts[0]
            if len(parts) >= 2:
                try:
                    resp.status_code = int(parts[1])
                except ValueError:
                    pass
            if len(parts) >= 3:
                resp.reason = parts[2]
        except (IndexError, ValueError):
            pass

        # Parse headers until empty line
        header_end = 0
        for i in range(1, len(lines)):
            if lines[i] == "":
                header_end = i
                break
            try:
                k, v = lines[i].split(": ", 1)
                v = v.rstrip("\r")
                if i == 1:
                    resp.headers.clear()
                resp.headers.add(k, v)
            except ValueError:
                pass

        # Body is everything after the empty line.  QScintilla keeps the
        # body's original line endings (CRLF stays CRLF), so encoding the
        # text back preserves the packet's line breaks as-is.
        if header_end > 0 and header_end + 1 < len(lines):
            body = "\n".join(lines[header_end + 1:])
            resp.content = body.encode(self._encoding, errors="replace")

        # Refresh all tabs from the updated flow
        if flow.response:
            self._refresh_response_tabs(flow)

    def _refresh_response_tabs(self, flow) -> None:
        """Refresh response tabs from the current flow's response data.

        Only the currently-visible tab is rendered eagerly; all other content
        tabs are marked stale and rendered lazily when the user switches to
        them, so selecting large flows never blocks the UI.
        """
        resp = flow.response
        if not resp:
            return

        self._stale_tabs = {"Raw", "Headers", "Hex", "JSON", "XML", "ImageView", "WebView"}
        self._render_tab(self._tabs.tabText(self._tabs.currentIndex()))

    def populate_response(self, flow) -> None:
        """Display the flow's response content in the text widgets.

        This method is read-only — it does NOT save edits.  Edits are only
        applied via explicit save paths.
        """
        resp = flow.response
        self._current_flow = flow

        if not resp:
            self.set_content("Raw", "(waiting for response...)")
            self.set_content("Headers", "(waiting for response...)")
            self.set_content("JSON", "")
            self.set_content("XML", "")
            self.set_content("Hex", "")
            if self._image_widget:
                self._image_widget._label.setText("")
            if self._web_view:
                self._web_view.setHtml("<html><body></body></html>")
            self._stale_tabs.clear()
            return

        self._refresh_response_tabs(flow)

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ReplaySequentiallyDialog(QDialog):
    """Configure repeated sequential replay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replay Sequentially")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.count = QSpinBox()
        self.count.setRange(0, 2_147_483_647)
        self.count.setValue(1)
        self.count.setToolTip("0 means unlimited")
        form.addRow("Count:", self.count)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.0, 2_147_483_647.0)
        self.interval.setDecimals(3)
        self.interval.setSingleStep(0.1)
        self.interval.setValue(1.0)
        self.interval.setSuffix(" s")
        form.addRow("Interval:", self.interval)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class FlowPropertiesDialog(QDialog):
    """Dialog showing detailed timing information for a flow."""

    def __init__(self, flow, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Properties")
        self.setWindowIcon(_make_icon("detail", "#00897B"))
        self.setMinimumSize(450, 250)
        self.resize(500, 300)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setContentsMargins(10, 10, 10, 10)

        def _ts(ts: float | None) -> str:
            if ts is None:
                return "N/A"
            dt = datetime.fromtimestamp(ts)
            return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"

        def _duration(start: float | None, end: float | None) -> str:
            if start is None or end is None:
                return "N/A"
            delta = end - start
            ms = int(delta * 1000)
            if ms >= 1000:
                return f"{ms / 1000:.3f} s ({ms} ms)"
            return f"{ms} ms"

        f = flow

        # Request outcome: show the failure reason when the request errored.
        if getattr(f, "error", None):
            form.addRow("Message:", QLabel(f"Request Failed: {f.error.msg}"))
        else:
            form.addRow("Message:", QLabel("Request OK"))

        req_ts = getattr(f, "timestamp_start", None)
        resp_start = None
        resp_end = None
        if hasattr(f, "response") and f.response:
            resp_start = getattr(f.response, "timestamp_start", None)
            resp_end = getattr(f.response, "timestamp_end", None)

        form.addRow("Client Request Time:", QLabel(_ts(req_ts)))
        form.addRow("Server Response Time:", QLabel(_ts(resp_start)))
        form.addRow("Request End Time:", QLabel(_ts(resp_end)))

        total = _duration(req_ts, resp_end) if resp_end else _duration(req_ts, resp_start)
        form.addRow("Total Duration:", QLabel(total))

        # Flow metadata written by plugins (e.g. fingerprint results stored
        # under the key "Finger"). Internal keys starting with "_" are hidden.
        meta = getattr(f, "metadata", None) or {}
        for key in sorted(meta):
            if key.startswith("_"):
                continue
            value = meta[key]
            if isinstance(value, list):
                value = ", ".join(
                    str(v.get("name", v)) if isinstance(v, dict) else str(v)
                    for v in value
                )
            form.addRow(f"{key}:", QLabel(str(value)))

        layout.addLayout(form)
        layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class _FilterRuleEditDialog(QDialog):
    """Non-modal dialog to add or edit a single filter rule (type + value
    filled in the same window)."""

    TYPES = ["hostname", "path"]

    def __init__(self, rule: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Rule" if rule is None else "Edit Rule")
        self.setWindowIcon(_make_icon("filter", "#8E24AA"))
        self.resize(360, 150)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._type_cb = QComboBox()
        self._type_cb.addItems(self.TYPES)
        self._type_cb.setCurrentText(
            rule.get("type", "hostname") if rule else "hostname"
        )
        form.addRow("Filter Type", self._type_cb)
        self._value_edit = QLineEdit()
        self._value_edit.setText(rule.get("value", "") if rule else "")
        form.addRow("Filter Value", self._value_edit)
        layout.addLayout(form)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._result: dict | None = None

    def _on_save(self) -> None:
        value = self._value_edit.text().strip()
        if not value:
            QMessageBox.warning(self, "Validation", "Value field cannot be empty.")
            return
        self._result = {"type": self._type_cb.currentText(), "value": value}
        self.accept()

    @property
    def result(self) -> dict | None:
        return self._result

    @staticmethod
    def open_nonblocking(rule: dict | None, parent, on_done) -> None:
        """Open the dialog as a non-modal window (does not block other windows).

        When the user saves, `on_done(dict)` is called with the new rule;
        when cancelled, `on_done(None)` is called. The dialog deletes itself
        on close.
        """
        dlg = _FilterRuleEditDialog(rule, parent)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(lambda _: on_done(dlg.result))
        dlg.show()


class FilterDialog(QDialog):
    """Dialog for viewing/editing filter rules."""

    def __init__(self, rules: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter Rules")
        self.setWindowIcon(_make_icon("filter", "#8E24AA"))
        self.setMinimumSize(450, 300)
        self.resize(500, 350)

        self.rules = list(rules)  # copy

        layout = QVBoxLayout(self)

        self._list = QListWidget()
        for rule in self.rules:
            self._list.addItem(f"{rule['type']}: {rule['value']}")
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add...")
        add_btn.clicked.connect(self._add_rule)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_rule)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_rule)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_rule(self) -> None:
        _FilterRuleEditDialog.open_nonblocking(None, self, self._on_add_done)

    def _on_add_done(self, rule) -> None:
        if rule:
            self.rules.append(rule)
            self._list.addItem(f"{rule['type']}: {rule['value']}")

    def _edit_rule(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self.rules):
            return
        _FilterRuleEditDialog.open_nonblocking(
            dict(self.rules[row]),
            self,
            lambda updated, r=row: self._on_edit_done(r, updated),
        )

    def _on_edit_done(self, row: int, rule) -> None:
        if rule:
            self.rules[row] = rule
            self._list.item(row).setText(f"{rule['type']}: {rule['value']}")

    def _remove_rule(self) -> None:
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)
            self.rules.pop(row)


class BreakpointRulesDialog(QDialog):
    """Dialog for configuring breakpoint rules (property, match type, value)."""

    def __init__(self, rules: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Breakpoint Rules")
        self.setWindowIcon(_make_icon("breakpoint", "#D32F2F"))
        self.setMinimumSize(450, 200)
        self.resize(480, 220)

        self.rules = list(rules) if rules else []

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._property_combo = QComboBox()
        self._property_combo.addItem("host")
        form.addRow("Property:", self._property_combo)

        self._match_type_combo = QComboBox()
        self._match_type_combo.addItem("Contains")
        self._match_type_combo.addItem("Regex")
        form.addRow("Match Type:", self._match_type_combo)

        self._value_edit = QLineEdit()
        self._value_edit.setPlaceholderText("www.baidu.com")
        form.addRow("Value:", self._value_edit)

        # Pre-fill if editing existing rules
        if self.rules:
            rule = self.rules[0]
            idx = self._property_combo.findText(rule.get("property", "host"))
            if idx >= 0:
                self._property_combo.setCurrentIndex(idx)
            mt = rule.get("match_type", "contains")
            if mt == "regex":
                self._match_type_combo.setCurrentIndex(1)
            self._value_edit.setText(rule.get("value", ""))

        layout.addLayout(form)
        layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self) -> None:
        value = self._value_edit.text().strip()
        if not value:
            return
        prop = self._property_combo.currentText()
        mt_text = self._match_type_combo.currentText().lower()
        self.rules = [{"property": prop, "match_type": mt_text, "value": value}]
        self.accept()


class FlowDetailDialog(QDialog):
    """Separate window showing full request/response details for a flow."""

    def __init__(self, flow, parent=None):
        super().__init__(parent)
        self._flow = flow
        self.setWindowTitle("Session Details")
        self.setWindowIcon(_make_icon("detail", "#00897B"))
        self.resize(1100, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        v_splitter = QSplitter(Qt.Orientation.Vertical)

        self._request_panel = InspectorPanel(
            ["Raw", "XML", "JSON", "Hex", "WebForms", "Headers"],
            panel_type="request",
            ignore_wheel_tabs=True,
        )
        self._response_panel = InspectorPanel(
            ["Raw", "Hex", "WebView", "ImageView", "Headers", "JSON", "XML"],
            panel_type="response",
            ignore_wheel_tabs=True,
        )

        v_splitter.addWidget(self._request_panel)
        v_splitter.addWidget(self._response_panel)
        v_splitter.setSizes([350, 350])

        layout.addWidget(v_splitter)

        self._request_panel.populate_request(flow)
        self._response_panel.populate_response(flow)


class CodeEditorDialog(QDialog):
    """A simple dialog for editing Python source code (e.g. rules.py)."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self.setWindowTitle(f"Custom Rules - {os.path.basename(file_path)}")
        self.setWindowIcon(_make_icon("code", "#37474F"))
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self._editor = QPlainTextEdit()
        mono = QFont("Consolas", 11)
        self._editor.setFont(mono)
        self._editor.setTabStopDistance(32)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # Load file content (create empty file template if missing)
        if os.path.isfile(file_path):
            try:
                self._editor.setPlainText(
                    open(file_path, "r", encoding="utf-8").read()
                )
            except OSError:
                pass
        else:
            self._editor.setPlainText(
                '"""mitmgui custom rules script.\n\n'
                "This file is auto-loaded (mitmproxy -s equivalent).\n"
                "Save to reload automatically.\n"
                '"""\n\n'
            )

        layout.addWidget(self._editor)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Save (Ctrl+S)")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Ctrl+S shortcut
        save_act = QAction("Save", self, shortcut=QKeySequence("Ctrl+S"))
        save_act.triggered.connect(self._save)
        self.addAction(save_act)

    def _save(self) -> None:
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                f.write(self._editor.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "Save Failed", str(e))


class HostsRemappingDialog(QDialog):
    """Dialog for editing hosts remapping rules (hosts.txt)."""

    HOSTS_FILE = os.path.join(os.getcwd(), "hosts.txt")

    def __init__(self, master, parent=None):
        super().__init__(parent)
        self._master = master
        self.setWindowTitle("Hosts Remapping")
        self.setWindowIcon(_make_icon("hosts", "#2E7D32"))
        self.resize(600, 420)

        layout = QVBoxLayout(self)

        self._editor = QPlainTextEdit()
        mono = QFont("Consolas", 11)
        self._editor.setFont(mono)
        self._editor.setPlaceholderText("127.0.0.1 example.com\ndomain:888 domain:8888")

        # ~20 lines visible
        line_h = self._editor.fontMetrics().height()
        self._editor.setMinimumHeight(line_h * 20 + 16)
        layout.addWidget(self._editor)

        # Load existing hosts.txt
        if os.path.isfile(self.HOSTS_FILE):
            try:
                self._editor.setPlainText(
                    open(self.HOSTS_FILE, "r", encoding="utf-8").read()
                )
            except OSError:
                pass

        # Bottom bar
        bottom = QHBoxLayout()

        hint = QLabel("NewIP Hostname\nNewHostname Hostname\nNewHost:NewPort Hostname[:OriginalPort]")
        hint.setStyleSheet("color: gray; font-size: 10pt;")
        bottom.addWidget(hint)
        bottom.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        bottom.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        bottom.addWidget(cancel_btn)

        layout.addLayout(bottom)

    def _save(self) -> None:
        """Save hosts rules to hosts.txt and reload the addon."""
        try:
            with open(self.HOSTS_FILE, "w", encoding="utf-8") as f:
                f.write(self._editor.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "Save Failed", str(e))
            return
        # Reload hosts in the proxy addon
        if hasattr(self._master, "hosts_remapping"):
            if self._master._loop:
                self._master._loop.call_soon_threadsafe(
                    self._master.hosts_remapping.reload
                )
        self.close()


class _TextEditDialog(QDialog):
    """Non-blocking dialog to view and edit a large block of text."""

    def __init__(self, text: str = "", title: str = "Edit Response Body", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(_make_icon("replace", "#E65100"))
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        self._edit = QPlainTextEdit()
        self._edit.setPlainText(text)
        layout.addWidget(self._edit, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._result_text = text

    @property
    def result_text(self) -> str:
        return self._result_text

    def accept(self) -> None:
        self._result_text = self._edit.toPlainText()
        super().accept()

    @staticmethod
    def open_nonblocking(editor: QPlainTextEdit, text: str, title: str, parent) -> None:
        """Open a non-modal edit dialog; on OK the text is written back to
        ``editor``. The dialog deletes itself on close.
        """
        dlg = _TextEditDialog(text, title, parent)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def _on_finished(res) -> None:
            if res == QDialog.DialogCode.Accepted:
                editor.setPlainText(dlg.result_text)

        dlg.finished.connect(_on_finished)
        dlg.show()


class _ResponseTextEdit(QPlainTextEdit):
    """Multiline editor that opens a dedicated edit dialog on double-click."""

    def mouseDoubleClickEvent(self, event) -> None:
        _TextEditDialog.open_nonblocking(
            self, self.toPlainText(), "Edit Response Body", self.window()
        )
        event.accept()


class _ClickableStatusLabel(QLabel):
    """Status area that opens quick settings on a left or right click."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.clicked.emit()
        else:
            super().mousePressEvent(event)


class AutoRuleDialog(QDialog):
    """Dialog for adding or editing a single Auto Rule."""

    ITEMS = [
        "Request.Url",
        "Request.Header",
        "Response.Header",
        "Response.Body",
    ]
    MATCH_TYPES = ["String", "Regex"]
    ACTIONS = ["Color", "Response With", "Response With File", "SaveToFile", "Replace"]
    REPLACE_INS = [
        "URL",
        "Request.Headers",
        "Request.Body",
        "Response.Headers",
        "Response.Body",
        "WebSocket.C2S",
        "WebSocket.S2C",
        "WebSocket.Both",
    ]
    REPLACE_TYPES = ["String", "Regex"]
    # Color choices (name, QColor); the first one (\u65e0) clears the color
    COLOR_CHOICES: list[tuple[str, QColor | None]] = [
        ("\u65e0", None),
        ("\u989c\u82721", QColor("#FF9999")),
        ("\u989c\u82722", QColor("#FFCC99")),
        ("\u989c\u82723", QColor("#FFFF99")),
        ("\u989c\u82724", QColor("#CCFF99")),
        ("\u989c\u82725", QColor("#99FF99")),
        ("\u989c\u82726", QColor("#99FFCC")),
        ("\u989c\u82727", QColor("#99FFFF")),
    ]

    def __init__(self, rule: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Rule" if rule is None else "Edit Rule")
        self.setWindowIcon(_make_icon("replace", "#E65100"))
        self.resize(480, 430)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._item_cb = QComboBox()
        self._item_cb.addItems(self.ITEMS)
        self._item_cb.setCurrentText(
            rule.get("item", "Request.Url") if rule else "Request.Url"
        )
        form.addRow("Item", self._item_cb)

        self._match_type_cb = QComboBox()
        self._match_type_cb.addItems(self.MATCH_TYPES)
        self._match_type_cb.setCurrentText(
            rule.get("match_type", "String") if rule else "String"
        )
        form.addRow("Match Type", self._match_type_cb)

        self._match_value_edit = QLineEdit()
        self._match_value_edit.setText(rule.get("match_value", "") if rule else "")
        form.addRow("Match Value", self._match_value_edit)

        self._action_cb = QComboBox()
        self._action_cb.addItems(self.ACTIONS)
        self._action_cb.setCurrentText(rule.get("action", "Color") if rule else "Color")
        self._action_cb.currentTextChanged.connect(self._on_action_changed)
        form.addRow("Action", self._action_cb)

        # ── Value rows (only the ones for the selected Action are shown) ──
        # They live in the same form right below "Action", so the spacing is
        # identical to the other rows and no large gap can appear.
        self._color_combo = QComboBox()
        for name, _ in self.COLOR_CHOICES:
            self._color_combo.addItem(name)
        form.addRow("Value", self._color_combo)
        self._color_row = form.rowCount() - 1

        self._response_with_edit = _ResponseTextEdit()
        # Minimum ~7 lines; grows with the dialog when the window is enlarged
        # (vertical size policy is Expanding).
        self._response_with_edit.setMinimumHeight(
            self._response_with_edit.fontMetrics().lineSpacing() * 7 + 12
        )
        self._response_with_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        form.addRow("Value", self._response_with_edit)
        self._resp_row = form.rowCount() - 1

        # "Response With File": single-line path + file picker button
        self._file_path_edit = QLineEdit()
        self._file_btn = QPushButton("选择文件...")
        self._file_btn.clicked.connect(self._on_browse_file)
        file_container = QWidget()
        file_lay = QHBoxLayout(file_container)
        file_lay.setContentsMargins(0, 0, 0, 0)
        file_lay.addWidget(self._file_path_edit, 1)
        file_lay.addWidget(self._file_btn)
        form.addRow("Value", file_container)
        self._file_row = form.rowCount() - 1

        # "SaveToFile": single-line directory + folder picker button
        self._savedir_edit = QLineEdit()
        self._savedir_btn = QPushButton("选择文件夹...")
        self._savedir_btn.clicked.connect(self._on_browse_savedir)
        savedir_container = QWidget()
        savedir_lay = QHBoxLayout(savedir_container)
        savedir_lay.setContentsMargins(0, 0, 0, 0)
        savedir_lay.addWidget(self._savedir_edit, 1)
        savedir_lay.addWidget(self._savedir_btn)
        form.addRow("Value", savedir_container)
        self._savedir_row = form.rowCount() - 1

        self._replace_in_cb = QComboBox()
        self._replace_in_cb.addItems(self.REPLACE_INS)
        form.addRow("In", self._replace_in_cb)
        self._replace_in_row = form.rowCount() - 1
        self._replace_type_cb = QComboBox()
        self._replace_type_cb.addItems(self.REPLACE_TYPES)
        form.addRow("Type", self._replace_type_cb)
        self._replace_type_row = form.rowCount() - 1
        self._replace_source_edit = QLineEdit()
        form.addRow("Source", self._replace_source_edit)
        self._replace_source_row = form.rowCount() - 1
        self._replace_dest_edit = QLineEdit()
        form.addRow("Destination", self._replace_dest_edit)
        self._replace_dest_row = form.rowCount() - 1

        self._form = form
        layout.addLayout(form)
        # Keep the fields at the top of the dialog and the buttons at the
        # bottom. The spacer is neutralized while "Response With" is active so
        # its value editor absorbs the extra vertical space instead.
        self._spacer = QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        layout.addSpacerItem(self._spacer)

        # ── Prefill from an existing rule ──
        if rule:
            action = rule.get("action", "Color")
            if action == "Color":
                saved_color = rule.get("value")
                if isinstance(saved_color, str):
                    idx = self._color_combo.findText(saved_color)
                    if idx >= 0:
                        self._color_combo.setCurrentIndex(idx)
            elif action == "Response With":
                v = rule.get("value")
                if isinstance(v, str):
                    self._response_with_edit.setPlainText(v)
            elif action == "Response With File":
                v = rule.get("value")
                if isinstance(v, str):
                    self._file_path_edit.setText(v)
            elif action == "SaveToFile":
                v = rule.get("value")
                if isinstance(v, str):
                    self._savedir_edit.setText(v)
            else:  # Replace
                v = rule.get("value")
                if isinstance(v, dict):
                    self._replace_in_cb.setCurrentText(v.get("in", "URL"))
                    self._replace_type_cb.setCurrentText(v.get("type", "String"))
                    self._replace_source_edit.setText(v.get("source", ""))
                    self._replace_dest_edit.setText(v.get("destination", ""))

        self._on_action_changed(self._action_cb.currentText())

        # ── Buttons (right-aligned) ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._result: dict | None = None

    def _on_action_changed(self, action: str) -> None:
        is_color = action == "Color"
        is_resp = action == "Response With"
        is_file = action == "Response With File"
        is_savedir = action == "SaveToFile"
        is_replace = action == "Replace"
        self._form.setRowVisible(self._color_row, is_color)
        self._form.setRowVisible(self._resp_row, is_resp)
        self._form.setRowVisible(self._file_row, is_file)
        self._form.setRowVisible(self._savedir_row, is_savedir)
        for row in (self._replace_in_row, self._replace_type_row,
                    self._replace_source_row, self._replace_dest_row):
            self._form.setRowVisible(row, is_replace)
        # While "Response With" is active let the value editor absorb the
        # extra vertical space; otherwise keep the fields compact at the top.
        self._spacer.changeSize(
            0, 0, QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Minimum if is_resp else QSizePolicy.Policy.Expanding,
        )
        if self.layout() is not None:
            self.layout().invalidate()

    def _on_browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Response File",
            self._file_path_edit.text().strip() or os.getcwd(),
        )
        if path:
            self._file_path_edit.setText(path)

    def _on_browse_savedir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select Save Directory",
            self._savedir_edit.text().strip() or os.getcwd(),
        )
        if directory:
            self._savedir_edit.setText(directory)

    def _on_save(self) -> None:
        match_value = self._match_value_edit.text().strip()
        if not match_value:
            QMessageBox.warning(self, "Validation", "Match Value field cannot be empty.")
            return
        action = self._action_cb.currentText()
        if action == "Color":
            value = self._color_combo.currentText()
        elif action == "Response With":
            value = self._response_with_edit.toPlainText()
        elif action == "Response With File":
            value = self._file_path_edit.text().strip()
        elif action == "SaveToFile":
            value = self._savedir_edit.text().strip()
        else:  # Replace
            source = self._replace_source_edit.text()
            if not source:
                QMessageBox.warning(self, "Validation", "Source field cannot be empty.")
                return
            value = {
                "in": self._replace_in_cb.currentText(),
                "type": self._replace_type_cb.currentText(),
                "source": source,
                "destination": self._replace_dest_edit.text(),
            }
        self._result = {
            "enabled": True,
            "item": self._item_cb.currentText(),
            "match_type": self._match_type_cb.currentText(),
            "match_value": match_value,
            "action": action,
            "value": value,
        }
        self.accept()

    @property
    def result(self) -> dict | None:
        return self._result

    @staticmethod
    def open_nonblocking(rule: dict | None, parent, on_done) -> None:
        """Open the dialog as a non-modal window (does not block other windows).

        When the user saves the dialog, `on_done(dict)` is called with the new
        rule; when cancelled, `on_done(None)` is called. The dialog deletes
        itself on close.
        """
        dlg = AutoRuleDialog(rule, parent)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(lambda _: on_done(dlg.result))
        dlg.show()


class AutoRulesDialog(QDialog):
    """Main window for managing Auto Rules."""

    AUTO_FILE = os.path.join(os.getcwd(), "autos.json")

    def __init__(self, master, parent=None):
        super().__init__(parent)
        self._master = master
        self.setWindowTitle("Auto Rules")
        self.setWindowIcon(_make_icon("replace", "#E65100"))
        self.resize(920, 460)

        main_layout = QHBoxLayout(self)

        # Left: buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self._add_btn = QPushButton("ADD")
        self._add_btn.clicked.connect(self._on_add)
        btn_layout.addWidget(self._add_btn)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.clicked.connect(self._on_remove)
        btn_layout.addWidget(self._remove_btn)

        self._up_btn = QPushButton("Up")
        self._up_btn.clicked.connect(self._on_up)
        btn_layout.addWidget(self._up_btn)

        self._down_btn = QPushButton("Down")
        self._down_btn.clicked.connect(self._on_down)
        btn_layout.addWidget(self._down_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # Right: table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Enabled", "Item", "Match Type", "Match Value", "Action", "Value"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Light-blue row selection so a checked "Enabled" checkbox stays clearly
        # visible (the global theme paints the row selection and the checkbox
        # with the same blue, which hides the checkmark on a selected row).
        self._table.setStyleSheet(
            """
            QTableWidget {
                selection-background-color: #BBDEFB;
                selection-color: #0D47A1;
            }
            QTableWidget::item:selected {
                background: #BBDEFB;
                color: #0D47A1;
            }
            """
        )
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 110)
        self._table.setColumnWidth(2, 80)
        self._table.setColumnWidth(4, 100)
        # Reserve ~8 rows of visible height (computed from the ORIGINAL row
        # height so the table's total height stays unchanged)
        row_h = self._table.verticalHeader().defaultSectionSize()
        self._table.setMinimumHeight(row_h * 8 + self._table.horizontalHeader().height() + 4)
        # Row height: +30% baseline for readability
        self._table.verticalHeader().setDefaultSectionSize(int(row_h * 1.3))
        # Double-click a row opens the Edit Rule dialog
        self._table.cellDoubleClicked.connect(self._on_edit)
        main_layout.addWidget(self._table)

        # Load data
        self._load_table()

    def _load_table(self) -> None:
        """Load rules from autos.json into the table."""
        import json
        try:
            if os.path.isfile(self.AUTO_FILE):
                with open(self.AUTO_FILE, "r", encoding="utf-8") as f:
                    self._rules = json.load(f)
            else:
                self._rules = []
        except (OSError, json.JSONDecodeError):
            self._rules = []
        if not isinstance(self._rules, list):
            self._rules = []

        self._table.setRowCount(len(self._rules))
        for i, rule in enumerate(self._rules):
            self._set_row(i, rule)

    def _set_row(self, row: int, rule: dict) -> None:
        """Populate a table row from a rule dict."""
        # Enabled checkbox
        cb = QCheckBox()
        cb.setChecked(rule.get("enabled", True))
        cb.clicked.connect(lambda checked, r=row: self._on_enabled_toggled(r, checked))
        self._table.setCellWidget(row, 0, cb)

        self._table.setItem(row, 1, QTableWidgetItem(rule.get("item", "")))
        self._table.setItem(row, 2, QTableWidgetItem(rule.get("match_type", "String")))
        self._table.setItem(row, 3, QTableWidgetItem(rule.get("match_value", "")))
        self._table.setItem(row, 4, QTableWidgetItem(rule.get("action", "")))
        value_item = QTableWidgetItem(self._value_text(rule))
        value_item.setToolTip(self._value_text(rule))
        self._table.setItem(row, 5, value_item)

    @staticmethod
    def _value_text(rule: dict) -> str:
        """Human-readable text for the Value column."""
        action = rule.get("action", "")
        value = rule.get("value")
        if action == "Replace" and isinstance(value, dict):
            return (
                f"{value.get('in', 'URL')}: {value.get('source', '')}"
                f" \u2192 {value.get('destination', '')}"
            )
        if isinstance(value, str):
            return value
        return ""

    def _on_enabled_toggled(self, row: int, checked: bool) -> None:
        """Called when a checkbox is clicked by the user (state already updated).

        Only the in-memory flag is changed and saved; the table is NOT rebuilt,
        otherwise the freshly-clicked checkbox widget would be destroyed while
        the user is still interacting with it.
        """
        if row < len(self._rules):
            self._rules[row]["enabled"] = checked
            self._save_rules()

    def _on_add(self) -> None:
        AutoRuleDialog.open_nonblocking(None, self, self._on_add_done)

    def _on_add_done(self, rule) -> None:
        if rule:
            self._rules.append(rule)
            self._save_and_reload()

    def _on_edit(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rules):
            return
        AutoRuleDialog.open_nonblocking(
            self._rules[row], self, lambda updated, r=row: self._on_edit_done(r, updated)
        )

    def _on_edit_done(self, row: int, updated) -> None:
        if updated is not None:
            # Preserve enabled state
            updated["enabled"] = self._rules[row].get("enabled", True)
            self._rules[row] = updated
            self._save_and_reload()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rules):
            return
        del self._rules[row]
        self._save_and_reload()

    def _on_up(self) -> None:
        row = self._table.currentRow()
        if row <= 0 or row >= len(self._rules):
            return
        self._rules[row], self._rules[row - 1] = self._rules[row - 1], self._rules[row]
        self._save_and_reload()
        self._table.selectRow(row - 1)

    def _on_down(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rules) - 1:
            return
        self._rules[row], self._rules[row + 1] = self._rules[row + 1], self._rules[row]
        self._save_and_reload()
        self._table.selectRow(row + 1)

    def _save_rules(self) -> None:
        """Persist rules to autos.json and notify the addon (no table rebuild)."""
        import json
        try:
            with open(self.AUTO_FILE, "w", encoding="utf-8") as f:
                json.dump(self._rules, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
        if (
            hasattr(self._master, "auto_rules_addon")
            and getattr(self._master, "_loop", None)
        ):
            self._master._loop.call_soon_threadsafe(
                self._master.auto_rules_addon.reload
            )

    def _save_and_reload(self) -> None:
        """Persist rules to autos.json, notify the addon and rebuild the table."""
        self._save_rules()
        self._load_table()


class FindDialog(QDialog):
    """Search dialog for finding text in sessions."""

    SEARCH_SCOPES = [
        "Requests and responses",
        "Requests Only",
        "Response Only",
        "Url Only",
    ]

    HIGHLIGHT_COLORS: list[tuple[str, QColor | None]] = [
        ("\u65e0", None),           # None
        ("\u989c\u82721", QColor("#FF9999")),
        ("\u989c\u82722", QColor("#FFCC99")),
        ("\u989c\u82723", QColor("#FFFF99")),
        ("\u989c\u82724", QColor("#CCFF99")),
        ("\u989c\u82725", QColor("#99FF99")),
        ("\u989c\u82726", QColor("#99FFCC")),
        ("\u989c\u82727", QColor("#99FFFF")),
    ]

    def __init__(self, session_model, parent=None):
        super().__init__(parent)
        self._session_model = session_model
        self.setWindowTitle("Find Sessions")
        self.setWindowIcon(_make_icon("proxy", "#1565C0"))
        self.setMinimumSize(460, 260)

        layout = QVBoxLayout(self)

        # ── Find text input ──
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find:"))
        self._find_text = QLineEdit()
        self._find_text.setPlaceholderText("Text To Search For")
        self._find_text.textChanged.connect(self._on_text_changed)
        find_layout.addWidget(self._find_text)
        layout.addLayout(find_layout)

        # ── Options group ──
        options_group = QVBoxLayout()

        # Search scope
        scope_layout = QHBoxLayout()
        scope_layout.addWidget(QLabel("Search"))
        self._scope_combo = QComboBox()
        self._scope_combo.addItems(self.SEARCH_SCOPES)
        scope_layout.addWidget(self._scope_combo)
        scope_layout.addStretch()
        options_group.addLayout(scope_layout)

        # Match case
        self._match_case = QCheckBox("Match Case")
        self._match_case.setChecked(False)
        options_group.addWidget(self._match_case)

        # Regular expression
        self._regex = QCheckBox("Regular Expr")
        self._regex.setChecked(False)
        options_group.addWidget(self._regex)

        # Unmark old results
        self._unmark_old = QCheckBox("Unmark old results")
        self._unmark_old.setChecked(False)
        options_group.addWidget(self._unmark_old)

        # Highlight color
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("\u5339\u914d\u7ed3\u679c\u989c\u8272\uff1a"))
        self._color_combo = QComboBox()
        for i, (name, color) in enumerate(self.HIGHLIGHT_COLORS):
            self._color_combo.addItem(name)
            if color is not None:
                self._color_combo.setItemData(i, color, Qt.ItemDataRole.BackgroundRole)
        self._color_combo.setCurrentIndex(1)  # Default: Color 1
        color_layout.addWidget(self._color_combo)
        color_layout.addStretch()
        options_group.addLayout(color_layout)

        layout.addLayout(options_group)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._search_btn = QPushButton("\u786e\u8ba4\u641c\u7d22")
        self._search_btn.setEnabled(False)
        self._search_btn.clicked.connect(self._do_search)
        btn_layout.addWidget(self._search_btn)
        self._cancel_btn = QPushButton("\u53d6\u6d88")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _on_text_changed(self, text: str) -> None:
        self._search_btn.setEnabled(bool(text.strip()))

    def _do_search(self) -> None:
        search_text = self._find_text.text().strip()
        if not search_text:
            return

        scope = self._scope_combo.currentIndex()
        match_case = self._match_case.isChecked()
        use_regex = self._regex.isChecked()
        unmark_old = self._unmark_old.isChecked()
        color_name = self._color_combo.currentText()
        color = None
        for name, c in self.HIGHLIGHT_COLORS:
            if name == color_name:
                color = c
                break

        # Unmark old results (clear all flow colors)
        if unmark_old:
            for f in self._session_model._flows:
                self._session_model.set_flow_color(f, None)

        # Compile regex
        if use_regex:
            try:
                flags = 0 if match_case else re.IGNORECASE
                pattern = re.compile(search_text, flags)
            except re.error:
                QMessageBox.warning(self, "Error", f"Invalid regular expression: {search_text}")
                return
        else:
            pattern = search_text.lower() if not match_case else search_text

        # Search flows
        matched_indices = []
        for idx, f in enumerate(self._session_model._flows):
            if self._flow_matches(f, scope, pattern, use_regex, match_case):
                matched_indices.append(idx)

        if not matched_indices:
            QMessageBox.information(self, "Result", "No matching sessions found.")
            self.accept()
            return

        # Highlight matching flows
        if color is not None:
            for idx in matched_indices:
                f = self._session_model._flows[idx]
                self._session_model.set_flow_color(f, color)

        self.accept()

    def _flow_matches(self, f, scope: int, pattern, use_regex: bool, match_case: bool) -> bool:
        """Check if a flow matches the search pattern."""
        texts = []

        if scope == 0:  # Requests and responses
            if f.request:
                texts.append(self._request_to_text(f.request))
            if f.response:
                texts.append(self._response_to_text(f.response))
        elif scope == 1:  # Requests Only
            if f.request:
                texts.append(self._request_to_text(f.request))
        elif scope == 2:  # Response Only
            if f.response:
                texts.append(self._response_to_text(f.response))
        elif scope == 3:  # Url Only
            if f.request:
                host = f.request.host or ""
                path = f.request.path or ""
                texts.append(f"{host}{path}")

        content = " ".join(texts)

        if use_regex:
            return bool(pattern.search(content))
        else:
            if not match_case:
                content = content.lower()
            return pattern in content

    @staticmethod
    def _request_to_text(req) -> str:
        """Convert request to searchable text."""
        parts = [
            f"{req.method or ''} {req.path or ''} {req.http_version or ''}",
            req.headers and str(req.headers) or "",
        ]
        try:
            content = req.get_content(strict=False)
        except Exception:
            content = None
        if content:
            parts.append(content.decode("utf-8", errors="replace"))
        return " ".join(parts)

    @staticmethod
    def _response_to_text(resp) -> str:
        """Convert response to searchable text."""
        parts = [
            f"{resp.http_version or ''} {resp.status_code} {resp.reason or ''}",
            resp.headers and str(resp.headers) or "",
        ]
        try:
            content = resp.get_content(strict=False)
        except Exception:
            content = None
        if content:
            parts.append(content.decode("utf-8", errors="replace"))
        return " ".join(parts)


class NewSessionDialog(QDialog):
    """Dialog for creating and sending a new raw HTTP request."""

    def __init__(self, main_window: "MitmGuiMainWindow", parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self.setWindowTitle("New Session")
        self.setWindowIcon(_make_icon("new_session", "#00897B"))
        self.setMinimumSize(640, 420)
        self.resize(720, 480)

        layout = QVBoxLayout(self)

        # Tab widget (currently just Raw, extensible later)
        self._tab_widget = QTabWidget()
        layout.addWidget(self._tab_widget)

        # Raw tab
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)

        self._raw_editor = _ScintillaTextEdit()
        self._raw_editor.setReadOnly(False)  # New Session is a compose editor
        self._raw_editor.setWrapMode(QsciScintilla.WrapMode.WrapNone)
        self._raw_editor.setPlaceholderText(
            "GET https://example.com/api HTTP/1.1\n"
            "Host: example.com\n"
            "Content-Type: application/json\n"
            "\n"
            "{\"key\": \"value\"}"
        )
        raw_layout.addWidget(self._raw_editor)
        self._tab_widget.addTab(raw_tab, "Raw")

        self._keep_open_checkbox = QCheckBox("Keep open after Send")
        self._keep_open_checkbox.setToolTip("Keep this window open for repeated sends.")
        self._tab_widget.setCornerWidget(self._keep_open_checkbox, Qt.Corner.TopRightCorner)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._send_btn = QPushButton("\u25b6 Send")
        self._send_btn.setDefault(True)
        self._send_btn.clicked.connect(self._on_send)
        btn_layout.addWidget(self._send_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _on_send(self) -> None:
        """Parse raw text, create a flow, and send it."""
        raw_text = self._raw_editor.text().strip()
        if not raw_text:
            return

        try:
            flow = self._parse_raw_to_flow(raw_text)
        except (ValueError, TypeError) as e:
            QMessageBox.warning(self, "Parse Error", str(e))
            return

        if flow is None:
            return

        # Add to session list and replay
        mw = self._main_window
        mw._session_model.add_flow(flow)
        mw._master.view.add([flow])
        mw._master.replay_flow(
            flow,
            lambda error: QTimer.singleShot(
                0, lambda: QMessageBox.warning(self, "Send Error", error)
            ),
        )
        mw._select_flow(flow)

        if not self._keep_open_checkbox.isChecked():
            self.accept()

    @staticmethod
    def _parse_raw_to_flow(raw_text: str):
        """Parse raw HTTP request text into an HTTPFlow."""
        from mitmproxy.http import HTTPFlow, Request, Headers
        from urllib.parse import urlparse

        # QScintilla preserves the line endings the user pasted (CRLF stays
        # CRLF).  Normalize them only for parsing; the body is re-encoded with
        # its original EOL style below.
        norm_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = norm_text.split("\n")

        # Parse request line: METHOD URL HTTP_VERSION
        if not lines:
            raise ValueError("Empty request")
        try:
            request_parts = lines[0].split(" ", 2)
            if len(request_parts) < 2:
                raise ValueError("Invalid request line (expected: METHOD URL [HTTP_VERSION])")
            method = request_parts[0].upper()
            url_str = request_parts[1]
            http_version = request_parts[2].strip() if len(request_parts) > 2 else "HTTP/1.1"
        except (IndexError, ValueError) as e:
            raise ValueError(f"Invalid request line: {e}")

        # Parse headers until empty line
        headers = Headers()
        header_end = 0
        for i in range(1, len(lines)):
            if lines[i] == "":
                header_end = i
                break
            try:
                k, v = lines[i].split(": ", 1)
                if i == 1:
                    headers.clear()
                headers.add(k, v)
            except ValueError:
                pass

        # Parse body (everything after the empty line)
        content = ""
        if header_end > 0 and header_end + 1 < len(lines):
            body_text = "\n".join(lines[header_end + 1:])
            # Restore the EOL style the user pasted (QScintilla keeps CRLF).
            if "\r\n" in raw_text:
                body_text = body_text.replace("\n", "\r\n")
            content = body_text.encode("utf-8")

        # Create the request
        from mitmproxy.net.http.url import hostport

        had_content_length = "content-length" in headers or "Content-Length" in headers
        explicit_host = headers.get("host", None)
        req = Request.make(method, url_str, content, headers)
        # Preserve the HTTP version from the original request line
        # (Request.make() always hardcodes HTTP/1.1).
        req.http_version = http_version
        # Preserve an explicitly supplied Host header. Request.make() and the
        # authority setter derive Host from the URL, but New Session needs to
        # support a different connection target and Host header.
        req.authority = explicit_host or hostport(req.scheme, req.host, req.port)
        if explicit_host:
            req.headers["Host"] = explicit_host
        # If body is empty and no Content-Length was in the user's raw headers,
        # remove the auto-added Content-Length: 0 (e.g. for GET requests).
        if not content and not had_content_length:
            req.headers.pop("content-length", None)
            req.headers.pop("Content-Length", None)

        # Create the flow with dummy connections (not from a real proxy session)
        from mitmproxy.connection import Client, Server
        client_conn = Client(peername=("127.0.0.1", 0), sockname=("127.0.0.1", 0))
        server_conn = Server(address=(req.host, req.port))
        flow = HTTPFlow(client_conn, server_conn)
        flow.request = req
        return flow


class LogsDialog(QDialog):
    """Log viewer: one table per category (Plugin / Info / Error / Debug).

    Tables are shells for now — data population is added later. Each table
    shows 时间 (YYYY-MM-DD HH:MM:SS.mmm) and Message columns; clicking a
    header sorts by that column. The Export button on the tab row is a no-op.
    The Plugin tab has extra columns (Time / From / Type / Message / Comment).
    """

    LOG_CATEGORIES = ["Plugin", "Info", "Error", "Debug"]
    TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
    # Plugin tab gets a From column; the other tabs are the same shape
    # (Time / Type / Message / Comment) but without the From column.
    COLUMNS = {
        "Plugin": ["Time", "From", "Type", "Message", "Comment"],
        "Info": ["Time", "Type", "Message", "Comment"],
        "Error": ["Time", "Type", "Message", "Comment"],
        "Debug": ["Time", "Type", "Message", "Comment"],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logs")
        self.setWindowIcon(_make_icon("logs", "#00897B"))
        self.resize(1170, 720)  # 50% larger to fit the Plugin tab columns

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tables: dict[str, QTableWidget] = {}
        for category in self.LOG_CATEGORIES:
            cols = self.COLUMNS[category]
            table = QTableWidget(0, len(cols))
            table.setHorizontalHeaderLabels(cols)
            table.setSortingEnabled(True)  # click header to sort by column
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)
            table.setColumnWidth(0, 190)  # time column
            table.horizontalHeader().setStretchLastSection(True)
            self._tables[category] = table
            self._tabs.addTab(table, category)
        layout.addWidget(self._tabs)

        # Export button on the right of the tab row (no-op for now).
        export_btn = QPushButton("Export")
        self._tabs.setCornerWidget(export_btn, Qt.Corner.TopRightCorner)

    def append_log(self, category: str, message: str, log_type: str = "Info",
                   comment=None) -> None:
        """Append a log line to a non-Plugin category table
        (Time / Type / Message / Comment)."""
        table = self._tables.get(category)
        if table is None or table.columnCount() != 4:
            return
        now = datetime.now().strftime(self.TIME_FORMAT)[:-3]
        # Sorting must be disabled while inserting, otherwise Qt re-sorts on
        # every setItem and the partially-filled row's cells get scattered.
        table.setSortingEnabled(False)
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(now))
        table.setItem(row, 1, QTableWidgetItem(str(log_type)))
        table.setItem(row, 2, QTableWidgetItem(str(message)))
        table.setItem(row, 3, QTableWidgetItem(str(comment) if comment else ""))
        table.setSortingEnabled(True)

    def append_plugin_log(self, from_name: str, log_type: str,
                          message: str, comment=None) -> None:
        """Append a row to the Plugin tab: Time / From / Type / Message / Comment."""
        table = self._tables.get("Plugin")
        if table is None:
            return
        now = datetime.now().strftime(self.TIME_FORMAT)[:-3]
        table.setSortingEnabled(False)
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(now))
        table.setItem(row, 1, QTableWidgetItem(str(from_name)))
        table.setItem(row, 2, QTableWidgetItem(str(log_type)))
        table.setItem(row, 3, QTableWidgetItem(str(message)))
        table.setItem(row, 4, QTableWidgetItem(str(comment) if comment else ""))
        table.setSortingEnabled(True)


class _PluginBridge(QObject):
    """Cross-thread bridge from the proxy thread to the GUI thread.

    Plugins run inside the proxy event loop; these signals are queued to the
    main thread where the Logs window / New Session dialog live.
    """

    log = pyqtSignal(str, str, str, object)  # from, type, message, comment
    new_session = pyqtSignal()
    set_flow_color = pyqtSignal(str, str)  # flow_id, color hex
    set_flow_info = pyqtSignal(str)  # flow_id


class _CenteredCheckDelegate(QStyledItemDelegate):
    """Draws a checkable item's checkbox centered in the cell.

    Without this, Qt draws the check indicator left-aligned, leaving a big
    blank area after it in the narrow Status column.
    """

    #: event types the delegate cares about for check toggling
    _CLICK_TYPES = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease)

    @staticmethod
    def _is_checked(state) -> bool:
        """``index.data(CheckStateRole)`` yields a plain int while
        ``Qt.CheckState.Checked`` is an enum (``enum == int`` is always False
        in PyQt6), so compare through ``.value``."""
        value = state.value if hasattr(state, "value") else state
        return value == Qt.CheckState.Checked.value

    def _check_rect(self, option) -> QRect:
        """Centered check indicator rect (must match what paint() draws)."""
        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()
        size = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, widget)
        rect = QRect(0, 0, size, size)
        rect.moveCenter(option.rect.center())
        return rect

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        # drop the default (left-aligned) check indicator; we draw it centered
        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()

        # cell background / selection / alternating color
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        # centered checkbox
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        if state is not None:
            check_opt = QStyleOptionButton()
            check_opt.rect = self._check_rect(opt)
            check_opt.state = QStyle.StateFlag.State_Enabled
            if self._is_checked(state):
                check_opt.state |= QStyle.StateFlag.State_On
            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                check_opt, painter, widget,
            )

    def editorEvent(self, event, model, option, index) -> bool:
        """Toggle the check state when the centered checkbox is clicked.

        The default implementation hit-tests against Qt's left-aligned
        ``SE_ItemViewItemCheckIndicator`` rect, which no longer matches the
        centered box this delegate draws.
        """
        if (
            event.type() in self._CLICK_TYPES
            and index.isValid()
            and index.flags() & Qt.ItemFlag.ItemIsUserCheckable
        ):
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            if self._check_rect(opt).contains(event.position().toPoint()):
                if event.type() == QEvent.Type.MouseButtonRelease:
                    state = index.data(Qt.ItemDataRole.CheckStateRole)
                    new_state = (
                        Qt.CheckState.Unchecked
                        if self._is_checked(state)
                        else Qt.CheckState.Checked
                    )
                    model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True
        return super().editorEvent(event, model, option, index)


class PluginsDialog(QDialog):
    """Manage loaded plugins: name / enabled / path / info / order."""

    def __init__(self, main_window: "MitmGuiMainWindow", parent=None):
        super().__init__(parent)
        self._win = main_window
        self.setWindowTitle("Plugins")
        self.setWindowIcon(_make_icon("plugins", "#7B1FA2"))
        self.resize(820, 420)

        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Status", "Name", "Path", "Info", "Order"]
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        # Stretch the Info column so Order (last column) keeps its tiny width
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(10)
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 140)
        self._table.setColumnWidth(2, 208)  # path: reduced by 20%
        # order: wide enough for at least 8 English characters
        order_w = self._table.fontMetrics().horizontalAdvance("12345678") + 20
        self._table.setColumnWidth(4, order_w)
        self._table.setItemDelegateForColumn(0, _CenteredCheckDelegate(self._table))
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_clicked)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_clicked)
        up_btn = QPushButton("\u2191")
        up_btn.setToolTip("Move selected plugin up (runs earlier)")
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn = QPushButton("\u2193")
        down_btn.setToolTip("Move selected plugin down (runs later)")
        down_btn.clicked.connect(lambda: self._move(1))
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._cancel_clicked)
        btn_row.addWidget(load_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(up_btn)
        btn_row.addWidget(down_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    # ── refresh ──

    @staticmethod
    def _display_path(path: str) -> str:
        """Show a path inside the current ``plugins`` directory as relative."""
        plugins_dir = os.path.abspath(os.path.join(os.getcwd(), "plugins"))
        abs_path = os.path.abspath(path)
        try:
            if os.path.commonpath([abs_path, plugins_dir]) == plugins_dir:
                return os.path.relpath(abs_path, plugins_dir)
        except ValueError:
            pass
        return path

    def refresh(self) -> None:
        addon = self._win._master.plugins_addon
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for i, p in enumerate(addon.plugins):
            row = self._table.rowCount()
            self._table.insertRow(row)
            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            chk.setCheckState(
                Qt.CheckState.Checked if p.enabled else Qt.CheckState.Unchecked
            )
            chk.setData(Qt.ItemDataRole.UserRole, p.name)
            self._table.setItem(row, 0, chk)
            self._table.setItem(row, 1, QTableWidgetItem(p.name))
            self._table.setItem(row, 2, QTableWidgetItem(self._display_path(p.path)))
            self._table.setItem(row, 3, QTableWidgetItem(p.info))
            self._table.setItem(row, 4, QTableWidgetItem(str(i + 1)))
        self._table.blockSignals(False)

    def _current_plugin(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 1)
        return item.text() if item else None

    def _on_item_changed(self, item) -> None:
        if item.column() == 0:
            name = item.data(Qt.ItemDataRole.UserRole)
            if name:
                enabled = item.checkState() == Qt.CheckState.Checked
                self._win._master.plugins_addon.set_enabled(name, enabled)
                self.refresh()

    # ── actions ──

    def _load_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Plugin", "", "Python Files (*.py)"
        )
        if not path:
            return
        try:
            self._win._master.plugins_addon.load_plugin(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Load Plugin", f"Failed to load plugin:\n{e}")
        self.refresh()

    def _remove_clicked(self) -> None:
        name = self._current_plugin()
        if name is None:
            return
        self._win._master.plugins_addon.unload_plugin(name)
        self.refresh()

    def _move(self, delta: int) -> None:
        name = self._current_plugin()
        if name is None:
            return
        self._win._master.plugins_addon.move(name, delta)
        self.refresh()

    def _save_clicked(self) -> None:
        """Persist the current plugin settings (enabled flags + order)."""
        self._win._master.plugins_addon.save()
        self.accept()

    def _cancel_clicked(self) -> None:
        """Discard unsaved in-memory changes and just close the window."""
        self._win._master.plugins_addon.reload_from_disk()
        self.reject()


class _DnsResolveWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, resolver, server: str, domain: str, qtype: str, method: str):
        super().__init__()
        self._resolver = resolver
        self._server = server
        self._domain = domain
        self._qtype = qtype
        self._method = method

    def run(self) -> None:
        try:
            if self._method == "DOH":
                answers = self._resolver._resolve_doh(self._server, self._domain, self._qtype)
            else:
                answers = self._resolver._resolve_wire(
                    self._server, self._domain, self._qtype, tcp=self._method == "TCP"
                )
            self.finished.emit(answers)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ToolsDialog(QDialog):
    """Utility tools window: DNS, Unicode escapes, Base64, and URL codec."""

    _DNS_TYPES = ["A", "CNAME", "AAAA", "MX", "NS", "TXT", "SOA", "PTR"]
    _DNS_METHODS = ["UDP", "TCP", "DOH"]
    _DNS_TYPE_CODES = {
        "A": 1,
        "NS": 2,
        "CNAME": 5,
        "SOA": 6,
        "PTR": 12,
        "MX": 15,
        "TXT": 16,
        "AAAA": 28,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tools")
        self.setWindowIcon(_make_icon("tools", "#455A64"))
        self.resize(1230, 630)
        self._dns_thread = None
        self._dns_worker = None
        self._dns_request = None

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_dns_tab(), "DNS")
        tabs.addTab(self._build_native_tab(), "Native2String")
        tabs.addTab(self._build_base64_tab(), "Base64")
        tabs.addTab(self._build_url_tab(), "URL")
        layout.addWidget(tabs)

    def _build_dns_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form_row = QHBoxLayout()
        self._dns_server = QComboBox()
        self._dns_server.setEditable(True)
        self._dns_server.addItems([
            "223.5.5.5",
            "223.6.6.6",
            "114.114.114.114",
            "119.29.29.29",
            "180.76.76.76",
            "1.2.4.8",
            "117.50.10.10",
            "8.8.8.8",
        ])
        self._dns_server.setCurrentText("223.5.5.5")
        self._dns_server.setToolTip("DNS Server, e.g. 223.5.5.5 or https://dns.alidns.com/resolve")
        self._dns_type = QComboBox()
        self._dns_type.addItems(self._DNS_TYPES)
        self._dns_method = QComboBox()
        self._dns_method.addItems(self._DNS_METHODS)
        self._dns_domain = QLineEdit()
        self._dns_domain.setPlaceholderText("example.com")
        self._dns_resolve_btn = QPushButton("Resolve")
        self._dns_resolve_btn.clicked.connect(self._resolve_dns)

        form_row.addWidget(QLabel("Server"))
        form_row.addWidget(self._dns_server, 2)
        form_row.addWidget(QLabel("Type"))
        form_row.addWidget(self._dns_type)
        form_row.addWidget(QLabel("Method"))
        form_row.addWidget(self._dns_method)
        form_row.addWidget(QLabel("Domain"))
        form_row.addWidget(self._dns_domain, 2)
        form_row.addWidget(self._dns_resolve_btn)
        layout.addLayout(form_row)

        self._dns_output = QPlainTextEdit()
        self._dns_output.setReadOnly(True)
        self._dns_output.setFont(QFont("Consolas", 10))
        layout.addWidget(self._dns_output, 1)
        return page

    def _build_native_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._native_ignore_latin = QCheckBox("Ignore latin characters (do not convert)")
        layout.addWidget(self._native_ignore_latin)
        left, right, mid = self._codec_widgets()
        self._native_left = left
        self._native_right = right
        to_native = QPushButton("->")
        to_native.setToolTip("String to Unicode escape")
        to_native.clicked.connect(self._string_to_native)
        to_string = QPushButton("<-")
        to_string.setToolTip("Unicode escape to string")
        to_string.clicked.connect(self._native_to_string)
        mid.addStretch(1)
        mid.addWidget(to_native)
        mid.addWidget(to_string)
        mid.addStretch(1)
        layout.addLayout(self._codec_layout(left, right, mid, "String", "Native"), 1)
        return page

    def _build_base64_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        left, right, mid = self._codec_widgets()
        self._base64_left = left
        self._base64_right = right
        self._base64_encode_padding = QCheckBox("Padding")
        self._base64_encode_padding.setChecked(True)
        self._base64_encode_lines = QCheckBox("Lines")
        self._base64_decode_strict = QCheckBox("Strict")
        self._base64_decode_lines = QCheckBox("Lines")
        self._base64_decode_lines.setChecked(True)
        encode_btn = QPushButton("Encode")
        encode_btn.clicked.connect(self._base64_encode)
        decode_btn = QPushButton("Decode")
        decode_btn.clicked.connect(self._base64_decode)
        mid.addStretch(1)
        mid.addWidget(QLabel("Encode"))
        mid.addWidget(self._base64_encode_padding)
        mid.addWidget(self._base64_encode_lines)
        mid.addWidget(encode_btn)
        mid.addSpacing(16)
        mid.addWidget(QLabel("Decode"))
        mid.addWidget(self._base64_decode_strict)
        mid.addWidget(self._base64_decode_lines)
        mid.addWidget(decode_btn)
        mid.addStretch(1)
        layout.addLayout(self._codec_layout(left, right, mid, "Plain Text", "Base64"), 1)
        return page

    def _build_url_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        left, right, mid = self._codec_widgets()
        self._url_left = left
        self._url_right = right
        self._url_encode_full = QCheckBox("Full")
        self._url_encode_lines = QCheckBox("Lines")
        self._url_decode_lines = QCheckBox("Lines")
        self._url_decode_lines.setChecked(True)
        encode_btn = QPushButton("Encode")
        encode_btn.clicked.connect(self._url_encode)
        decode_btn = QPushButton("Decode")
        decode_btn.clicked.connect(self._url_decode)
        mid.addStretch(1)
        mid.addWidget(QLabel("Encode"))
        mid.addWidget(self._url_encode_full)
        mid.addWidget(self._url_encode_lines)
        mid.addWidget(encode_btn)
        mid.addSpacing(16)
        mid.addWidget(QLabel("Decode"))
        mid.addWidget(self._url_decode_lines)
        mid.addWidget(decode_btn)
        mid.addStretch(1)
        layout.addLayout(self._codec_layout(left, right, mid, "Plain Text", "URL Encoded"), 1)
        return page

    def _codec_widgets(self):
        left = QPlainTextEdit()
        right = QPlainTextEdit()
        for editor in (left, right):
            editor.setFont(QFont("Consolas", 10))
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mid = QVBoxLayout()
        return left, right, mid

    def _codec_layout(self, left: QPlainTextEdit, right: QPlainTextEdit, mid: QVBoxLayout, left_label: str, right_label: str) -> QHBoxLayout:
        left_col = QVBoxLayout()
        left_col.addWidget(QLabel(left_label))
        left_col.addWidget(left, 1)
        right_col = QVBoxLayout()
        right_col.addWidget(QLabel(right_label))
        right_col.addWidget(right, 1)
        layout = QHBoxLayout()
        layout.addLayout(left_col, 1)
        layout.addLayout(mid)
        layout.addLayout(right_col, 1)
        return layout

    def _resolve_dns(self) -> None:
        domain = self._dns_domain.text().strip().rstrip(".")
        server = self._dns_server.currentText().strip()
        qtype = self._dns_type.currentText()
        method = self._dns_method.currentText()
        if not domain:
            self._dns_output.setPlainText("Please enter a domain.")
            return
        if not server:
            self._dns_output.setPlainText("Please enter a DNS server.")
            return
        if self._dns_thread is not None and self._dns_thread.isRunning():
            return

        self._dns_request = (domain, server, qtype, method)
        self._dns_resolve_btn.setEnabled(False)
        self._dns_output.setPlainText("Resolving...")
        self._dns_thread = QThread(self)
        self._dns_worker = _DnsResolveWorker(self, server, domain, qtype, method)
        self._dns_worker.moveToThread(self._dns_thread)
        self._dns_thread.started.connect(self._dns_worker.run)
        self._dns_worker.finished.connect(self._dns_query_finished)
        self._dns_worker.failed.connect(self._dns_query_failed)
        self._dns_worker.finished.connect(self._dns_worker.deleteLater)
        self._dns_worker.failed.connect(self._dns_worker.deleteLater)
        self._dns_worker.finished.connect(self._dns_thread.quit)
        self._dns_worker.failed.connect(self._dns_thread.quit)
        self._dns_thread.finished.connect(self._dns_thread_finished)
        self._dns_thread.start()

    def _dns_query_finished(self, answers: list[str]) -> None:
        if self._dns_request is None:
            return
        domain, server, qtype, method = self._dns_request
        lines = [
            f"Domain: {domain}",
            f"Type: {qtype}",
            f"Method: {method}",
            f"Server: {server}",
            "",
            "Answers:",
        ]
        lines.extend(f"  {item}" for item in answers) if answers else lines.append("  (no answers)")
        self._dns_output.setPlainText("\n".join(lines))

    def _dns_query_failed(self, error: str) -> None:
        self._dns_output.setPlainText(f"DNS query failed:\n{error}")

    def _dns_thread_finished(self) -> None:
        thread = self._dns_thread
        self._dns_worker = None
        self._dns_thread = None
        self._dns_request = None
        self._dns_resolve_btn.setEnabled(True)
        if thread is not None:
            thread.deleteLater()

    def _resolve_doh(self, server: str, domain: str, qtype: str) -> list[str]:
        url = self._doh_url(server)
        packet = self._build_dns_query(domain, self._DNS_TYPE_CODES[qtype])
        req = urllib.request.Request(
            url,
            data=packet,
            headers={
                "Accept": "application/dns-message",
                "Content-Type": "application/dns-message",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return self._parse_dns_response(resp.read())

    def _doh_url(self, server: str) -> str:
        endpoint = server if server.startswith(("http://", "https://")) else f"https://{server}"
        parsed = urllib.parse.urlparse(endpoint)
        path = parsed.path.rstrip("/")
        if not path:
            path = "/dns-query"
        elif path != "/dns-query":
            path = f"{path}/dns-query"
        return urllib.parse.urlunparse(parsed._replace(path=path, query=""))

    def _resolve_wire(self, server: str, domain: str, qtype: str, tcp: bool) -> list[str]:
        qtype_code = self._DNS_TYPE_CODES[qtype]
        packet = self._build_dns_query(domain, qtype_code)
        host, port = self._split_host_port(server, 53)
        if tcp:
            with socket.create_connection((host, port), timeout=8) as sock:
                sock.sendall(struct.pack("!H", len(packet)) + packet)
                header = self._recvall(sock, 2)
                size = struct.unpack("!H", header)[0]
                data = self._recvall(sock, size)
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(8)
                sock.sendto(packet, (host, port))
                data, _ = sock.recvfrom(4096)
        return self._parse_dns_response(data)

    def _split_host_port(self, value: str, default_port: int) -> tuple[str, int]:
        if value.startswith("[") and "]" in value:
            host, _, tail = value[1:].partition("]")
            return host, int(tail[1:]) if tail.startswith(":") else default_port
        if value.count(":") == 1:
            host, port = value.rsplit(":", 1)
            return host, int(port)
        return value, default_port

    def _build_dns_query(self, domain: str, qtype: int) -> bytes:
        query_id = random.randrange(0, 65536)
        header = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0)
        qname = b"".join(bytes([len(part)]) + part.encode("idna") for part in domain.split(".")) + b"\0"
        return header + qname + struct.pack("!HH", qtype, 1)

    def _parse_dns_response(self, data: bytes) -> list[str]:
        if len(data) < 12:
            raise ValueError("Invalid DNS response.")
        _qid, flags, qdcount, ancount, _nscount, _arcount = struct.unpack("!HHHHHH", data[:12])
        rcode = flags & 0x000F
        if rcode:
            raise ValueError(f"DNS server returned rcode {rcode}.")
        offset = 12
        for _ in range(qdcount):
            _, offset = self._read_dns_name(data, offset)
            offset += 4
        answers = []
        for _ in range(ancount):
            name, offset = self._read_dns_name(data, offset)
            rtype, _rclass, ttl, rdlen = struct.unpack("!HHIH", data[offset:offset + 10])
            offset += 10
            rdata_offset = offset
            rdata = data[offset:offset + rdlen]
            offset += rdlen
            answers.append(self._format_wire_answer(data, name, rtype, ttl, rdata, rdata_offset))
        return answers

    def _read_dns_name(self, data: bytes, offset: int) -> tuple[str, int]:
        labels = []
        jumped = False
        end_offset = offset
        seen = set()
        while True:
            if offset >= len(data):
                raise ValueError("Invalid DNS name.")
            length = data[offset]
            if length & 0xC0 == 0xC0:
                if offset + 1 >= len(data):
                    raise ValueError("Invalid DNS pointer.")
                pointer = ((length & 0x3F) << 8) | data[offset + 1]
                if pointer in seen:
                    raise ValueError("DNS pointer loop.")
                seen.add(pointer)
                if not jumped:
                    end_offset = offset + 2
                offset = pointer
                jumped = True
                continue
            if length == 0:
                if not jumped:
                    end_offset = offset + 1
                break
            offset += 1
            labels.append(self._decode_dns_label(data[offset:offset + length]))
            offset += length
        return ".".join(labels), end_offset

    def _decode_dns_label(self, label: bytes) -> str:
        try:
            return label.decode("idna")
        except UnicodeError:
            return label.decode("ascii", errors="replace")

    def _format_wire_answer(self, packet: bytes, name: str, rtype: int, ttl: int, rdata: bytes, rdata_offset: int) -> str:
        type_name = next((k for k, v in self._DNS_TYPE_CODES.items() if v == rtype), str(rtype))
        if rtype == 1 and len(rdata) == 4:
            value = socket.inet_ntop(socket.AF_INET, rdata)
        elif rtype == 28 and len(rdata) == 16:
            value = socket.inet_ntop(socket.AF_INET6, rdata)
        elif rtype in (2, 5, 12):
            value, _ = self._read_dns_name(packet, rdata_offset)
        elif rtype == 15 and len(rdata) >= 3:
            pref = struct.unpack("!H", rdata[:2])[0]
            host, _ = self._read_dns_name(packet, rdata_offset + 2)
            value = f"{pref} {host}"
        elif rtype == 16:
            parts = []
            pos = 0
            while pos < len(rdata):
                length = rdata[pos]
                pos += 1
                parts.append(rdata[pos:pos + length].decode("utf-8", errors="replace"))
                pos += length
            value = " ".join(parts)
        else:
            value = rdata.hex(" ")
        return f"{name or '.'}  TTL={ttl}  TYPE={type_name}  {value}"

    def _recvall(self, sock: socket.socket, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ValueError("DNS TCP connection closed early.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _native_to_string(self) -> None:
        try:
            self._native_left.setPlainText(bytes(self._native_right.toPlainText(), "utf-8").decode("unicode_escape"))
        except UnicodeDecodeError as e:
            self._native_left.setPlainText(f"Decode failed:\n{e}")

    def _string_to_native(self) -> None:
        text = self._native_left.toPlainText()
        ignore_latin = self._native_ignore_latin.isChecked()
        converted = []
        for ch in text:
            code = ord(ch)
            if ignore_latin and code <= 0x7F:
                converted.append(ch)
            elif code <= 0xFFFF:
                converted.append(f"\\u{code:04x}")
            else:
                converted.append(f"\\U{code:08x}")
        self._native_right.setPlainText("".join(converted))

    def _base64_encode(self) -> None:
        padding = self._base64_encode_padding.isChecked()
        lines = self._base64_encode_lines.isChecked()
        def encode_one(value: str) -> str:
            encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
            return encoded if padding else encoded.rstrip("=")
        text = self._base64_left.toPlainText()
        result = "\n".join(encode_one(line) for line in text.splitlines()) if lines else encode_one(text)
        self._base64_right.setPlainText(result)

    def _base64_decode(self) -> None:
        strict = self._base64_decode_strict.isChecked()
        lines = self._base64_decode_lines.isChecked()
        def decode_one(value: str) -> str:
            raw = value.strip()
            if not strict:
                raw += "=" * (-len(raw) % 4)
            return base64.b64decode(raw, validate=strict).decode("utf-8", errors="replace")
        try:
            text = self._base64_right.toPlainText()
            result = "\n".join(decode_one(line) for line in text.splitlines()) if lines else decode_one(text)
            self._base64_left.setPlainText(result)
        except (binascii.Error, UnicodeDecodeError) as e:
            self._base64_left.setPlainText(f"Decode failed:\n{e}")

    def _url_encode(self) -> None:
        full = self._url_encode_full.isChecked()
        lines = self._url_encode_lines.isChecked()
        def encode_one(value: str) -> str:
            if full:
                return "".join(f"%{byte:02X}" for byte in value.encode("utf-8"))
            return urllib.parse.quote(value, safe="-._~")
        text = self._url_left.toPlainText()
        result = "\n".join(encode_one(line) for line in text.splitlines()) if lines else encode_one(text)
        self._url_right.setPlainText(result)

    def _url_decode(self) -> None:
        lines = self._url_decode_lines.isChecked()
        def decode_one(value: str) -> str:
            return urllib.parse.unquote_plus(value)
        text = self._url_right.toPlainText()
        result = "\n".join(decode_one(line) for line in text.splitlines()) if lines else decode_one(text)
        self._url_left.setPlainText(result)


class MitmGuiMainWindow(QMainWindow):
    """Main window for mitmgui, styled after Fiddler Classic."""

    def __init__(self, proxy_master: MitmGuiMaster, config: AppConfig):
        super().__init__()
        self._config = config
        self._master = proxy_master
        self._bridge = _SignalBridge()
        self._bridge.flow_added.connect(self._on_flow_added)
        self._bridge.flow_updated.connect(self._on_flow_updated)

        self._selected_flow = None
        self._edit_mode = False  # F2 toggle
        self._compose_mode = False  # E key: compose new request
        self._flow_state: dict[str, str] = {}  # flow_id -> "edit" | "waiting_response"
        self._breakpoint_mode = False  # F11 toggle: all flows become pending
        self._breakpoint_rules: list[dict] = []  # Shift+F11 rule-based breakpoints
        self._auto_roll = True  # Ctrl+E toggle: auto-scroll to bottom on new flows
        self._detail_windows: list[FlowDetailDialog] = []  # prevent GC
        self._logs_dialog: "LogsDialog | None" = None  # single instance Logs window
        self._plugins_dialog: "PluginsDialog | None" = None  # single instance
        self._tools_dialog: "ToolsDialog | None" = None  # single instance

        # Plugins run on the proxy thread; bridge their Logs/New Session calls
        # back to the GUI thread.
        self._plugin_bridge = _PluginBridge()
        self._plugin_bridge.log.connect(self._append_plugin_log)
        self._plugin_bridge.new_session.connect(self._open_new_session_dialog)
        self._plugin_bridge.set_flow_color.connect(self._set_plugin_flow_color)
        self._plugin_bridge.set_flow_info.connect(self._set_plugin_flow_info)
        self._master.plugins_addon.bridge = self._plugin_bridge

        # Frameless window: the menu bar strip doubles as the title bar
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(900, 600)

        self._drag_offset: QPoint | None = None          # title-bar drag state
        self._resize_edge: str | None = None             # Qt-level edge resize state
        self._resize_start_global = QPoint()
        self._resize_start_geom = QRect()
        self._normal_geo: QRect | None = None            # geometry to restore to after maximize
        self._mouse_grabbed = False                      # system-menu Move/Size loop
        self._dwm_shadow_enabled = False                 # DWM shadow applied once on first show
        self.setMouseTracking(True)  # hover feedback for edge resizing
        QApplication.instance().installEventFilter(self)  # keep edge cursor in sync over child widgets

        self.setWindowTitle("mitmgui - mitmproxy GUI")
        self.setWindowIcon(_make_icon("proxy", "#1565C0"))
        self._restore_window_geometry()
        self._start_maximized = self._config.window_maximized

        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._setup_shortcuts()
        self._setup_frame_overlay()

        self._master.start()
        self._master.view.sig_view_add.connect(self._on_proxy_flow_add)
        self._master.view.sig_view_update.connect(self._on_proxy_flow_update)

        self._proxy_toggle_action.setChecked(self._get_proxy_enabled())
        self._update_proxy_icon()

        # Apply saved filter rules on startup
        QTimer.singleShot(500, self._apply_filters)

    # ── Shortcuts ──

    def _setup_shortcuts(self) -> None:
        self._shortcuts = []  # Keep references to prevent GC
        act = QAction("Replay", self, shortcut=QKeySequence("R"), triggered=self._replay_all_selected)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        act = QAction(
            "Replay Sequentially", self,
            shortcut=QKeySequence("Shift+R"),
            triggered=self._open_replay_sequentially,
        )
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        act = QAction("Compose", self, shortcut=QKeySequence("E"), triggered=self._compose_request)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        act = QAction("Edit", self, shortcut=QKeySequence("F2"), triggered=self._toggle_edit_mode)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # Ctrl+1..9: color selected sessions, Ctrl+0: reset
        _CTRL_COLORS = [
            (Qt.Key.Key_0, None),                  # reset
            (Qt.Key.Key_1, QColor("#FFAAAA")),      # light red
            (Qt.Key.Key_2, QColor("#FFCCCC")),      # lighter red
            (Qt.Key.Key_3, QColor("#FFEEEE")),      # lightest red
            (Qt.Key.Key_4, QColor("#AAFFAA")),      # light green
            (Qt.Key.Key_5, QColor("#CCFFCC")),      # lighter green
            (Qt.Key.Key_6, QColor("#EEFFEE")),      # lightest green
            (Qt.Key.Key_7, QColor("#AAAADD")),      # light blue
            (Qt.Key.Key_8, QColor("#CCCCFF")),      # lighter blue
            (Qt.Key.Key_9, QColor("#EEEEFF")),      # lightest blue
        ]
        for key, color in _CTRL_COLORS:
            act = QAction(
                f"Color_{key}", self,
                shortcut=QKeySequence(Qt.Modifier.CTRL | key),
                triggered=lambda _checked, c=color: self._color_selected(c),
            )
            act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            self._shortcuts.append(act)
            self.addAction(act)

        # F12: toggle system proxy (same as clicking Capture)
        act = QAction("ProxyToggle", self, shortcut=QKeySequence("F12"), triggered=self._f12_toggle_proxy)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # F11: toggle breakpoint mode
        act = QAction("Breakpoint", self, shortcut=QKeySequence("F11"), triggered=self._f11_toggle_breakpoint)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # Shift+F11: open breakpoint rules dialog
        act = QAction("BreakpointRules", self, shortcut=QKeySequence("Shift+F11"), triggered=self._shift_f11_breakpoint_rules)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # Ctrl+F: find sessions
        act = QAction("Find", self, shortcut=QKeySequence("Ctrl+F"), triggered=self._open_find_dialog)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # Ctrl+U: copy selected session URLs (newline-separated)
        act = QAction("CopyURLs", self, shortcut=QKeySequence("Ctrl+U"), triggered=self._copy_selected_urls)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # Ctrl+R: open Edit - Custom Rules
        act = QAction("CustomRules", self, shortcut=QKeySequence("Ctrl+R"), triggered=self._open_custom_rules)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

        # Ctrl+E: toggle auto-roll
        act = QAction("ToggleAutoRoll", self, shortcut=QKeySequence("Ctrl+E"), triggered=self._toggle_auto_roll)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcuts.append(act)
        self.addAction(act)

    # ── Menu bar ──

    def _apply_session_list_font_size(self, size: int | None = None) -> None:
        if size is None:
            size = self._config.session_list_font_size
        font = QFont(self._session_table.font())
        font.setPointSize(int(size))
        self._session_table.setFont(font)
        self._session_table.viewport().setFont(font)
        self._session_table.horizontalHeader().setFont(font)
        self._session_table.verticalHeader().setFont(font)
        # Keep row height and header height in sync with the font, so the
        # list stays readable when the font is scaled very large or small.
        metrics = QFontMetrics(font)
        self._session_table.verticalHeader().setDefaultSectionSize(metrics.height() + 10)
        self._session_table.horizontalHeader().setMinimumHeight(metrics.height() + 10)
        self._session_table.horizontalHeader().setFixedHeight(metrics.height() + 12)
        self._session_table.viewport().update()

    def _setup_menu_bar(self) -> None:
        menubar = _FramelessMenuBar(self)
        menubar.setObjectName("mainMenuBar")
        menubar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._menu_bar = menubar

        file_menu = menubar.addMenu("&File")
        save_sessions_action = QAction("Save Sessions...", self)
        save_sessions_action.triggered.connect(self._save_sessions)
        file_menu.addAction(save_sessions_action)
        load_sessions_action = QAction("Load Sessions...", self)
        load_sessions_action.triggered.connect(self._load_sessions)
        file_menu.addAction(load_sessions_action)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("&Edit")
        clear_action = QAction("&Clear Session List", self)
        clear_action.setShortcut(QKeySequence("Ctrl+X"))
        clear_action.triggered.connect(self._clear_sessions)
        edit_menu.addAction(clear_action)
        edit_menu.addSeparator()

        # Themes submenu (radio group, applied via QSS)
        themes_menu = edit_menu.addMenu("&Themes")
        self._theme_group = QActionGroup(self)
        current_theme = self._config.theme
        for theme_id, theme_name in themes.THEMES.items():
            act = QAction(theme_name, self)
            act.setCheckable(True)
            act.setChecked(theme_id == current_theme)
            act.setData(theme_id)
            act.triggered.connect(self._on_theme_selected)
            self._theme_group.addAction(act)
            themes_menu.addAction(act)
        edit_menu.addSeparator()

        rules_action = QAction("Custom Rules", self)
        rules_action.triggered.connect(self._open_custom_rules)
        edit_menu.addAction(rules_action)

        view_menu = menubar.addMenu("&View")
        capture_action = QAction("&Capture Traffic", self)
        capture_action.setCheckable(True)
        capture_action.setChecked(True)
        view_menu.addAction(capture_action)

        tools_menu = menubar.addMenu("&Tools")
        hosts_action = QAction("&Hosts", self)
        hosts_action.triggered.connect(self._open_hosts_remapping)
        tools_menu.addAction(hosts_action)
        tools_menu.addSeparator()
        self._options_action = QAction("&Options...", self)
        self._options_action.triggered.connect(self._open_options)
        tools_menu.addAction(self._options_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About mitmgui", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        # ── Unified strip: menus | title (draggable) | window controls ──
        title_bar = _TitleBar(self)
        title_bar.setObjectName("titleBar")
        self._title_bar = title_bar
        lay = QHBoxLayout(title_bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(menubar)

        self._title_label = QLabel(self.windowTitle(), title_bar)
        self._title_label.setObjectName("titleLabel")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setMinimumWidth(0)
        self._title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._title_label.setMouseTracking(True)  # hover feedback for edge resizing
        lay.addWidget(self._title_label, 1)

        self._btn_min = _WindowButton("min", title_bar)
        self._btn_max = _WindowButton("max", title_bar)
        self._btn_close = _WindowButton("close", title_bar)
        for b in (self._btn_min, self._btn_max, self._btn_close):
            b.setMouseTracking(True)  # hover feedback for edge resizing
        self._btn_min.clicked.connect(self.showMinimized)
        self._btn_max.clicked.connect(self._toggle_maximize)
        self._btn_close.clicked.connect(self.close)
        lay.addWidget(self._btn_min)
        lay.addWidget(self._btn_max)
        lay.addWidget(self._btn_close)

        self.setMenuWidget(title_bar)
        self._apply_title_bar_theme(self._config.theme)

    def _setup_frame_overlay(self) -> None:
        self._frame_overlay = _FrameOverlay(self)
        self._frame_overlay.setGeometry(self.rect())
        self._frame_overlay.set_dark(self._config.theme in _DARK_THEMES)
        self._frame_overlay.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        overlay = getattr(self, "_frame_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
            overlay.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        overlay = getattr(self, "_frame_overlay", None)
        if overlay is not None:
            overlay.raise_()
        if not self._dwm_shadow_enabled:
            self._dwm_shadow_enabled = True
            self._enable_dwm_shadow()
        if self._start_maximized:
            self._start_maximized = False
            self.showMaximized()

    def _enable_dwm_shadow(self) -> None:
        """Let DWM draw the real window shadow + thin outside frame border
        (the WeChat/Edge look) instead of painting them in Qt.

        The window keeps WS_THICKFRAME (which makes DWM render the shadow),
        while WM_NCCALCSIZE removes the native frame so the client area covers
        the whole window, and WM_NCHITTEST keeps native hit-testing disabled
        (Qt-level edge resizing in this file stays in charge).
        """
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            style = user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
            style = (style | _WS_THICKFRAME) & ~_WS_CAPTION
            user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, style)
            margins = _MARGINS(1, 1, 1, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                wintypes.HWND(hwnd), ctypes.byref(margins)
            )
            user32.SetWindowPos(
                wintypes.HWND(hwnd), wintypes.HWND(0), 0, 0, 0, 0,
                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_FRAMECHANGED,
            )
        except Exception:
            # Never let a WinAPI error escape: PyQt crashes the process if an
            # exception crosses a native boundary.
            pass

    def _show_about(self) -> None:
        QMessageBox.about(self, "About mitmgui", "MITMGUI Ver 1.0.0")

    def _on_theme_selected(self) -> None:
        """Apply the selected theme via QSS and persist the choice."""
        act = self.sender()
        if act is None or not act.isChecked():
            return
        theme_id = act.data()
        themes.apply_theme(QApplication.instance(), theme_id)
        # QScintilla editors draw their own colours, so refresh them too.
        for w in self.findChildren(_ScintillaTextEdit):
            w.apply_theme(theme_id)
        self._config.theme = theme_id
        self._config.save()
        self._apply_title_bar_theme(theme_id)

    # ── Toolbar ──

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._replay_action = toolbar.addAction("Replay")
        self._replay_action.setToolTip("Replay selected request (R)")
        self._replay_action.triggered.connect(self._replay_all_selected)

        toolbar.addSeparator()

        self._proxy_toggle_action = toolbar.addAction("\u25b6 Capture")
        self._proxy_toggle_action.setToolTip("Toggle system proxy")
        self._proxy_toggle_action.setCheckable(True)
        self._proxy_toggle_action.triggered.connect(self._toggle_system_proxy)
        # Fix button width so icon change does not shift position
        w = toolbar.widgetForAction(self._proxy_toggle_action)
        if w:
            w.setFixedWidth(90)

        toolbar.addSeparator()

        self._resume_action = toolbar.addAction("\u23ed Resume")
        self._resume_action.setToolTip("Resume selected flows, or all intercepted flows if none selected")
        self._resume_action.triggered.connect(self._resume_intercepted)

        toolbar.addSeparator()

        self._filter_action = toolbar.addAction("\U0001f50d Filter")
        self._filter_action.setToolTip("Edit filter rules")
        self._filter_action.triggered.connect(self._open_filter_dialog)

        self._find_action = toolbar.addAction("\U0001f52d Find")
        self._find_action.setToolTip("Find sessions (Ctrl+F)")
        self._find_action.triggered.connect(self._open_find_dialog)

        toolbar.addSeparator()

        self._auto_rule_action = toolbar.addAction("\u2699 AutoRule")
        self._auto_rule_action.setToolTip("Edit auto rules")
        self._auto_rule_action.triggered.connect(self._open_auto_rules_dialog)

        self._new_session_action = toolbar.addAction("\U0001f4dd New Session")
        self._new_session_action.setToolTip("Create and send a new HTTP request")
        self._new_session_action.triggered.connect(self._open_new_session_dialog)

        self._logs_action = toolbar.addAction("\U0001f4c4 Logs")
        self._logs_action.setToolTip("Open the logs window")
        self._logs_action.triggered.connect(self._open_logs_dialog)

        self._plugins_action = toolbar.addAction("\U0001f3e2 Plugins")
        self._plugins_action.setToolTip("Manage plugins")
        self._plugins_action.triggered.connect(self._open_plugins_dialog)

        self._tools_action = toolbar.addAction("\U0001f6e0 Tools")
        self._tools_action.setToolTip("Open utility tools")
        self._tools_action.triggered.connect(self._open_tools_dialog)

    def _update_proxy_icon(self) -> None:
        # Use fixed-width prefix so button position does not shift
        if self._proxy_toggle_action.isChecked():
            self._proxy_toggle_action.setText("\u23f8 Capture")
        else:
            self._proxy_toggle_action.setText("\u25b6 Capture")

    # ── Central widget ──

    def _setup_central_widget(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        # A thin transparent frame is kept around the content so the window can
        # still be resized by dragging its edges (Qt-level edge resize).
        m = 6
        layout.setContentsMargins(m, m, m, m)
        layout.setSpacing(0)
        central.setMouseTracking(True)

        h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left panel: session list (multi-select) ---
        self._session_table = QTableView()
        self._session_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._session_table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._session_table.setAlternatingRowColors(True)
        self._session_table.setShowGrid(False)
        self._session_table.setWordWrap(False)
        self._apply_session_list_font_size()
        session_palette = QPalette(self._session_table.palette())
        active_selection = session_palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
        active_text = session_palette.brush(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText)
        session_palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, active_selection)
        session_palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, active_text)
        self._session_table.setPalette(session_palette)
        self._session_table.verticalHeader().setVisible(False)
        self._session_table.setAutoScroll(False)  # prevent header from shifting on click

        self._session_model = SessionTableModel()
        self._sort_proxy = QSortFilterProxyModel()
        self._sort_proxy.setSourceModel(self._session_model)
        self._sort_proxy.setSortRole(Qt.ItemDataRole.UserRole)  # numeric sort for # column
        self._session_table.setModel(self._sort_proxy)

        # Dashed column separators in the header row (50% transparent)
        self._session_header = _DashedHeaderView(
            Qt.Orientation.Horizontal, self._session_table
        )
        self._session_header.set_dark(self._config.theme in _DARK_THEMES)
        self._session_table.setHorizontalHeader(self._session_header)
        # Qt6's QTableView.setSortingEnabled() does not reliably enable section
        # clicking on a custom header, so enable it explicitly here (otherwise
        # clicking a column header cannot change the sort order).
        self._session_header.setSectionsClickable(True)
        self._session_header.setSortIndicatorShown(True)

        # Sorting: click column header to sort
        self._session_table.setSortingEnabled(True)
        self._session_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        header = self._session_table.horizontalHeader()
        for col, (_, width) in enumerate(SessionTableModel.COLUMNS):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self._session_table.setColumnWidth(col, width)
        header.setStretchLastSection(True)

        self._session_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        # Double-click to view flow in a separate window
        self._session_table.doubleClicked.connect(self._on_session_double_clicked)

        # Delete key: remove selected sessions (same as right-click > Remove > Selected Sessions)
        act = QAction("RemoveSelected", self._session_table)
        act.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act.triggered.connect(self._remove_selected)
        self._session_table.addAction(act)

        # Ctrl+L: toggle lock state of selected sessions (locked sessions
        # cannot be removed via right-click > Remove or the Delete key)
        lock_act = QAction("LockSelected", self._session_table)
        lock_act.setShortcut(QKeySequence("Ctrl+L"))
        lock_act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        lock_act.triggered.connect(self._toggle_lock_selected)
        self._session_table.addAction(lock_act)

        # Right-click context menu
        self._session_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_table.customContextMenuRequested.connect(self._on_context_menu)

        # --- Right panel ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Compose bar (visible when E is pressed)
        self._compose_bar = QWidget()
        compose_hl = QHBoxLayout(self._compose_bar)
        compose_hl.setContentsMargins(4, 2, 4, 2)
        self._send_button = QPushButton("\u25b6 Send")
        self._send_button.setToolTip("Send the edited request")
        self._send_button.clicked.connect(self._send_composed_request)
        compose_hl.addWidget(self._send_button)
        self._break_response_btn = QPushButton("Break On Response")
        self._break_response_btn.setToolTip("Send and intercept response for editing")
        self._break_response_btn.clicked.connect(self._break_on_response)
        compose_hl.addWidget(self._break_response_btn)
        self._run_completion_btn = QPushButton("Run To Completion")
        self._run_completion_btn.setToolTip("Release the intercepted response to the client")
        self._run_completion_btn.clicked.connect(self._run_to_completion)
        self._run_completion_btn.setEnabled(False)
        compose_hl.addWidget(self._run_completion_btn)
        compose_hl.addStretch()
        self._cancel_compose = QPushButton("Cancel")
        self._cancel_compose.clicked.connect(self._cancel_compose_mode)
        compose_hl.addWidget(self._cancel_compose)
        self._compose_bar.setVisible(False)
        right_layout.addWidget(self._compose_bar)

        # Vertical splitter (Request | Response)
        v_splitter = QSplitter(Qt.Orientation.Vertical)

        self._request_panel = InspectorPanel(
            ["Raw", "XML", "JSON", "Hex", "WebForms", "Headers"],
            panel_type="request",
            ignore_wheel_tabs=True,
        )
        self._response_panel = InspectorPanel(
            ["Raw", "Hex", "WebView", "ImageView", "Headers", "JSON", "XML"],
            panel_type="response",
            ignore_wheel_tabs=True,
        )

        v_splitter.addWidget(self._request_panel)
        v_splitter.addWidget(self._response_panel)
        v_splitter.setSizes([400, 400])
        v_splitter.setStretchFactor(0, 1)
        v_splitter.setStretchFactor(1, 1)

        right_layout.addWidget(v_splitter)

        h_splitter.addWidget(self._session_table)
        h_splitter.addWidget(right_panel)
        # Left session table is 20% wider, space taken from the right panel
        h_splitter.setSizes([720, 560])
        h_splitter.setStretchFactor(0, 12)
        h_splitter.setStretchFactor(1, 1)

        layout.addWidget(h_splitter)

    # ── Status bar ──

    def _setup_status_bar(self) -> None:
        status = QStatusBar()
        self._status_label = QLabel(" Ready")
        status.addWidget(self._status_label)

        # Each quick-toggleable function gets its own dedicated clickable area
        self._proxy_status_label = self._make_status_area("System Proxy: OFF")
        self._proxy_status_label.clicked.connect(self._show_proxy_quick_menu)
        status.addWidget(self._proxy_status_label)

        self._autoroll_status_label = self._make_status_area("AutoRoll: OFF")
        self._autoroll_status_label.clicked.connect(self._show_autoroll_quick_menu)
        status.addWidget(self._autoroll_status_label)

        self._breakpoint_status_label = self._make_status_area("BreakPoint: OFF")
        self._breakpoint_status_label.clicked.connect(self._show_breakpoint_quick_menu)
        status.addWidget(self._breakpoint_status_label)

        self.setStatusBar(status)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(2000)

        # Apply filter rules on startup
        self._apply_filters()

    def _make_status_area(self, initial: str) -> _ClickableStatusLabel:
        """Create a visually distinct status area for one quick-toggle function."""
        label = _ClickableStatusLabel(initial)
        label.setToolTip("Left/Right click: quick settings (On/Off)")
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.setStyleSheet(
            "QLabel { padding: 0 8px; border-left: 1px solid rgba(128, 128, 128, 90); }"
        )
        return label

    def _update_status(self) -> None:
        proxy_state = "ON" if self._proxy_toggle_action.isChecked() else "OFF"
        servers = self._master.proxyserver.servers
        if not servers:
            self._status_label.setText(
                f" Proxy starting... | Sessions: {len(self._session_model._flows)}"
            )
        elif self._master.startup_errors:
            self._status_label.setText(
                f" Proxy ERROR: {self._master.startup_errors[0]}"
            )
        else:
            specs = [s.mode.full_spec for s in servers]
            self._status_label.setText(
                f" Proxy: {', '.join(specs)} | Sessions: {len(self._session_model._flows)}"
            )
        # System Proxy area
        self._proxy_status_label.setText(f" System Proxy: {proxy_state}")
        # AutoRoll area
        self._autoroll_status_label.setText(
            " AutoRoll: On" if self._auto_roll else " AutoRoll: Off"
        )
        # BreakPoint area
        if self._breakpoint_rules:
            self._breakpoint_status_label.setText(" BreakPoint: Rule")
        elif self._breakpoint_mode:
            self._breakpoint_status_label.setText(" BreakPoint: On")
        else:
            self._breakpoint_status_label.setText(" BreakPoint: Off")

    def _show_proxy_quick_menu(self) -> None:
        """Quick settings for the System Proxy status area (left/right click)."""
        menu = QMenu(self)
        on_act = menu.addAction("System Proxy: On")
        off_act = menu.addAction("System Proxy: Off")
        on_act.setCheckable(True)
        off_act.setCheckable(True)
        current = self._proxy_toggle_action.isChecked()
        on_act.setChecked(current)
        off_act.setChecked(not current)
        chosen = menu.exec(
            self._proxy_status_label.mapToGlobal(QPoint(0, -menu.sizeHint().height()))
        )
        if chosen is on_act and not current:
            self._toggle_system_proxy(True)
        elif chosen is off_act and current:
            self._toggle_system_proxy(False)

    def _show_autoroll_quick_menu(self) -> None:
        """Quick settings for the AutoRoll status area (left/right click)."""
        menu = QMenu(self)
        on_act = menu.addAction("AutoRoll: On")
        off_act = menu.addAction("AutoRoll: Off")
        on_act.setCheckable(True)
        off_act.setCheckable(True)
        current = self._auto_roll
        on_act.setChecked(current)
        off_act.setChecked(not current)
        chosen = menu.exec(
            self._autoroll_status_label.mapToGlobal(QPoint(0, -menu.sizeHint().height()))
        )
        if chosen is on_act and not current:
            self._auto_roll = True
            self._update_status()
        elif chosen is off_act and current:
            self._auto_roll = False
            self._update_status()

    def _show_breakpoint_quick_menu(self) -> None:
        """Quick settings for the BreakPoint status area (left/right click)."""
        menu = QMenu(self)
        on_act = menu.addAction("BreakPoint: On")
        off_act = menu.addAction("BreakPoint: Off")
        on_act.setCheckable(True)
        off_act.setCheckable(True)
        current = self._breakpoint_mode or bool(self._breakpoint_rules)
        on_act.setChecked(current)
        off_act.setChecked(not current)
        chosen = menu.exec(
            self._breakpoint_status_label.mapToGlobal(QPoint(0, -menu.sizeHint().height()))
        )
        if chosen is on_act and not current:
            self._breakpoint_mode = True
            self._breakpoint_rules = []
            self._master.breakpoint_req_intercept.breakpoint_mode = True
            self._master.breakpoint_req_intercept.breakpoint_rules = []
            self._update_status()
        elif chosen is off_act and current:
            self._breakpoint_mode = False
            self._breakpoint_rules = []
            self._master.breakpoint_req_intercept.breakpoint_mode = False
            self._master.breakpoint_req_intercept.breakpoint_rules = []
            self._release_breakpoint_intercepts()
            self._update_status()

    # ── Keyboard shortcuts ──

    def _get_selected_flows(self) -> list:
        """Return all selected flows, resolving through sort proxy."""
        flows = []
        for idx in self._session_table.selectionModel().selectedRows():
            source_idx = self._sort_proxy.mapToSource(idx)
            flow = self._session_model.get_flow(source_idx.row())
            if flow is not None:
                flows.append(flow)
        return flows

    def _copy_selected_urls(self) -> None:
        """Copy URLs of all selected flows to clipboard, newline-separated."""
        flows = self._get_selected_flows()
        if not flows:
            return
        urls = []
        for flow in flows:
            try:
                urls.append(flow.request.pretty_url)
            except Exception:
                urls.append(str(flow.request.url))
        QApplication.clipboard().setText("\n".join(urls))

    def _toggle_auto_roll(self) -> None:
        """Toggle auto-roll mode."""
        self._auto_roll = not self._auto_roll
        self._update_status()

    def _select_flow(self, flow) -> None:
        """Select a specific flow in the session table."""
        try:
            row = self._session_model._flows.index(flow)
        except ValueError:
            return
        proxy_idx = self._sort_proxy.mapFromSource(self._session_model.index(row, 0))
        self._session_table.selectRow(proxy_idx.row())
        self._session_table.scrollTo(proxy_idx)

    def _compose_request(self) -> None:
        """Clone selected flow, add to session list, and enter edit mode."""
        if self._selected_flow is None:
            return
        new_flow = self._selected_flow.copy()
        new_flow.response = None
        new_flow.intercepted = False  # copy preserves intercepted but not _resume_event
        # Preserve hosts-remapping metadata so the original hostname is kept
        # during edit-and-replay (flow.copy() loses dynamic attributes).
        for attr in ("_original_host", "_hosts_remapped"):
            if hasattr(self._selected_flow, attr):
                setattr(new_flow, attr, getattr(self._selected_flow, attr))
        # Add to session list immediately so it appears before editing
        self._session_model.add_flow(new_flow)
        self._flow_state[str(new_flow.id)] = "edit"
        self._compose_mode = True
        self._compose_bar.setVisible(True)
        self._request_panel.set_editable(True)
        self._request_panel.populate_request(new_flow)
        self._response_panel.populate_response(new_flow)
        self._selected_flow = new_flow
        # Select the new row in the table
        self._select_flow(new_flow)

    def _send_composed_request(self) -> None:
        """Apply edits and send the composed request (no response interception)."""
        if not self._compose_mode or self._selected_flow is None:
            return
        flow = self._selected_flow
        fid = str(flow.id)
        self._request_panel.apply_request_edits(flow)
        self._sync_content_length(flow, is_request=True)

        in_breakpoint = self._breakpoint_mode or (
            self._breakpoint_rules and self._match_breakpoint_rules(flow)
        )

        if flow.intercepted:
            # Resume the intercepted flow on the proxy event loop. The proxy
            # forwards the (edited) request to the server and delivers the
            # response back to the ORIGINAL client connection. Killing then
            # replaying would orphan that connection (the replay answers a
            # mock client), which is why Send always failed in breakpoint mode.
            if self._master._loop:
                self._master._loop.call_soon_threadsafe(flow.resume)
        else:
            # Replay And Edit flow: replay to send to server.
            if in_breakpoint:
                self._master.breakpoint_req_intercept.response_only_ids.add(fid)
            self._master.view.add([flow])
            self._master.replay_flow(flow)

        # Send always exits compose mode — response is NOT intercepted.
        self._flow_state.pop(fid, None)
        self._cancel_compose_mode()

    def _cancel_compose_mode(self) -> None:
        self._compose_mode = False
        self._compose_bar.setVisible(False)
        self._request_panel.set_editable(False)
        self._response_panel.set_editable(False)

    def _release_breakpoint_intercepts(self) -> None:
        """Resume every flow intercepted by BreakPoint (mode or rules).

        Called on the proxy event loop via call_soon_threadsafe because
        flow.resume() touches asyncio state. Used when BreakPoint is turned
        off so no traffic is left stuck / released one at a time.
        """
        master = self._master
        if master._loop:
            master._loop.call_soon_threadsafe(
                master.breakpoint_req_intercept.release_all
            )

    def _resume_intercepted(self) -> None:
        """Resume intercepted flows.

        If rows are selected, only the selected flows are resumed; otherwise
        every intercepted flow known to the proxy is resumed. Each resumed
        flow is forwarded by the proxy to its server and the response is
        delivered back to the original client connection, completing the
        whole flow.
        """
        master = self._master
        compose_flow = self._selected_flow if self._compose_mode else None

        selected = self._get_selected_flows()
        if selected:
            flows = [
                f for f in selected
                if getattr(f, "intercepted", False) and getattr(f, "request", None)
            ]
            if not flows:
                return
        else:
            # No selection — resume all pending (intercepted) flows known to
            # the proxy.  We must NOT use the session model here: it can miss
            # intercepted flows (filter rules hide them from the table, or the
            # GUI has not processed their add-signal yet), which would leave
            # them stuck in breakpoint mode.
            flows = None

        # If the compose-mode flow is being edited, apply the edits before it
        # is released (applies to both the selected and the all-flows case).
        if compose_flow is not None and (
            flows is None or compose_flow in flows
        ):
            self._request_panel.apply_request_edits(compose_flow)
            self._sync_content_length(compose_flow, is_request=True)

        if master._loop:
            if flows is None:
                # Walk the full view store on the proxy event loop so the
                # resume decision sees every intercepted flow and avoids
                # cross-thread reads of the store from the GUI thread.
                def _resume_all():
                    for f in master.view._store.values():
                        if (
                            getattr(f, "intercepted", False)
                            and getattr(f, "request", None)
                        ):
                            f.resume()

                master._loop.call_soon_threadsafe(_resume_all)
            else:
                # Release every selected flow in a single event-loop callback
                # so they all complete together.
                def _resume_selected():
                    for f in flows:
                        f.resume()

                master._loop.call_soon_threadsafe(_resume_selected)

        # If compose-mode flow was sent, exit compose mode
        if compose_flow is not None and (flows is None or compose_flow in flows):
            self._flow_state.pop(str(compose_flow.id), None)
            self._cancel_compose_mode()

    def _toggle_edit_mode(self) -> None:
        """F2: toggle editable state for inspector text widgets."""
        if self._selected_flow is None:
            return
        self._edit_mode = not self._edit_mode
        if not self._edit_mode:
            # Exiting edit mode: apply edits from Raw tabs and sync Content-Length
            flow = self._selected_flow
            self._request_panel.apply_request_edits(flow)
            self._sync_content_length(flow, is_request=True)
            self._response_panel.apply_response_edits(flow)
            self._sync_content_length(flow, is_request=False)
        self._request_panel.set_editable(self._edit_mode)
        self._response_panel.set_editable(self._edit_mode)

    def _replay_all_selected(self) -> None:
        """R key: replay all selected flows. Each gets cloned and replayed."""
        flows = self._get_selected_flows()
        if not flows:
            return
        for flow in flows:
            new_flow = flow.copy()
            new_flow.intercepted = False  # copy preserves intercepted state
            self._master.view.add([new_flow])
            self._master.replay_flow(new_flow)

    def _open_replay_sequentially(self) -> None:
        """Shift+R: configure and start repeated replay for selected flows."""
        flows = self._get_selected_flows()
        if not flows:
            return
        dialog = ReplaySequentiallyDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.accepted.connect(
            lambda: self._start_replay_sequentially(
                flows, dialog.count.value(), dialog.interval.value()
            )
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _start_replay_sequentially(self, flows: list, count: int, interval: float) -> None:
        """Replay every selected flow once per interval until count is reached."""
        timer = QTimer(self)
        timer.setInterval(max(0, round(interval * 1000)))
        sent = 0

        def send_batch() -> None:
            nonlocal sent
            if count and sent >= count:
                timer.stop()
                timer.deleteLater()
                return
            for source_flow in flows:
                new_flow = source_flow.copy()
                new_flow.intercepted = False
                new_flow.metadata["_replay_sequentially"] = True
                self._master.view.add([new_flow])
                self._master.replay_flow(new_flow)
            sent += 1

        timer.timeout.connect(send_batch)
        self._replay_sequentially_timers = getattr(self, "_replay_sequentially_timers", [])
        self._replay_sequentially_timers.append(timer)
        timer.destroyed.connect(lambda: self._replay_sequentially_timers.remove(timer))
        send_batch()
        timer.start()

    def _abort_selected(self) -> None:
        """Abort (kill) selected live flows. Completed flows are ignored."""
        flows = self._get_selected_flows()
        if not flows:
            return
        killed = 0
        for flow in flows:
            if flow.killable:
                if self._master._loop:
                    self._master._loop.call_soon_threadsafe(
                        self._master.proxyserver.abort_flow, flow
                    )
                self._on_flow_updated(flow)
                killed += 1
                # If the killed flow was intercepted, clean up flow state
                fid = str(flow.id)
                self._flow_state.pop(fid, None)

    def _break_on_response(self) -> None:
        """Send request, intercept the response for editing."""
        if not self._compose_mode or self._selected_flow is None:
            return
        flow = self._selected_flow
        fid = str(flow.id)
        self._request_panel.apply_request_edits(flow)
        self._sync_content_length(flow, is_request=True)

        # Mark for response-only interception.
        self._master.response_intercept.intercept_ids.add(fid)
        self._flow_state[fid] = "waiting_response"

        if flow.intercepted:
            # Original intercepted flow: resume so it proceeds to server.
            # Response will be intercepted by _ResponseIntercept addon.
            if self._master._loop:
                self._master._loop.call_soon_threadsafe(flow.resume)
        else:
            # Replay And Edit flow: replay to send to server.
            # Prevent the breakpoint addon from re-intercepting the replayed flow.
            # Response will be intercepted by _ResponseIntercept addon.
            self._master.breakpoint_req_intercept.response_only_ids.add(fid)
            self._master.view.add([flow])
            self._master.replay_flow(flow)

        # Stay in compose mode — user edits the response next.
        self._update_compose_bar_for(flow)

    def _run_to_completion(self) -> None:
        """Release the intercepted response to the client."""
        if self._selected_flow is None:
            return
        flow = self._selected_flow
        fid = str(flow.id)
        self._response_panel.apply_response_edits(flow)
        self._sync_content_length(flow, is_request=False)

        # Clean up all intercept markers and flow state.
        self._master.response_intercept.intercept_ids.discard(fid)
        self._master.breakpoint_req_intercept.response_only_ids.discard(fid)
        self._flow_state.pop(fid, None)

        if flow.intercepted:
            flow.resume()

        self._cancel_compose_mode()

    def _update_compose_bar_for(self, flow) -> None:
        """Update compose bar button states based on flow's current phase."""
        fid = str(flow.id)
        waiting_response = self._flow_state.get(fid) == "waiting_response"
        self._send_button.setEnabled(not waiting_response)
        self._break_response_btn.setEnabled(not waiting_response)
        self._run_completion_btn.setEnabled(waiting_response)

    def _sync_content_length(self, flow, is_request: bool) -> None:
        """Sync Content-Length header with actual body size.

        - If Content-Length already exists: always adjust to actual body
          length (never delete it).
        - If Content-Length does not exist: only add it when body is
          non-empty.  An empty body without an existing Content-Length
          header stays header-less.
        """
        msg = flow.request if is_request else flow.response
        if not msg:
            return
        cl_bytes = b"content-length"
        if not msg.content:
            # Never delete an existing Content-Length — only adjust to 0.
            # Do not add Content-Length if it was not already present.
            if cl_bytes in msg.headers:
                msg.headers[cl_bytes] = b"0"
            return
        body_len = len(msg.content)
        if cl_bytes in msg.headers:
            if self._config.auto_adjust_content_length:
                msg.headers[cl_bytes] = str(body_len).encode()
        else:
            msg.headers.add(cl_bytes, str(body_len).encode())

    def _save_pending_edits(self) -> None:
        """Save any pending edits from edit/compose mode to the flow before conversion."""
        if self._selected_flow is None:
            return
        if self._edit_mode or self._compose_mode:
            self._request_panel.apply_request_edits(self._selected_flow)
            self._sync_content_length(self._selected_flow, is_request=True)
            self._response_panel.apply_response_edits(self._selected_flow)
            self._sync_content_length(self._selected_flow, is_request=False)

    # ── Convert methods ──

    @staticmethod
    def _parse_urlencoded(body: bytes) -> list[tuple[str, str]]:
        """Parse urlencoded body into (key, value) pairs."""
        from urllib.parse import parse_qs
        try:
            text = body.decode("utf-8")
        except Exception:
            return []
        result: list[tuple[str, str]] = []
        for k, vals in parse_qs(text, keep_blank_values=True).items():
            for v in vals:
                result.append((k, v))
        return result

    @staticmethod
    def _parse_json_body(body: bytes) -> list[tuple[str, str]]:
        """Parse JSON body into flat (key, value) pairs. Nested objects become str."""
        import json
        try:
            obj = json.loads(body.decode("utf-8"))
        except Exception:
            return []
        if not isinstance(obj, dict):
            return [("body", str(obj))]
        result: list[tuple[str, str]] = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                result.append((k, json.dumps(v)))
            else:
                result.append((k, str(v)))
        return result

    @staticmethod
    def _kv_to_urlencoded(pairs: list[tuple[str, str]]) -> bytes:
        """Convert (key, value) pairs to urlencoded form body."""
        from urllib.parse import urlencode
        return urlencode(pairs).encode("utf-8")

    @staticmethod
    def _kv_to_json(pairs: list[tuple[str, str]]) -> bytes:
        """Convert (key, value) pairs to JSON body."""
        import json
        obj = {}
        for k, v in pairs:
            if k in obj:
                existing = obj[k]
                if isinstance(existing, list):
                    existing.append(v)
                else:
                    obj[k] = [existing, v]
            else:
                obj[k] = v
        return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _kv_to_multipart(pairs: list[tuple[str, str]], boundary: str) -> bytes:
        """Convert (key, value) pairs to multipart/form-data body."""
        lines: list[bytes] = []
        for k, v in pairs:
            lines.append(f"--{boundary}".encode("utf-8"))
            lines.append(f'Content-Disposition: form-data; name="{k}"'.encode("utf-8"))
            lines.append(b"")
            lines.append(v.encode("utf-8"))
        lines.append(f"--{boundary}--".encode("utf-8"))
        return b"\r\n".join(lines)

    @staticmethod
    def _parse_multipart(content_type: str, body: bytes) -> list[tuple[str, str]]:
        """Parse multipart/form-data body into (key, value) pairs.
        
        For file parts, the value is the filename.
        For form fields, the value is the field value.
        """
        import re
        # Extract boundary from Content-Type
        boundary_match = re.search(r'boundary=([^;]+)', content_type)
        if not boundary_match:
            return []
        boundary = boundary_match.group(1).strip().strip('"')
        if not boundary:
            return []
        
        boundary_bytes = f"--{boundary}".encode("utf-8")
        end_boundary = f"--{boundary}--".encode("utf-8")
        
        # Split by boundary
        if boundary_bytes not in body:
            return []
        
        parts = body.split(boundary_bytes)
        result: list[tuple[str, str]] = []
        
        for part in parts[1:]:  # Skip preamble before first boundary
            part = part.strip()
            if part == b"--" or part == b"":
                continue
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            
            # Split headers from body
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            headers_section = part[:header_end].decode("utf-8", errors="replace")
            part_body = part[header_end + 4:]
            
            # Parse Content-Disposition
            disp_match = re.search(r'name="([^"]*)"', headers_section)
            if not disp_match:
                continue
            name = disp_match.group(1)
            
            # Check for filename
            filename_match = re.search(r'filename="([^"]*)"', headers_section)
            if filename_match:
                result.append((name, filename_match.group(1)))
            else:
                value = part_body.decode("utf-8", errors="replace")
                result.append((name, value))
        
        return result

    def _convert_get_to_post(self) -> None:
        """Convert GET request to POST by moving query string to urlencoded body."""
        self._save_pending_edits()
        flows = self._get_selected_flows()
        selected = self._selected_flow
        modified: list = []
        for flow in flows:
            req = flow.request
            if not req or req.method.upper() != "GET":
                continue
            from urllib.parse import urlsplit, urlencode, urlunsplit, parse_qs
            
            parsed = urlsplit(req.path)
            if not parsed.query:
                # No query string: append ?id=1 before converting
                req.path = urlunsplit(("", "", parsed.path, "id=1", parsed.fragment))
                parsed = urlsplit(req.path)
            
            # Build urlencoded body from query string
            qs_pairs: list[tuple[str, str]] = []
            for k, vals in parse_qs(parsed.query, keep_blank_values=True).items():
                for v in vals:
                    qs_pairs.append((k, v))
            
            body = urlencode(qs_pairs).encode("utf-8")
            req.content = body
            req.method = "POST"
            
            # Remove query string from path while preserving path parameters and fragment.
            req.path = urlunsplit(("", "", parsed.path, "", parsed.fragment))
            
            # Set Content-Type header
            req.headers[b"content-type"] = b"application/x-www-form-urlencoded"
            self._sync_content_length(flow, is_request=True)
            self._session_model.update_flow(flow)
            modified.append(flow)
        
        # Refresh displayed flow if it was modified
        if selected and selected in modified:
            self._request_panel.populate_request(selected)

    def _convert_post_to_get(self) -> None:
        """Convert POST request to GET by moving body params to query string."""
        self._save_pending_edits()
        flows = self._get_selected_flows()
        selected = self._selected_flow
        modified: list = []
        for flow in flows:
            req = flow.request
            if not req or req.method.upper() != "POST":
                continue
            if not req.content:
                # No body, just change method
                req.method = "GET"
                req.headers.pop(b"content-type", None)
                self._session_model.update_flow(flow)
                modified.append(flow)
                continue

            from urllib.parse import urlsplit, urlencode, urlunsplit, parse_qs

            ct = req.headers.get("content-type", "").lower()
            pairs: list[tuple[str, str]] = []

            if "json" in ct:
                pairs = self._parse_json_body(req.content)
            elif "x-www-form-urlencoded" in ct:
                pairs = self._parse_urlencoded(req.content)
            elif "multipart/form-data" in ct:
                pairs = self._parse_multipart(ct, req.content)
            else:
                # Unknown content type, skip
                continue

            if not pairs:
                # No params extracted, just change method
                req.method = "GET"
                req.content = None
                req.headers.pop(b"content-type", None)
                self._session_model.update_flow(flow)
                modified.append(flow)
                continue

            # Build query string and append to path
            qs = urlencode(pairs)
            parsed = urlsplit(req.path)
            if parsed.query:
                new_query = parsed.query + "&" + qs
            else:
                new_query = qs
            req.path = urlunsplit(("", "", parsed.path, new_query, parsed.fragment))

            req.method = "GET"
            req.content = None
            req.headers.pop(b"content-type", None)
            self._session_model.update_flow(flow)
            modified.append(flow)

        # Refresh displayed flow if it was modified
        if selected and selected in modified:
            self._request_panel.populate_request(selected)

    def _convert_body_to_json(self) -> None:
        """Convert POST body to JSON format."""
        self._save_pending_edits()
        flows = self._get_selected_flows()
        selected = self._selected_flow
        modified: list = []
        for flow in flows:
            req = flow.request
            if not req or not req.content:
                continue
            
            ct = req.headers.get("content-type", "").lower()
            pairs: list[tuple[str, str]] = []
            
            if "json" in ct:
                continue  # Already JSON, skip
            
            if "x-www-form-urlencoded" in ct:
                pairs = self._parse_urlencoded(req.content)
            elif "multipart/form-data" in ct:
                pairs = self._parse_multipart(ct, req.content)
            else:
                continue
            
            if not pairs:
                continue
            
            req.content = self._kv_to_json(pairs)
            req.headers[b"content-type"] = b"application/json"
            self._sync_content_length(flow, is_request=True)
            self._session_model.update_flow(flow)
            modified.append(flow)
        
        if selected and selected in modified:
            self._request_panel.populate_request(selected)

    def _convert_body_to_urlformed(self) -> None:
        """Convert POST body to urlencoded form format."""
        self._save_pending_edits()
        flows = self._get_selected_flows()
        selected = self._selected_flow
        modified: list = []
        for flow in flows:
            req = flow.request
            if not req or not req.content:
                continue
            
            ct = req.headers.get("content-type", "").lower()
            pairs: list[tuple[str, str]] = []
            
            if "x-www-form-urlencoded" in ct:
                continue  # Already urlencoded, skip
            
            if "json" in ct:
                pairs = self._parse_json_body(req.content)
            elif "multipart/form-data" in ct:
                pairs = self._parse_multipart(ct, req.content)
            else:
                continue
            
            if not pairs:
                continue
            
            req.content = self._kv_to_urlencoded(pairs)
            req.headers[b"content-type"] = b"application/x-www-form-urlencoded"
            self._sync_content_length(flow, is_request=True)
            self._session_model.update_flow(flow)
            modified.append(flow)
        
        if selected and selected in modified:
            self._request_panel.populate_request(selected)

    def _convert_body_to_multipart(self) -> None:
        """Convert POST body to multipart/form-data format."""
        import uuid
        self._save_pending_edits()
        flows = self._get_selected_flows()
        selected = self._selected_flow
        modified: list = []
        for flow in flows:
            req = flow.request
            if not req or not req.content:
                continue

            ct = req.headers.get("content-type", "").lower()
            pairs: list[tuple[str, str]] = []

            if "x-www-form-urlencoded" in ct:
                pairs = self._parse_urlencoded(req.content)
            elif "json" in ct:
                pairs = self._parse_json_body(req.content)
            elif "multipart/form-data" in ct:
                continue  # Already multipart, skip
            else:
                continue

            if not pairs:
                continue

            boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
            req.content = self._kv_to_multipart(pairs, boundary)
            req.headers[b"content-type"] = f"multipart/form-data; boundary={boundary}".encode("utf-8")
            self._sync_content_length(flow, is_request=True)
            self._session_model.update_flow(flow)
            modified.append(flow)

        if selected and selected in modified:
            self._request_panel.populate_request(selected)

    def _f11_toggle_breakpoint(self) -> None:
        """F11: toggle global breakpoint mode (all new flows become pending)."""
        self._breakpoint_mode = not self._breakpoint_mode
        self._breakpoint_rules = []  # clear rules when toggling mode
        if self._breakpoint_mode:
            self._master.breakpoint_req_intercept.breakpoint_mode = True
            self._master.breakpoint_req_intercept.breakpoint_rules = []
        else:
            self._master.breakpoint_req_intercept.breakpoint_mode = False
            self._master.breakpoint_req_intercept.breakpoint_rules = []
            self._release_breakpoint_intercepts()
        self._update_status()

    def _shift_f11_breakpoint_rules(self) -> None:
        """Shift+F11: open breakpoint rules dialog (non-blocking)."""
        dlg = BreakpointRulesDialog(self._breakpoint_rules, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.accepted.connect(lambda: self._breakpoint_rules_applied(dlg))
        dlg.rejected.connect(lambda: self._breakpoint_rules_cancelled())
        dlg.show()

    def _breakpoint_rules_applied(self, dlg) -> None:
        self._breakpoint_rules = dlg.rules
        self._breakpoint_mode = False  # rules take precedence
        if self._breakpoint_rules:
            # Set rules directly on the proxy addon (bypasses flowfilter)
            self._master.breakpoint_req_intercept.breakpoint_mode = False
            self._master.breakpoint_req_intercept.breakpoint_rules = self._breakpoint_rules
        else:
            self._master.breakpoint_req_intercept.breakpoint_mode = False
            self._master.breakpoint_req_intercept.breakpoint_rules = []
            self._release_breakpoint_intercepts()
        self._update_status()

    def _breakpoint_rules_cancelled(self) -> None:
        # Cancelled: if no rules, clear intercept
        if not self._breakpoint_rules:
            self._master.breakpoint_req_intercept.breakpoint_mode = False
            self._master.breakpoint_req_intercept.breakpoint_rules = []
            self._release_breakpoint_intercepts()
            self._update_status()

    def _color_selected(self, color: QColor | None) -> None:
        """Ctrl+0..9: apply/reset background color on all selected flows."""
        for flow in self._get_selected_flows():
            self._session_model.set_flow_color(flow, color)

    def _f12_toggle_proxy(self) -> None:
        """F12: toggle system proxy (same as clicking the Capture button)."""
        new_state = not self._proxy_toggle_action.isChecked()
        self._proxy_toggle_action.setChecked(new_state)
        self._toggle_system_proxy(new_state)

    # ── Context menu ──

    _CTRL_COLORS_LIST: list[tuple[str, QColor]] = [
        ("Light Red", QColor("#FFAAAA")),
        ("Lighter Red", QColor("#FFCCCC")),
        ("Lightest Red", QColor("#FFEEEE")),
        ("Light Green", QColor("#AAFFAA")),
        ("Lighter Green", QColor("#CCFFCC")),
        ("Lightest Green", QColor("#EEFFEE")),
        ("Light Blue", QColor("#AAAADD")),
        ("Lighter Blue", QColor("#CCCCFF")),
        ("Lightest Blue", QColor("#EEEEFF")),
    ]

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self._session_table)
        flows = self._get_selected_flows()

        # ── Copy ──
        copy_menu = menu.addMenu("Copy")
        just_url = copy_menu.addAction("Just URL")
        just_url.triggered.connect(self._copy_just_url)
        copy_request = copy_menu.addAction("Request")
        copy_request.triggered.connect(self._copy_request)
        copy_response = copy_menu.addAction("Response")
        copy_response.triggered.connect(self._copy_response)
        copy_session = copy_menu.addAction("Session")
        copy_session.triggered.connect(self._copy_session)

        # ── View ──
        view_action = menu.addAction("View")
        view_action.triggered.connect(self._view_flow_detail)

        # ── SendTo ──
        sendto_entries = self._config.sendto_entries
        if sendto_entries:
            sendto_menu = menu.addMenu("SendTo")
            for entry in sendto_entries:
                name = entry.get("name", "")
                addr = entry.get("address", "")
                if name and addr:
                    action = sendto_menu.addAction(f"Send To {name}")
                    action.triggered.connect(
                        lambda checked, a=addr: self._sendto_forward(a)
                    )

        # ── Save ──
        save_menu = menu.addMenu("Save")
        save_urlname = save_menu.addAction("Save Selected Response To UrlName")
        save_urlname.triggered.connect(self._save_response_to_urlname)
        save_ts = save_menu.addAction("Save Selected Response To TimeStamp")
        save_ts.triggered.connect(self._save_response_to_timestamp)
        save_zip = save_menu.addAction("Save Selected Sessions To Zip")
        save_zip.triggered.connect(self._save_sessions)

        # ── Convert ──
        if flows:
            convert_menu = menu.addMenu("Convert")
            g2p = convert_menu.addAction("Get -> Post")
            g2p.triggered.connect(self._convert_get_to_post)
            p2g = convert_menu.addAction("Post -> Get")
            p2g.triggered.connect(self._convert_post_to_get)
            b2j = convert_menu.addAction("Body -> Json")
            b2j.triggered.connect(self._convert_body_to_json)
            b2u = convert_menu.addAction("Body -> Urlformed")
            b2u.triggered.connect(self._convert_body_to_urlformed)
            b2m = convert_menu.addAction("Body -> MultiPart")
            b2m.triggered.connect(self._convert_body_to_multipart)

        # ── Remove ──
        remove_menu = menu.addMenu("Remove")
        rm_selected = remove_menu.addAction("Selected Sessions")
        rm_selected.triggered.connect(self._remove_selected)
        rm_unselected = remove_menu.addAction("Unselected Sessions")
        rm_unselected.triggered.connect(self._remove_unselected)
        rm_all = remove_menu.addAction("All Sessions")
        rm_all.triggered.connect(self._clear_sessions)

        # ── Mark ──
        mark_menu = menu.addMenu("Mark")
        reset_action = mark_menu.addAction("Reset Color")
        reset_action.triggered.connect(lambda: self._color_selected(None))
        mark_menu.addSeparator()
        lock_action = mark_menu.addAction("Locked")
        lock_action.triggered.connect(lambda: self._set_selected_locked(True))
        unlock_action = mark_menu.addAction("Unlocked")
        unlock_action.triggered.connect(lambda: self._set_selected_locked(False))
        mark_menu.addSeparator()
        for name, color in self._CTRL_COLORS_LIST:
            act = mark_menu.addAction(name)
            act.triggered.connect(lambda _checked, c=color: self._color_selected(c))

        # ── Replay ──
        replay_menu = menu.addMenu("Replay")
        rp_selected = replay_menu.addAction("Replay Selected Sessions")
        rp_selected.triggered.connect(self._replay_all_selected)
        rp_edit = replay_menu.addAction("Replay And Edit")
        rp_edit.triggered.connect(self._compose_request)
        rp_sequential = replay_menu.addAction("Replay Sequentially")
        rp_sequential.triggered.connect(self._open_replay_sequentially)
        rp_adv = replay_menu.addAction("Replay Advanced")
        rp_adv.setEnabled(False)

        # ── Abort ──
        abort_action = menu.addAction("Abort Session")
        killable_flows = [f for f in flows if f.killable]
        abort_action.setEnabled(bool(killable_flows))
        abort_action.triggered.connect(self._abort_selected)

        # ── Properties ──
        props_action = menu.addAction("Properties")
        props_action.triggered.connect(self._show_properties)

        # ── Filter ──
        filter_menu = menu.addMenu("Filter")
        host_label = flows[0].request.host if flows and flows[0].request and flows[0].request.host else "hostname"
        filter_host = filter_menu.addAction(f"Filter {host_label}")
        filter_host.triggered.connect(self._filter_hostname)
        path_label = flows[0].request.path.lstrip("/") if flows and flows[0].request and flows[0].request.path else "url"
        filter_url = filter_menu.addAction(f"Filter {path_label}")
        filter_url.triggered.connect(self._filter_url)
        # Extra rule filtering by path only (query string stripped), when present
        if flows and flows[0].request and flows[0].request.query:
            path_wo_q = flows[0].request.path.lstrip("/").split("?", 1)[0]
            filter_url_wo_q = filter_menu.addAction(f"Filter {path_wo_q}")
            filter_url_wo_q.triggered.connect(self._filter_url_wo_query)

        menu.exec(self._session_table.viewport().mapToGlobal(pos))

    def _copy_just_url(self) -> None:
        flows = self._get_selected_flows()
        if not flows:
            return
        urls = []
        for f in flows:
            if f.request:
                scheme = f.request.scheme or "https"
                host = f.request.host or ""
                port = f.request.port
                # Include port only when non-standard
                if scheme == "http" and port != 80:
                    host = f"{host}:{port}"
                elif scheme == "https" and port != 443:
                    host = f"{host}:{port}"
                urls.append(f"{scheme}://{host}{f.request.path}")
        QApplication.clipboard().setText("\n".join(urls))

    def _copy_session(self) -> None:
        flows = self._get_selected_flows()
        if not flows:
            return
        parts = []
        for f in flows:
            parts.append(_format_request_raw(f))
            parts.append("")
            parts.append(_format_response_raw(f))
            parts.append("\n" + "=" * 60 + "\n")
        QApplication.clipboard().setText("\n".join(parts))

    def _copy_request(self) -> None:
        flows = self._get_selected_flows()
        if not flows:
            return
        parts = []
        for f in flows:
            txt = _format_request_raw(f)
            if txt:
                parts.append(txt)
        if len(flows) > 1:
            QApplication.clipboard().setText("\n\n" + "=" * 60 + "\n\n".join(parts))
        elif parts:
            QApplication.clipboard().setText(parts[0])

    def _copy_response(self) -> None:
        flows = self._get_selected_flows()
        if not flows:
            return
        parts = []
        for f in flows:
            txt = _format_response_raw(f)
            if txt:
                parts.append(txt)
        if len(flows) > 1:
            QApplication.clipboard().setText("\n\n" + "=" * 60 + "\n\n".join(parts))
        elif parts:
            QApplication.clipboard().setText(parts[0])

    # ── Session locking ──

    @staticmethod
    def _is_flow_locked(f) -> bool:
        return bool((getattr(f, "metadata", None) or {}).get("_locked"))

    @staticmethod
    def _set_flow_locked(f, locked: bool) -> None:
        if locked:
            f.metadata["_locked"] = True
        else:
            f.metadata.pop("_locked", None)

    def _set_selected_locked(self, locked: bool) -> None:
        flows = self._get_selected_flows()
        if not flows:
            return
        for f in flows:
            self._set_flow_locked(f, locked)
            self._session_model.update_flow(f)

    def _toggle_lock_selected(self) -> None:
        """Ctrl+L: toggle lock state of the selected flows.

        A mixed selection (locked + unlocked) becomes fully locked; a fully
        locked selection becomes fully unlocked."""
        flows = self._get_selected_flows()
        if not flows:
            return
        self._set_selected_locked(any(not self._is_flow_locked(f) for f in flows))

    def _remove_selected(self) -> None:
        flows = [
            f for f in self._get_selected_flows() if not self._is_flow_locked(f)
        ]
        if not flows:
            return
        indices = []
        flows_list = self._session_model._flows
        for f in flows:
            try:
                indices.append(flows_list.index(f))
            except ValueError:
                pass
        self._session_model.beginResetModel()
        for row in sorted(indices, reverse=True):
            f = self._session_model._flows[row]
            fid = getattr(f, "id", None)
            self._session_model._flow_colors.pop(fid, None)
            self._session_model._flows.pop(row)
        self._session_model.endResetModel()
        self._selected_flow = None

    def _remove_unselected(self) -> None:
        selected_ids = set(f.id for f in self._get_selected_flows())
        to_remove = [
            (i, f) for i, f in enumerate(self._session_model._flows)
            if f.id not in selected_ids and not self._is_flow_locked(f)
        ]
        self._session_model.beginResetModel()
        for row, f in reversed(to_remove):
            fid = getattr(f, "id", None)
            self._session_model._flow_colors.pop(fid, None)
            self._session_model._flows.pop(row)
        self._session_model.endResetModel()

    def _show_properties(self) -> None:
        flows = self._get_selected_flows()
        if not flows:
            return
        dlg = FlowPropertiesDialog(flows[0], self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _view_flow_detail(self) -> None:
        """Open a separate window showing the selected flow's details."""
        flows = self._get_selected_flows()
        if not flows:
            return
        dlg = FlowDetailDialog(flows[0], self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.destroyed.connect(lambda: self._detail_windows.remove(dlg) if dlg in self._detail_windows else None)
        self._detail_windows.append(dlg)
        dlg.show()

    def _sendto_forward(self, proxy_addr: str) -> None:
        """Forward the selected flow's request through the specified proxy address.

        Establishes a CONNECT tunnel to the target server through the upstream proxy,
        then sends the HTTP request in origin-form (RFC 7230 §5.3.1).
        Runs network I/O in background threads to keep the UI responsive.
        """
        from urllib.parse import urlparse
        import socket
        import threading

        flows = self._get_selected_flows()
        if not flows:
            return
        parsed = urlparse(proxy_addr)
        proxy_host = parsed.hostname or "127.0.0.1"
        proxy_port = parsed.port or 8888

        from mitmproxy.net.http import http1 as mitm_http1
        from mitmproxy import flow as mitm_flow

        def _do_forward(src_flow):
            target_host = src_flow.request.host
            target_port = src_flow.request.port

            new_flow = src_flow.copy()
            new_flow.intercepted = False
            # SendTo sends a brand-new request: drop the copied response/error
            # so the Result column shows this forward's outcome instead of the
            # original flow's (a stale response would otherwise mask failures).
            new_flow.response = None
            new_flow.error = None

            sock = None
            try:
                # 1. Connect to upstream proxy
                sock = socket.create_connection(
                    (proxy_host, proxy_port), timeout=30
                )

                # 2. Send CONNECT to establish tunnel
                authority = f"{target_host}:{target_port}"
                connect_req = (
                    f"CONNECT {authority} HTTP/1.1\r\n"
                    f"Host: {authority}\r\n\r\n"
                )
                sock.sendall(connect_req.encode())

                # 3. Read CONNECT response
                response_data = b""
                while b"\r\n\r\n" not in response_data:
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise ConnectionError(
                            "Proxy closed connection during CONNECT"
                        )
                    response_data += chunk

                header_end = response_data.find(b"\r\n\r\n")
                resp_header_lines = response_data[:header_end].split(b"\r\n")

                try:
                    connect_resp = mitm_http1.read_response_head(
                        resp_header_lines
                    )
                except ValueError:
                    raise ConnectionError(
                        "Invalid CONNECT response from proxy"
                    )

                if connect_resp.status_code != 200:
                    raise ConnectionError(
                        f"Proxy refused CONNECT: "
                        f"{connect_resp.status_code} {connect_resp.reason}"
                    )

                # 3b. TLS handshake for HTTPS targets
                import ssl

                is_https = src_flow.request.scheme == "https"
                if is_https:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    sock = ctx.wrap_socket(
                        sock, server_hostname=target_host
                    )

                # 4. Assemble request in origin-form
                request = src_flow.request
                req_line = (
                    request.data.method
                    + b" "
                    + request.data.path
                    + b" HTTP/1.1\r\n"
                )

                # Build headers: keep originals, convert HTTP/2 → HTTP/1.1 as needed.
                req_headers = request.headers.copy()

                # HTTP/2 uses :authority pseudo-header, may lack a Host header.
                if "Host" not in req_headers and "host" not in req_headers:
                    if request.authority:
                        req_headers["Host"] = request.authority
                    else:
                        req_headers["Host"] = f"{target_host}:{target_port}"

                # HTTP/2 permits multiple Cookie headers; HTTP/1.1 requires one.
                cookie_vals = req_headers.get_all("Cookie")
                if len(cookie_vals) > 1:
                    del req_headers["Cookie"]
                    req_headers["Cookie"] = "; ".join(cookie_vals)

                # Replace transfer-encoding with content-length (we send raw body).
                if "transfer-encoding" in req_headers:
                    del req_headers["transfer-encoding"]
                    if request.content:
                        req_headers["content-length"] = str(
                            len(request.content)
                        )
                headers_bytes = bytes(req_headers)

                raw_request = req_line + headers_bytes + b"\r\n"
                if request.content:
                    raw_request += request.content

                sock.sendall(raw_request)

                # 5. Read response headers
                response_data = b""
                while b"\r\n\r\n" not in response_data:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    response_data += chunk

                header_end = response_data.find(b"\r\n\r\n")
                if header_end == -1:
                    raise ConnectionError("No response headers received")

                resp_header_lines = (
                    response_data[:header_end].split(b"\r\n")
                )
                try:
                    response = mitm_http1.read_response_head(
                        resp_header_lines
                    )
                except ValueError:
                    raise ConnectionError("Invalid HTTP response")

                # 6. Read response body
                content = response_data[header_end + 4 :]
                expected_size = mitm_http1.expected_http_body_size(
                    request, response
                )
                if expected_size is None:
                    # Chunked — read until terminating chunk
                    while b"0\r\n\r\n" not in content:
                        chunk = sock.recv(8192)
                        if not chunk:
                            break
                        content += chunk
                elif expected_size > 0:
                    remaining = expected_size - len(content)
                    while remaining > 0:
                        chunk = sock.recv(min(8192, remaining))
                        if not chunk:
                            break
                        content += chunk
                        remaining = expected_size - len(content)
                elif expected_size == -1:
                    # Read until connection close
                    while True:
                        chunk = sock.recv(8192)
                        if not chunk:
                            break
                        content += chunk

                response.content = content

                # 7. Add result to view
                new_flow.response = response
                self._master.view.add([new_flow])

            except Exception as e:
                new_flow.error = mitm_flow.Error(str(e))
                self._master.view.add([new_flow])
            finally:
                if sock:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    try:
                        sock.close()
                    except Exception:
                        pass

        for flow in flows:
            t = threading.Thread(
                target=_do_forward, args=(flow,), daemon=True
            )
            t.start()

    # ── File: Save/Load Sessions ──

    def _save_sessions(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Sessions", "sessions.zip", "ZIP Files (*.zip)"
        )
        if not path:
            return
        from mitmproxy.io.tnetstring import dumps as tnet_dumps

        flows = self._get_selected_flows()
        if not flows:
            return
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, f in enumerate(flows):
                try:
                    raw = tnet_dumps(f.get_state())
                    zf.writestr(f"session_{i:05d}.tnet", raw)
                except Exception:
                    continue

    @staticmethod
    def _extract_url_filename(flow) -> str:
        """Extract a safe filename from the request URL path."""
        from urllib.parse import urlparse
        path = flow.request.path or "/"
        parsed = urlparse(path)
        clean_path = parsed.path.rstrip("/")
        if not clean_path or clean_path == "/":
            return "index"
        name = clean_path.rsplit("/", 1)[-1]
        if not name:
            return "index"
        # Remove query string remnants that may be in name
        name = name.split("?")[0]
        return name if name else "index"

    def _save_response_to_urlname(self) -> None:
        """Save selected flows' response bodies to a directory, named by URL."""
        flows = self._get_selected_flows()
        if not flows:
            return
        directory = QFileDialog.getExistingDirectory(self, "Save Responses To Directory")
        if not directory:
            return
        saved = 0
        for flow in flows:
            if not flow.response or not flow.response.content:
                continue
            name = self._extract_url_filename(flow)
            # Ensure unique filename within this batch
            filepath = os.path.join(directory, name)
            if os.path.exists(filepath):
                base, ext = os.path.splitext(name)
                idx = 1
                while os.path.exists(os.path.join(directory, f"{base}_{idx}{ext}")):
                    idx += 1
                filepath = os.path.join(directory, f"{base}_{idx}{ext}")
            try:
                with open(filepath, "wb") as f:
                    f.write(flow.response.content)
                saved += 1
            except OSError:
                pass
        self.statusBar().showMessage(f"Saved {saved} response(s) to {directory}", 5000)

    def _save_response_to_timestamp(self) -> None:
        """Save selected flows' response bodies, named by timestamp + index."""
        flows = self._get_selected_flows()
        if not flows:
            return
        directory = QFileDialog.getExistingDirectory(self, "Save Responses To Directory")
        if not directory:
            return
        saved = 0
        for i, flow in enumerate(flows):
            if not flow.response or not flow.response.content:
                continue
            ts = flow.request.timestamp_start if flow.request else datetime.now().timestamp()
            dt = datetime.fromtimestamp(ts)
            ts_str = dt.strftime("%Y%m%d_%H%M%S")
            # Extract extension from URL
            url_name = self._extract_url_filename(flow)
            _, ext = os.path.splitext(url_name)
            filename = f"{ts_str}_{i + 1}{ext}"
            try:
                with open(os.path.join(directory, filename), "wb") as f:
                    f.write(flow.response.content)
                saved += 1
            except OSError:
                pass
        self.statusBar().showMessage(f"Saved {saved} response(s) to {directory}", 5000)

    def _load_sessions(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Sessions", "", "ZIP Files (*.zip)"
        )
        if not path:
            return
        from mitmproxy import flow as flow_mod
        from mitmproxy.io.tnetstring import loads as tnet_loads

        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = sorted(n for n in zf.namelist() if n.endswith(".tnet"))
                for name in names:
                    raw = zf.read(name)
                    try:
                        state = tnet_loads(raw)
                        f = flow_mod.Flow.from_state(state)
                        self._master.view.add([f])
                        self._session_model.add_flow(f)
                    except Exception as e:
                        print(f"[Load] Skipping {name}: {e}", file=sys.stderr)
        except zipfile.BadZipFile:
            QMessageBox.warning(self, "Error", "Invalid ZIP file.")

    # ── Filter system ──

    _FILTER_FILE = Path("filter.json")

    def _match_any_filter(self, flow) -> bool:
        """Return True if the flow matches any filter rule."""
        rules = self._load_filters()
        if not rules:
            return False
        for rule in rules:
            if self._match_filter_rule(flow, rule):
                return True
        return False

    def _load_filters(self) -> list[dict]:
        """Load saved filter rules from filter.json, return list."""
        try:
            if self._FILTER_FILE.exists():
                data = json_mod.loads(self._FILTER_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save_filters(self, rules: list[dict]) -> None:
        """Save filter rules to filter.json."""
        self._FILTER_FILE.write_text(
            json_mod.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Keep the proxy-side breakpoint addon in sync: sessions matching the
        # filter rules must bypass BreakPoint and complete directly.
        bp = getattr(self._master, "breakpoint_req_intercept", None)
        if bp is not None:
            bp.filter_rules = [dict(r) for r in rules]

    def _apply_filters(self) -> None:
        """Remove flows matching any active filter rule."""
        rules = self._load_filters()
        # Keep the proxy-side breakpoint addon in sync (also covers startup,
        # where filter.json may have changed after the addon was initialized).
        bp = getattr(self._master, "breakpoint_req_intercept", None)
        if bp is not None:
            bp.filter_rules = [dict(r) for r in rules]
        if not rules:
            return

        to_remove = []
        for i, f in enumerate(self._session_model._flows):
            for rule in rules:
                if f.request and self._match_filter_rule(f, rule):
                    to_remove.append((i, f))
                    break

        self._session_model.beginResetModel()
        for row, f in reversed(to_remove):
            fid = getattr(f, "id", None)
            self._session_model._flow_colors.pop(fid, None)
            self._session_model._flows.pop(row)
        self._session_model.endResetModel()

    @staticmethod
    def _match_filter_rule(flow, rule: dict) -> bool:
        """Check if a flow matches a filter rule."""
        r = flow.request
        if not r:
            return False

        rule_type = rule.get("type", "")
        rule_value = rule.get("value", "")

        if rule_type == "hostname":
            return _glob_match((r.host or ""), rule_value, case_sensitive=False)
        elif rule_type == "path":
            # Ignore a leading slash and optionally the query string, so a
            # rule value like "news?id=1" or plain "news" both match a flow
            # whose request.path is "/news?id=1".
            rule_value = rule_value.lstrip("/")
            full = (r.path or "").lstrip("/")      # "news?id=1"
            bare = full.split("?", 1)[0]           # "news"
            return _glob_match(full, rule_value, True) or _glob_match(
                bare, rule_value, True
            )
        return False

    def _filter_hostname(self) -> None:
        """Add a hostname filter and apply it."""
        flows = self._get_selected_flows()
        if not flows or not flows[0].request or not flows[0].request.host:
            return
        hostname = flows[0].request.host
        self._add_filter_rule("hostname", hostname)

    def _filter_url(self) -> None:
        """Add a path filter (the part after host) and apply it."""
        flows = self._get_selected_flows()
        if not flows or not flows[0].request or not flows[0].request.path:
            return
        # Take the "login?id=1" part (everything after the first /)
        path = flows[0].request.path.lstrip("/")
        self._add_filter_rule("path", path)

    def _filter_url_wo_query(self) -> None:
        """Add a path filter with the query string stripped, e.g. "news" from "news?id=1"."""
        flows = self._get_selected_flows()
        if not flows or not flows[0].request or not flows[0].request.path:
            return
        path = flows[0].request.path.lstrip("/").split("?", 1)[0]
        self._add_filter_rule("path", path)

    def _add_filter_rule(self, rule_type: str, value: str) -> None:
        """Add a filter rule, save, and re-apply."""
        rules = self._load_filters()
        rules.append({"type": rule_type, "value": value})
        self._save_filters(rules)
        self._apply_filters()

    def _open_filter_dialog(self) -> None:
        """Open a dialog showing current filter rules (non-blocking)."""
        dlg = FilterDialog(self._load_filters(), self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.accepted.connect(lambda: self._filters_applied(dlg))
        dlg.show()

    def _filters_applied(self, dlg) -> None:
        self._save_filters(dlg.rules)
        self._apply_filters()

    def _open_auto_rules_dialog(self) -> None:
        """Open the Auto Rules dialog."""
        dlg = AutoRulesDialog(self._master, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _open_find_dialog(self) -> None:
        """Open the Find Sessions search dialog (non-blocking)."""
        dlg = FindDialog(self._session_model, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _open_new_session_dialog(self) -> None:
        """Open the New Session dialog for crafting a raw HTTP request (non-blocking)."""
        dlg = NewSessionDialog(self, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _open_logs_dialog(self) -> None:
        """Open the Logs window (non-blocking, single instance)."""
        if self._logs_dialog is None:
            self._logs_dialog = LogsDialog(self)
        self._logs_dialog.show()
        self._logs_dialog.raise_()
        self._logs_dialog.activateWindow()

    def _append_plugin_log(self, from_name: str, log_type: str,
                           message: str, comment) -> None:
        """Slot for the plugin bridge: append a line to the Logs Plugin tab."""
        if self._logs_dialog is None:
            self._logs_dialog = LogsDialog(self)
        self._logs_dialog.append_plugin_log(from_name, log_type, message, comment)

    def _set_plugin_flow_color(self, flow_id: str, color_hex: str) -> None:
        """Slot for the plugin bridge: color a session row (GUI thread)."""
        for f in self._session_model._flows:
            if getattr(f, "id", None) == flow_id:
                self._session_model.set_flow_color(f, QColor(color_hex))
                break

    def _set_plugin_flow_info(self, flow_id: str) -> None:
        """Slot for the plugin bridge: repaint a session row after its Info
        column changed (GUI thread). The Info text itself is read from the
        flow metadata directly by the model."""
        for f in self._session_model._flows:
            if getattr(f, "id", None) == flow_id:
                self._session_model.update_flow(f)
                break

    def _open_plugins_dialog(self) -> None:
        """Open the Plugins manager (non-blocking, single instance)."""
        if self._plugins_dialog is None:
            self._plugins_dialog = PluginsDialog(self)
        self._plugins_dialog.refresh()
        self._plugins_dialog.show()
        self._plugins_dialog.raise_()
        self._plugins_dialog.activateWindow()

    def _open_tools_dialog(self) -> None:
        """Open the Tools window (non-blocking, single instance)."""
        if self._tools_dialog is None:
            self._tools_dialog = ToolsDialog(self)
        self._tools_dialog.show()
        self._tools_dialog.raise_()
        self._tools_dialog.activateWindow()

    # ── Proxy toggle ──

    def _get_proxy_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0, winreg.KEY_READ,
            )
            val, _ = winreg.QueryValueEx(key, "ProxyEnable")
            winreg.CloseKey(key)
            return val == 1
        except OSError:
            return False

    @staticmethod
    def _normalize_proxy_host(host: str) -> str:
        # Addresses that mean "all interfaces" are reachable via loopback.
        return "127.0.0.1" if host in ("", "0.0.0.0", "::") else host

    def _get_local_proxy_address(self) -> tuple[str, int]:
        """Host/port of the local mitmproxy listener for the system proxy.

        Prefers the regular-mode server; falls back to the first server
        bound to a port (e.g. an upstream-mode listener) and finally to the
        configured listen options. This avoids ever using a hardcoded port,
        both while the proxy is still starting (empty server list) and when
        no regular mode is configured.
        """
        opts = self._master.options
        default_addr = (self._normalize_proxy_host(opts.listen_host), int(opts.listen_port))
        first_bound = None
        try:
            servers = self._master.proxyserver.servers
        except Exception:
            return default_addr
        for s in servers:
            port = s.mode.listen_port(opts.listen_port)
            if port is None:
                continue
            host = self._normalize_proxy_host(s.mode.listen_host(opts.listen_host))
            if "regular" in s.mode.full_spec:
                return host, int(port)
            if first_bound is None:
                first_bound = (host, int(port))
        return first_bound or default_addr

    def _set_proxy_enabled(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        import ctypes
        import winreg

        host, port = self._get_local_proxy_address()
        proxy_server = f"{host}:{port}"

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        )
        if enabled:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>")
        else:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "")
        winreg.CloseKey(key)

        ctypes.windll.wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.wininet.InternetSetOptionW(0, 37, 0, 0)

    def _toggle_system_proxy(self, checked: bool) -> None:
        self._set_proxy_enabled(checked)
        self._proxy_toggle_action.setChecked(checked)
        self._update_proxy_icon()
        self._update_status()

    # ── Options dialog ──

    def _open_options(self) -> None:
        from mitmproxy.tools.mitmgui.options_dialog import OptionsDialog

        dlg = OptionsDialog(self._config, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.session_list_font_size_changed.connect(self._apply_session_list_font_size)
        dlg.finished.connect(lambda result: self._on_options_finished(dlg, result))
        dlg.show()

    def _on_options_finished(self, dlg, result: int) -> None:
        self._apply_session_list_font_size()
        if result == QDialog.DialogCode.Accepted and dlg.was_modified:
            self._restart_proxy()

    def _restart_proxy(self) -> None:
        """Apply updated config and restart the proxy listener on the new port."""
        # Apply options and restart servers on the proxy event loop. Options.update()
        # synchronously invokes proxyserver.configure(), which schedules async work.
        import asyncio
        if self._master._loop and self._master._loop.is_running():
            async def _do_restart():
                self._config.apply_to_opts(self._master.options)
                servers = self._master.proxyserver.servers
                await servers.update([])
                await servers.update(self._master.options.mode)

            asyncio.run_coroutine_threadsafe(_do_restart(), self._master._loop)
        else:
            try:
                self._config.apply_to_opts(self._master.options)
            except Exception as e:
                QMessageBox.warning(self, "Proxy Configuration Error", str(e))
                return
        self._update_status()

    # ── Session table selection ──

    def _on_selection_changed(self, selected, deselected) -> None:
        indexes = self._session_table.selectionModel().selectedRows()
        if indexes:
            source_idx = self._sort_proxy.mapToSource(indexes[0])
            flow = self._session_model.get_flow(source_idx.row())
            # Save edits from the outgoing flow when switching to a different one.
            # Both edit_mode (F2) and compose_mode (Replay and Edit / E key)
            # make the request panel editable.
            prev = self._selected_flow
            if prev is not None and prev is not flow:
                if self._edit_mode or self._compose_mode:
                    self._request_panel.apply_request_edits(prev)
                    self._sync_content_length(prev, is_request=True)
                    self._response_panel.apply_response_edits(prev)
                    self._sync_content_length(prev, is_request=False)
                if self._edit_mode:
                    self._edit_mode = False
                    self._request_panel.set_editable(False)
                    self._response_panel.set_editable(False)
            self._selected_flow = flow
            fid = str(flow.id)
            # If in compose mode and user selected a different flow, cancel compose
            if self._compose_mode:
                if self._flow_state and fid not in self._flow_state:
                    self._cancel_compose_mode()
                else:
                    # Staying in compose mode — reset panel editability for the flow's state
                    state = self._flow_state.get(fid, "")
                    if state == "waiting_response":
                        self._request_panel.set_editable(False)
                        self._response_panel.set_editable(True)
                    else:
                        self._request_panel.set_editable(True)
                        self._response_panel.set_editable(False)
            # Restore compose mode when switching back to a pending flow
            if not self._compose_mode and fid in self._flow_state:
                self._compose_mode = True
                self._compose_bar.setVisible(True)
                state = self._flow_state[fid]
                if state == "waiting_response":
                    self._request_panel.set_editable(False)
                    self._response_panel.set_editable(True)
                else:
                    self._request_panel.set_editable(True)
                    self._response_panel.set_editable(False)
                # Clear stale response data immediately
                self._response_panel.populate_response(flow)
                self._update_compose_bar_for(flow)
            if self._compose_mode:
                self._update_compose_bar_for(flow)
            QTimer.singleShot(0, lambda: self._populate_detail(flow))
        else:
            # All rows deselected — save edits from the outgoing flow
            prev = self._selected_flow
            if prev is not None:
                if self._edit_mode or self._compose_mode:
                    self._request_panel.apply_request_edits(prev)
                    self._sync_content_length(prev, is_request=True)
                    self._response_panel.apply_response_edits(prev)
                    self._sync_content_length(prev, is_request=False)
                if self._edit_mode:
                    self._edit_mode = False
                    self._request_panel.set_editable(False)
                    self._response_panel.set_editable(False)
            self._selected_flow = None
            if self._compose_mode:
                self._cancel_compose_mode()

    def _on_session_double_clicked(self, index) -> None:
        """Open a separate detail window when a session is double-clicked."""
        if not index.isValid():
            return
        source_idx = self._sort_proxy.mapToSource(index)
        flow = self._session_model.get_flow(source_idx.row())
        if flow is not None:
            self._view_flow_detail()

    def _populate_detail(self, flow) -> None:
        if flow is None:
            return
        self._request_panel.populate_request(flow)
        self._response_panel.populate_response(flow)

    # ── Proxy event handlers (called from proxy thread) ──

    def _on_proxy_flow_add(self, flow) -> None:
        self._bridge.flow_added.emit(flow)

    def _on_proxy_flow_update(self, flow) -> None:
        self._bridge.flow_updated.emit(flow)

    # ── Qt main thread handlers ──

    def _on_flow_added(self, flow) -> None:
        from mitmproxy.http import HTTPFlow
        if not isinstance(flow, HTTPFlow):
            return
        # Filter out flows matching filter rules on arrival
        if self._match_any_filter(flow):
            return
        # Skip if already in model (prevents duplicate on compose + send)
        if flow in self._session_model._flows:
            return
        self._session_model.add_flow(flow)
        if flow.metadata.get("_replay_sequentially"):
            self._session_model.set_flow_fg_color(flow, QColor("#3d7aa1"))
        # Auto-scroll to bottom if auto-roll is enabled
        if self._auto_roll:
            self._session_table.scrollToBottom()
        # In breakpoint mode, mark as pending so compose bar appears on selection
        if self._breakpoint_mode or (
            self._breakpoint_rules and self._match_breakpoint_rules(flow)
        ):
            self._flow_state[str(flow.id)] = "edit"
        # Apply Auto Rule Color
        self._apply_auto_color(flow)
        # Apply a color stashed by a plugin hook (e.g. plugin request handler)
        c = flow.metadata.get("_plugin_color") if flow.metadata else None
        if c:
            self._session_model.set_flow_color(flow, QColor(c))

    def _match_breakpoint_rules(self, flow) -> bool:
        """Check if a flow matches any breakpoint rule.
        
        Must match _BreakpointRequestIntercept._match_rules() exactly:
        case-insensitive for both 'contains' and 'regex' modes.
        """
        if not flow.request:
            return False
        for rule in self._breakpoint_rules:
            prop = rule.get("property", "host")
            match_type = rule.get("match_type", "contains")
            value = rule.get("value", "")
            if prop == "host":
                target = flow.request.host or ""
            else:
                target = ""
            if match_type == "regex":
                import re
                try:
                    if re.search(value, target, re.IGNORECASE):
                        return True
                except re.error:
                    pass
            else:  # contains
                if value.lower() in target.lower():
                    return True
        return False

    def _on_flow_updated(self, flow) -> None:
        from mitmproxy.http import HTTPFlow
        if not isinstance(flow, HTTPFlow):
            return
        fid = str(flow.id)
        self._session_model.update_flow(flow)
        # Apply Auto Rule Color
        self._apply_auto_color(flow)
        # Keep Sequential Replay's color ahead of the Hosts Remapping color.
        if flow.metadata.get("_replay_sequentially"):
            self._session_model.set_flow_fg_color(flow, QColor("#3d7aa1"))
        elif getattr(flow, "_hosts_remapped", False):
            self._session_model.set_flow_fg_color(flow, QColor("#3399FF"))
        # Intercepted flow received response → show it for editing
        if self._flow_state.get(fid) == "waiting_response" and flow.response:
            # Clean up bypass marker if response-only replay completed
            self._master.breakpoint_req_intercept.response_only_ids.discard(fid)
            if self._selected_flow is flow:
                self._request_panel.set_editable(False)
                self._response_panel.set_editable(True)
                self._response_panel.populate_response(flow)
                self._update_compose_bar_for(flow)
        elif self._selected_flow is flow and not self._compose_mode:
            self._response_panel.populate_response(flow)

    # ── Auto Rules ──

    def _auto_rules(self) -> list[dict]:
        """Load Auto Rules from autos.json, caching by file mtime."""
        auto_file = os.path.join(os.getcwd(), "autos.json")
        try:
            mtime = os.path.getmtime(auto_file)
        except OSError:
            mtime = None
        if (
            not hasattr(self, "_auto_rules_cache")
            or mtime != getattr(self, "_auto_rules_mtime", None)
        ):
            try:
                with open(auto_file, "r", encoding="utf-8") as f:
                    data = json_mod.load(f)
                self._auto_rules_cache = data if isinstance(data, list) else []
            except (OSError, ValueError):
                self._auto_rules_cache = []
            self._auto_rules_mtime = mtime
        return self._auto_rules_cache

    @staticmethod
    def _auto_rule_text(flow, item: str) -> str:
        """Return the matching text of ``item`` for a flow (same as the addon).

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
            return str(flow.request.headers)
        if item == "Response.Header":
            if not flow.response:
                return ""
            return str(flow.response.headers)
        if item == "Response.Body":
            if not flow.response:
                return ""
            content = flow.response.get_text(strict=False)
            return content or ""
        return ""

    @staticmethod
    def _auto_rule_matches(rule: dict, text: str) -> bool:
        """Check whether ``text`` satisfies the rule's match condition."""
        match_type = rule.get("match_type", "String")
        match_value = rule.get("match_value", "")
        if not match_value:
            return False
        if match_type == "Regex":
            try:
                return re.search(match_value, text) is not None
            except re.error:
                return False
        return match_value in text

    def _apply_auto_color(self, flow) -> None:
        """Apply the color of the first matching Auto Rule with action=Color.

        Runs on every flow add/update. When a matching Color rule exists the
        color is (re)applied; otherwise the flow color is left untouched so
        manual highlights (e.g. Find) are preserved.
        """
        found = False
        color = None
        for rule in self._auto_rules():
            if not rule.get("enabled", True):
                continue
            if rule.get("action") != "Color":
                continue
            text = self._auto_rule_text(flow, rule.get("item", ""))
            if self._auto_rule_matches(rule, text):
                found = True
                cname = rule.get("value")
                for name, c in AutoRuleDialog.COLOR_CHOICES:
                    if name == cname:
                        color = c
                        break
                break
        if found:
            self._session_model.set_flow_color(flow, color)

    def _clear_sessions(self) -> None:
        locked = [f for f in self._session_model._flows if self._is_flow_locked(f)]
        if not locked:
            self._session_model.clear()
            self._master.view.clear()
            self._selected_flow = None
            return
        # Keep locked sessions; remove only the unlocked ones.
        locked_ids = {f.id for f in locked}
        model = self._session_model
        model.beginResetModel()
        model._flows = locked
        model._flow_colors = {
            fid: c for fid, c in model._flow_colors.items() if fid in locked_ids
        }
        model._flow_fg_colors = {
            fid: c for fid, c in model._flow_fg_colors.items() if fid in locked_ids
        }
        model.endResetModel()
        to_remove = [
            f for f in list(self._master.view) if not self._is_flow_locked(f)
        ]
        if to_remove:
            self._master.view.remove(to_remove)
        if self._selected_flow is not None and self._selected_flow not in locked:
            self._selected_flow = None

    def _open_custom_rules(self) -> None:
        """Open rules.py in a Python code editor dialog."""
        rules_path = os.path.join(os.getcwd(), "rules.py")
        dlg = CodeEditorDialog(rules_path, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _open_hosts_remapping(self) -> None:
        """Open the Hosts Remapping dialog."""
        dlg = HostsRemappingDialog(self._master, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    # ── Frameless window management ──

    def _apply_title_bar_theme(self, theme_id: str) -> None:
        """Style the title strip: theme QSS for the built-in themes, an inline
        fallback for the Default theme (which has no global stylesheet)."""
        if theme_id == "default":
            self._title_bar.setStyleSheet(_DEFAULT_TITLE_BAR_QSS)
        else:
            self._title_bar.setStyleSheet("")
        overlay = getattr(self, "_frame_overlay", None)
        if overlay is not None:
            overlay.set_dark(theme_id in _DARK_THEMES)
        hdr = getattr(self, "_session_header", None)
        if hdr is not None:
            hdr.set_dark(theme_id in _DARK_THEMES)

    def _native_is_maximized(self) -> bool:
        """Read the real native WS_MAXIMIZE style bit (Windows).  Qt's
        isMaximized() can disagree with the OS state on frameless windows."""
        if sys.platform != "win32":
            return False
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            style = user32.GetWindowLongPtrW(wintypes.HWND(hwnd), _GWL_STYLE)
            return bool(style & 0x01000000)  # WS_MAXIMIZE
        except Exception:
            return False

    def _restore_window_geometry(self) -> None:
        """Restore the last window position/size if it is still on a screen."""
        saved = self._config.window_geometry
        if isinstance(saved, list) and len(saved) == 4:
            rect = QRect(*saved)
            for screen in QApplication.screens():
                avail = screen.availableGeometry()
                if avail.intersects(rect) and rect.width() < avail.width() and rect.height() < avail.height():
                    width = min(max(rect.width(), self.minimumWidth()), avail.width() - 1)
                    height = min(max(rect.height(), self.minimumHeight()), avail.height() - 1)
                    x = min(max(rect.x(), avail.left()), avail.right() - width)
                    y = min(max(rect.y(), avail.top()), avail.bottom() - height)
                    self.setGeometry(x, y, width, height)
                    return
        avail = QApplication.primaryScreen().availableGeometry()
        w = min(1613, max(self.minimumWidth(), avail.width() - 20))
        h = min(1008, max(self.minimumHeight(), avail.height() - 20))
        self.resize(w, h)

    def showNormal(self) -> None:
        """Restore the window to its normal (non-maximized) size.

        On Windows this frameless window (WS_THICKFRAME + DWM, see
        _enable_dwm_shadow) hits a Qt bug: Qt's own showNormal() flips
        isMaximized() to False but never clears the native WS_MAXIMIZE style
        bit, so every later move()/setGeometry() is forced back to the
        maximized rect by the OS.  Clear WS_MAXIMIZE natively and re-apply the
        geometry we saved right before maximizing."""
        did_restore = False
        if sys.platform == "win32" and (self.isMaximized() or self._native_is_maximized()):
            did_restore = True
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                user32.ShowWindow(wintypes.HWND(hwnd), 9)  # SW_RESTORE
                # Belt and braces: drop WS_MAXIMIZE explicitly so the OS can
                # no longer override our geometry afterwards.
                user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
                user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
                style = user32.GetWindowLongPtrW(wintypes.HWND(hwnd), _GWL_STYLE)
                if style & 0x01000000:  # WS_MAXIMIZE
                    user32.SetWindowLongPtrW(wintypes.HWND(hwnd), _GWL_STYLE, style & ~0x01000000)
                    user32.SetWindowPos(
                        wintypes.HWND(hwnd), wintypes.HWND(0), 0, 0, 0, 0,
                        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_FRAMECHANGED,
                    )
            except Exception:
                pass
        super().showNormal()
        if did_restore and not self.isMaximized() and self._normal_geo is not None:
            self.setGeometry(self._normal_geo)

    def showMaximized(self) -> None:
        # Remember the real normal geometry: Qt's own record gets corrupted to
        # the maximized rect when this frameless window is restored later.
        if not self.isMaximized():
            self._normal_geo = QRect(self.geometry())
        super().showMaximized()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._config.window_maximized = False
            self._update_edge_cursor(self.mapFromGlobal(QCursor.pos()))
        else:
            self.showMaximized()
            self._config.window_maximized = True
        self._update_window_buttons()

    def _update_window_buttons(self) -> None:
        """Swap the maximize glyph between ▢ and ▣ depending on the state."""
        btn_max = getattr(self, "_btn_max", None)
        if btn_max is None:
            return
        if self.isMaximized():
            btn_max.setText("\u25a3")  # ▣ restore
            btn_max.setToolTip("Restore")
        else:
            btn_max.setText("\u25a2")  # ▢ maximize
            btn_max.setToolTip("Maximize")

    def _begin_window_drag(self, global_pos: QPoint) -> None:
        if self.isMaximized():
            return
        self._drag_offset = global_pos - self.frameGeometry().topLeft()

    def _continue_window_drag(self, global_pos: QPoint) -> None:
        if self._drag_offset is None or self.isMaximized() or self._resize_edge is not None:
            return
        self.move(global_pos - self._drag_offset)

    def _end_window_drag(self) -> None:
        self._drag_offset = None

    def _edge_at(self, pos: QPoint) -> str | None:
        """Return the resize edge ('n','s','e','w','nw','ne','sw','se') under
        ``pos`` (window coordinates), or None when not near an edge."""
        if self.isMaximized():
            return None
        r = self.rect()
        x, y = pos.x(), pos.y()
        west = x <= 6
        east = x >= r.width() - 1 - 6
        north = y <= 6
        south = y >= r.height() - 1 - 6
        if west and north:
            return "nw"
        if east and north:
            return "ne"
        if west and south:
            return "sw"
        if east and south:
            return "se"
        if west:
            return "w"
        if east:
            return "e"
        if north:
            return "n"
        if south:
            return "s"
        return None

    def _do_manual_resize(self, global_pos: QPoint) -> None:
        geo = QRect(self._resize_start_geom)
        dx = global_pos.x() - self._resize_start_global.x()
        dy = global_pos.y() - self._resize_start_global.y()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        e = self._resize_edge or ""
        if "w" in e:
            geo.setLeft(min(geo.x() + dx, geo.right() + 1 - min_w))
        if "e" in e:
            geo.setWidth(max(min_w, geo.width() + dx))
        if "n" in e:
            geo.setTop(min(geo.y() + dy, geo.bottom() + 1 - min_h))
        if "s" in e:
            geo.setHeight(max(min_h, geo.height() + dy))

        self.setGeometry(geo)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._resize_edge = None
            self._drag_offset = None
            self._update_edge_cursor(self.mapFromGlobal(QCursor.pos()))
            self._update_window_buttons()

    def _begin_edge_resize(self, local_pos: QPoint, global_pos: QPoint) -> bool:
        """Start a Qt-level edge resize when ``local_pos`` (in window
        coordinates) is inside an edge zone.

        The top-level window's own mouse handlers and the child widgets that
        cover the window edges (title bar, menu bar) all route through here, so
        edge resizing works no matter which widget the cursor happens to be
        over.  Returns True when a resize was started."""
        if self.isMaximized():
            return False
        edge = self._edge_at(local_pos)
        if edge is None:
            return False
        self._resize_edge = edge
        self._resize_start_global = global_pos
        self._resize_start_geom = QRect(self.geometry())
        self.setCursor(_EDGE_CURSORS[edge])
        return True

    def _end_edge_resize(self) -> None:
        self._resize_edge = None
        self.unsetCursor()

    # ── Right-click system menu (title-bar style) ──

    def _show_window_system_menu(self, global_pos: QPoint) -> None:
        """Pop up the classic window system menu (Restore / Move / Size /
        Minimize / Maximize / Close) like right-clicking a native title bar."""
        menu = QMenu(self)
        maximized = self.isMaximized()

        act_restore = menu.addAction("Restore")
        act_restore.setEnabled(maximized)
        act_restore.triggered.connect(self.showNormal)

        act_move = menu.addAction("Move")
        act_move.setEnabled(not maximized)
        act_move.triggered.connect(self._system_menu_move)

        act_size = menu.addAction("Size")
        act_size.setEnabled(not maximized)
        act_size.triggered.connect(self._system_menu_size)

        menu.addSeparator()

        act_min = menu.addAction("Minimize")
        act_min.triggered.connect(self.showMinimized)

        act_max = menu.addAction("Restore" if maximized else "Maximize")
        act_max.triggered.connect(self._toggle_maximize)

        menu.addSeparator()

        act_close = menu.addAction("Close")
        act_close.triggered.connect(self.close)

        menu.exec(global_pos)

    def _system_menu_move(self) -> None:
        """'Move': grab the mouse and drag the window until the button is
        released (Esc cancels).  Reuses the title-bar drag logic."""
        if self.isMaximized():
            return
        self._begin_window_drag(QCursor.pos())
        self._mouse_grabbed = True
        self.grabMouse()
        self.grabKeyboard()
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def _system_menu_size(self) -> None:
        """'Size': grab the mouse and resize from the bottom-right corner
        until the button is released (Esc cancels)."""
        if self.isMaximized():
            return
        self._resize_edge = "se"
        self._resize_start_global = QCursor.pos()
        self._resize_start_geom = self.geometry()
        self._mouse_grabbed = True
        self.grabMouse()
        self.grabKeyboard()
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def _update_edge_cursor(self, local_pos: QPoint) -> None:
        if self.isMaximized():
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        self.setCursor(
            _EDGE_CURSORS.get(self._edge_at(local_pos), Qt.CursorShape.ArrowCursor)
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            local_pos = event.position().toPoint()
            global_pos = event.globalPosition().toPoint()
            if self._begin_edge_resize(local_pos, global_pos):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resize_edge is not None:
            self._do_manual_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self._mouse_grabbed and self._drag_offset is not None:
            # System-menu "Move" loop: the mouse is grabbed, so the window
            # receives the move events directly.
            self._continue_window_drag(event.globalPosition().toPoint())
            event.accept()
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            self._update_edge_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_edge is not None:
            self._end_edge_resize()
        if self._drag_offset is not None:
            self._end_window_drag()
        if self._mouse_grabbed:
            self._mouse_grabbed = False
            self.releaseMouse()
            self.releaseKeyboard()
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._mouse_grabbed:
            if self._resize_edge is not None:
                self._end_edge_resize()
            if self._drag_offset is not None:
                self._end_window_drag()
            self._mouse_grabbed = False
            self.releaseMouse()
            self.releaseKeyboard()
            self.unsetCursor()
            event.accept()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:
        if self._resize_edge is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def eventFilter(self, obj, event) -> bool:
        # Child widgets (e.g. the session table) inherit the window cursor, so
        # the edge-resize cursor would stick after the pointer moves off an
        # edge onto a child widget - the window's own mouseMoveEvent no longer
        # fires there.  Recompute the cursor from the global position instead.
        if (
            event.type() == QEvent.Type.MouseMove
            and self._resize_edge is None
            and not self._mouse_grabbed
        ):
            w = obj if isinstance(obj, QWidget) else None
            if w is not None and w.window() is self:
                self._update_edge_cursor(
                    self.mapFromGlobal(event.globalPosition().toPoint())
                )
        return super().eventFilter(obj, event)

    def nativeEvent(self, eventType, message):
        """Windows: frameless-window DWM chrome + keep a maximized window
        from covering the taskbar.

        WM_GETMINMAXINFO constrains the maximized size to the monitor's work
        area.  WM_NCCALCSIZE removes the native frame so the client covers the
        whole window (DWM still draws the shadow/border outside), and
        WM_NCHITTEST disables native hit-testing so Qt-level edge resizing
        stays in charge.  Everything else (dragging, edge resizing,
        double-click maximize/restore, control buttons) is handled by Qt's
        mouse handlers, which are more reliable than the OS hit-testing a
        frameless window.
        """
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_GETMINMAXINFO:
                    return self._native_min_max_info(msg)
                if msg.message == _WM_NCCALCSIZE:
                    # Full client area: the DWM frame/border/shadow live outside.
                    return True, 0
                if msg.message == _WM_NCHITTEST:
                    return True, _HTCLIENT
            except Exception:
                # Never let a Python error escape nativeEvent: PyQt crashes the
                # process (0xC0000409) when an exception crosses the C++ boundary.
                pass
        # NB: do not call super().nativeEvent() here - on PyQt6 6.11 + Python 3.14
        # that call chain crashes with 0xC0000409 (stack buffer overrun) during
        # window show.  Returning (False, 0) lets Qt's default handling continue,
        # which is exactly what QObject::nativeEvent does by default anyway.
        return False, 0

    def _native_min_max_info(self, msg) -> tuple[bool, int]:
        mmi = _MINMAXINFO.from_address(int(msg.lParam))
        hwnd = int(self.winId())
        monitor = ctypes.windll.user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            mmi.ptMaxPosition.x = work.left
            mmi.ptMaxPosition.y = work.top
            mmi.ptMaxSize.x = work.right - work.left
            mmi.ptMaxSize.y = work.bottom - work.top
        return True, 0

    def closeEvent(self, event) -> None:
        # Persist window state so the next launch opens where it left off
        if self.isMaximized():
            geo = self._normal_geo if self._normal_geo is not None else self.normalGeometry()
        else:
            geo = self.geometry()
        # Reload first because editor preferences are saved by short-lived
        # AppConfig instances and self._config may contain an older snapshot.
        config = AppConfig()
        config.window_geometry = [geo.x(), geo.y(), geo.width(), geo.height()]
        config.window_maximized = self.isMaximized()
        config.save()
        self._master.stop()
        event.accept()


def launch(args: Sequence[str] | None = None) -> int | None:
    import os as _os
    _os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")

    if args is None:
        args = sys.argv[1:]

    config = AppConfig()

    opts = options.Options()
    parser = cmdline.mitmgui(opts)
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        return 0

    if parsed.version:
        from mitmproxy.utils import debug

        print(debug.dump_system_info())
        return 0

    adict = {k: v for k, v in vars(parsed).items() if k in opts and v is not None}
    opts.update(**adict)

    # Apply config after CLI args so CLI args win on conflict
    config.apply_to_opts(opts)

    app = QApplication(sys.argv)
    app.setApplicationName("mitmgui")

    # Apply saved theme before any widget is created
    themes.apply_theme(app, config.theme)

    try:
        proxy = MitmGuiMaster(opts)
    except Exception as e:
        print(f"FATAL: Failed to create proxy: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    # Replay all selected flows in parallel. mitmproxy's default is 1, which
    # makes each replayed request wait for the previous one to complete.
    proxy.options.update(client_replay_concurrency=-1)

    window = MitmGuiMainWindow(proxy, config)
    window.show()

    ret = app.exec()
    proxy.stop()
    return ret
    window.show()

    ret = app.exec()
    proxy.stop()
    return ret
