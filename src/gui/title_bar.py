from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class CustomTitleBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_position: QPoint | None = None

        self.setFixedHeight(32)
        self.setStyleSheet("""
            CustomTitleBar {
                background-color: #f0f0f0;
                border-bottom: 1px solid #ddd;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        self.title_label = QLabel(self)
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.title_label.setText(self._get_window_title())
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title_label.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.min_button = QPushButton("─", self)
        self.max_button = QPushButton("□", self)
        self.close_button = QPushButton("✕", self)

        for btn in (self.min_button, self.max_button, self.close_button):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.ArrowCursor)

        self.close_button.setStyleSheet("""
            QPushButton { border: none; padding: 8px 12px; }
            QPushButton:hover { background-color: #e81123; color: white; }
        """)

        for btn in (self.min_button, self.max_button):
            btn.setStyleSheet("""
                QPushButton { border: none; padding: 8px 12px; }
                QPushButton:hover { background-color: #e0e0e0; }
            """)

        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

        window = self.window()
        if isinstance(window, QWidget):
            window.windowTitleChanged.connect(self.title_label.setText)

    def set_maximized(self, is_maximized: bool) -> None:
        self.max_button.setText("❐" if is_maximized else "□")

    def _get_main_window(self) -> QWidget | None:
        """Get the top-level main window."""
        widget = self.parentWidget()
        while widget is not None:
            parent = widget.parentWidget()
            if parent is None:
                return widget
            widget = parent
        return None

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            super().mousePressEvent(a0)
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            main_window = self._get_main_window()
            if main_window:
                if not main_window.isMaximized():
                    handle = main_window.windowHandle()
                    if handle and handle.startSystemMove():
                        self._drag_position = None
                        a0.accept()
                        return
                self._drag_position = a0.globalPosition().toPoint() - main_window.pos()
            a0.accept()
        else:
            super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            super().mouseMoveEvent(a0)
            return
        if self._drag_position is not None and a0.buttons() & Qt.MouseButton.LeftButton:
            main_window = self._get_main_window()
            if main_window and not main_window.isMaximized():
                main_window.move(a0.globalPosition().toPoint() - self._drag_position)
            a0.accept()
        else:
            super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            super().mouseReleaseEvent(a0)
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._drag_position = None
            a0.accept()
        else:
            super().mouseReleaseEvent(a0)

    def mouseDoubleClickEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            super().mouseDoubleClickEvent(a0)
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self.max_button.click()
            a0.accept()
        else:
            super().mouseDoubleClickEvent(a0)

    def _get_window_title(self) -> str:
        window = self.window()
        return window.windowTitle() if window else ""
