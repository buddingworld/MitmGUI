"""Theme management for MitmGUI.

Themes are applied globally through ``QApplication.setStyleSheet``:

- ``default``   : stock PyQt look (no stylesheet)
- ``ios``       : hand-written QSS mimicking the iOS 26 design language
- ``android``   : hand-written QSS mimicking the latest Material-based Android
- ``pyqt_light``: hand-written QSS borrowing the PyQtDarkTheme light palette
- ``pyqt_dark`` : hand-written QSS borrowing the PyQtDarkTheme dark palette

The PyQtDarkTheme look is reimplemented directly (no external dependency) so
the QSS can avoid a global ``QWidget { background-color }`` rule, which would
otherwise make Qt item views ignore the model's BackgroundRole and break the
Ctrl+0..9 session highlighting.
"""

from __future__ import annotations

DEFAULT_THEME = "default"

# id -> display name (order matters: used to build the Themes menu)
THEMES: dict[str, str] = {
    DEFAULT_THEME: "Default",
    "ios": "IOS Style",
    "android": "Android Style",
    "pyqt_light": "PyQtDarkTheme (Light)",
    "pyqt_dark": "PyQtDarkTheme (Dark)",
}

# Editor colours per theme for QScintilla widgets (Raw tab / New Session).
# QScintilla paints its own editor background, so the application QSS cannot
# colour the editor area; these values mirror each theme's
# QLineEdit/QPlainTextEdit/QTextEdit rules and are applied programmatically.
# Format: (background, foreground, selection_background, selection_foreground)
EDITOR_COLORS: dict[str, tuple[str, str, str, str]] = {
    DEFAULT_THEME: ("#FFFFFF", "#000000", "#308CC6", "#FFFFFF"),
    "ios": ("#FFFFFF", "#000000", "#007AFF", "#FFFFFF"),
    "android": ("#FFFFFF", "#1D1B20", "#6750A4", "#FFFFFF"),
    "pyqt_light": ("#FFFFFF", "#4D5157", "#0081DB", "#FFFFFF"),
    "pyqt_dark": ("#202124", "#E4E7EB", "#12507B", "#FFFFFF"),
}

# Editor fonts per theme for QScintilla widgets, mirroring the
# QsciScintilla rule of each stylesheet.  Qt 6 resolves the QSS
# "font-size: 13px" of the QsciScintilla rules to a 13 px pixel font and
# applies it over any widget-level setFont() (QSS wins), so these values
# are only a fallback for the "default" theme which has no stylesheet
# (there the application font is used: point_size 0).
# Format: (family, point_size)
THEME_FONTS: dict[str, tuple[str, int]] = {
    DEFAULT_THEME: ("Segoe UI", 0),
    "ios": ("Segoe UI", 13),
    "android": ("Segoe UI", 13),
    "pyqt_light": ("Segoe UI", 13),
    "pyqt_dark": ("Segoe UI", 13),
}

# ── iOS 26 ("Liquid Glass") inspired theme ──────────────────────────────────

