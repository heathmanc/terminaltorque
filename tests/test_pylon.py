"""Unit tests for the Basler (pypylon) source using a fake camera.

These exercise the control/mode/grab logic without a real camera or the Pylon
runtime, by injecting a fake InstantCamera-like object.
"""

import types

import numpy as np

from terminaltorque.gui.pylon_source import PylonCameraSource
from terminaltorque.gui.v4l2 import AUTO_EXPOSURE_AUTO, AUTO_EXPOSURE_MANUAL


class FakeNode:
    def __init__(self, value, mn=0, mx=0, inc=1):
        self.Value = value
        self.Min = mn
        self.Max = mx
        self.Inc = inc


class FakeCam:
    def __init__(self):
        self.ExposureTime = FakeNode(5000.0, 34, 1000000)
        self.Gain = FakeNode(2.0, 0, 36)
        self.ExposureAuto = FakeNode("Off")
        self.Width = FakeNode(1920, 16, 1920, 16)
        self.Height = FakeNode(1080, 2, 1080, 2)
        self.OffsetX = FakeNode(0, 0, 1920, 16)
        self.OffsetY = FakeNode(0, 0, 1080, 2)
        self.AcquisitionFrameRate = FakeNode(30.0, 1, 100)
        self.AcquisitionFrameRateEnable = FakeNode(False)
        self._grabbing = True
        self._open = True

    def IsOpen(self):
        return self._open

    def IsGrabbing(self):
        return self._grabbing

    def StopGrabbing(self):
        self._grabbing = False

    def StartGrabbing(self, *a):
        self._grabbing = True


def _src():
    s = PylonCameraSource(0)
    s._camera = FakeCam()
    return s


def test_controls_expose_real_ranges():
    s = _src()
    c = s.controls()
    assert set(c) == {"auto_exposure", "exposure_time_absolute", "gain"}
    assert c["exposure_time_absolute"].maximum == 1000000
    assert c["gain"].maximum == 36
    # ExposureAuto is Off -> auto_exposure reads as Manual.
    assert c["auto_exposure"].value == AUTO_EXPOSURE_MANUAL


def test_set_exposure_and_gain():
    s = _src()
    s.set_property("exposure_time_absolute", 8000)
    s.set_property("gain", 5)
    assert s._camera.ExposureTime.Value == 8000.0
    assert s._camera.Gain.Value == 5.0


def test_auto_exposure_drives_enum():
    s = _src()
    s.set_property("auto_exposure", 1.0)
    assert s._camera.ExposureAuto.Value == "Continuous"
    s.set_auto_exposure(False)
    assert s._camera.ExposureAuto.Value == "Off"
    # And it now reads back as Auto when Continuous.
    s.set_auto_exposure(True)
    assert s.controls()["auto_exposure"].value == AUTO_EXPOSURE_AUTO


def test_probe_modes_lists_sensor_resolutions():
    s = _src()
    modes = s.probe_modes()
    assert modes[0] == (1920, 1080, 30.0)        # full sensor first
    assert (1280, 720, 30.0) in modes


def test_set_mode_sizes_and_centers():
    s = _src()
    s.set_mode(1280, 720, 30.0)
    assert s._camera.Width.Value == 1280
    assert s._camera.Height.Value == 720
    assert s._camera.OffsetX.Value == 320     # (1920-1280)/2, aligned to inc 16
    assert s._camera.OffsetY.Value == 180     # (1080-720)/2, aligned to inc 2
    assert s._camera.AcquisitionFrameRate.Value == 30.0


def test_read_converts_grab_to_array():
    s = _src()
    arr = np.zeros((4, 4, 3), np.uint8)

    class Grab:
        def GrabSucceeded(self):
            return True

        def Release(self):
            pass

    s._pylon = types.SimpleNamespace(TimeoutHandling_Return=0)
    s._converter = types.SimpleNamespace(
        Convert=lambda res: types.SimpleNamespace(GetArray=lambda: arr))
    s._camera.RetrieveResult = lambda timeout, handling: Grab()
    assert s.read() is arr
