"""Camera tab: choose the source, list modes, and adjust image controls.

Connection is driven from the Live View's *Start Live* (or Capture) button -
this tab only configures *which* camera and *how* it is tuned. The camera keeps
its own auto-exposure on connect; nothing is forced onto it, so the picture is
never darkened behind the operator's back.
"""

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

        hint = QtWidgets.QLabel(
            "Pick the source here, then press Start Live (or Capture) on the "
            "Live View tab - it connects automatically."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b96a0; font-size:11px;")

        form.addWidget(self.use_synthetic, 0, 0, 1, 2)
        form.addWidget(QtWidgets.QLabel("Device index:"), 1, 0)
        form.addWidget(self.index_spin, 1, 1)
        form.addWidget(hint, 2, 0, 1, 2)
        root.addWidget(src)

        # --- resolution / frame rate ---
        self.modes_box = QtWidgets.QGroupBox("Resolution / Frame Rate")
        mgrid = QtWidgets.QGridLayout(self.modes_box)
        self.btn_detect = QtWidgets.QPushButton("Detect supported modes")
        self.btn_detect.clicked.connect(self._detect_modes)
        self.modes_combo = QtWidgets.QComboBox()
        self.btn_apply_mode = QtWidgets.QPushButton("Apply")
        self.btn_apply_mode.clicked.connect(self._apply_mode)
        self.btn_apply_mode.setEnabled(False)
        mgrid.addWidget(self.btn_detect, 0, 0)
        mgrid.addWidget(self.modes_combo, 0, 1)
        mgrid.addWidget(self.btn_apply_mode, 0, 2)
        root.addWidget(self.modes_box)

        # --- adjustments ---
        self.adjust_box = QtWidgets.QGroupBox("Image Adjustments")
        grid = QtWidgets.QVBoxLayout(self.adjust_box)
        for prop in CAMERA_PROPERTIES:
            if prop.is_toggle:
                cb = QtWidgets.QCheckBox(prop.label)
                cb.setChecked(bool(prop.default))
                cb.toggled.connect(
                    lambda v, key=prop.key: self._toggle_changed(key, v)
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

        # Exposure is meaningful only with auto-exposure off.
        if "exposure" in self._sliders and "auto_exposure" in self._toggles:
            self._sliders["exposure"].setEnabled(
                not self._toggles["auto_exposure"].isChecked()
            )

        note = QtWidgets.QLabel(
            "Ranges are nominal; a real camera rescales or clamps each control "
            "per its driver. Exposure applies only when Auto Exposure is off."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8b96a0; font-size:11px;")
        grid.addWidget(note)
        root.addWidget(self.adjust_box)
        root.addStretch(1)

        self._sync_source_widgets()
        self.on_camera_connected(False)

    # -- source --------------------------------------------------------------
    def _sync_source_widgets(self):
        self.index_spin.setEnabled(not self.use_synthetic.isChecked())

    def use_synthetic_source(self) -> bool:
        return self.use_synthetic.isChecked()

    def device_index(self) -> int:
        return self.index_spin.value()

    # -- adjustments ---------------------------------------------------------
    def _toggle_changed(self, key: str, value: bool):
        self.main.apply_camera_property(key, 1.0 if value else 0.0)
        if key == "auto_exposure" and "exposure" in self._sliders:
            # Disable manual exposure while auto is on; apply it when turned off.
            self._sliders["exposure"].setEnabled(not value)
            if not value:
                self.main.apply_camera_property("exposure", self._sliders["exposure"].value())

    def on_camera_connected(self, connected: bool):
        self.adjust_box.setEnabled(connected)
        self.modes_box.setEnabled(connected)

    def apply_initial_settings(self):
        """Push only the auto-exposure state on connect (keeps the image bright).

        Deliberately does NOT blast every slider at the camera; forcing manual
        exposure/gain on connect is what previously darkened the picture.
        """
        if "auto_exposure" in self._toggles:
            on = self._toggles["auto_exposure"].isChecked()
            self.main.apply_camera_property("auto_exposure", 1.0 if on else 0.0)

    # -- modes ---------------------------------------------------------------
    def _detect_modes(self):
        modes = self.main.probe_camera_modes()
        self.modes_combo.clear()
        if not modes:
            self.modes_combo.addItem("No camera / no modes found")
            self.btn_apply_mode.setEnabled(False)
            return
        for w, h, fps in modes:
            fps_txt = f"{fps:g} fps" if fps else "fps n/a"
            self.modes_combo.addItem(f"{w} x {h}  @  {fps_txt}", (w, h, fps))
        self.btn_apply_mode.setEnabled(True)

    def _apply_mode(self):
        data = self.modes_combo.currentData()
        if data:
            self.main.apply_camera_mode(*data)
