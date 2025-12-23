from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class CustomTitleBar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drag_position: Optional[QPoint] = None

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

        self.close_button.setStyleSheet(
            """
            QPushButton { border: none; padding: 8px 12px; }
            QPushButton:hover { background-color: #e81123; color: white; }
        """
        )

        for btn in (self.min_button, self.max_button):
            btn.setStyleSheet(
                """
                QPushButton { border: none; padding: 8px 12px; }
                QPushButton:hover { background-color: #e0e0e0; }
            """
            )

        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

        window = self.window()
        if hasattr(window, "windowTitleChanged"):
            window.windowTitleChanged.connect(self.title_label.setText)

    def set_maximized(self, is_maximized: bool) -> None:
        self.max_button.setText("❐" if is_maximized else "□")

    def _get_main_window(self) -> Optional[QWidget]:
        """Get the top-level main window."""
        widget = self.parent()
        while widget is not None:
            parent = widget.parent()
            if parent is None:
                return widget
            widget = parent
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            main_window = self._get_main_window()
            if main_window:
                if not main_window.isMaximized():
                    handle = main_window.windowHandle()
                    if handle and handle.startSystemMove():
                        self._drag_position = None
                        event.accept()
                        return
                self._drag_position = event.globalPosition().toPoint() - main_window.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            main_window = self._get_main_window()
            if main_window and not main_window.isMaximized():
                main_window.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.max_button.click()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _get_window_title(self) -> str:
        window = self.window()
        return window.windowTitle() if window else ""
