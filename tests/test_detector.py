import math

import numpy as np
import pytest

from terminaltorque import (
    Calibration,
    DetectionParams,
    detect_terminal_wells,
)
from terminaltorque.synthetic import GroundTruthWell, make_lid_image


def _match(wells, gt, tol_px):
    """Return the detected well closest to ground-truth center, if within tol."""
    best = None
    best_d = tol_px
    for w in wells:
        d = math.hypot(w.center_px[0] - gt.center_px[0], w.center_px[1] - gt.center_px[1])
        if d <= best_d:
            best = w
            best_d = d
    return best


def test_detects_default_two_wells():
    image, gt = make_lid_image()
    params = DetectionParams(min_radius_px=25, max_radius_px=70, expected_count=2)
    wells = detect_terminal_wells(image, params)
    assert len(wells) == 2
    for g in gt:
        m = _match(wells, g, tol_px=3.0)
        assert m is not None, "every ground-truth well should be detected"


def test_center_and_diameter_accuracy():
    image, gt = make_lid_image()
    params = DetectionParams(min_radius_px=25, max_radius_px=70, expected_count=2)
    wells = detect_terminal_wells(image, params)
    for g in gt:
        m = _match(wells, g, tol_px=3.0)
        assert m is not None
        # Sub-pixel-ish center accuracy.
        err = math.hypot(m.center_px[0] - g.center_px[0], m.center_px[1] - g.center_px[1])
        assert err < 2.5
        # Diameter within ~12% of truth.
        assert abs(m.diameter_px - 2 * g.radius_px) / (2 * g.radius_px) < 0.12


def test_calibration_produces_mm_fields():
    image, gt = make_lid_image()
    # 42 px radius well is 12 mm true diameter -> mm_per_px from 84 px.
    cal = Calibration.from_known_length(pixels=84.0, millimeters=12.0,
                                        origin_u=0.0, origin_v=0.0, invert_y=False)
    params = DetectionParams(min_radius_px=25, max_radius_px=70, expected_count=2)
    wells = detect_terminal_wells(image, params, calibration=cal)
    assert wells
    for w in wells:
        assert w.center_mm is not None
        assert w.diameter_mm is not None
        # Diameter should be near 12 mm.
        assert abs(w.diameter_mm - 12.0) < 2.0


def test_expected_count_limits_results():
    image, _ = make_lid_image()
    params = DetectionParams(min_radius_px=25, max_radius_px=70, expected_count=1)
    wells = detect_terminal_wells(image, params)
    assert len(wells) == 1


def test_custom_layout_three_wells():
    layout = [
        GroundTruthWell((120, 120), 35),
        GroundTruthWell((320, 160), 35),
        GroundTruthWell((220, 340), 35),
    ]
    image, gt = make_lid_image(size=(480, 480), wells=layout)
    params = DetectionParams(min_radius_px=20, max_radius_px=55, expected_count=3)
    wells = detect_terminal_wells(image, params)
    assert len(wells) == 3
    for g in gt:
        assert _match(wells, g, tol_px=3.0) is not None


def test_empty_image_raises():
    with pytest.raises(ValueError):
        detect_terminal_wells(np.empty((0, 0), dtype=np.uint8))


def test_no_circles_returns_empty():
    blank = np.full((200, 200, 3), 150, dtype=np.uint8)
    wells = detect_terminal_wells(blank, DetectionParams(min_radius_px=20, max_radius_px=40))
    assert wells == []


def test_rejects_textured_noncircular_clutter():
    """Busy surface (lines, text, noise) but no real wells -> ~no detections."""
    rng = np.random.default_rng(7)
    import cv2
    img = np.full((480, 640, 3), 150, np.uint8)
    for _ in range(40):
        p1 = tuple(rng.integers(0, 640, 2).tolist())
        p2 = tuple(rng.integers(0, 480, 2).tolist())
        cv2.line(img, p1, p2, (90, 90, 90), 1)
    cv2.putText(img, "WARNING 12V", (60, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 40, 40), 2)
    img = np.clip(img + rng.normal(0, 12, img.shape), 0, 255).astype(np.uint8)

    # Classic transform with no edge filtering hallucinates a field of circles.
    classic = detect_terminal_wells(img, DetectionParams(
        min_radius_px=10, max_radius_px=80,
        use_gradient_alt=False, min_edge_support=0.0))
    # The default (alt) method rejects the overwhelming majority of them.
    alt = detect_terminal_wells(img, DetectionParams(min_radius_px=10, max_radius_px=80))

    assert len(classic) >= 20          # the problem the user reported
    assert len(alt) <= 3               # essentially cleaned up
    assert len(alt) < len(classic) / 10


def test_merges_concentric_into_single_well():
    """A rim plus an inner post at the same center collapse to one well."""
    layout = [GroundTruthWell((220, 220), 50)]
    image, _ = make_lid_image(size=(440, 440), wells=layout)
    # Permissive radius range admits the inner post circle too.
    wells = detect_terminal_wells(
        image, DetectionParams(min_radius_px=10, max_radius_px=90)
    )
    assert len(wells) == 1
    assert abs(wells[0].center_px[0] - 220) < 3
    assert abs(wells[0].center_px[1] - 220) < 3
