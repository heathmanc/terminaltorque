"""Basler camera support via pypylon (Pylon SDK / GenICam).

Basler GigE/USB3 cameras are not V4L2 devices; they are driven through the
Pylon SDK's GenICam node map. This source conforms to the same small
``CameraSource`` interface as the synthetic and V4L2 sources, so the rest of the
HMI is unchanged: it grabs frames (converting to BGR), exposes the camera's real
exposure/gain ranges as controls, and lists sensor resolutions.

pypylon is imported lazily, so the app runs without it installed; only selecting
the Basler source requires it. Frame grab, control, and mode logic operate on
the open ``InstantCamera`` object, which lets the non-hardware logic be unit
tested with a fake camera.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .camera_source import CameraSource
from .v4l2 import V4l2Control, AUTO_EXPOSURE_AUTO, AUTO_EXPOSURE_MANUAL


def _import_pylon():
    try:
        from pypylon import pylon
        return pylon
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pypylon is required for Basler cameras. Install with "
            "`pip install pypylon`.") from exc


def available() -> bool:
    try:
        import pypylon  # noqa: F401
        return True
    except ImportError:
        return False


class PylonCameraSource(CameraSource):
    # Logical control key -> candidate GenICam feature names (newer first).
    _EXPOSURE = ("ExposureTime", "ExposureTimeAbs")
    _GAIN = ("Gain", "GainRaw")

    def __init__(self, index: int = 0, width: Optional[int] = None,
                 height: Optional[int] = None, fps: Optional[float] = None):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.name = f"Basler {index}"
        self._pylon = None
        self._camera = None
        self._converter = None

    # -- capture ---------------------------------------------------------
    def open(self) -> bool:
        pylon = _import_pylon()
        self._pylon = pylon
        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()
        if not devices or self.index >= len(devices):
            return False
        self._camera = pylon.InstantCamera(tlf.CreateDevice(devices[self.index]))
        self._camera.Open()
        try:
            self.name = f"Basler {self._camera.GetDeviceInfo().GetModelName()}"
        except Exception:  # pragma: no cover
            pass
        if self.width and self.height:
            self.set_mode(self.width, self.height, self.fps)
        conv = pylon.ImageFormatConverter()
        conv.OutputPixelFormat = pylon.PixelType_BGR8packed
        conv.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        self._converter = conv
        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        return bool(self._safe(self._camera.IsGrabbing, False))

    def is_open(self) -> bool:
        return self._camera is not None and bool(self._safe(self._camera.IsOpen, False))

    def read(self) -> Optional[np.ndarray]:
        if self._camera is None or not self._safe(self._camera.IsGrabbing, False):
            return None
        res = self._camera.RetrieveResult(2000, self._pylon.TimeoutHandling_Return)
        try:
            if not res.GrabSucceeded():
                return None
            return self._converter.Convert(res).GetArray()
        finally:
            res.Release()

    def close(self) -> None:
        if self._camera is not None:
            try:
                if self._safe(self._camera.IsGrabbing, False):
                    self._camera.StopGrabbing()
                if self._safe(self._camera.IsOpen, False):
                    self._camera.Close()
            finally:
                self._camera = None

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    def _node(self, *names):
        for n in names:
            try:
                node = getattr(self._camera, n)
            except Exception:
                continue
            if node is not None:
                return node
        return None

    @staticmethod
    def _value(node):
        try:
            return node.Value
        except Exception:
            return PylonCameraSource._safe(node.GetValue) if node is not None else None

    # -- controls --------------------------------------------------------
    def controls(self) -> Dict[str, V4l2Control]:
        """Expose exposure/gain/auto-exposure as V4l2Control-shaped descriptors.

        Reusing that shape lets the Camera tab build the same dynamic sliders it
        uses for V4L2 cameras.
        """
        out: Dict[str, V4l2Control] = {}
        ea = self._node("ExposureAuto")
        if ea is not None:
            cur = str(self._value(ea))
            out["auto_exposure"] = V4l2Control(
                "auto_exposure", "menu", 0, AUTO_EXPOSURE_AUTO, 1, AUTO_EXPOSURE_AUTO,
                AUTO_EXPOSURE_AUTO if cur == "Continuous" else AUTO_EXPOSURE_MANUAL)
        exp = self._node(*self._EXPOSURE)
        if exp is not None:
            out["exposure_time_absolute"] = V4l2Control(
                "exposure_time_absolute", "int",
                int(exp.Min), int(exp.Max), 1, int(exp.Min), int(self._value(exp)),
                inactive=str(self._value(ea)) == "Continuous" if ea is not None else False)
        gain = self._node(*self._GAIN)
        if gain is not None:
            out["gain"] = V4l2Control(
                "gain", "int", int(gain.Min), int(gain.Max), 1,
                int(gain.Min), int(self._value(gain)))
        return out

    def set_property(self, key: str, value: float) -> None:
        if key == "auto_exposure":
            self.set_auto_exposure(bool(value))
            return
        if key == "exposure_time_absolute":
            node = self._node(*self._EXPOSURE)
        elif key == "gain":
            node = self._node(*self._GAIN)
        else:
            node = self._node(key)
        if node is None:
            return
        try:
            node.Value = float(value)
        except Exception:
            try:
                node.Value = int(value)
            except Exception:
                pass

    def get_property(self, key: str) -> Optional[float]:
        if key == "exposure_time_absolute":
            node = self._node(*self._EXPOSURE)
        elif key == "gain":
            node = self._node(*self._GAIN)
        else:
            node = self._node(key)
        return None if node is None else self._value(node)

    def set_auto_exposure(self, enabled: bool) -> None:
        node = self._node("ExposureAuto")
        if node is None:
            return
        try:
            node.Value = "Continuous" if enabled else "Off"
        except Exception:
            pass

    # -- modes -----------------------------------------------------------
    def probe_modes(self) -> List[tuple]:
        wn, hn = self._node("Width"), self._node("Height")
        if wn is None or hn is None:
            return []
        wmax, hmax = int(wn.Max), int(hn.Max)
        fr = self._node("ResultingFrameRate", "AcquisitionFrameRate",
                        "AcquisitionFrameRateAbs")
        fps = round(float(self._value(fr)), 1) if fr is not None else 0.0
        wanted = [(wmax, hmax), (1920, 1080), (1280, 720), (640, 480)]
        modes, seen = [], set()
        for w, h in wanted:
            if w <= wmax and h <= hmax and (w, h) not in seen:
                seen.add((w, h))
                modes.append((w, h, fps))
        return modes

    def set_mode(self, width: int, height: int, fps: Optional[float] = None) -> None:
        if self._camera is None:
            return
        was_grabbing = self._safe(self._camera.IsGrabbing, False)
        if was_grabbing:
            self._safe(self._camera.StopGrabbing)
        # Zero offsets first so the full sensor is addressable, then size+center.
        for name in ("OffsetX", "OffsetY"):
            node = self._node(name)
            if node is not None:
                self._safe(lambda n=node: setattr(n, "Value", 0))
        self._set_geometry("Width", width, "OffsetX")
        self._set_geometry("Height", height, "OffsetY")
        if fps:
            self.fps = fps
            fr = self._node("AcquisitionFrameRate", "AcquisitionFrameRateAbs")
            en = self._node("AcquisitionFrameRateEnable")
            if en is not None:
                self._safe(lambda: setattr(en, "Value", True))
            if fr is not None:
                self._safe(lambda: setattr(fr, "Value", float(fps)))
        self.width, self.height = int(width), int(height)
        if was_grabbing:
            self._safe(lambda: self._camera.StartGrabbing(
                self._pylon.GrabStrategy_LatestImageOnly))

    def _set_geometry(self, size_name: str, value: int, offset_name: str) -> None:
        node = self._node(size_name)
        if node is None:
            return
        inc = self._safe(lambda: node.Inc, 1) or 1
        v = max(int(node.Min), min(int(node.Max), int(round(value / inc)) * inc))
        self._safe(lambda: setattr(node, "Value", v))
        off = self._node(offset_name)
        if off is not None:
            centered = (int(node.Max) - v) // 2
            oinc = self._safe(lambda: off.Inc, 1) or 1
            centered = (centered // oinc) * oinc
            self._safe(lambda: setattr(off, "Value", centered))
