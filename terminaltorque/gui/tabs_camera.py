"""Camera tab: source, capture backend, real modes, and real controls.

For a real V4L2 camera the image-adjustment sliders are built from the device's
*actual* controls (true ranges, correct exposure handling) queried via
``v4l2-ctl`` -- no capture pipeline required, so Detect works without starting a
live view. The synthetic demo source keeps a fixed set of nominal sliders.
"""

from __future__ import annotations

from PySide6 import QtWidgets

from .camera_source import CAMERA_PROPERTIES
from .widgets import PropertySlider
from .v4l2 import AUTO_EXPOSURE_AUTO


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)   # remove from view immediately (no overlap flicker)
            w.deleteLater()


class CameraTab(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._auto_exposure_cb = None
        self._exposure_widget = None
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

        self.backend = QtWidgets.QComboBox()
        self.backend.addItem("GStreamer (recommended)", "gstreamer")
        self.backend.addItem("V4L2", "v4l2")

        hint = QtWidgets.QLabel(
            "Pick the source, then Detect to load this camera's real "
            "resolutions and controls (no live view needed). Start Live or "
            "Capture on the Live View connects automatically."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b96a0; font-size:11px;")

        form.addWidget(self.use_synthetic, 0, 0, 1, 2)
        form.addWidget(QtWidgets.QLabel("Device index:"), 1, 0)
        form.addWidget(self.index_spin, 1, 1)
        form.addWidget(QtWidgets.QLabel("Capture backend:"), 2, 0)
        form.addWidget(self.backend, 2, 1)
        form.addWidget(hint, 3, 0, 1, 2)
        root.addWidget(src)

        # --- resolution / frame rate ---
        modes_box = QtWidgets.QGroupBox("Resolution / Frame Rate")
        mgrid = QtWidgets.QGridLayout(modes_box)
        self.btn_detect = QtWidgets.QPushButton("Detect modes && controls")
        self.btn_detect.setObjectName("Primary")
        self.btn_detect.clicked.connect(self._detect)
        self.modes_combo = QtWidgets.QComboBox()
        self.btn_apply_mode = QtWidgets.QPushButton("Apply")
        self.btn_apply_mode.clicked.connect(self._apply_mode)
        self.btn_apply_mode.setEnabled(False)
        mgrid.addWidget(self.btn_detect, 0, 0)
        mgrid.addWidget(self.modes_combo, 0, 1)
        mgrid.addWidget(self.btn_apply_mode, 0, 2)
        root.addWidget(modes_box)

        # --- adjustments (rebuilt to match the active source) ---
        self.adjust_box = QtWidgets.QGroupBox("Image Adjustments")
        self.adjust_layout = QtWidgets.QVBoxLayout(self.adjust_box)
        root.addWidget(self.adjust_box)
        root.addStretch(1)

        self._sync_source_widgets()
        self._build_nominal_adjustments()   # synthetic by default

    # -- source --------------------------------------------------------------
    def _sync_source_widgets(self):
        real = not self.use_synthetic.isChecked()
        self.index_spin.setEnabled(real)
        self.backend.setEnabled(real)

    def use_synthetic_source(self) -> bool:
        return self.use_synthetic.isChecked()

    def device_index(self) -> int:
        return self.index_spin.value()

    def capture_backend(self) -> str:
        return self.backend.currentData()

    def selected_mode(self):
        return self.modes_combo.currentData()

    def on_camera_connected(self, connected: bool):
        self.adjust_box.setEnabled(True)   # controls work offline via v4l2-ctl

    def apply_initial_settings(self):
        """On connect, enable auto-exposure so the image is bright.

        For a real camera this sets the V4L2 auto_exposure menu to aperture
        priority -- the actual fix for the dark picture -- instead of forcing a
        bogus manual value.
        """
        if self._auto_exposure_cb is not None:
            self.main.set_camera_auto_exposure(self._auto_exposure_cb.isChecked())

    # -- modes ---------------------------------------------------------------
    def _detect(self):
        modes = self.main.query_modes()
        self.modes_combo.clear()
        if modes:
            for w, h, fps in modes:
                fps_txt = f"{fps:g} fps" if fps else "fps n/a"
                self.modes_combo.addItem(f"{w} x {h}  @  {fps_txt}", (w, h, fps))
            self.btn_apply_mode.setEnabled(True)
        else:
            self.modes_combo.addItem("No modes found (is v4l2-ctl installed?)")
            self.btn_apply_mode.setEnabled(False)

        controls = self.main.query_controls()
        self._rebuild_adjustments(controls)

    def _apply_mode(self):
        data = self.modes_combo.currentData()
        if data:
            self.main.apply_camera_mode(*data)

    # -- adjustments ---------------------------------------------------------
    def _rebuild_adjustments(self, controls):
        _clear_layout(self.adjust_layout)
        self._auto_exposure_cb = None
        self._exposure_widget = None
        if controls is None:
            self._build_nominal_adjustments()
        elif not controls:
            self._build_no_controls_notice()
        else:
            self._build_dynamic_adjustments(controls)

    def _build_no_controls_notice(self):
        msg = QtWidgets.QLabel(
            "No V4L2 controls found. Install v4l2-utils (`sudo apt install "
            "v4l-utils`) to expose this camera's exposure and image controls."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color:#e6b800;")
        self.adjust_layout.addWidget(msg)

    def _build_nominal_adjustments(self):
        """Fixed sliders for the synthetic demo source."""
        for prop in CAMERA_PROPERTIES:
            if prop.is_toggle:
                cb = QtWidgets.QCheckBox(prop.label)
                cb.setChecked(bool(prop.default))
                cb.toggled.connect(self._on_auto_exposure_toggled)
                self._auto_exposure_cb = cb
                self.adjust_layout.addWidget(cb)
            else:
                slider = PropertySlider(
                    prop.label, prop.minimum, prop.maximum, prop.default, prop.step,
                    on_change=lambda v, key=prop.key: self.main.set_camera_control(key, v),
                )
                if prop.key == "exposure":
                    self._exposure_widget = slider
                self.adjust_layout.addWidget(slider)
        self._sync_exposure_enabled()

    def _build_dynamic_adjustments(self, controls):
        """Sliders built from a real camera's v4l2 controls (true ranges)."""
        if "auto_exposure" in controls:
            c = controls["auto_exposure"]
            cb = QtWidgets.QCheckBox("Auto Exposure")
            cb.setChecked(c.value == AUTO_EXPOSURE_AUTO)
            cb.toggled.connect(self._on_auto_exposure_toggled)
            self._auto_exposure_cb = cb
            self.adjust_layout.addWidget(cb)

        for name, c in controls.items():
            if name == "auto_exposure":
                continue
            label = name.replace("_", " ").title()
            if c.type == "bool":
                cb = QtWidgets.QCheckBox(label)
                cb.setChecked(bool(c.value))
                cb.setEnabled(not c.inactive)
                cb.toggled.connect(
                    lambda v, n=name: self.main.set_camera_control(n, 1 if v else 0)
                )
                self.adjust_layout.addWidget(cb)
            else:  # int or menu -> slider over the real range
                slider = PropertySlider(
                    label, c.minimum, c.maximum, c.value, max(1, c.step),
                    on_change=lambda v, n=name: self.main.set_camera_control(n, v),
                )
                slider.setEnabled(not c.inactive)
                if name == "exposure_time_absolute":
                    self._exposure_widget = slider
                self.adjust_layout.addWidget(slider)

        note = QtWidgets.QLabel(
            "Controls reflect this camera's real V4L2 ranges. Exposure applies "
            "only with Auto Exposure off."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8b96a0; font-size:11px;")
        self.adjust_layout.addWidget(note)
        self._sync_exposure_enabled()

    # -- exposure wiring -----------------------------------------------------
    def _on_auto_exposure_toggled(self, on: bool):
        self.main.set_camera_auto_exposure(on)
        self._sync_exposure_enabled()
        if not on and self._exposure_widget is not None:
            # Re-assert the manual exposure value when leaving auto.
            key = "exposure" if self.use_synthetic_source() else "exposure_time_absolute"
            self.main.set_camera_control(key, self._exposure_widget.value())

    def _sync_exposure_enabled(self):
        if self._exposure_widget is not None and self._auto_exposure_cb is not None:
            self._exposure_widget.setEnabled(not self._auto_exposure_cb.isChecked())
