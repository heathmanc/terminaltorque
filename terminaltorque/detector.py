"""Detection of circular terminal wells on a battery lid.

Pipeline:

1. Convert to grayscale and blur to suppress sensor noise.
2. Find candidate circles with the Hough gradient transform
   (``cv2.HoughCircles``), which is robust to partial occlusion and uneven
   lighting and is the standard tool for circular-feature detection.
3. Refine each candidate to sub-pixel accuracy from local image gradients so
   the reported center is good enough for the robot to seat a nut driver.
4. Optionally convert centers and diameters to millimeters via a
   :class:`~terminaltorque.calibration.Calibration`.

The Hough center is only accurate to roughly a pixel, which can be a
millimeter or more of robot error depending on the lens. The refinement step
fits the center to the intensity-weighted edge ring inside the candidate, which
typically tightens repeatability to a fraction of a pixel on a clean machined
well.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

try:  # pragma: no cover - import guard
    import cv2
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "OpenCV is required. Install with `pip install opencv-python-headless`."
    ) from exc


@dataclass
class DetectionParams:
    """Tunable parameters for terminal-well detection.

    The radius bounds are the single most important setting: constrain them to
    the physical well size (converted to pixels) to reject spurious circles
    from bolt heads, text, or reflections. ``expected_count`` keeps only the
    strongest N detections when set.
    """

    # Expected well radius range, in pixels. Defaults span a wide range; set
    # these to your lens/standoff for best results.
    min_radius_px: int = 10
    max_radius_px: int = 200

    # Minimum distance between detected centers, in pixels. Defaults to the
    # min radius so two wells cannot merge into one detection.
    min_dist_px: Optional[float] = None

    # Detection method. The "alt" gradient transform (HOUGH_GRADIENT_ALT)
    # scores true circularity and rejects the texture/text/scratch "circles"
    # the classic transform hallucinates -- it is the right default. Set False
    # to fall back to the classic HOUGH_GRADIENT (uses accumulator_threshold).
    use_gradient_alt: bool = True

    # Circularity strictness for the "alt" method, in [0, 1]. Higher accepts
    # only rounder shapes (fewer false positives); lower is more permissive.
    circularity: float = 0.8

    # Hough accumulator inverse resolution. 1.0 = full res; larger is faster
    # but coarser. The "alt" method wants ~1.5.
    dp: float = 1.2

    # Canny high threshold passed to HoughCircles (low is half of this).
    canny_high: float = 120.0

    # Accumulator threshold for the CLASSIC method's centers. Lower = more (and
    # weaker) circles. Ignored when use_gradient_alt is True.
    accumulator_threshold: float = 30.0

    # Merge near-concentric detections (e.g. a well's rim and the terminal post
    # inside it), keeping the larger -- the well opening the robot torques over.
    merge_concentric: bool = True

    # Gaussian blur kernel (odd). Smooths noise before edge detection.
    blur_ksize: int = 5

    # Keep only the strongest N wells, if set (e.g. a 2-terminal lid -> 2).
    expected_count: Optional[int] = None

    # Half-width (in radii) of the ROI used for sub-pixel refinement.
    refine_margin: float = 0.35

    # Minimum fraction of a candidate's circumference that must coincide with a
    # real image edge for it to be accepted, in [0, 1]. The Hough accumulator
    # happily "finds" circles in texture and noise where no continuous rim
    # exists; this rejects them. Raise toward 0.7 for very clean machined wells;
    # lower toward 0.3 if real wells are partly occluded. 0 disables the check.
    min_edge_support: float = 0.45

    def resolved_min_dist(self) -> float:
        if self.min_dist_px is not None:
            return float(self.min_dist_px)
        return max(8.0, float(self.min_radius_px))


@dataclass
class TerminalWell:
    """A detected terminal well.

    Pixel fields are always populated. Millimeter fields are populated only
    when a calibration is supplied to :func:`detect_terminal_wells`.
    """

    center_px: Tuple[float, float]
    diameter_px: float
    confidence: float
    center_mm: Optional[Tuple[float, float]] = None
    diameter_mm: Optional[float] = None
    refined: bool = False

    @property
    def radius_px(self) -> float:
        return self.diameter_px / 2.0

    def to_dict(self) -> dict:
        d = {
            "center_px": [round(self.center_px[0], 3), round(self.center_px[1], 3)],
            "diameter_px": round(self.diameter_px, 3),
            "confidence": round(self.confidence, 4),
            "refined": self.refined,
        }
        if self.center_mm is not None:
            d["center_mm"] = [round(self.center_mm[0], 4), round(self.center_mm[1], 4)]
        if self.diameter_mm is not None:
            d["diameter_mm"] = round(self.diameter_mm, 4)
        return d


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _refine_circle(
    edges: np.ndarray,
    cx: float,
    cy: float,
    r: float,
) -> Optional[Tuple[float, float, float]]:
    """Refine center *and* radius by least-squares fitting the rim edge points.

    Collects the Canny edge pixels in a thin annulus around the candidate and
    fits a circle to them algebraically (Kasa fit). Unlike a gradient-weighted
    centroid, this depends only on the *geometry* of the rim, so uneven lighting
    or a specular highlight on one side does not pull the center off -- the
    behavior that left detections visibly offset on real metallic terminals.

    Returns ``(cx, cy, r)`` or None if there is not a clean rim to fit.
    """
    h, w = edges.shape[:2]
    band = max(2.0, 0.30 * r)
    x0 = max(0, int(np.floor(cx - r - band)))
    y0 = max(0, int(np.floor(cy - r - band)))
    x1 = min(w, int(np.ceil(cx + r + band)))
    y1 = min(h, int(np.ceil(cy + r + band)))
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None

    ys, xs = np.nonzero(edges[y0:y1, x0:x1])
    if xs.size < 8:
        return None
    ex = xs.astype(np.float64) + x0
    ey = ys.astype(np.float64) + y0
    # Keep only edge points near the expected rim (reject interior nut/threads).
    d = np.hypot(ex - cx, ey - cy)
    keep = np.abs(d - r) <= band
    ex, ey = ex[keep], ey[keep]
    if ex.size < 8:
        return None

    # Kasa circle fit: solve A [D, E, F]^T = b for x^2+y^2 + Dx + Ey + F = 0.
    A = np.column_stack([ex, ey, np.ones_like(ex)])
    b = ex ** 2 + ey ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    ax, ay = sol[0] / 2.0, sol[1] / 2.0
    rr2 = sol[2] + ax ** 2 + ay ** 2
    if rr2 <= 0:
        return None
    rr = float(np.sqrt(rr2))
    # Reject a runaway fit (keep the Hough estimate instead).
    if np.hypot(ax - cx, ay - cy) > 0.5 * r or abs(rr - r) > 0.5 * r:
        return None
    return float(ax), float(ay), rr


def _edge_support(
    edges: np.ndarray, cx: float, cy: float, r: float, samples: int = 72, band: int = 2
) -> float:
    """Fraction of the circle's circumference that lies on an image edge.

    Samples points evenly around the circle and checks a small radial band at
    each for a Canny edge pixel. A genuine well rim scores near 1.0; a circle
    hallucinated from scattered texture scores low.
    """
    if r < 1:
        return 0.0
    h, w = edges.shape[:2]
    angles = np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)
    radii = r + np.arange(-band, band + 1)[:, None]  # (2*band+1, 1)
    xs = np.rint(cx + radii * cos_a).astype(np.intp)  # (bands, samples)
    ys = np.rint(cy + radii * sin_a).astype(np.intp)
    valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    hit = (edges[np.clip(ys, 0, h - 1), np.clip(xs, 0, w - 1)] > 0) & valid
    # A circumference sample counts if any pixel in its radial band is an edge.
    return float(hit.any(axis=0).mean())


def detect_terminal_wells(
    image: np.ndarray,
    params: Optional[DetectionParams] = None,
    calibration: "Optional[object]" = None,
) -> List[TerminalWell]:
    """Detect circular terminal wells in a lid image.

    Args:
        image: BGR, BGRA, or grayscale image as a NumPy array.
        params: Detection tuning. Uses sensible defaults if omitted.
        calibration: Optional ``Calibration`` to populate millimeter fields.

    Returns:
        Terminal wells sorted by descending confidence (strongest first).
    """
    if image is None or image.size == 0:
        raise ValueError("image is empty")
    params = params or DetectionParams()

    gray = _to_gray(image)
    k = params.blur_ksize | 1  # force odd
    blurred = cv2.GaussianBlur(gray, (k, k), 0)

    if params.use_gradient_alt:
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT_ALT,
            dp=max(1.5, params.dp),
            minDist=params.resolved_min_dist(),
            param1=300.0,                 # ALT wants a high Canny threshold
            param2=params.circularity,    # circularity in [0, 1]
            minRadius=int(params.min_radius_px),
            maxRadius=int(params.max_radius_px),
        )
    else:
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=params.dp,
            minDist=params.resolved_min_dist(),
            param1=params.canny_high,
            param2=params.accumulator_threshold,
            minRadius=int(params.min_radius_px),
            maxRadius=int(params.max_radius_px),
        )

    wells: List[TerminalWell] = []
    if circles is None:
        return wells

    circles = np.squeeze(circles, axis=0)  # (N, 3): x, y, r
    if circles.ndim == 1:
        circles = circles[None, :]

    # Edge map used to verify each candidate is backed by a real circular rim.
    edges = cv2.Canny(blurred, max(1.0, params.canny_high * 0.5), params.canny_high)

    # Collect (cx, cy, r, support) for candidates with real edge support.
    candidates = []
    for cx, cy, r in circles:
        cx, cy, r = float(cx), float(cy), float(r)
        if r < 1:
            continue
        support = _edge_support(edges, cx, cy, r)
        if support < params.min_edge_support:
            continue
        candidates.append((cx, cy, r, support))

    if params.merge_concentric:
        candidates = _merge_concentric(candidates)

    for cx, cy, r, support in candidates:
        refined = _refine_circle(edges, cx, cy, r)
        is_refined = refined is not None
        if is_refined:
            cx, cy, r = refined
        # Confidence is the measured edge support: how complete the rim is, in
        # [0, 1]. This is a real quality signal, unlike the Hough vote rank.
        well = TerminalWell(
            center_px=(cx, cy),
            diameter_px=2.0 * r,
            confidence=round(support, 4),
            refined=is_refined,
        )
        if calibration is not None:
            wx, wy = calibration.pixel_to_world(cx, cy)
            well.center_mm = (wx, wy)
            well.diameter_mm = calibration.length_to_mm(2.0 * r)
        wells.append(well)

    wells.sort(key=lambda w: w.confidence, reverse=True)
    if params.expected_count is not None:
        wells = wells[: params.expected_count]
    return wells


def _merge_concentric(candidates):
    """Drop smaller circles sharing a center with a larger one.

    A terminal well often yields both an outer rim and an inner post/nut circle
    at the same center. The robot torques over the well opening, so keep the
    larger circle. ``candidates`` is a list of ``(cx, cy, r, support)``.
    """
    kept = []
    for cx, cy, r, support in sorted(candidates, key=lambda c: c[2], reverse=True):
        concentric = any(
            (cx - kx) ** 2 + (cy - ky) ** 2 <= (0.5 * kr) ** 2
            for kx, ky, kr, _ in kept
        )
        if not concentric:
            kept.append((cx, cy, r, support))
    return kept


def draw_detections(
    image: np.ndarray,
    wells: List[TerminalWell],
    color: Tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    """Return a copy of ``image`` with detected wells annotated (for debugging)."""
    if image.ndim == 2:
        canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        canvas = image.copy()
    for i, w in enumerate(wells):
        cx, cy = int(round(w.center_px[0])), int(round(w.center_px[1]))
        r = int(round(w.radius_px))
        cv2.circle(canvas, (cx, cy), r, color, 2)
        cv2.drawMarker(canvas, (cx, cy), color, cv2.MARKER_CROSS, 12, 2)
        label = f"#{i+1}"
        if w.diameter_mm is not None:
            label += f" {w.diameter_mm:.1f}mm"
        cv2.putText(
            canvas, label, (cx + r + 4, cy),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    return canvas
