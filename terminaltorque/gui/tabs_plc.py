"""PLC tab: enable the push, configure the connection, and review tags."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..plc import PlcConfig, tag_catalog


class PlcTab(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._build()
        self.rebuild_table()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)

        # --- master enable / behavior ---
        top = QtWidgets.QGroupBox("PLC Push")
        tl = QtWidgets.QVBoxLayout(top)
        self.enable = QtWidgets.QCheckBox("Enable push to PLC")
        self.enable.toggled.connect(self.main.set_plc_enabled)
        self.auto_push = QtWidgets.QCheckBox("Auto-push after each Process")
        self.auto_push.toggled.connect(self.main.set_plc_auto_push)
        self.wait_ack = QtWidgets.QCheckBox(
            "Wait for PLC acknowledgement (DataReady cleared)"
        )
        self.wait_ack.toggled.connect(self.main.set_plc_wait_ack)
        tl.addWidget(self.enable)
        tl.addWidget(self.auto_push)
        tl.addWidget(self.wait_ack)
        root.addWidget(top)

        # --- connection ---
        conn = QtWidgets.QGroupBox("Connection")
        grid = QtWidgets.QGridLayout(conn)
        self.ip = QtWidgets.QLineEdit(self.main.plc_config.path.split("/")[0])
        self.compactlogix = QtWidgets.QCheckBox("CompactLogix (no slot)")
        self.compactlogix.setChecked("/" not in self.main.plc_config.path)
        self.compactlogix.toggled.connect(lambda v: self.slot.setEnabled(not v))
        self.slot = QtWidgets.QSpinBox()
        self.slot.setRange(0, 16)
        self.slot.setEnabled(not self.compactlogix.isChecked())
        self.prefix = QtWidgets.QLineEdit("Vision")
        self.max_wells = QtWidgets.QSpinBox()
        self.max_wells.setRange(1, 64)
        self.max_wells.setValue(self.main.plc_config.max_wells)

        grid.addWidget(QtWidgets.QLabel("PLC IP:"), 0, 0)
        grid.addWidget(self.ip, 0, 1)
        grid.addWidget(self.compactlogix, 0, 2)
        grid.addWidget(QtWidgets.QLabel("Slot:"), 1, 0)
        grid.addWidget(self.slot, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Tag prefix:"), 2, 0)
        grid.addWidget(self.prefix, 2, 1)
        grid.addWidget(QtWidgets.QLabel("Array size (max wells):"), 3, 0)
        grid.addWidget(self.max_wells, 3, 1)

        self.btn_apply = QtWidgets.QPushButton("Apply / Build Tag List")
        self.btn_apply.setObjectName("Primary")
        self.btn_apply.clicked.connect(self.apply_config)
        grid.addWidget(self.btn_apply, 4, 0, 1, 3)
        root.addWidget(conn)

        # --- tag table ---
        tags = QtWidgets.QGroupBox("PLC Tags (tick to write; create these in the PLC)")
        tv = QtWidgets.QVBoxLayout(tags)
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Write", "Tag", "Type", "Description"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tv.addWidget(self.table)
        root.addWidget(tags, 1)

    def apply_config(self):
        slot = None if self.compactlogix.isChecked() else self.slot.value()
        config = PlcConfig.from_ip(
            ip=self.ip.text().strip(),
            slot=slot,
            prefix=self.prefix.text().strip() or "Vision",
            max_wells=self.max_wells.value(),
        )
        self.main.set_plc_config(config)
        self.rebuild_table()

    def rebuild_table(self):
        catalog = tag_catalog(self.main.plc_config)
        self.table.setRowCount(len(catalog))
        for row, entry in enumerate(catalog):
            group = entry["group"]
            cb = QtWidgets.QCheckBox()
            cb.setChecked(group in self.main.plc_enabled_groups)
            cb.toggled.connect(
                lambda v, g=group: self.main.set_plc_group_enabled(g, v)
            )
            wrap = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(wrap)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setAlignment(QtCore.Qt.AlignCenter)
            lay.addWidget(cb)
            self.table.setCellWidget(row, 0, wrap)
            for col, key in enumerate(("tag", "type", "description"), start=1):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(entry[key]))
