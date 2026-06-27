"""TerminalTorque: vision-based detection of battery-lid terminal wells.

Detects circular terminal wells on a battery lid from a camera image and
reports each well's center and diameter, in pixels and (when calibrated) in
real-world millimeters, so a robot can position over each terminal and torque
the nut.
"""

from .detector import (
    DetectionParams,
    TerminalWell,
    detect_terminal_wells,
)
from .calibration import Calibration

__all__ = [
    "DetectionParams",
    "TerminalWell",
    "detect_terminal_wells",
    "Calibration",
]

__version__ = "0.1.0"
