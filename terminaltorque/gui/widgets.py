"""Reusable Qt widgets and helpers for the HMI."""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import cv2

from PySide6 import QtCore, QtGui, QtWidgets


def snap_to_edge(frame: np.ndarray, x: float, y: float, radius: int = 8):
    """Snap a click to the nearest strong sub-pixel edge within ``radius`` px.

    Finds the strongest image gradient in a small window around (x, y) and
    refines it to sub-pixel with a local gradient-weighted centroid, so a point
    placed by hand lands exactly on a machined rim instead of a pixel or two
    off. Returns the (possibly unchanged) (x, y).
    """
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(0, xi - radius), min(w, xi + radius + 1)
    y0, y1 = max(0, yi - radius), min(h, yi + radius + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return x, y
    roi = gray[y0:y1, x0:x1].astype(np.float32)
    gx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    if float(mag.max()) < 1e-3:
        return x, y                      # no edge nearby; leave the click as-is
    # Gradient-weighted centroid over the ROI (centered on the click). Across a
    # straight edge this lands on the edge; along it, the symmetric window keeps
    # the coordinate near where the user clicked instead of drifting.
    weights = mag ** 2
    ys, xs = np.mgrid[0:mag.shape[0], 0:mag.shape[1]].astype(np.float32)
    total = float(weights.sum())
    cx = float((weights * xs).sum() / total) + x0
    cy = float((weights * ys).sum() / total) + y0
    # Never snap further than the search radius.
    if np.hypot(cx - x, cy - y) > radius:
        return x, y
    return cx, cy


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
    """Image display with zoom/pan and a precise click-to-measure mode.

    * Mouse wheel zooms (centred on the cursor); right-drag (or left-drag when
      not measuring) pans. "Reset View" / :meth:`reset_view` fits the image.
    * In measure mode a full-view crosshair replaces the cursor and a magnifier
      loupe shows the pixels under it, so the two endpoints can be placed
      accurately. ``measurementReady`` fires with the segment length in image
      pixels once both points are clicked.

    All overlay/measurement geometry is kept in image coordinates, so it stays
    correct at any zoom or pan.
    """

    measurementReady = QtCore.Signal(float)

    _MIN_ZOOM = 1.0
    _MAX_ZOOM = 25.0
    _LOUPE_D = 150      # loupe diameter, widget px
    _LOUPE_MAG = 4.0    # loupe magnification over the current scale

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setObjectName("ImageView")
        self.setMouseTracking(True)
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._frame: Optional[np.ndarray] = None   # raw BGR, for edge snapping
        self._snap = True
        self._measure_mode = False
        self._points: list = []           # image-coordinate points
        self._zoom = 1.0
        self._fit = True                  # auto-fit until the user zooms/pans
        self._offset = QtCore.QPointF(0, 0)   # widget coords of image top-left
        self._cursor_pos: Optional[QtCore.QPointF] = None
        self._panning = False
        self._pan_last: Optional[QtCore.QPointF] = None

    # -- frame ---------------------------------------------------------------
    def set_snap(self, enabled: bool) -> None:
        self._snap = enabled

    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        if frame is None:
            self._pixmap = None
            self._frame = None
            self.update()
            return
        self._frame = frame
        self._pixmap = bgr_to_qpixmap(frame)
        if self._fit:
            self._zoom = 1.0
        self._clamp()
        self.update()

    def resizeEvent(self, event):  # noqa: N802
        self._clamp()
        super().resizeEvent(event)

    # -- view transform ------------------------------------------------------
    def _base_scale(self) -> float:
        pw, ph = self._pixmap.width(), self._pixmap.height()
        return min(self.width() / pw, self.height() / ph)

    def _scale(self) -> float:
        return self._base_scale() * self._zoom

    def _clamp(self):
        if self._pixmap is None:
            return
        scale = self._scale()
        iw, ih = self._pixmap.width() * scale, self._pixmap.height() * scale
        w, h = self.width(), self.height()
        ox, oy = self._offset.x(), self._offset.y()
        ox = (w - iw) / 2 if iw <= w else min(0.0, max(w - iw, ox))
        oy = (h - ih) / 2 if ih <= h else min(0.0, max(h - ih, oy))
        self._offset = QtCore.QPointF(ox, oy)

    def reset_view(self):
        self._fit = True
        self._zoom = 1.0
        self._clamp()
        self.update()

    def _widget_to_image(self, x: float, y: float):
        if self._pixmap is None:
            return None
        scale = self._scale()
        ix = (x - self._offset.x()) / scale
        iy = (y - self._offset.y()) / scale
        if 0 <= ix < self._pixmap.width() and 0 <= iy < self._pixmap.height():
            return ix, iy
        return None

    def _image_to_widget(self, ix: float, iy: float):
        scale = self._scale()
        return QtCore.QPointF(self._offset.x() + ix * scale,
                              self._offset.y() + iy * scale)

    # -- measure mode --------------------------------------------------------
    def start_measure(self):
        self._measure_mode = True
        self._points = []
        self.setCursor(QtCore.Qt.BlankCursor)   # crosshair replaces the pointer
        self.update()

    def clear_measure(self):
        self._measure_mode = False
        self._points = []
        self.unsetCursor()
        self.update()

    # -- input ---------------------------------------------------------------
    def wheelEvent(self, event):  # noqa: N802
        if self._pixmap is None:
            return
        c = event.position()
        anchor = self._widget_to_image(c.x(), c.y()) or (
            self._pixmap.width() / 2, self._pixmap.height() / 2)
        step = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self._zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, self._zoom * step))
        self._fit = self._zoom <= self._MIN_ZOOM
        scale = self._scale()
        # Keep the anchored image point under the cursor.
        self._offset = QtCore.QPointF(c.x() - anchor[0] * scale,
                                      c.y() - anchor[1] * scale)
        self._clamp()
        self.update()

    def mousePressEvent(self, event):  # noqa: N802
        if self._measure_mode and event.button() == QtCore.Qt.LeftButton:
            p = self._widget_to_image(event.position().x(), event.position().y())
            if p is not None:
                if self._snap and self._frame is not None:
                    p = snap_to_edge(self._frame, p[0], p[1])
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
        # Otherwise begin panning (right button always; left when not measuring).
        if event.button() in (QtCore.Qt.RightButton, QtCore.Qt.MiddleButton) or (
            event.button() == QtCore.Qt.LeftButton and not self._measure_mode
        ):
            self._panning = True
            self._pan_last = event.position()
            self._fit = False

    def mouseMoveEvent(self, event):  # noqa: N802
        self._cursor_pos = event.position()
        if self._panning and self._pan_last is not None:
            self._offset += event.position() - self._pan_last
            self._pan_last = event.position()
            self._clamp()
        self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._panning = False
        self._pan_last = None

    def leaveEvent(self, event):  # noqa: N802
        self._cursor_pos = None
        self.update()

    # -- painting ------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802
        painter = QtGui.QPainter(self)
        opt = QtWidgets.QStyleOption()
        opt.initFrom(self)
        self.style().drawPrimitive(QtWidgets.QStyle.PE_Widget, opt, painter, self)

        if self._pixmap is None:
            painter.setPen(QtGui.QColor("#5a636d"))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "No image")
            painter.end()
            return

        painter.setClipRect(self.rect())
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        scale = self._scale()
        dst = QtCore.QRectF(self._offset.x(), self._offset.y(),
                            self._pixmap.width() * scale,
                            self._pixmap.height() * scale)
        painter.drawPixmap(dst, self._pixmap, QtCore.QRectF(self._pixmap.rect()))

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        self._draw_measurement(painter)
        if self._measure_mode and self._cursor_pos is not None:
            self._draw_crosshair(painter, self._cursor_pos)
            self._draw_loupe(painter, self._cursor_pos)
            self._draw_hint(painter)
        if self._zoom > 1.0:
            painter.setPen(QtGui.QColor("#8b96a0"))
            painter.drawText(QtCore.QPointF(8, self.height() - 8),
                             f"{self._zoom:.1f}x")
        painter.end()

    def _draw_measurement(self, painter):
        if not self._points:
            return
        pen = QtGui.QPen(QtGui.QColor("#ffd166"), 2)
        painter.setPen(pen)
        pts = [self._image_to_widget(ix, iy) for ix, iy in self._points]
        for wp in pts:
            painter.drawEllipse(wp, 4, 4)
        if len(pts) == 1 and self._cursor_pos is not None:
            painter.drawLine(pts[0], self._cursor_pos)   # rubber band
        if len(pts) == 2:
            painter.drawLine(pts[0], pts[1])
            (x0, y0), (x1, y1) = self._points
            mid = (pts[0] + pts[1]) / 2.0
            painter.drawText(mid + QtCore.QPointF(6, -6),
                             f"{np.hypot(x1 - x0, y1 - y0):.1f} px")

    def _draw_crosshair(self, painter, c):
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 209, 102, 200), 1))
        painter.drawLine(QtCore.QPointF(c.x(), 0), QtCore.QPointF(c.x(), self.height()))
        painter.drawLine(QtCore.QPointF(0, c.y()), QtCore.QPointF(self.width(), c.y()))

    def _draw_loupe(self, painter, c):
        ip = self._widget_to_image(c.x(), c.y())
        if ip is None:
            return
        d = self._LOUPE_D
        # Place the loupe near the cursor, flipping away from the edges.
        lx = c.x() + 24 if c.x() + 24 + d < self.width() else c.x() - 24 - d
        ly = c.y() - 24 - d if c.y() - 24 - d > 0 else c.y() + 24
        rect = QtCore.QRectF(lx, ly, d, d)
        center = rect.center()
        path = QtGui.QPainterPath()
        path.addEllipse(rect)

        painter.save()
        painter.setClipPath(path)
        painter.fillRect(rect, QtGui.QColor("#0c0f12"))
        total = self._scale() * self._LOUPE_MAG
        half = (d / 2) / total
        src = QtCore.QRectF(ip[0] - half, ip[1] - half, 2 * half, 2 * half)
        painter.drawPixmap(rect, self._pixmap, src)
        painter.restore()

        painter.setPen(QtGui.QPen(QtGui.QColor("#ffd166"), 2))
        painter.drawEllipse(rect)
        painter.setPen(QtGui.QPen(QtGui.QColor("#ff3b3b"), 1))
        painter.drawLine(QtCore.QPointF(center.x() - 10, center.y()),
                         QtCore.QPointF(center.x() + 10, center.y()))
        painter.drawLine(QtCore.QPointF(center.x(), center.y() - 10),
                         QtCore.QPointF(center.x(), center.y() + 10))

    def _draw_hint(self, painter):
        painter.setPen(QtGui.QColor("#c9d2da"))
        n = len(self._points)
        msg = ("Measure: click point 1  •  scroll = zoom  •  right-drag = pan"
               if n == 0 else
               "Measure: click point 2  •  scroll = zoom  •  right-drag = pan")
        painter.drawText(QtCore.QPointF(10, 18), msg)


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
