import math
import os

import pytest

from terminaltorque import Calibration
from terminaltorque.calibration import default_origin


def test_scale_and_length():
    cal = Calibration(mm_per_px=0.1)
    assert cal.length_to_mm(100) == pytest.approx(10.0)


def test_pixel_to_world_with_origin_and_invert():
    cal = Calibration(mm_per_px=0.5, origin_u=100, origin_v=100, invert_y=True)
    x, y = cal.pixel_to_world(120, 80)
    assert x == pytest.approx(10.0)   # (120-100)*0.5
    assert y == pytest.approx(10.0)   # -(80-100)*0.5 = 10


def test_from_known_length():
    cal = Calibration.from_known_length(pixels=84, millimeters=12)
    assert cal.mm_per_px == pytest.approx(12 / 84)


def test_invalid_scale_raises():
    with pytest.raises(ValueError):
        Calibration(mm_per_px=0)
    with pytest.raises(ValueError):
        Calibration.from_known_length(pixels=0, millimeters=12)


def test_default_origin_is_center():
    ou, ov = default_origin((480, 640))
    assert ou == pytest.approx((640 - 1) / 2)
    assert ov == pytest.approx((480 - 1) / 2)


def test_roundtrip_save_load(tmp_path):
    cal = Calibration(mm_per_px=0.123, origin_u=10, origin_v=20, invert_y=False)
    p = os.path.join(tmp_path, "cal.json")
    cal.save(p)
    loaded = Calibration.load(p)
    assert loaded.to_dict() == cal.to_dict()