IOS_STYLESHEET = """
* {
    font-family: "SF Pro Display", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #000000;
}

QMainWindow, QDialog {
    background-color: #F2F2F7;
}

QMenuBar {
    background-color: rgba(248, 248, 252, 0.92);
    border-bottom: 1px solid #D1D1D6;
    padding: 2px 6px;
}
QMenuBar#mainMenuBar {
    border-bottom: none;
}
QWidget#titleBar {
    background-color: rgba(248, 248, 252, 0.92);
    border-bottom: 1px solid #D1D1D6;
}
QLabel#titleLabel {
    color: #3C3C43;
    background: transparent;
}
QToolButton#titleMinBtn, QToolButton#titleMaxBtn, QToolButton#titleCloseBtn {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #3C3C43;
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
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 8px;
    color: #3C3C43;
}
QMenuBar::item:selected {
    background: rgba(0, 122, 255, 0.12);
    color: #007AFF;
}
QMenuBar::item:pressed {
    background: rgba(0, 122, 255, 0.18);
}

QMenu {
    background-color: rgba(248, 248, 252, 0.96);
    border: 1px solid #D1D1D6;
    border-radius: 14px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 28px 8px 16px;
    border-radius: 8px;
    color: #000000;
}
QMenu::item:selected {
    background-color: #007AFF;
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: #8E8E93;
}
QMenu::separator {
    height: 1px;
    background: #E5E5EA;
    margin: 6px 12px;
}

QToolBar {
    background: rgba(248, 248, 252, 0.92);
    border-bottom: 1px solid #D1D1D6;
    padding: 6px;
    spacing: 6px;
}
QToolBar::separator {
    width: 1px;
    background: #E5E5EA;
    margin: 4px 4px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 6px 12px;
    color: #007AFF;
}
QToolButton:hover {
    background: rgba(0, 122, 255, 0.10);
}
QToolButton:pressed {
    background: rgba(0, 122, 255, 0.18);
}
QToolButton:checked {
    background: #007AFF;
    color: #FFFFFF;
}

QTableView, QTableWidget, QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F7F7FA;
    gridline-color: #E5E5EA;
    border: none;
    selection-background-color: rgba(0, 122, 255, 0.25);
    selection-color: #000000;
}
QTableView::item, QTableWidget::item, QListWidget::item, QTreeWidget::item {
    padding: 4px;
}
QTableView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected, QTreeWidget::item:selected {
    background: rgba(0, 122, 255, 0.25);
    color: #000000;
}
QHeaderView::section {
    background-color: #F2F2F7;
    color: #8E8E93;
    border: none;
    border-bottom: 1px solid #E5E5EA;
    padding: 8px 6px;
    font-weight: 600;
}
QHeaderView::section:hover {
    color: #3C3C43;
}
QTableCornerButton::section {
    background: #F2F2F7;
    border: none;
}

QPushButton {
    background-color: #F2F2F7;
    color: #000000;
    border: none;
    border-radius: 12px;
    padding: 8px 16px;
    min-width: 40px;
}
QPushButton:hover {
    background-color: #E5E5EA;
}
QPushButton:pressed {
    background-color: #D1D1D6;
}
QPushButton:disabled {
    background-color: #F2F2F7;
    color: #C7C7CC;
}
QPushButton:default {
    background-color: #007AFF;
    color: #FFFFFF;
}
QPushButton:default:hover {
    background-color: #3395FF;
}
QPushButton:default:pressed {
    background-color: #0062CC;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 10px;
    padding: 6px;
    selection-background-color: #007AFF;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #007AFF;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    background-color: #F2F2F7;
    color: #C7C7CC;
}

QsciScintilla {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 10px;
    padding: 6px;
    /* Pick a font that actually exists on Windows: Scintilla passes the
       family name straight to GDI, so the "SF Pro Display" fallback chain
       of the global "*" rule would resolve to a different (bolder/larger
       looking) system font than Qt uses for QPlainTextEdit. */
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}
QsciScintilla:focus {
    border: 1px solid #007AFF;
}

QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 10px;
    padding: 5px 10px;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #007AFF;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #3C3C43;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D1D1D6;
    border-radius: 10px;
    selection-background-color: rgba(0, 122, 255, 0.20);
    selection-color: #000000;
}

QTabWidget::pane {
    border: 1px solid #D1D1D6;
    border-radius: 12px;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #8E8E93;
    padding: 8px 16px;
    border: none;
    border-radius: 10px;
    margin: 2px 2px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #007AFF;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: rgba(0, 122, 255, 0.08);
}

QCheckBox, QRadioButton {
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 20px;
    height: 20px;
    border: 1.5px solid #C7C7CC;
    background: #FFFFFF;
}
QCheckBox::indicator {
    border-radius: 6px;
}
QRadioButton::indicator {
    border-radius: 10px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #007AFF;
}
QCheckBox::indicator:checked {
    background: #007AFF;
    border-color: #007AFF;
}
QRadioButton::indicator:checked {
    background: #FFFFFF;
    border: 6px solid #007AFF;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background: #E5E5EA;
    border-color: #E5E5EA;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #C7C7CC;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #AEAEB2;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #C7C7CC;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QSplitter::handle {
    background: transparent;
}
QSplitter::handle:hover {
    background: rgba(0, 122, 255, 0.15);
}

QStatusBar {
    background: rgba(248, 248, 252, 0.92);
    border-top: 1px solid #D1D1D6;
    color: #8E8E93;
}
QStatusBar::item {
    border: none;
}

QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #E5E5EA;
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #3C3C43;
    font-weight: 600;
}

QToolTip {
    background-color: rgba(60, 60, 67, 0.95);
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
}

QMessageBox {
    background-color: #F2F2F7;
}
QMessageBox QLabel {
    color: #000000;
}
"""

