from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PyQt6.QtGui import QColor
from mitmproxy import flow


class SessionTableModel(QAbstractTableModel):
    """Table model for displaying HTTP flows in the session list."""

    COLUMNS = [
        ("#", 40),
        ("Result", 60),
        ("Protocol", 70),
        ("Host", 200),
        ("URL", 300),
        ("Method", 60),
        ("Body", 80),
        ("Content-Type", 130),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._flows: list[flow.Flow] = []
        self._flow_colors: dict[str, QColor] = {}
        self._flow_fg_colors: dict[str, QColor] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._flows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        f = self._flows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.UserRole:
            if col == 0:
                try:
                    return self._flows.index(f) + 1
                except ValueError:
                    return 0
            return self._get_column_data(f, col)

        if role == Qt.ItemDataRole.DisplayRole:
            return self._get_column_data(f, col)
        elif role == Qt.ItemDataRole.ForegroundRole:
            fid = getattr(f, "id", None)
            if fid in self._flow_fg_colors:
                return self._flow_fg_colors[fid]
            if col == 1:  # Result column coloring
                status = getattr(getattr(f, "response", None), "status_code", 0)
                if 200 <= status < 300:
                    return QColor("#006600")
                elif 400 <= status < 500:
                    return QColor("#cc6600")
                elif status >= 500:
                    return QColor("#cc0000")
        elif role == Qt.ItemDataRole.BackgroundRole:
            fid = getattr(f, "id", None)
            if fid in self._flow_colors:
                return self._flow_colors[fid]

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section][0]
        return None

    def _get_column_data(self, f, col: int) -> str:
        if col == 0:
            try:
                idx = self._flows.index(f) + 1
            except ValueError:
                idx = "?"
            return str(idx)
        elif col == 1:  # Result
            if hasattr(f, "response") and f.response:
                return str(f.response.status_code)
            elif hasattr(f, "error") and f.error:
                return "ERR"
            return "..."
        elif col == 2:  # Protocol
            if hasattr(f, "request") and f.request:
                return f.request.http_version or "HTTP/1.1"
            return ""
        elif col == 3:  # Host
            if hasattr(f, "request") and f.request:
                # For hosts-mapped flows, use the saved original host header value
                original = getattr(f, "_original_host", None)
                if original:
                    return original
                return f.request.host_header or f.request.host or ""
            return ""
        elif col == 4:  # URL
            if hasattr(f, "request") and f.request:
                return f.request.path or ""
            return ""
        elif col == 5:  # Method
            if hasattr(f, "request") and f.request:
                return f.request.method or ""
            return ""
        elif col == 6:  # Body
            if hasattr(f, "response") and f.response:
                if f.response.timestamp_end is None:
                    content_length = f.response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            return f"{self._format_size(int(content_length))}..."
                        except ValueError:
                            pass
                    return "..."
                # Use strict=False so malformed content-encoding headers (e.g.
                # a charset like "utf-8" or a non-decodable binary body) don't
                # raise; we only need the size here.
                content = f.response.get_content(strict=False)
                if content is None:
                    return "..."
                return self._format_size(len(content))
            return "-"
        elif col == 7:  # Content-Type
            if hasattr(f, "response") and f.response:
                content_type = f.response.headers.get("content-type", "")
                if ";" in content_type:
                    return content_type.split(";", 1)[0].strip()
                return content_type
            return ""
        return ""

    def _format_size(self, size: int) -> str:
        if size < 1024:
            return str(size)
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}K"
        else:
            return f"{size / (1024 * 1024):.1f}M"

    def add_flow(self, flow: flow.Flow) -> None:
        row = len(self._flows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._flows.append(flow)
        self.endInsertRows()

    def update_flow(self, flow: flow.Flow) -> None:
        """Notify view that a flow's data has changed (e.g. response arrived).
        Emit a single dataChanged covering columns 1-7 (excluding # column)
        to batch the repaint and prevent header flicker."""
        try:
            row = self._flows.index(flow)
        except ValueError:
            return
        top_left = self.index(row, 1)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def get_flow(self, row: int) -> flow.Flow | None:
        if 0 <= row < len(self._flows):
            return self._flows[row]
        return None

    def clear(self) -> None:
        self.beginResetModel()
        self._flows.clear()
        self._flow_colors.clear()
        self._flow_fg_colors.clear()
        self.endResetModel()

    def set_flow_color(self, flow: flow.Flow, color: QColor | None) -> None:
        """Set background color for a flow. Pass None to reset to default."""
        fid = getattr(flow, "id", None)
        if fid is None:
            return
        try:
            row = self._flows.index(flow)
        except ValueError:
            return
        if color is None:
            self._flow_colors.pop(fid, None)
        else:
            self._flow_colors[fid] = color
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def set_flow_fg_color(self, flow: flow.Flow, color: QColor | None) -> None:
        """Set foreground (text) color for a flow. Pass None to reset to default."""
        fid = getattr(flow, "id", None)
        if fid is None:
            return
        try:
            row = self._flows.index(flow)
        except ValueError:
            return
        if color is None:
            self._flow_fg_colors.pop(fid, None)
        else:
            self._flow_fg_colors[fid] = color
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)
