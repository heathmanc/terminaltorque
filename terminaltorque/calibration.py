"""Pixel <-> real-world coordinate conversion.

For a flat lid imaged at a fixed working distance with the camera roughly
perpendicular to the lid, a single uniform scale (millimeters per pixel) plus
an origin offset is enough to map image pixels to the robot's work plane.

The mapping is::

    x_mm = (u_px - origin_u) * mm_per_px
    y_mm = (v_px - origin_v) * mm_per_px * (-1 if invert_y else 1)

Image pixel rows (v) increase downward, while robot Y commonly increases
upward, so ``invert_y`` is True by default. ``origin_u/origin_v`` is the pixel
that corresponds to robot coordinate (0, 0); leave it at the image's optical
center, or set it to a fiducial you have taught the robot.

Calibrate ``mm_per_px`` once from a known reference: image an object of known
size (e.g. a gauge or a terminal of known diameter) and use
``Calibration.from_known_length``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import json


@dataclass
class Calibration:
    """Affine pixel-to-millimeter mapping for a flat, fronto-parallel lid."""

    mm_per_px: float
    origin_u: float = 0.0
    origin_v: float = 0.0
    invert_y: bool = True

    def __post_init__(self) -> None:
        if self.mm_per_px <= 0:
            raise ValueError("mm_per_px must be positive")

    @classmethod
    def from_known_length(
        cls,
        pixels: float,
        millimeters: float,
        origin_u: float = 0.0,
        origin_v: float = 0.0,
        invert_y: bool = True,
    ) -> "Calibration":
        """Build a calibration from a measured reference length.

        ``pixels`` is the measured length in the image of a feature whose true
        size is ``millimeters`` (for example, the pixel diameter of a terminal
        well whose machined diameter you know).
        """
        if pixels <= 0:
            raise ValueError("pixels must be positive")
        if millimeters <= 0:
            raise ValueError("millimeters must be positive")
        return cls(
            mm_per_px=millimeters / pixels,
            origin_u=origin_u,
            origin_v=origin_v,
            invert_y=invert_y,
        )

    def pixel_to_world(self, u: float, v: float) -> Tuple[float, float]:
        """Map an image pixel (u, v) to robot-plane (x_mm, y_mm)."""
        x = (u - self.origin_u) * self.mm_per_px
        y = (v - self.origin_v) * self.mm_per_px
        if self.invert_y:
            y = -y
        return x, y

    def length_to_mm(self, pixels: float) -> float:
        """Convert a length in pixels (e.g. a diameter) to millimeters."""
        return pixels * self.mm_per_px

    # --- persistence -----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "mm_per_px": self.mm_per_px,
            "origin_u": self.origin_u,
            "origin_v": self.origin_v,
            "invert_y": self.invert_y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Calibration":
        return cls(
            mm_per_px=float(data["mm_per_px"]),
            origin_u=float(data.get("origin_u", 0.0)),
            origin_v=float(data.get("origin_v", 0.0)),
            invert_y=bool(data.get("invert_y", True)),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Calibration":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


def default_origin(image_shape: Tuple[int, ...]) -> Tuple[float, float]:
    """Optical-center origin (u, v) for an image of the given shape."""
    h, w = image_shape[:2]
    return (w - 1) / 2.0, (h - 1) / 2.0
