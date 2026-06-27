"""Live View tab: stream, capture, process, and review results."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .widgets import ImageView


class LiveViewTab(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._build()

    def _build(self):
        root = QtWidgets.QHBoxLayout(self)

        # --- left: image + capture controls ---
        left = QtWidgets.QVBoxLayout()
        self.view = ImageView()
        self.view.measurementReady.connect(self.main.on_measurement)
        left.addWidget(self.view, 1)

        self.btn_live = QtWidgets.QPushButton("Start Live")
        self.btn_live.setCheckable(True)
        self.btn_live.toggled.connect(self._toggle_live)

        self.btn_capture = QtWidgets.QPushButton("Capture")
        self.btn_capture.clicked.connect(self.main.capture)

        self.btn_process = QtWidgets.QPushButton("Capture && Process")
        self.btn_process.setObjectName("Primary")
        self.btn_process.clicked.connect(self.main.capture_and_process)

        self.btn_reprocess = QtWidgets.QPushButton("Re-process")
        self.btn_reprocess.clicked.connect(self.main.process)

        self.btn_measure = QtWidgets.QPushButton("Measure Scale")
        self.btn_measure.setToolTip(
            "Click two points on a feature of known size to set mm-per-pixel. "
            "Scroll to zoom, right-drag to pan; a loupe aids precise placement."
        )
        self.btn_measure.clicked.connect(self.main.begin_measure)

        self.btn_reset_view = QtWidgets.QPushButton("Reset View")
        self.btn_reset_view.setToolTip("Fit the image to the window (undo zoom/pan).")
        self.btn_reset_view.clicked.connect(lambda: self.view.reset_view())

        self.btn_cal_sizes = QtWidgets.QPushButton("Calibrate from sizes")
        self.btn_cal_sizes.setToolTip(
            "Enter each circle's known diameter in the 'Known O (mm)' column, "
            "then click to fit mm-per-pixel across all of them (least squares)."
        )
        self.btn_cal_sizes.clicked.connect(self.main.calibrate_from_known_sizes)

        self.snap_cb = QtWidgets.QCheckBox("Snap to edge")
        self.snap_cb.setChecked(True)
        self.snap_cb.setToolTip("Snap measure clicks to the nearest sub-pixel edge.")
        self.snap_cb.toggled.connect(self.view.set_snap)

        self.btn_push = QtWidgets.QPushButton("Push to PLC")
        self.btn_push.clicked.connect(self.main.push_to_plc)

        # Two rows so the button strip doesn't force the results panel narrow.
        row1 = QtWidgets.QHBoxLayout()
        for b in (self.btn_live, self.btn_capture, self.btn_process,
                  self.btn_reprocess, self.btn_push):
            row1.addWidget(b)
        row1.addStretch(1)
        row2 = QtWidgets.QHBoxLayout()
        for b in (self.btn_measure, self.btn_reset_view, self.btn_cal_sizes):
            row2.addWidget(b)
        row2.addWidget(self.snap_cb)
        row2.addStretch(1)
        left.addLayout(row1)
        left.addLayout(row2)
        root.addLayout(left, 3)

        # --- right: results ---
        right = QtWidgets.QVBoxLayout()
        self.summary = QtWidgets.QLabel("No detection yet.")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-weight:600; color:#00c2c2;")
        right.addWidget(self.summary)

        self.KNOWN_COL = 5
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "X", "Y", "Diameter", "Conf", "Known Ø (mm)"]
        )
        hdr = self.table.horizontalHeader()
        for col in range(self.KNOWN_COL):       # numeric columns size to content
            hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(                # Known column takes the rest
            self.KNOWN_COL, QtWidgets.QHeaderView.Stretch)
        self.table.setMinimumWidth(360)
        # Only the "Known O (mm)" column is editable (double-click to type).
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        right.addWidget(self.table, 1)
        hint = QtWidgets.QLabel(
            "Calibration from sizes: type each circle's true diameter in "
            "'Known Ø (mm)', then 'Calibrate from sizes'."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b96a0; font-size:11px;")
        right.addWidget(hint)
        root.addLayout(right, 2)

        self.set_controls_enabled(False)

    def set_controls_enabled(self, camera_connected: bool):
        for b in (self.btn_live, self.btn_capture, self.btn_process):
            b.setEnabled(camera_connected)

    def _toggle_live(self, on: bool):
        if on:
            self.btn_live.setText("Stop Live")
            self.main.start_live()
        else:
            self.btn_live.setText("Start Live")
            self.main.stop_live()

    def show_frame(self, frame):
        self.view.set_frame(frame)

    def show_results(self, wells, units: str):
        self.summary.setText(
            f"{len(wells)} terminal well(s) detected. "
            f"Coordinates in {units}."
        )
        self.table.setRowCount(len(wells))
        for row, w in enumerate(wells):
            if w.center_mm is not None:
                x, y, dia = w.center_mm[0], w.center_mm[1], w.diameter_mm
            else:
                x, y, dia = w.center_px[0], w.center_px[1], w.diameter_px
            values = [
                str(row + 1),
                f"{x:.2f}",
                f"{y:.2f}",
                f"{dia:.2f}",
                f"{w.confidence:.2f}",
            ]
            for col, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
            # Editable "Known Ø (mm)" cell for size-based calibration.
            known = QtWidgets.QTableWidgetItem("")
            known.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, self.KNOWN_COL, known)

    def known_diameters(self):
        """Yield (row_index, mm) for cells the operator filled with a value."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.KNOWN_COL)
            if item is None or not item.text().strip():
                continue
            try:
                mm = float(item.text())
            except ValueError:
                continue
            if mm > 0:
                yield row, mm
