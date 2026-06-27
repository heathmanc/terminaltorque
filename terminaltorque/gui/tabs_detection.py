"""Detection tab: tell the system what hole size to look for, plus calibration."""

from __future__ import annotations

from PySide6 import QtWidgets


class DetectionTab(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._build()
        self.apply()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)

        # --- hole size ---
        size = QtWidgets.QGroupBox("Target Hole Size")
        grid = QtWidgets.QGridLayout(size)

        self.units = QtWidgets.QComboBox()
        self.units.addItems(["Pixels", "Millimeters"])
        self.units.currentIndexChanged.connect(self._on_change)

        self.min_dia = QtWidgets.QDoubleSpinBox()
        self.min_dia.setRange(1, 5000)
        self.min_dia.setValue(20)
        self.max_dia = QtWidgets.QDoubleSpinBox()
        self.max_dia.setRange(1, 5000)
        self.max_dia.setValue(160)
        for w in (self.min_dia, self.max_dia):
            w.valueChanged.connect(self._on_change)

        grid.addWidget(QtWidgets.QLabel("Units:"), 0, 0)
        grid.addWidget(self.units, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Min diameter:"), 1, 0)
        grid.addWidget(self.min_dia, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Max diameter:"), 2, 0)
        grid.addWidget(self.max_dia, 2, 1)
        self.size_hint = QtWidgets.QLabel()
        self.size_hint.setStyleSheet("color:#8b96a0; font-size:11px;")
        grid.addWidget(self.size_hint, 3, 0, 1, 2)
        root.addWidget(size)

        # --- detection tuning ---
        tune = QtWidgets.QGroupBox("Detection")
        tgrid = QtWidgets.QGridLayout(tune)
        self.auto_count = QtWidgets.QCheckBox("Auto (keep every well found)")
        self.auto_count.setChecked(True)
        self.auto_count.toggled.connect(self._on_change)

        self.expected = QtWidgets.QSpinBox()
        self.expected.setRange(1, 64)
        self.expected.setValue(2)
        self.expected.setEnabled(False)  # enabled only when Auto is unchecked
        self.expected.valueChanged.connect(self._on_change)

        self.circularity = QtWidgets.QDoubleSpinBox()
        self.circularity.setRange(0.50, 0.98)
        self.circularity.setSingleStep(0.05)
        self.circularity.setDecimals(2)
        self.circularity.setValue(0.80)
        self.circularity.valueChanged.connect(self._on_change)

        tgrid.addWidget(QtWidgets.QLabel("Expected wells:"), 0, 0)
        tgrid.addWidget(self.auto_count, 0, 1)
        tgrid.addWidget(self.expected, 0, 2)
        tgrid.addWidget(QtWidgets.QLabel("Circularity (strictness):"), 1, 0)
        tgrid.addWidget(self.circularity, 1, 1, 1, 2)
        hint = QtWidgets.QLabel(
            "Higher circularity accepts only rounder shapes and rejects false "
            "detections from text, scratches, and noise; lower it if real wells "
            "are missed. Set Expected wells to keep only the strongest N."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b96a0; font-size:11px;")
        tgrid.addWidget(hint, 2, 0, 1, 3)
        root.addWidget(tune)

        # --- calibration ---
        cal = QtWidgets.QGroupBox("Calibration (pixels -> millimeters)")
        cgrid = QtWidgets.QGridLayout(cal)
        self.mm_per_px = QtWidgets.QDoubleSpinBox()
        self.mm_per_px.setRange(0.0, 100.0)
        self.mm_per_px.setDecimals(5)
        self.mm_per_px.setSingleStep(0.001)
        self.mm_per_px.setValue(0.0)
        self.mm_per_px.setSpecialValueText("Uncalibrated")
        self.mm_per_px.valueChanged.connect(self._on_change)

        self.invert_y = QtWidgets.QCheckBox("Invert Y (image down -> robot up)")
        self.invert_y.setChecked(True)
        self.invert_y.toggled.connect(self._on_change)

        # quick calibrate from a known length
        self.cal_px = QtWidgets.QDoubleSpinBox()
        self.cal_px.setRange(1, 10000)
        self.cal_px.setValue(84)
        self.cal_mm = QtWidgets.QDoubleSpinBox()
        self.cal_mm.setRange(0.01, 10000)
        self.cal_mm.setValue(12.0)
        btn_cal = QtWidgets.QPushButton("Set scale from known length")
        btn_cal.clicked.connect(self._calibrate_from_length)

        cgrid.addWidget(QtWidgets.QLabel("mm per pixel:"), 0, 0)
        cgrid.addWidget(self.mm_per_px, 0, 1)
        cgrid.addWidget(self.invert_y, 1, 0, 1, 2)
        cgrid.addWidget(QtWidgets.QLabel("Reference length (px):"), 2, 0)
        cgrid.addWidget(self.cal_px, 2, 1)
        cgrid.addWidget(QtWidgets.QLabel("True length (mm):"), 3, 0)
        cgrid.addWidget(self.cal_mm, 3, 1)
        cgrid.addWidget(btn_cal, 4, 0, 1, 2)
        root.addWidget(cal)
        root.addStretch(1)

    # -- logic --------------------------------------------------------------
    def is_mm(self) -> bool:
        return self.units.currentText() == "Millimeters"

    def _calibrate_from_length(self):
        if self.cal_px.value() > 0:
            self.mm_per_px.setValue(self.cal_mm.value() / self.cal_px.value())

    def set_scale(self, mm_per_px: float):
        """Set the calibration scale (e.g. from the Live View measure tool)."""
        self.mm_per_px.setValue(mm_per_px)  # triggers _on_change -> applies calibration

    def _diameter_px(self, value: float) -> float:
        """Convert a diameter in the selected units to pixels."""
        if self.is_mm():
            scale = self.mm_per_px.value()
            if scale <= 0:
                return value  # no calibration; treat the number as pixels
            return value / scale
        return value

    def _on_change(self, *args):
        mm_per_px = self.mm_per_px.value()
        if self.is_mm() and mm_per_px <= 0:
            self.size_hint.setText(
                "Millimeters selected but no calibration set - values are "
                "treated as pixels until you set mm/px below."
            )
        elif self.is_mm():
            self.size_hint.setText(
                f"= {self._diameter_px(self.min_dia.value()):.0f}"
                f"..{self._diameter_px(self.max_dia.value()):.0f} px"
            )
        else:
            self.size_hint.setText("")
        self.apply()

    def apply(self):
        min_px = self._diameter_px(self.min_dia.value())
        max_px = self._diameter_px(self.max_dia.value())
        auto = self.auto_count.isChecked()
        self.expected.setEnabled(not auto)
        expected = None if auto else self.expected.value()
        self.main.set_detection(
            min_radius_px=int(max(1, min_px / 2)),
            max_radius_px=int(max(2, max_px / 2)),
            expected_count=expected,
            circularity=float(self.circularity.value()),
        )
        self.main.set_calibration_params(
            mm_per_px=self.mm_per_px.value(),
            invert_y=self.invert_y.isChecked(),
        )
