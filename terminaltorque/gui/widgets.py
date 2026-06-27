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
    """A QLabel that displays a frame scaled to fit, with a click-to-measure mode.

    In measure mode the next two clicks mark a segment on the *image* (mapped
    from widget coordinates through the aspect-fit scaling); ``measurementReady``
    fires with the segment length in image pixels once both points are set.
    """

    # Emitted with the distance in image pixels once two points are clicked.
    measurementReady = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setObjectName("ImageView")
        self.setText("No image")
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._measure_mode = False
        self._points: list = []  # image-coordinate points

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
        self.update()

    # -- measure mode --------------------------------------------------------
    def start_measure(self):
        self._measure_mode = True
        self._points = []
        self.setCursor(QtCore.Qt.CrossCursor)
        self.update()

    def clear_measure(self):
        self._measure_mode = False
        self._points = []
        self.unsetCursor()
        self.update()

    def _displayed_rect(self):
        """(offset_x, offset_y, scale) of the image within the widget, or None."""
        if self._pixmap is None:
            return None
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw == 0 or ph == 0:
            return None
        scale = min(self.width() / pw, self.height() / ph)
        ox = (self.width() - pw * scale) / 2.0
        oy = (self.height() - ph * scale) / 2.0
        return ox, oy, scale

    def _widget_to_image(self, x: float, y: float):
        r = self._displayed_rect()
        if r is None:
            return None
        ox, oy, scale = r
        ix, iy = (x - ox) / scale, (y - oy) / scale
        if 0 <= ix < self._pixmap.width() and 0 <= iy < self._pixmap.height():
            return ix, iy
        return None

    def _image_to_widget(self, ix: float, iy: float):
        ox, oy, scale = self._displayed_rect()
        return QtCore.QPointF(ox + ix * scale, oy + iy * scale)

    def mousePressEvent(self, event):  # noqa: N802
        if self._measure_mode and event.button() == QtCore.Qt.LeftButton:
            pos = event.position()
            p = self._widget_to_image(pos.x(), pos.y())
            if p is not None:
                self._points.append(p)
                if len(self._points) == 2:
                    (x0, y0), (x1, y1) = self._points
                    dist = float(np.hypot(x1 - x0, y1 - y0))
                    self._measure_mode = False
                    self.unsetCursor()
                    self.update()
                    self.measurementReady.emit(dist)
                else:
                    self.update()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)  # draws the scaled pixmap (and stylesheet)
        if self._pixmap is None or not self._points:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#ffd166"), 2)
        painter.setPen(pen)
        widget_pts = [self._image_to_widget(ix, iy) for ix, iy in self._points]
        for wp in widget_pts:
            painter.drawEllipse(wp, 4, 4)
        if len(widget_pts) == 2:
            painter.drawLine(widget_pts[0], widget_pts[1])
            (x0, y0), (x1, y1) = self._points
            dist = np.hypot(x1 - x0, y1 - y0)
            mid = (widget_pts[0] + widget_pts[1]) / 2.0
            painter.drawText(mid + QtCore.QPointF(6, -6), f"{dist:.1f} px")
        painter.end()


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
