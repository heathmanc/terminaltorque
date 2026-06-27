"""Entry point for the TerminalTorque HMI."""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    from PySide6 import QtWidgets

    from .main_window import MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        argv if argv is not None else sys.argv
    )
    app.setApplicationName("TerminalTorque HMI")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
