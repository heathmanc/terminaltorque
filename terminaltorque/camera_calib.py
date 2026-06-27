"""Lens (intrinsic) calibration: remove radial/tangential distortion.

A uniform millimeters-per-pixel scale assumes a perfect pinhole camera. Real
lenses bend the image, so a circle far from the optical center appears
*offset* from where a linear model predicts -- exactly the "off-center circles
are wrong" symptom. The fix is a standard chessboard calibration:

1. Show a chessboard of known square size in several poses across the field of
   view; ``cv2.findChessboardCorners`` locates its corners in each.
2. ``cv2.calibrateCamera`` solves for the camera matrix and distortion
   coefficients (with a reprojection error in pixels as a quality check).
3. Every frame is ``undistort``ed before detection. On the undistorted image a
   single mm/px scale is valid everywhere, so off-center wells land correctly.

``CameraCalibration`` holds the result and undistorts images/points;
``ChessboardCalibrator`` accumulates views and runs the solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import cv2


@dataclass
class CameraCalibration:
    camera_matrix: np.ndarray   # 3x3 intrinsics (K)
    dist_coeffs: np.ndarray     # distortion coefficients (k1, k2, p1, p2, k3, ...)
    image_size: Tuple[int, int]  # (width, height) the calibration was solved at
    rms: float = 0.0            # RMS reprojection error, pixels

    def undistort_image(self, image: np.ndarray) -> np.ndarray:
        """Return ``image`` with lens distortion removed (same size)."""
        return cv2.undistort(image, self.camera_matrix, self.dist_coeffs,
                             None, self.camera_matrix)

    def undistort_points(self, points: np.ndarray) -> np.ndarray:
        """Undistort an (N, 2) array of pixel coordinates -> (N, 2) pixels."""
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        out = cv2.undistortPoints(pts, self.camera_matrix, self.dist_coeffs,
                                  P=self.camera_matrix)
        return out.reshape(-1, 2)

    # -- persistence ------------------------------------------------------
    def save(self, path: str) -> None:
        np.savez(path,
                 camera_matrix=self.camera_matrix,
                 dist_coeffs=self.dist_coeffs,
                 image_size=np.asarray(self.image_size),
                 rms=np.asarray(self.rms))

    @classmethod
    def load(cls, path: str) -> "CameraCalibration":
        data = np.load(path)
        return cls(
            camera_matrix=data["camera_matrix"],
            dist_coeffs=data["dist_coeffs"],
            image_size=tuple(int(v) for v in data["image_size"]),
            rms=float(data["rms"]),
        )


class ChessboardCalibrator:
    """Accumulates chessboard views and solves for the camera calibration.

    ``pattern_size`` is the number of *inner* corners (columns, rows) -- a board
    with 10x7 squares has 9x6 inner corners. ``square_mm`` is the printed square
    size; it sets the units but does not affect the distortion solve.
    """

    def __init__(self, pattern_size: Tuple[int, int] = (9, 6),
                 square_mm: float = 25.0):
        self.pattern_size = pattern_size
        self.square_mm = square_mm
        self.obj_points: List[np.ndarray] = []
        self.img_points: List[np.ndarray] = []
        self._criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                          30, 0.001)

    def _template(self) -> np.ndarray:
        cols, rows = self.pattern_size
        objp = np.zeros((rows * cols, 3), np.float32)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
        return objp * self.square_mm

    @staticmethod
    def _gray(image: np.ndarray) -> np.ndarray:
        return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def find_corners(self, image: np.ndarray):
        """Return refined corners if the chessboard is found, else None."""
        gray = self._gray(image)
        flags = (cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
                 + cv2.CALIB_CB_FAST_CHECK)
        found, corners = cv2.findChessboardCorners(gray, self.pattern_size, flags)
        if not found:
            return None
        return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), self._criteria)

    def add_view(self, image: np.ndarray) -> bool:
        """Detect and store the chessboard in ``image``. True if it was found."""
        corners = self.find_corners(image)
        if corners is None:
            return False
        self.add_detected(corners)
        return True

    def add_detected(self, corners: np.ndarray) -> None:
        """Store an already-detected corner set (with its object-point template)."""
        self.img_points.append(corners)
        self.obj_points.append(self._template())

    @property
    def count(self) -> int:
        return len(self.img_points)

    def reset(self) -> None:
        self.obj_points.clear()
        self.img_points.clear()

    def calibrate(self, image_size: Tuple[int, int]) -> CameraCalibration:
        """Solve for intrinsics + distortion from the accumulated views."""
        if self.count < 3:
            raise ValueError("Need at least 3 chessboard views to calibrate")
        rms, k, dist, _rvecs, _tvecs = cv2.calibrateCamera(
            self.obj_points, self.img_points, image_size, None, None)
        return CameraCalibration(k, dist, tuple(image_size), float(rms))
