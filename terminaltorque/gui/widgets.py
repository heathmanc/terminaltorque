"""Reusable Qt widgets and helpers for the HMI."""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import cv2

from PySide6 import QtCore, QtGui, QtWidgets


def bgr_to_qpixmap(frame: np.ndarray) -> QtGui.QPixmap:
    """Convert an OpenCV BGR (or grayscale) frame to a QPixmap."""
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    image = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
    # Copy so the pixmap owns its memory after `rgb` goes out of scope.
    return QtGui.QPixmap.fromImage(image.copy())


class ImageView(QtWidgets.QLabel):
    """A QLabel that displays a frame, scaled to fit while keeping aspect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setObjectName("ImageView")
        self.setText("No image")
        self._pixmap: Optional[QtGui.QPixmap] = None

    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        if frame is None:
            self._pixmap = None
            self.setText("No image")
            return
        self._pixmap = bgr_to_qpixmap(frame)
        self._rescale()

    def resizeEvent(self, event):  # noqa: N802 (Qt naming)
        self._rescale()
        super().resizeEvent(event)

    def _rescale(self):
        if self._pixmap is None:
            return
        self.setPixmap(
            self._pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )


class StatusLED(QtWidgets.QWidget):
    """A small colored indicator with a text label, for connection status."""

    COLORS = {"ok": "#3ad07a", "warn": "#e6b800", "error": "#e44", "off": "#666"}

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._dot = QtWidgets.QLabel()
        self._dot.setFixedSize(12, 12)
        self._label = QtWidgets.QLabel(text)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        self.set_state("off")

    def set_state(self, state: str, text: Optional[str] = None) -> None:
        color = self.COLORS.get(state, self.COLORS["off"])
        self._dot.setStyleSheet(
            f"background:{color}; border-radius:6px; border:1px solid #222;"
        )
        if text is not None:
            self._label.setText(text)


class PropertySlider(QtWidgets.QWidget):
    """A labeled slider + spin box bound to a numeric value with a callback."""

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        step: float = 1.0,
        on_change: Optional[Callable[[float], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._step = step
        self._min = minimum
        self._on_change = on_change

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._name = QtWidgets.QLabel(label)
        self._name.setMinimumWidth(130)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(int(round((maximum - minimum) / step)))
        self._slider.setValue(self._to_pos(value))

        self._spin = QtWidgets.QDoubleSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setDecimals(0 if step >= 1 else 2)
        self._spin.setValue(value)
        self._spin.setFixedWidth(90)

        layout.addWidget(self._name)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._spin)

        self._slider.valueChanged.connect(self._slider_changed)
        self._spin.valueChanged.connect(self._spin_changed)

    def _to_pos(self, value: float) -> int:
        return int(round((value - self._min) / self._step))

    def _to_value(self, pos: int) -> float:
        return self._min + pos * self._step

    def _slider_changed(self, pos: int):
        value = self._to_value(pos)
        self._spin.blockSignals(True)
        self._spin.setValue(value)
        self._spin.blockSignals(False)
        self._emit(value)

    def _spin_changed(self, value: float):
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_pos(value))
        self._slider.blockSignals(False)
        self._emit(value)

    def _emit(self, value: float):
        if self._on_change is not None:
            self._on_change(value)

    def value(self) -> float:
        return self._spin.value()

    def set_value(self, value: float) -> None:
        self._spin.setValue(value)
