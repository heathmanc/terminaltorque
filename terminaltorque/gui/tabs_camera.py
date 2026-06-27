"""Camera tab: choose the source and adjust exposure/contrast/hue/etc."""

from __future__ import annotations

from PySide6 import QtWidgets

from .camera_source import CAMERA_PROPERTIES
from .widgets import PropertySlider


class CameraTab(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._sliders = {}
        self._toggles = {}
        self._build()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)

        # --- source selection ---
        src = QtWidgets.QGroupBox("Camera Source")
        form = QtWidgets.QGridLayout(src)
        self.use_synthetic = QtWidgets.QCheckBox("Use synthetic demo lid (no hardware)")
        self.use_synthetic.setChecked(True)
        self.use_synthetic.toggled.connect(self._sync_source_widgets)

        self.index_spin = QtWidgets.QSpinBox()
        self.index_spin.setRange(0, 16)
        self.index_spin.setEnabled(False)

        self.btn_connect = QtWidgets.QPushButton("Connect")
        self.btn_connect.setObjectName("Primary")
        self.btn_connect.clicked.connect(self._connect)
        self.btn_disconnect = QtWidgets.QPushButton("Disconnect")
        self.btn_disconnect.clicked.connect(self.main.disconnect_camera)

        form.addWidget(self.use_synthetic, 0, 0, 1, 2)
        form.addWidget(QtWidgets.QLabel("Device index:"), 1, 0)
        form.addWidget(self.index_spin, 1, 1)
        form.addWidget(self.btn_connect, 2, 0)
        form.addWidget(self.btn_disconnect, 2, 1)
        root.addWidget(src)

        # --- adjustments ---
        self.adjust_box = QtWidgets.QGroupBox("Image Adjustments")
        grid = QtWidgets.QVBoxLayout(self.adjust_box)
        for prop in CAMERA_PROPERTIES:
            if prop.is_toggle:
                cb = QtWidgets.QCheckBox(prop.label)
                cb.setChecked(bool(prop.default))
                cb.toggled.connect(
                    lambda v, key=prop.key: self.main.apply_camera_property(key, 1.0 if v else 0.0)
                )
                self._toggles[prop.key] = cb
                grid.addWidget(cb)
            else:
                slider = PropertySlider(
                    prop.label, prop.minimum, prop.maximum, prop.default, prop.step,
                    on_change=lambda v, key=prop.key: self.main.apply_camera_property(key, v),
                )
                self._sliders[prop.key] = slider
                grid.addWidget(slider)

        note = QtWidgets.QLabel(
            "Ranges are nominal; a real camera rescales or clamps each control "
            "per its driver. Auto Exposure overrides the manual Exposure slider."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8b96a0; font-size:11px;")
        grid.addWidget(note)
        root.addWidget(self.adjust_box)
        root.addStretch(1)

        self.adjust_box.setEnabled(False)
        self._sync_source_widgets()

    def _sync_source_widgets(self):
        self.index_spin.setEnabled(not self.use_synthetic.isChecked())

    def _connect(self):
        if self.use_synthetic.isChecked():
            self.main.connect_synthetic_camera()
        else:
            self.main.connect_camera(self.index_spin.value())

    def on_camera_connected(self, connected: bool):
        self.adjust_box.setEnabled(connected)
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)
        if connected:
            self.push_all_properties()

    def push_all_properties(self):
        """Apply every current control value to the freshly connected camera."""
        for key, slider in self._sliders.items():
            self.main.apply_camera_property(key, slider.value())
        for key, cb in self._toggles.items():
            self.main.apply_camera_property(key, 1.0 if cb.isChecked() else 0.0)
