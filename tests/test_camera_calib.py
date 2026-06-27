import numpy as np
import cv2
import pytest

from terminaltorque.camera_calib import CameraCalibration, ChessboardCalibrator
from terminaltorque.gui.widgets import snap_to_edge


def _make_chessboard(cols=9, rows=6, square=40, pad=40):
    """Render a chessboard whose inner-corner grid is cols x rows."""
    sc, sr = cols + 1, rows + 1  # squares
    img = np.full((sr * square + 2 * pad, sc * square + 2 * pad), 255, np.uint8)
    for i in range(sr):
        for j in range(sc):
            if (i + j) % 2 == 0:
                y, x = pad + i * square, pad + j * square
                img[y:y + square, x:x + square] = 0
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


# --- snap-to-edge -------------------------------------------------------------

def test_snap_to_edge_finds_vertical_edge():
    img = np.zeros((60, 60, 3), np.uint8)
    img[:, 30:] = 255                       # vertical edge at x=30
    x, y = snap_to_edge(img, 26.0, 25.0, radius=8)
    assert abs(x - 30) < 1.5                 # snapped onto the edge
    assert abs(y - 25.0) < 2.0


def test_snap_to_edge_no_edge_keeps_point():
    flat = np.full((40, 40, 3), 120, np.uint8)
    x, y = snap_to_edge(flat, 20.0, 20.0)
    assert (x, y) == (20.0, 20.0)


# --- lens calibration ---------------------------------------------------------

def test_chessboard_detection():
    calib = ChessboardCalibrator(pattern_size=(9, 6), square_mm=20.0)
    assert calib.add_view(_make_chessboard(9, 6)) is True
    assert calib.count == 1
    # A blank image yields no corners.
    assert calib.add_view(np.full((480, 640, 3), 127, np.uint8)) is False
    assert calib.count == 1


def test_calibrate_requires_three_views():
    calib = ChessboardCalibrator(pattern_size=(9, 6))
    calib.add_view(_make_chessboard(9, 6))
    with pytest.raises(ValueError):
        calib.calibrate((640, 480))


def test_undistort_identity_when_no_distortion():
    K = np.array([[800, 0, 320], [0, 800, 240], [0, 0, 1]], np.float64)
    cal = CameraCalibration(K, np.zeros(5), (640, 480), rms=0.2)
    pts = np.array([[100.0, 80.0], [320.0, 240.0]])
    out = cal.undistort_points(pts)
    assert np.allclose(out, pts, atol=1e-3)   # zero distortion -> unchanged


def test_calibration_save_load_roundtrip(tmp_path):
    K = np.array([[800, 0, 320], [0, 800, 240], [0, 0, 1]], np.float64)
    dist = np.array([0.1, -0.05, 0.001, 0.0, 0.0])
    cal = CameraCalibration(K, dist, (640, 480), rms=0.33)
    path = str(tmp_path / "cal.npz")
    cal.save(path)
    loaded = CameraCalibration.load(path)
    assert np.allclose(loaded.camera_matrix, K)
    assert np.allclose(loaded.dist_coeffs, dist)
    assert loaded.image_size == (640, 480)
    assert loaded.rms == pytest.approx(0.33)


def test_undistort_image_runs_and_preserves_size():
    K = np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]], np.float64)
    dist = np.array([-0.2, 0.05, 0.0, 0.0, 0.0])   # barrel distortion
    cal = CameraCalibration(K, dist, (640, 480))
    img = np.random.default_rng(0).integers(0, 255, (480, 640, 3), np.uint8)
    out = cal.undistort_image(img)
    assert out.shape == img.shape
