"""Lens tab: chessboard calibration to remove distortion (off-center accuracy).

Workflow: set the board geometry, hold a printed chessboard in front of the
camera and Capture View from several angles/positions across the field of view,
then Calibrate. Tick Undistort to apply the correction to every frame -- after
which off-center circles land where they should and the mm/px scale is valid
across the whole image.
"""

from __future__ import annotations

from PySide6 import QtWidgets


class LensTab(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._build()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)

        board = QtWidgets.QGroupBox("Chessboard")
        g = QtWidgets.QGridLayout(board)
        self.cols = QtWidgets.QSpinBox(); self.cols.setRange(3, 30); self.cols.setValue(9)
        self.rows = QtWidgets.QSpinBox(); self.rows.setRange(3, 30); self.rows.setValue(6)
        self.square = QtWidgets.QDoubleSpinBox()
        self.square.setRange(0.1, 500); self.square.setValue(25.0); self.square.setSuffix(" mm")
        for wdg in (self.cols, self.rows, self.square):
            wdg.valueChanged.connect(self.main.reset_lens_calibrator)
        g.addWidget(QtWidgets.QLabel("Inner corners - columns:"), 0, 0)
        g.addWidget(self.cols, 0, 1)
        g.addWidget(QtWidgets.QLabel("Inner corners - rows:"), 1, 0)
        g.addWidget(self.rows, 1, 1)
        g.addWidget(QtWidgets.QLabel("Square size:"), 2, 0)
        g.addWidget(self.square, 2, 1)
        note = QtWidgets.QLabel(
            "Inner corners = squares minus one (a 10x7 board has 9x6). The "
            "square size sets units; it does not affect the distortion solve."
        )
        note.setWordWrap(True); note.setStyleSheet("color:#8b96a0; font-size:11px;")
        g.addWidget(note, 3, 0, 1, 2)
        root.addWidget(board)

        cap = QtWidgets.QGroupBox("Calibrate")
        c = QtWidgets.QVBoxLayout(cap)
        row = QtWidgets.QHBoxLayout()
        self.btn_capture = QtWidgets.QPushButton("Capture View")
        self.btn_capture.clicked.connect(self._capture_view)
        self.btn_reset = QtWidgets.QPushButton("Reset Views")
        self.btn_reset.clicked.connect(self._reset)
        self.btn_calibrate = QtWidgets.QPushButton("Calibrate")
        self.btn_calibrate.setObjectName("Primary")
        self.btn_calibrate.clicked.connect(self._calibrate)
        row.addWidget(self.btn_capture)
        row.addWidget(self.btn_reset)
        row.addWidget(self.btn_calibrate)
        c.addLayout(row)
        self.status = QtWidgets.QLabel("Views captured: 0")
        self.status.setStyleSheet("font-weight:600; color:#00c2c2;")
        c.addWidget(self.status)
        root.addWidget(cap)

        use = QtWidgets.QGroupBox("Apply / Persist")
        u = QtWidgets.QGridLayout(use)
        self.undistort = QtWidgets.QCheckBox("Undistort image (apply correction)")
        self.undistort.setEnabled(False)
        self.undistort.toggled.connect(self.main.set_undistort)
        self.btn_save = QtWidgets.QPushButton("Save…")
        self.btn_save.clicked.connect(self._save)
        self.btn_load = QtWidgets.QPushButton("Load…")
        self.btn_load.clicked.connect(self._load)
        u.addWidget(self.undistort, 0, 0, 1, 2)
        u.addWidget(self.btn_save, 1, 0)
        u.addWidget(self.btn_load, 1, 1)
        root.addWidget(use)
        root.addStretch(1)

    # -- actions -------------------------------------------------------------
    def board_config(self):
        return (self.cols.value(), self.rows.value()), self.square.value()

    def _capture_view(self):
        found = self.main.add_calibration_view()
        n = self.main.calibrator.count
        if found:
            self.status.setText(f"Views captured: {n}  (chessboard found)")
        else:
            self.status.setText(
                f"Views captured: {n}  (no chessboard in the current frame)")

    def _reset(self):
        self.main.calibrator.reset()
        self.status.setText("Views captured: 0")

    def _calibrate(self):
        result = self.main.calibrate_lens()
        if result is None:
            return
        self.status.setText(
            f"Calibrated from {self.main.calibrator.count} views — "
            f"reprojection error {result:.3f} px")
        self.undistort.setEnabled(True)
        self.undistort.setChecked(True)

    def on_calibration_loaded(self, rms: float):
        self.status.setText(f"Calibration loaded — reprojection error {rms:.3f} px")
        self.undistort.setEnabled(True)
        self.undistort.setChecked(True)

    def _save(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save calibration", "camera_calibration.npz",
            "NumPy (*.npz)")
        if path:
            self.main.save_lens_calibration(path)

    def _load(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load calibration", "", "NumPy (*.npz)")
        if path:
            self.main.load_lens_calibration(path)