# ── Latest Android (Material 3) inspired theme ──────────────────────────────

ANDROID_STYLESHEET = """
* {
    font-family: "Roboto", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #1D1B20;
}

QMainWindow, QDialog {
    background-color: #F7F2FA;
}

QMenuBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E6E0E9;
    padding: 2px 4px;
}
QMenuBar#mainMenuBar {
    border-bottom: none;
}
QWidget#titleBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E6E0E9;
}
QLabel#titleLabel {
    color: #49454F;
    background: transparent;
}
QToolButton#titleMinBtn, QToolButton#titleMaxBtn, QToolButton#titleCloseBtn {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #49454F;
    min-width: 46px;
    max-width: 46px;
    padding: 0;
}
QToolButton#titleMinBtn:hover, QToolButton#titleMaxBtn:hover {
    background: rgba(0, 0, 0, 0.08);
    color: #1D1B20;
}
QToolButton#titleCloseBtn:hover {
    background: #E81123;
    color: #FFFFFF;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 8px;
    color: #49454F;
}
QMenuBar::item:selected {
    background: #E8DEF8;
    color: #21005D;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E6E0E9;
    border-radius: 12px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 28px 8px 16px;
    border-radius: 8px;
    color: #1D1B20;
}
QMenu::item:selected {
    background: #E8DEF8;
    color: #21005D;
}
QMenu::item:disabled {
    color: #CAC4D0;
}
QMenu::separator {
    height: 1px;
    background: #E6E0E9;
    margin: 6px 12px;
}

QToolBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E6E0E9;
    padding: 4px;
    spacing: 4px;
}
QToolBar::separator {
    width: 1px;
    background: #E6E0E9;
    margin: 6px 4px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 6px 12px;
    color: #6750A4;
}
QToolButton:hover {
    background: #E8DEF8;
}
QToolButton:pressed {
    background: #D0BCFF;
}
QToolButton:checked {
    background: #6750A4;
    color: #FFFFFF;
}

QTableView, QTableWidget, QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F7F2FA;
    gridline-color: #E6E0E9;
    border: none;
    selection-background-color: #E8DEF8;
    selection-color: #21005D;
}
QTableView::item, QTableWidget::item, QListWidget::item, QTreeWidget::item {
    padding: 4px;
}
QTableView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #E8DEF8;
    color: #21005D;
}
QHeaderView::section {
    background-color: #F7F2FA;
    color: #49454F;
    border: none;
    border-right: 1px solid #E6E0E9;
    border-bottom: 1px solid #E6E0E9;
    padding: 8px 6px;
    font-weight: 600;
}
QHeaderView::section:hover {
    color: #21005D;
}
QTableCornerButton::section {
    background: #F7F2FA;
    border: none;
}

QPushButton {
    background-color: #E8DEF8;
    color: #21005D;
    border: none;
    border-radius: 20px;
    padding: 8px 24px;
    min-width: 40px;
}
QPushButton:hover {
    background-color: #D0BCFF;
}
QPushButton:pressed {
    background-color: #BDB2FF;
}
QPushButton:disabled {
    background-color: #E6E0E9;
    color: #CAC4D0;
}
QPushButton:default {
    background-color: #6750A4;
    color: #FFFFFF;
}
QPushButton:default:hover {
    background-color: #7C67BC;
}
QPushButton:default:pressed {
    background-color: #59428C;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #79747E;
    border-radius: 8px;
    padding: 7px;
    selection-background-color: #6750A4;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 2px solid #6750A4;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    background-color: #F3EDF7;
    color: #CAC4D0;
}

QsciScintilla {
    background-color: #FFFFFF;
    border: 1px solid #79747E;
    border-radius: 8px;
    padding: 7px;
    /* "Roboto" does not exist on Windows; name a real font first so
       Scintilla's GDI resolution matches the Qt fallback of the global
       "*" rule (Segoe UI). */
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}
QsciScintilla:focus {
    border: 2px solid #6750A4;
}

QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    border: 1px solid #79747E;
    border-radius: 8px;
    padding: 5px 10px;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #6750A4;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #49454F;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E6E0E9;
    border-radius: 8px;
    selection-background-color: #E8DEF8;
    selection-color: #21005D;
}

QTabWidget::pane {
    border: 1px solid #E6E0E9;
    border-radius: 12px;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #49454F;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #6750A4;
    border-bottom: 2px solid #6750A4;
    font-weight: 600;
}

QCheckBox, QRadioButton {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #79747E;
    border-radius: 5px;
    background: #FFFFFF;
}
QCheckBox::indicator:hover {
    border-color: #6750A4;
}
QCheckBox::indicator:checked {
    background: #6750A4;
    border-color: #6750A4;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #79747E;
    border-radius: 9px;
    background: #FFFFFF;
}
QRadioButton::indicator:hover {
    border-color: #6750A4;
}
QRadioButton::indicator:checked {
    background: #FFFFFF;
    border: 6px solid #6750A4;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #CAC4D0;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #B0A6BC;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #CAC4D0;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QSplitter::handle {
    background: transparent;
}
QSplitter::handle:hover {
    background: #E8DEF8;
}

QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E6E0E9;
    color: #49454F;
}
QStatusBar::item {
    border: none;
}

QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #E6E0E9;
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #49454F;
    font-weight: 600;
}

QToolTip {
    background-color: #3B383E;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}

QMessageBox {
    background-color: #F7F2FA;
}
QMessageBox QLabel {
    color: #1D1B20;
}
"""


