"""Main HMI window: holds application state and coordinates the tabs."""

from __future__ import annotations

from typing import Optional, Set

from PySide6 import QtCore, QtWidgets

from ..detector import DetectionParams, detect_terminal_wells, draw_detections
from ..calibration import Calibration, default_origin
from ..plc import PlcConfig, ALL_GROUPS, push_to_plc
from .camera_source import (
    CameraSource,
    SyntheticCameraSource,
    V4l2CameraSource,
)
from . import v4l2
from .style import DARK_INDUSTRIAL_QSS
from .widgets import StatusLED
from .tabs_live import LiveViewTab
from .tabs_camera import CameraTab
from .tabs_plc import PlcTab
from .tabs_detection import DetectionTab


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TerminalTorque HMI")
        self.resize(1180, 760)

        # --- application state ---
        self.camera: Optional[CameraSource] = None
        self.live_frame = None
        self.captured_frame = None
        self.last_wells: list = []

        self.params = DetectionParams()
        self.mm_per_px = 0.0
        self.invert_y = True

        self.plc_config = PlcConfig.from_ip("192.168.1.10", slot=None)
        self.plc_enabled = False
        self.plc_auto_push = False
        self.plc_wait_ack = False
        self.plc_enabled_groups: Set[str] = set(ALL_GROUPS)

        self.live_timer = QtCore.QTimer(self)
        self.live_timer.setInterval(50)  # ~20 FPS
        self.live_timer.timeout.connect(self._on_live_tick)

        self._build_ui()
        self.setStyleSheet(DARK_INDUSTRIAL_QSS)
        self._refresh_status()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        self.tabs = QtWidgets.QTabWidget()
        self.live_tab = LiveViewTab(self)
        self.camera_tab = CameraTab(self)
        self.plc_tab = PlcTab(self)
        self.detection_tab = DetectionTab(self)
        self.tabs.addTab(self.live_tab, "Live View")
        self.tabs.addTab(self.camera_tab, "Camera")
        self.tabs.addTab(self.detection_tab, "Detection")
        self.tabs.addTab(self.plc_tab, "PLC")
        outer.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

    def _build_header(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QWidget()
        bar.setObjectName("HeaderBar")
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 16, 10)

        titles = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("TERMINALTORQUE")
        title.setObjectName("HeaderTitle")
        sub = QtWidgets.QLabel("Battery terminal-well vision station")
        sub.setObjectName("HeaderSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.led_camera = StatusLED("Camera")
        self.led_plc = StatusLED("PLC")
        layout.addWidget(self.led_camera)
        layout.addSpacing(18)
        layout.addWidget(self.led_plc)
        return bar

    def _refresh_status(self):
        cam_ok = self.camera is not None and self.camera.is_open()
        self.led_camera.set_state(
            "ok" if cam_ok else "off",
            f"Camera: {self.camera.name}" if cam_ok else "Camera: offline",
        )
        if not self.plc_enabled:
            self.led_plc.set_state("off", "PLC: disabled")
        else:
            self.led_plc.set_state("warn", f"PLC: {self.plc_config.path}")
        # Live-view buttons stay enabled - Start Live / Capture auto-connect.
        self.live_tab.set_controls_enabled(True)
        self.camera_tab.on_camera_connected(cam_ok)

    # -------------------------------------------------------------- camera
    def connect_synthetic_camera(self):
        self._set_camera(SyntheticCameraSource())

    def connect_camera(self, index: int):
        mode = self.camera_tab.selected_mode()
        w = h = fps = None
        if mode:
            w, h, fps = mode
        self._set_camera(V4l2CameraSource(
            index, backend=self.camera_tab.capture_backend(),
            width=w, height=h, fps=fps,
        ))

    # -- camera control routing (synthetic source vs real v4l2 device) -----
    def selected_device(self) -> str:
        return f"/dev/video{self.camera_tab.device_index()}"

    def query_modes(self):
        if self.camera_tab.use_synthetic_source():
            return SyntheticCameraSource().probe_modes()
        if v4l2.available():
            return [(m.width, m.height, m.fps)
                    for m in v4l2.list_modes(self.selected_device())]
        return []

    def query_controls(self):
        # None -> synthetic (use nominal sliders); dict -> real controls.
        if self.camera_tab.use_synthetic_source():
            return None
        if v4l2.available():
            return v4l2.list_controls(self.selected_device())
        return {}

    def set_camera_control(self, key, value):
        if self.camera_tab.use_synthetic_source():
            if self.camera is not None:
                self.camera.set_property(key, value)
        elif v4l2.available():
            v4l2.set_control(self.selected_device(), key, int(value))

    def set_camera_auto_exposure(self, on: bool):
        if self.camera_tab.use_synthetic_source():
            if self.camera is not None:
                self.camera.set_property("auto_exposure", 1.0 if on else 0.0)
        elif v4l2.available():
            v4l2.set_auto_exposure(self.selected_device(), on)

    def ensure_camera(self) -> bool:
        """Connect using the Camera tab's current source selection if needed."""
        if self.camera is not None and self.camera.is_open():
            return True
        if self.camera_tab.use_synthetic_source():
            self.connect_synthetic_camera()
        else:
            self.connect_camera(self.camera_tab.device_index())
        return self.camera is not None and self.camera.is_open()

    def _set_camera(self, source: CameraSource):
        self.disconnect_camera()
        if not source.open():
            QtWidgets.QMessageBox.critical(
                self, "Camera", f"Could not open {source.name}."
            )
            return
        self.camera = source
        # Push ONLY the auto-exposure state (keeps the image bright); never
        # force manual exposure/gain on connect.
        self.camera_tab.apply_initial_settings()
        frame = self.camera.read()
        if frame is not None:
            self.live_frame = frame
            self.live_tab.show_frame(frame)
        self.statusBar().showMessage(f"Connected to {source.name}")
        self._refresh_status()

    def probe_camera_modes(self):
        if not self.ensure_camera():
            return []
        return self.camera.probe_modes()

    def apply_camera_mode(self, width, height, fps=None):
        if self.camera is None:
            return
        self.camera.set_mode(width, height, fps)
        frame = self.camera.read()
        if frame is not None:
            self.live_frame = frame
            self.live_tab.show_frame(frame)
        self.statusBar().showMessage(f"Resolution set to {width} x {height}")

    def disconnect_camera(self):
        self.stop_live()
        if self.camera is not None:
            self.camera.close()
            self.camera = None
        self._refresh_status()

    def apply_camera_property(self, key: str, value: float):
        if self.camera is not None:
            self.camera.set_property(key, value)

    def start_live(self):
        # Start Live does the whole thing: connect (per the Camera tab's source)
        # then stream.
        if not self.ensure_camera():
            self.stop_live()
            self.statusBar().showMessage("Could not start a camera")
            return
        self.live_timer.start()

    def stop_live(self):
        self.live_timer.stop()
        if hasattr(self, "live_tab") and self.live_tab.btn_live.isChecked():
            self.live_tab.btn_live.setChecked(False)

    def _on_live_tick(self):
        if self.camera is None:
            return
        frame = self.camera.read()
        if frame is not None:
            self.live_frame = frame
            self.live_tab.show_frame(frame)

    # ------------------------------------------------------------- capture
    def capture(self):
        if not self.ensure_camera():
            self.statusBar().showMessage("No camera connected")
            return None
        frame = self.camera.read()
        if frame is None:
            frame = self.live_frame
        if frame is None:
            self.statusBar().showMessage("Failed to capture a frame")
            return None
        # Freeze: stop live streaming so the captured frame (and any detection
        # overlay drawn on it) stays on screen instead of being overwritten by
        # the next live tick.
        self.stop_live()
        self.captured_frame = frame
        self.live_tab.show_frame(frame)
        self.statusBar().showMessage("Frame captured - image frozen")
        return frame

    def process(self):
        frame = self.captured_frame if self.captured_frame is not None else self.live_frame
        if frame is None:
            self.statusBar().showMessage("Nothing to process - capture a frame first")
            return
        calibration = self._current_calibration(frame.shape)
        self.last_wells = detect_terminal_wells(frame, self.params, calibration)
        overlay = draw_detections(frame, self.last_wells)
        self.live_tab.show_frame(overlay)
        units = "mm" if calibration is not None else "pixels"
        self.live_tab.show_results(self.last_wells, units)
        self.statusBar().showMessage(
            f"Detected {len(self.last_wells)} well(s)"
        )
        if self.plc_enabled and self.plc_auto_push and self.last_wells:
            self.push_to_plc()

    def capture_and_process(self):
        if self.capture() is not None:
            self.process()

    # ----------------------------------------------------------- detection
    def set_detection(self, min_radius_px, max_radius_px, expected_count,
                      circularity=0.8):
        self.params = DetectionParams(
            min_radius_px=min_radius_px,
            max_radius_px=max_radius_px,
            expected_count=expected_count,
            circularity=circularity,
        )

    def set_calibration_params(self, mm_per_px: float, invert_y: bool):
        self.mm_per_px = mm_per_px
        self.invert_y = invert_y

    def _current_calibration(self, image_shape) -> Optional[Calibration]:
        if self.mm_per_px and self.mm_per_px > 0:
            ou, ov = default_origin(image_shape)
            return Calibration(mm_per_px=self.mm_per_px, origin_u=ou, origin_v=ov,
                               invert_y=self.invert_y)
        return None

    # ----------------------------------------------------------------- PLC
    def set_plc_enabled(self, value: bool):
        self.plc_enabled = value
        self._refresh_status()

    def set_plc_auto_push(self, value: bool):
        self.plc_auto_push = value

    def set_plc_wait_ack(self, value: bool):
        self.plc_wait_ack = value

    def set_plc_config(self, config: PlcConfig):
        self.plc_config = config
        self._refresh_status()

    def set_plc_group_enabled(self, group: str, enabled: bool):
        if enabled:
            self.plc_enabled_groups.add(group)
        else:
            self.plc_enabled_groups.discard(group)

    def push_to_plc(self):
        if not self.plc_enabled:
            self.statusBar().showMessage("PLC push is disabled (enable it on the PLC tab)")
            return
        if not self.last_wells:
            self.statusBar().showMessage("No detection results to push")
            return
        # Honor a disabled DataReady group by dropping the handshake tag.
        effective = PlcConfig(**vars(self.plc_config))
        if "data_ready" not in self.plc_enabled_groups:
            effective.data_ready_tag = None
        try:
            status = push_to_plc(
                self.last_wells,
                effective,
                wait_for_ack=self.plc_wait_ack,
                enabled_groups=self.plc_enabled_groups,
            )
        except Exception as exc:  # noqa: BLE001
            self.led_plc.set_state("error", f"PLC: {type(exc).__name__}")
            QtWidgets.QMessageBox.critical(self, "PLC push failed", str(exc))
            self.statusBar().showMessage(f"PLC push failed: {exc}")
            return
        self.led_plc.set_state("ok", f"PLC: pushed {status['written']}")
        self.statusBar().showMessage(
            f"Pushed {status['written']} well(s) to PLC "
            f"(handshake={status['handshake_set']}, ack={status['acked']})"
        )

    def closeEvent(self, event):  # noqa: N802
        self.disconnect_camera()
        super().closeEvent(event)
