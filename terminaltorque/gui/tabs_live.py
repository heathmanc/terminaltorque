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
        left.addWidget(self.view, 1)

        controls = QtWidgets.QHBoxLayout()
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

        self.btn_push = QtWidgets.QPushButton("Push to PLC")
        self.btn_push.clicked.connect(self.main.push_to_plc)

        for b in (self.btn_live, self.btn_capture, self.btn_process,
                  self.btn_reprocess, self.btn_push):
            controls.addWidget(b)
        controls.addStretch(1)
        left.addLayout(controls)
        root.addLayout(left, 3)

        # --- right: results ---
        right = QtWidgets.QVBoxLayout()
        self.summary = QtWidgets.QLabel("No detection yet.")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-weight:600; color:#00c2c2;")
        right.addWidget(self.summary)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "X", "Y", "Diameter", "Conf", "Valid"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        right.addWidget(self.table, 1)
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
                "yes",
            ]
            for col, text in enumerate(values):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.table.setItem(row, col, item)