# ── PyQtDarkTheme palette reimplemented (light) ─────────────────────────────
# Colors borrowed from PyQtDarkTheme (MIT). Structured like the iOS/Android
# themes above: backgrounds are scoped to concrete widget classes so the
# session table still honours the model's BackgroundRole (Ctrl+0..9).

PYQT_LIGHT_STYLESHEET = """
* {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #4D5157;
}

QMainWindow, QDialog {
    background-color: #F8F9FA;
}

QMenuBar {
    background-color: #EBEBEB;
    border-bottom: 1px solid #DADCE0;
    padding: 2px 4px;
}
QMenuBar#mainMenuBar {
    border-bottom: none;
}
QWidget#titleBar {
    background-color: #EBEBEB;
    border-bottom: 1px solid #DADCE0;
}
QLabel#titleLabel {
    color: #4D5157;
    background: transparent;
}
QToolButton#titleMinBtn, QToolButton#titleMaxBtn, QToolButton#titleCloseBtn {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #4D5157;
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
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
    color: #4D5157;
}
QMenuBar::item:selected {
    background-color: #DADCE0;
}
QMenuBar::item:pressed {
    background-color: #C8CBD0;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 28px 6px 16px;
    border-radius: 4px;
    color: #4D5157;
}
QMenu::item:selected {
    background-color: #DADCE0;
    color: #4D5157;
}
QMenu::item:disabled {
    color: #BABDC2;
}
QMenu::separator {
    height: 1px;
    background: #DADCE0;
    margin: 4px 8px;
}

QToolBar {
    background-color: #EBEBEB;
    border-bottom: 1px solid #DADCE0;
    padding: 2px;
    spacing: 4px;
}
QToolBar::separator {
    width: 1px;
    background: #C8CBD0;
    margin: 4px 4px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    color: #0081DB;
}
QToolButton:hover {
    background-color: #DADCE0;
}
QToolButton:pressed {
    background-color: #C8CBD0;
}
QToolButton:checked {
    background-color: #B5CAF4;
    color: #004A8F;
}

QTableView, QTableWidget, QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    alternate-background-color: #E9ECEF;
    gridline-color: #58595C;
    border: none;
    selection-background-color: #0081DB;
    selection-color: #FFFFFF;
}
QTableView::item, QTableWidget::item, QListWidget::item, QTreeWidget::item {
    padding: 4px;
}
QTableView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #0081DB;
    color: #FFFFFF;
}
QHeaderView::section {
    background-color: #DADCE0;
    color: #4D5157;
    border: none;
    border-bottom: 1px solid #C8CBD0;
    padding: 6px 4px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #DADCE0;
    border: none;
}

QPushButton {
    background-color: transparent;
    color: #0081DB;
    border: 1px solid #DADCE0;
    border-radius: 4px;
    padding: 5px 12px;
    min-width: 40px;
}
QPushButton:hover {
    background-color: #E9ECEF;
}
QPushButton:pressed {
    background-color: #DADCE0;
}
QPushButton:disabled {
    color: #BABDC2;
    border-color: #DADCE0;
}
QPushButton:checked {
    border-color: #0081DB;
}
QPushButton:default {
    border-color: #0081DB;
    background-color: #0081DB;
    color: #FFFFFF;
}
QPushButton:default:hover {
    background-color: #1A8FDF;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 4px;
    padding: 5px;
    selection-background-color: #0081DB;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #0081DB;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    color: #BABDC2;
}

QsciScintilla {
    background-color: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 4px;
    padding: 5px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}
QsciScintilla:focus {
    border: 1px solid #0081DB;
}

QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #F8F9FA;
    border: 1px solid #DADCE0;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #0081DB;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #4D5157;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #DADCE0;
    selection-background-color: #0081DB;
    selection-color: #FFFFFF;
}

QTabWidget::pane {
    border: 1px solid #DADCE0;
    border-radius: 4px;
    background: #FFFFFF;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #4D5157;
    padding: 6px 14px;
    border: none;
}
QTabBar::tab:selected {
    background-color: #B5CAF4;
    color: #0081DB;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background-color: #E2EAFB;
}

QCheckBox, QRadioButton {
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #BABDC2;
    background: #FFFFFF;
}
QCheckBox::indicator {
    border-radius: 3px;
}
QRadioButton::indicator {
    border-radius: 9px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #0081DB;
}
QCheckBox::indicator:checked {
    background: #0081DB;
    border-color: #0081DB;
}
QRadioButton::indicator:checked {
    background: #FFFFFF;
    border: 6px solid #0081DB;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background: #E9ECEF;
    border-color: #E9ECEF;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #9B9B9D;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #757577;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #9B9B9D;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QSplitter::handle {
    background: transparent;
}
QSplitter::handle:hover {
    background: #DADCE0;
}

QStatusBar {
    background-color: #DFE1E5;
    color: #4D5157;
    border-top: 1px solid #C8CBD0;
}
QStatusBar::item {
    border: none;
}

QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #4D5157;
    font-weight: 600;
}

QToolTip {
    background-color: #FFFFFF;
    color: #4D5157;
    border: 1px solid #DADCE0;
    border-radius: 4px;
    padding: 4px 8px;
}

QMessageBox {
    background-color: #F8F9FA;
}
QMessageBox QLabel {
    color: #4D5157;
}
"""

