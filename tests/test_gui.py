"""Headless smoke tests for the HMI (offscreen Qt platform).

These build the real window and exercise the capture/process/PLC wiring
without a display or any camera hardware, using the synthetic camera source
and a fake PLC.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6 import QtWidgets  # noqa: E402

from terminaltorque.plc import PlcConfig  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture()
def window(qapp):
    from terminaltorque.gui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.disconnect_camera()
    win.close()


def test_window_builds_with_four_tabs(window):
    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert labels == ["Live View", "Camera", "Detection", "PLC"]


def test_connect_synthetic_and_capture_process(window):
    window.connect_synthetic_camera()
    assert window.camera is not None and window.camera.is_open()

    # Constrain detection to the synthetic wells and process.
    window.set_detection(min_radius_px=25, max_radius_px=70,
                         expected_count=2, circularity=0.8)
    window.capture_and_process()

    assert len(window.last_wells) == 2
    assert window.live_tab.table.rowCount() == 2


def test_camera_property_changes_live_image(window):
    window.connect_synthetic_camera()
    f1 = window.camera.read().copy()
    window.apply_camera_property("brightness", 80)
    f2 = window.camera.read()
    # Brightness change should visibly raise mean intensity.
    assert f2.mean() > f1.mean()


def test_detection_tab_mm_conversion(window):
    tab = window.detection_tab
    tab.units.setCurrentText("Millimeters")
    tab.mm_per_px.setValue(0.1)      # 0.1 mm/px
    tab.min_dia.setValue(10.0)       # 10 mm -> 100 px diameter -> r=50
    tab.max_dia.setValue(20.0)       # 20 mm -> 200 px diameter -> r=100
    tab.apply()
    assert window.params.min_radius_px == 50
    assert window.params.max_radius_px == 100
    # Calibration becomes active.
    cal = window._current_calibration((480, 640))
    assert cal is not None and cal.mm_per_px == pytest.approx(0.1)


def test_plc_push_uses_fake_driver(window):
    # Detect something first.
    window.connect_synthetic_camera()
    window.set_detection(25, 70, 2, 0.8)
    window.capture_and_process()
    assert window.last_wells

    # Configure + enable PLC, then push through a fake driver.
    window.set_plc_config(PlcConfig.from_ip("1.2.3.4", max_wells=4))
    window.set_plc_enabled(True)

    from terminaltorque.plc import push_to_plc
    captured = {}

    class FakePlc:
        def write(self, *tags):
            captured.setdefault("writes", []).extend(tags)
            return True

        def read(self, tag):
            return False

        def close(self):
            pass

    status = push_to_plc(window.last_wells, window.plc_config, plc=FakePlc(),
                         enabled_groups=window.plc_enabled_groups)
    assert status["written"] == 2
    assert any(t[0] == "Vision_Count" for t in captured["writes"])


def test_expected_count_auto_is_reversible(window):
    tab = window.detection_tab
    # Default: Auto checked -> no count limit.
    assert tab.auto_count.isChecked()
    tab.apply()
    assert window.params.expected_count is None

    # Uncheck Auto -> spin enabled, count applied.
    tab.auto_count.setChecked(False)
    tab.expected.setValue(2)
    tab.apply()
    assert tab.expected.isEnabled()
    assert window.params.expected_count == 2

    # Re-check Auto -> back to None (the bug being fixed).
    tab.auto_count.setChecked(True)
    tab.apply()
    assert window.params.expected_count is None
    assert not tab.expected.isEnabled()


def test_capture_freezes_live_stream(window):
    window.connect_synthetic_camera()
    window.start_live()
    assert window.live_timer.isActive()
    window.capture()
    # Capture must stop the live stream so the frame (and overlay) stays put.
    assert not window.live_timer.isActive()


def test_plc_group_disable_drops_tag(window):
    window.set_plc_config(PlcConfig.from_ip("1.2.3.4", max_wells=2))
    window.set_plc_group_enabled("dia", False)
    assert "dia" not in window.plc_enabled_groups

    from terminaltorque.detector import TerminalWell
    from terminaltorque.plc import build_writes
    well = TerminalWell(center_px=(1, 2), diameter_px=10, confidence=1.0,
                        center_mm=(1, 2), diameter_mm=10)
    writes = dict(build_writes([well], window.plc_config,
                               enabled_groups=window.plc_enabled_groups))
    assert "Vision_Dia[0]" not in writes
    assert "Vision_X[0]" in writes
