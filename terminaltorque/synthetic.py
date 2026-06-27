"""Generate synthetic battery-lid images for demos and tests.

Produces a lid with a configurable set of circular terminal wells so the
detector can be exercised without real hardware. Ground-truth geometry is
returned so tests can assert detection accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import cv2


@dataclass
class GroundTruthWell:
    center_px: Tuple[float, float]
    radius_px: float


def make_lid_image(
    size: Tuple[int, int] = (480, 640),
    wells: List[GroundTruthWell] | None = None,
    noise_sigma: float = 4.0,
    seed: int = 0,
) -> Tuple[np.ndarray, List[GroundTruthWell]]:
    """Render a synthetic lid (BGR) and return it with ground-truth wells.

    Args:
        size: (height, width) in pixels.
        wells: Wells to draw; a default 2-terminal layout is used if omitted.
        noise_sigma: Gaussian sensor-noise standard deviation.
        seed: RNG seed for reproducible noise.
    """
    h, w = size
    rng = np.random.default_rng(seed)

    if wells is None:
        wells = [
            GroundTruthWell((w * 0.30, h * 0.5), 42.0),
            GroundTruthWell((w * 0.70, h * 0.5), 42.0),
        ]

    # Lid body: mid-gray plastic with a subtle lighting gradient.
    img = np.full((h, w, 3), 150, dtype=np.uint8)
    grad = np.linspace(-18, 18, w, dtype=np.float32)
    img = np.clip(img.astype(np.float32) + grad[None, :, None], 0, 255)

    for gw in wells:
        cx, cy = int(round(gw.center_px[0])), int(round(gw.center_px[1]))
        r = int(round(gw.radius_px))
        # Recessed dark well with a bright machined rim and an inner terminal.
        cv2.circle(img, (cx, cy), r + 3, (95, 95, 95), -1, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), r, (60, 60, 60), -1, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), r, (210, 210, 210), 2, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), int(r * 0.45), (120, 120, 120), -1, cv2.LINE_AA)

    if noise_sigma > 0:
        noise = rng.normal(0, noise_sigma, img.shape).astype(np.float32)
        img = img + noise

    return np.clip(img, 0, 255).astype(np.uint8), wells