# ── PyQtDarkTheme palette reimplemented (dark) ──────────────────────────────

PYQT_DARK_STYLESHEET = """
* {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #E4E7EB;
}

QMainWindow, QDialog {
    background-color: #202124;
}

QMenuBar {
    background-color: #333333;
    border-bottom: 1px solid #3F4042;
    padding: 2px 4px;
}
QMenuBar#mainMenuBar {
    border-bottom: none;
}
QWidget#titleBar {
    background-color: #333333;
    border-bottom: 1px solid #3F4042;
}
QLabel#titleLabel {
    color: #E4E7EB;
    background: transparent;
}
QToolButton#titleMinBtn, QToolButton#titleMaxBtn, QToolButton#titleCloseBtn {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #E4E7EB;
    min-width: 46px;
    max-width: 46px;
    padding: 0;
}
QToolButton#titleMinBtn:hover, QToolButton#titleMaxBtn:hover {
    background: rgba(255, 255, 255, 0.10);
    color: #FFFFFF;
}
QToolButton#titleCloseBtn:hover {
    background: #E81123;
    color: #FFFFFF;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
    color: #E4E7EB;
}
QMenuBar::item:selected {
    background-color: #3F4042;
}
QMenuBar::item:pressed {
    background-color: #4A4C4E;
}

QMenu {
    background-color: #292A2D;
    border: 1px solid #3F4042;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 28px 6px 16px;
    border-radius: 4px;
    color: #E4E7EB;
}
QMenu::item:selected {
    background-color: #3F4042;
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: #697177;
}
QMenu::separator {
    height: 1px;
    background: #3F4042;
    margin: 4px 8px;
}

QToolBar {
    background-color: #333333;
    border-bottom: 1px solid #3F4042;
    padding: 2px;
    spacing: 4px;
}
QToolBar::separator {
    width: 1px;
    background: #4A4C4E;
    margin: 4px 4px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    color: #8AB4F7;
}
QToolButton:hover {
    background-color: #3F4042;
}
QToolButton:pressed {
    background-color: #4A4C4E;
}
QToolButton:checked {
    background-color: #2E465E;
    color: #8AB4F7;
}

QTableView, QTableWidget, QListWidget, QTreeWidget {
    background-color: #000000;
    alternate-background-color: #292B2E;
    gridline-color: #58595C;
    border: none;
    selection-background-color: #8AB4F7;
    selection-color: #202124;
}
QTableView::item, QTableWidget::item, QListWidget::item, QTreeWidget::item {
    padding: 4px;
}
QTableView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #8AB4F7;
    color: #202124;
}
QHeaderView::section {
    background-color: #3F4042;
    color: #E4E7EB;
    border: none;
    border-bottom: 1px solid #4A4C4E;
    padding: 6px 4px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #3F4042;
    border: none;
}

QPushButton {
    background-color: transparent;
    color: #8AB4F7;
    border: 1px solid #3F4042;
    border-radius: 4px;
    padding: 5px 12px;
    min-width: 40px;
}
QPushButton:hover {
    background-color: #1E2B3C;
}
QPushButton:pressed {
    background-color: #2E465E;
}
QPushButton:disabled {
    color: #697177;
    border-color: #3F4042;
}
QPushButton:checked {
    border-color: #8AB4F7;
}
QPushButton:default {
    border-color: #8AB4F7;
    background-color: #1E2B3C;
    color: #8AB4F7;
}
QPushButton:default:hover {
    background-color: #2E465E;
}

QLineEdit, QPlainTextEdit, QTextEdit {
    background-color: #202124;
    border: 1px solid #3F4042;
    border-radius: 4px;
    padding: 5px;
    selection-background-color: #12507B;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #8AB4F7;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    color: #697177;
}

QsciScintilla {
    background-color: #202124;
    border: 1px solid #3F4042;
    border-radius: 4px;
    padding: 5px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}
QsciScintilla:focus {
    border: 1px solid #8AB4F7;
}

QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #3F4042;
    border: 1px solid #3F4042;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #8AB4F7;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #E4E7EB;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #292A2D;
    border: 1px solid #3F4042;
    selection-background-color: #8AB4F7;
    selection-color: #202124;
}

QTabWidget::pane {
    border: 1px solid #3F4042;
    border-radius: 4px;
    background: #202124;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #E4E7EB;
    padding: 6px 14px;
    border: none;
}
QTabBar::tab:selected {
    background-color: #2E465E;
    color: #8AB4F7;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background-color: #3F4042;
}

QCheckBox, QRadioButton {
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #697177;
    background: #202124;
}
QCheckBox::indicator {
    border-radius: 3px;
}
QRadioButton::indicator {
    border-radius: 9px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #8AB4F7;
}
QCheckBox::indicator:checked {
    background: #8AB4F7;
    border-color: #8AB4F7;
}
QRadioButton::indicator:checked {
    background: #202124;
    border: 6px solid #8AB4F7;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background: #3F4042;
    border-color: #3F4042;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #414242;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #5F6368;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #414242;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QSplitter::handle {
    background: transparent;
}
QSplitter::handle:hover {
    background: #3F4042;
}

QStatusBar {
    background-color: #2A2B2E;
    color: #E4E7EB;
    border-top: 1px solid #3F4042;
}
QStatusBar::item {
    border: none;
}

QGroupBox {
    background-color: #292A2D;
    border: 1px solid #3F4042;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #E4E7EB;
    font-weight: 600;
}

QToolTip {
    background-color: #292A2D;
    color: #E4E7EB;
    border: 1px solid #3F4042;
    border-radius: 4px;
    padding: 4px 8px;
}

QMessageBox {
    background-color: #202124;
}
QMessageBox QLabel {
    color: #E4E7EB;
}
"""


def load_stylesheet(theme_id: str) -> str:
    """Return the QSS string for the given theme id ("" for the default theme)."""
    if theme_id == "default":
        return ""
    if theme_id == "ios":
        return IOS_STYLESHEET
    if theme_id == "android":
        return ANDROID_STYLESHEET
    if theme_id == "pyqt_light":
        return PYQT_LIGHT_STYLESHEET
    if theme_id == "pyqt_dark":
        return PYQT_DARK_STYLESHEET
    return ""


def apply_theme(app, theme_id: str) -> None:
    """Apply the given theme to a QApplication instance."""
    app.setStyleSheet(load_stylesheet(theme_id))
