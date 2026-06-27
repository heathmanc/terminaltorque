"""Image acquisition helpers: load from file or grab a frame from a camera."""

from __future__ import annotations

from typing import Optional

import numpy as np
import cv2


def load_image(path: str) -> np.ndarray:
    """Load an image from disk as BGR. Raises if the file cannot be read."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return img


def grab_frame(camera_index: int = 0, warmup_frames: int = 5) -> np.ndarray:
    """Capture a single frame from a connected camera.

    Grabs a few warm-up frames first so auto-exposure/white-balance settle
    before the measurement frame is taken.

    Args:
        camera_index: OpenCV device index.
        warmup_frames: Frames to discard before the returned frame.

    Raises:
        RuntimeError: if the camera cannot be opened or read.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {camera_index}")
    try:
        frame = None
        for _ in range(max(1, warmup_frames)):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Failed to read frame from camera")
        return frame
    finally:
        cap.release()


def save_image(path: str, image: np.ndarray) -> None:
    if not cv2.imwrite(path, image):
        raise IOError(f"Could not write image: {path}")
