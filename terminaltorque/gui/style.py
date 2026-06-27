"""Dark industrial HMI stylesheet (Qt QSS)."""

DARK_INDUSTRIAL_QSS = """
QWidget {
    background-color: #1f242b;
    color: #d7dde3;
    font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #1a1f25; }

#HeaderBar {
    background-color: #11151a;
    border-bottom: 2px solid #00a3a3;
}
#HeaderTitle { font-size: 18px; font-weight: 700; color: #e9eef2; }
#HeaderSub { color: #8b96a0; font-size: 11px; }

QTabWidget::pane { border: 1px solid #2c333c; top: -1px; }
QTabBar::tab {
    background: #242b33;
    color: #aeb7c0;
    padding: 9px 20px;
    border: 1px solid #2c333c;
    border-bottom: none;
    font-weight: 600;
}
QTabBar::tab:selected { background: #2f3742; color: #ffffff; border-top: 2px solid #00a3a3; }
QTabBar::tab:hover { background: #2a323b; }

QGroupBox {
    border: 1px solid #313944;
    border-radius: 4px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #00c2c2; }

QPushButton {
    background-color: #2c333c;
    border: 1px solid #3a4350;
    border-radius: 3px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover { background-color: #354051; }
QPushButton:pressed { background-color: #222831; }
QPushButton:disabled { color: #5a636d; border-color: #2a2f37; }

QPushButton#Primary { background-color: #00a3a3; color: #062626; border: none; }
QPushButton#Primary:hover { background-color: #00bcbc; }
QPushButton#Primary:pressed { background-color: #008a8a; }
QPushButton#Danger { background-color: #b5462f; color: #fff; border: none; }
QPushButton#Danger:hover { background-color: #cc5238; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #161a1f;
    border: 1px solid #333b45;
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: #00a3a3;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #00a3a3;
}

QSlider::groove:horizontal { height: 5px; background: #333b45; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #00c2c2; width: 16px; margin: -6px 0; border-radius: 8px;
}
QSlider::sub-page:horizontal { background: #007e7e; border-radius: 2px; }

QTableWidget {
    background-color: #161a1f;
    gridline-color: #2c333c;
    border: 1px solid #2c333c;
    selection-background-color: #00595a;
}
QHeaderView::section {
    background-color: #242b33;
    color: #aeb7c0;
    padding: 5px;
    border: none;
    border-right: 1px solid #2c333c;
    font-weight: 600;
}
#ImageView {
    background-color: #0c0f12;
    border: 1px solid #2c333c;
    color: #5a636d;
}
QStatusBar { background: #11151a; color: #8b96a0; }
QCheckBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked { border: 1px solid #4a5562; background: #161a1f; border-radius: 3px; }
QCheckBox::indicator:checked { border: 1px solid #00a3a3; background: #00a3a3; border-radius: 3px; }
"""
