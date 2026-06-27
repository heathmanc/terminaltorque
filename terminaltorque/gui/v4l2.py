"""Thin wrapper around ``v4l2-ctl`` for real V4L2 cameras on Linux.

OpenCV's ``CAP_PROP_*`` exposure/auto-exposure mapping is unreliable across
UVC drivers (it tries to squeeze a menu control into a normalized 0.25/0.75
value), which is exactly what darkens many webcams. This module instead talks
to the kernel control interface directly:

* resolutions / frame rates come from ``v4l2-ctl --list-formats-ext`` (the real
  supported modes, queried straight from the device node -- no capture needed);
* image controls come from ``v4l2-ctl --list-ctrls`` with their true ranges;
* values are set with ``v4l2-ctl --set-ctrl``.

All of this works on the device node (``/dev/videoN``) whether or not a capture
pipeline is open, so the operator can probe and tune without starting a live
view. The parsing functions are pure and unit-tested against real hardware
output; the device functions just shell out and parse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import re
import shutil
import subprocess


@dataclass
class V4l2Control:
    name: str
    type: str          # int | bool | menu
    minimum: int = 0
    maximum: int = 0
    step: int = 1
    default: int = 0
    value: int = 0
    inactive: bool = False


@dataclass
class V4l2Mode:
    width: int
    height: int
    fps: float
    fourcc: str = ""


# Standard UVC auto_exposure menu values (V4L2_CID_EXPOSURE_AUTO).
AUTO_EXPOSURE_AUTO = 3      # Aperture Priority Mode (camera drives exposure)
AUTO_EXPOSURE_MANUAL = 1    # Manual Mode


_CTRL_RE = re.compile(
    r"^\s*([\w_]+)\s+0x[0-9a-fA-F]+\s+\((\w+)\)\s*:\s*(.*)$"
)


def parse_controls(text: str) -> Dict[str, V4l2Control]:
    """Parse ``v4l2-ctl --list-ctrls`` output into a name -> control map."""
    controls: Dict[str, V4l2Control] = {}
    for line in text.splitlines():
        m = _CTRL_RE.match(line)
        if not m:
            continue
        name, ctype, rest = m.groups()
        fields = dict(re.findall(r"(\w+)=(-?\d+)", rest))
        controls[name] = V4l2Control(
            name=name,
            type=ctype,
            minimum=int(fields.get("min", 0)),
            maximum=int(fields.get("max", 0)),
            step=int(fields.get("step", 1)) or 1,
            default=int(fields.get("default", 0)),
            value=int(fields.get("value", 0)),
            inactive="flags=inactive" in rest,
        )
    return controls


def parse_formats(text: str) -> List[V4l2Mode]:
    """Parse ``v4l2-ctl --list-formats-ext`` output into modes.

    Deduplicates to one entry per (width, height, fourcc), keeping the highest
    frame rate, and sorts largest-area first with MJPG preferred (it gives the
    high frame rates; YUYV is often capped to a few fps at large sizes).
    """
    raw: Dict[tuple, float] = {}
    fourcc = ""
    size: Optional[tuple] = None
    for line in text.splitlines():
        s = line.strip()
        fm = re.match(r"\[\d+\]:\s*'(\w+)'", s)
        if fm:
            fourcc = fm.group(1)
            continue
        sm = re.match(r"Size:\s*Discrete\s+(\d+)x(\d+)", s)
        if sm:
            size = (int(sm.group(1)), int(sm.group(2)))
            continue
        im = re.search(r"\(([\d.]+)\s*fps\)", s)
        if im and size is not None:
            fps = float(im.group(1))
            key = (size[0], size[1], fourcc)
            if fps > raw.get(key, 0.0):
                raw[key] = fps

    modes = [V4l2Mode(w, h, fps, fc) for (w, h, fc), fps in raw.items()]
    modes.sort(key=lambda m: (m.fourcc != "MJPG", -(m.width * m.height), -m.fps))
    return modes


# --------------------------------------------------------------------- device

def available() -> bool:
    """True if the ``v4l2-ctl`` utility is installed."""
    return shutil.which("v4l2-ctl") is not None


def _run(args: List[str]) -> str:
    proc = subprocess.run(
        ["v4l2-ctl", *args],
        capture_output=True, text=True, timeout=5, check=False,
    )
    return proc.stdout


def list_controls(device: str = "/dev/video0") -> Dict[str, V4l2Control]:
    return parse_controls(_run(["-d", device, "--list-ctrls"]))


def list_modes(device: str = "/dev/video0") -> List[V4l2Mode]:
    return parse_formats(_run(["-d", device, "--list-formats-ext"]))


def set_control(device: str, name: str, value: int) -> None:
    _run(["-d", device, "--set-ctrl", f"{name}={int(value)}"])


def get_control(device: str, name: str) -> Optional[int]:
    out = _run(["-d", device, "--get-ctrl", name])
    m = re.search(r":\s*(-?\d+)", out)
    return int(m.group(1)) if m else None


def set_auto_exposure(device: str, enabled: bool) -> None:
    """Enable hardware auto-exposure (aperture priority) or switch to manual."""
    set_control(device, "auto_exposure",
                AUTO_EXPOSURE_AUTO if enabled else AUTO_EXPOSURE_MANUAL)
