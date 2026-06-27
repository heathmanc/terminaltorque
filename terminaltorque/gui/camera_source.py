"""Camera sources for the HMI: a real OpenCV camera and a synthetic stand-in.

Both expose the same small interface (``open``/``read``/``close`` plus
``get_property``/``set_property``) so the GUI does not care whether a real
camera is attached. The synthetic source renders the demo lid and actually
applies the exposure/brightness/contrast/etc. adjustments to the frame, so the
Camera tab is demonstrable with no hardware connected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import cv2

from ..synthetic import make_lid_image


@dataclass(frozen=True)
class CameraProperty:
    """A camera control exposed in the Camera tab.

    ``cv_prop`` is the ``cv2.CAP_PROP_*`` id used for real cameras. Ranges are
    nominal: real UVC/GenICam cameras rescale or clamp these per driver, so the
    slider range is a sensible default, not a guarantee.
    """

    key: str
    label: str
    cv_prop: int
    minimum: float
    maximum: float
    default: float
    step: float = 1.0
    is_toggle: bool = False


# Order here is the order shown in the Camera tab.
CAMERA_PROPERTIES: List[CameraProperty] = [
    CameraProperty("auto_exposure", "Auto Exposure", cv2.CAP_PROP_AUTO_EXPOSURE,
                   0, 1, 1, 1, is_toggle=True),
    CameraProperty("exposure", "Exposure (EV)", cv2.CAP_PROP_EXPOSURE,
                   -13, 0, -6, 1),
    CameraProperty("brightness", "Brightness", cv2.CAP_PROP_BRIGHTNESS,
                   -100, 100, 0, 1),
    CameraProperty("contrast", "Contrast (%)", cv2.CAP_PROP_CONTRAST,
                   0, 200, 100, 1),
    CameraProperty("saturation", "Saturation (%)", cv2.CAP_PROP_SATURATION,
                   0, 200, 100, 1),
    CameraProperty("hue", "Hue (deg)", cv2.CAP_PROP_HUE,
                   -90, 90, 0, 1),
    CameraProperty("gain", "Gain", cv2.CAP_PROP_GAIN,
                   0, 100, 0, 1),
]

PROPERTY_BY_KEY: Dict[str, CameraProperty] = {p.key: p for p in CAMERA_PROPERTIES}

# Common sensor resolutions probed when listing camera modes.
STANDARD_RESOLUTIONS = [
    (320, 240), (640, 480), (800, 600), (1024, 768), (1280, 720),
    (1280, 960), (1600, 1200), (1920, 1080), (2560, 1440), (3840, 2160),
]


class CameraSource:
    """Interface shared by all camera sources."""

    name: str = "camera"

    def open(self) -> bool:  # pragma: no cover - trivial
        raise NotImplementedError

    def is_open(self) -> bool:  # pragma: no cover - trivial
        raise NotImplementedError

    def read(self) -> Optional[np.ndarray]:  # pragma: no cover - trivial
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - trivial
        raise NotImplementedError

    def set_property(self, key: str, value: float) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_property(self, key: str) -> Optional[float]:  # pragma: no cover
        raise NotImplementedError

    def probe_modes(self) -> List[tuple]:  # pragma: no cover - trivial
        """Return supported (width, height, fps) modes."""
        return []

    def set_mode(self, width: int, height: int, fps: Optional[float] = None) -> None:
        """Select a capture resolution / frame rate."""
        pass


class OpenCVCameraSource(CameraSource):
    """A real camera accessed through ``cv2.VideoCapture``."""

    def __init__(self, index: int = 0):
        self.index = index
        self.name = f"Camera {index}"
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.index)
        return bool(self._cap and self._cap.isOpened())

    def is_open(self) -> bool:
        return bool(self._cap and self._cap.isOpened())

    def read(self) -> Optional[np.ndarray]:
        if not self.is_open():
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def set_property(self, key: str, value: float) -> None:
        prop = PROPERTY_BY_KEY.get(key)
        if prop is None or not self.is_open():
            return
        if key == "auto_exposure":
            # V4L2 convention: 0.75 = auto, 0.25 = manual.
            self._cap.set(prop.cv_prop, 0.75 if value else 0.25)
        else:
            self._cap.set(prop.cv_prop, float(value))

    def get_property(self, key: str) -> Optional[float]:
        prop = PROPERTY_BY_KEY.get(key)
        if prop is None or not self.is_open():
            return None
        return self._cap.get(prop.cv_prop)

    def probe_modes(self) -> List[tuple]:
        """Probe which standard resolutions the camera actually accepts.

        OpenCV has no enumeration API, so we set each candidate and read back
        what the driver snapped to, deduplicating. The current mode is restored
        afterwards.
        """
        if not self.is_open():
            return []
        cur_w = self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        cur_h = self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        modes, seen = [], set()
        for w, h in STANDARD_RESOLUTIONS:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            aw = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ah = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = round(float(self._cap.get(cv2.CAP_PROP_FPS)), 1)
            if aw and ah and (aw, ah) not in seen:
                seen.add((aw, ah))
                modes.append((aw, ah, fps))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cur_w)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cur_h)
        return modes

    def set_mode(self, width: int, height: int, fps: Optional[float] = None) -> None:
        if not self.is_open():
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fps:
            self._cap.set(cv2.CAP_PROP_FPS, fps)


class SyntheticCameraSource(CameraSource):
    """Software camera that renders the demo lid and applies adjustments.

    Lets the HMI run end-to-end without hardware. Property changes visibly
    affect the live image so the Camera tab can be demonstrated and tested.
    """

    name = "Synthetic (demo lid)"

    def __init__(self, size=(480, 640)):
        self._size = size
        self._open = False
        self._frame_no = 0
        self._props: Dict[str, float] = {p.key: p.default for p in CAMERA_PROPERTIES}

    def open(self) -> bool:
        self._open = True
        return True

    def is_open(self) -> bool:
        return self._open

    def close(self) -> None:
        self._open = False

    def set_property(self, key: str, value: float) -> None:
        if key in self._props:
            self._props[key] = float(value)

    def get_property(self, key: str) -> Optional[float]:
        return self._props.get(key)

    def probe_modes(self) -> List[tuple]:
        return [(640, 480, 30.0), (1280, 720, 30.0), (1920, 1080, 30.0)]

    def set_mode(self, width: int, height: int, fps: Optional[float] = None) -> None:
        self._size = (int(height), int(width))

    def read(self) -> Optional[np.ndarray]:
        if not self._open:
            return None
        # Vary only the sensor noise frame-to-frame so the view looks "live"
        # while well geometry stays fixed for stable detection.
        self._frame_no += 1
        base, _ = make_lid_image(size=self._size, seed=self._frame_no % 32)
        return self._apply_adjustments(base)

    def _apply_adjustments(self, frame: np.ndarray) -> np.ndarray:
        p = self._props
        f = frame.astype(np.float32)

        # Exposure (skipped when auto-exposure is on): EV as a brightness gain.
        if not p.get("auto_exposure"):
            f *= float(2.0 ** ((p["exposure"] + 6.0) / 4.0))

        # Contrast about mid-gray, then brightness offset.
        f = (f - 128.0) * (p["contrast"] / 100.0) + 128.0 + p["brightness"]
        f = np.clip(f, 0, 255)

        # Hue/saturation in HSV.
        if p["saturation"] != 100.0 or p["hue"] != 0.0:
            hsv = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 0] = (hsv[..., 0] + p["hue"] / 2.0) % 180.0
            hsv[..., 1] = np.clip(hsv[..., 1] * (p["saturation"] / 100.0), 0, 255)
            f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

        # Gain adds sensor noise.
        if p["gain"] > 0:
            noise = np.random.normal(0, p["gain"] / 10.0, f.shape).astype(np.float32)
            f = f + noise

        return np.clip(f, 0, 255).astype(np.uint8)
