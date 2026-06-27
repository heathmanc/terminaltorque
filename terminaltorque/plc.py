"""Push detection results to an Allen-Bradley Logix PLC over EtherNet/IP.

Uses CIP via ``pycomm3`` to write each terminal well's center (X, Y) and
diameter into PLC tags, then raises a *data-ready* handshake bit so the robot
program knows a fresh, complete result set is available.

Tag layout (defaults, ``prefix="Vision"``)::

    Vision_Count        DINT          number of valid wells in this result
    Vision_X[i]         REAL[]        well i center X (mm if calibrated)
    Vision_Y[i]         REAL[]        well i center Y
    Vision_Dia[i]       REAL[]        well i diameter
    Vision_Valid[i]     BOOL[]        true for populated slots
    Vision_DataReady    BOOL          set after a complete write

The arrays are fixed-size in the PLC (``max_wells``). Every slot is written on
every push -- unused slots are zeroed and marked invalid -- so the robot never
reads stale geometry from a previous cycle.

Write order is deliberate: ``DataReady`` is cleared first, all geometry is
written, then ``DataReady`` is set. With the robot program gated on
``DataReady`` it can never latch a half-written result. Optionally
``wait_for_ack`` blocks until the PLC clears ``DataReady`` (its acknowledgement
that it consumed the data).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
import time

from .detector import TerminalWell


@dataclass
class PlcConfig:
    """Connection and tag mapping for the PLC push.

    ``path`` is the pycomm3 connection path. For a CompactLogix this is just the
    IP (e.g. ``"192.168.1.10"``); for a ControlLogix include the processor slot
    (e.g. ``"192.168.1.10/0"``). Use :meth:`from_ip` to build it from parts.
    """

    path: str
    count_tag: str = "Vision_Count"
    x_tag: str = "Vision_X[{i}]"
    y_tag: str = "Vision_Y[{i}]"
    dia_tag: str = "Vision_Dia[{i}]"
    valid_tag: Optional[str] = "Vision_Valid[{i}]"
    data_ready_tag: Optional[str] = "Vision_DataReady"
    max_wells: int = 8

    @classmethod
    def from_ip(
        cls,
        ip: str,
        slot: Optional[int] = None,
        prefix: str = "Vision",
        max_wells: int = 8,
    ) -> "PlcConfig":
        """Build a config from an IP, optional slot, and a tag-name prefix."""
        path = f"{ip}/{slot}" if slot is not None else ip
        return cls(
            path=path,
            count_tag=f"{prefix}_Count",
            x_tag=f"{prefix}_X[{{i}}]",
            y_tag=f"{prefix}_Y[{{i}}]",
            dia_tag=f"{prefix}_Dia[{{i}}]",
            valid_tag=f"{prefix}_Valid[{{i}}]",
            data_ready_tag=f"{prefix}_DataReady",
            max_wells=max_wells,
        )


def _well_values(well: TerminalWell) -> Tuple[float, float, float]:
    """Prefer calibrated millimeters; fall back to pixels if uncalibrated."""
    if well.center_mm is not None:
        x, y = well.center_mm
    else:
        x, y = well.center_px
    dia = well.diameter_mm if well.diameter_mm is not None else well.diameter_px
    return float(x), float(y), float(dia)


# Human-readable descriptions for the HMI PLC tab, keyed by logical group.
TAG_DESCRIPTIONS: dict = {
    "count": "Number of valid wells found this cycle.",
    "x": "Well center X (mm if calibrated, else pixels).",
    "y": "Well center Y (mm if calibrated, else pixels).",
    "dia": "Well diameter (mm if calibrated, else pixels).",
    "valid": "True for populated array slots; false for unused slots.",
    "data_ready": "Set after a complete write. Robot gates on this; clear it "
                  "to acknowledge the data was consumed.",
}

# Logical groups that can be individually enabled/disabled from the HMI.
ALL_GROUPS = ("count", "x", "y", "dia", "valid", "data_ready")


def tag_catalog(config: PlcConfig) -> List[dict]:
    """Describe the tags this config writes, for display in the HMI.

    Returns one entry per logical group: ``{group, tag, type, description}``.
    Array tags use ``[0..N-1]`` notation.
    """
    last = config.max_wells - 1
    rows = [
        {"group": "count", "tag": config.count_tag, "type": "DINT"},
        {"group": "x", "tag": config.x_tag.format(i=f"0..{last}"), "type": "REAL[]"},
        {"group": "y", "tag": config.y_tag.format(i=f"0..{last}"), "type": "REAL[]"},
        {"group": "dia", "tag": config.dia_tag.format(i=f"0..{last}"), "type": "REAL[]"},
    ]
    if config.valid_tag:
        rows.append({"group": "valid",
                     "tag": config.valid_tag.format(i=f"0..{last}"), "type": "BOOL[]"})
    if config.data_ready_tag:
        rows.append({"group": "data_ready", "tag": config.data_ready_tag, "type": "BOOL"})
    for r in rows:
        r["description"] = TAG_DESCRIPTIONS.get(r["group"], "")
    return rows


def build_writes(
    wells: Sequence[TerminalWell],
    config: PlcConfig,
    enabled_groups: Optional[Sequence[str]] = None,
) -> List[Tuple[str, object]]:
    """Return the ordered ``(tag, value)`` writes for one push, sans handshake.

    Every array slot up to ``max_wells`` is included so stale slots are cleared.
    Wells beyond ``max_wells`` are dropped (already sorted strongest-first).
    ``enabled_groups`` optionally restricts which logical groups are written
    (used by the HMI to disable individual tags); ``None`` writes all.
    """
    def on(group: str) -> bool:
        return enabled_groups is None or group in enabled_groups

    n = min(len(wells), config.max_wells)
    writes: List[Tuple[str, object]] = []
    for i in range(config.max_wells):
        if i < n:
            x, y, dia = _well_values(wells[i])
            valid = True
        else:
            x = y = dia = 0.0
            valid = False
        if on("x"):
            writes.append((config.x_tag.format(i=i), x))
        if on("y"):
            writes.append((config.y_tag.format(i=i), y))
        if on("dia"):
            writes.append((config.dia_tag.format(i=i), dia))
        if config.valid_tag and on("valid"):
            writes.append((config.valid_tag.format(i=i), valid))
    if on("count"):
        writes.append((config.count_tag, int(n)))
    return writes


def push_to_plc(
    wells: Sequence[TerminalWell],
    config: PlcConfig,
    plc=None,
    wait_for_ack: bool = False,
    ack_timeout_s: float = 5.0,
    poll_interval_s: float = 0.05,
    enabled_groups: Optional[Sequence[str]] = None,
) -> dict:
    """Write detection results to the PLC and raise the data-ready handshake.

    Args:
        wells: Detected wells (strongest first).
        config: Connection path and tag mapping.
        plc: An open pycomm3-style driver (must expose ``write(*tags)`` and
            ``read(tag)``). If ``None``, a ``LogixDriver`` is opened from
            ``config.path`` for the duration of the push.
        wait_for_ack: If true, block until the PLC clears ``data_ready_tag``.
        ack_timeout_s: Max seconds to wait for the acknowledgement.
        poll_interval_s: Poll period while waiting for the ack.

    Returns:
        A status dict: number of wells written, whether the handshake was set,
        and whether an ack was received.
    """
    owns_connection = plc is None
    if owns_connection:
        plc = _open_driver(config.path)

    try:
        if config.data_ready_tag:
            plc.write((config.data_ready_tag, False))

        writes = build_writes(wells, config, enabled_groups)
        plc.write(*writes)

        handshake_set = False
        if config.data_ready_tag:
            plc.write((config.data_ready_tag, True))
            handshake_set = True

        acked = False
        if wait_for_ack and config.data_ready_tag:
            acked = _wait_for_clear(
                plc, config.data_ready_tag, ack_timeout_s, poll_interval_s
            )

        return {
            "written": min(len(wells), config.max_wells),
            "handshake_set": handshake_set,
            "acked": acked,
        }
    finally:
        if owns_connection:
            _close_driver(plc)


def _wait_for_clear(plc, tag: str, timeout_s: float, poll_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = plc.read(tag)
        value = getattr(result, "value", result)
        if not value:
            return True
        time.sleep(poll_s)
    return False


def _open_driver(path: str):  # pragma: no cover - requires hardware/pycomm3
    try:
        from pycomm3 import LogixDriver
    except ImportError as exc:
        raise ImportError(
            "pycomm3 is required for PLC output. Install with `pip install pycomm3`."
        ) from exc
    driver = LogixDriver(path)
    driver.open()
    return driver


def _close_driver(plc) -> None:  # pragma: no cover - requires hardware/pycomm3
    close = getattr(plc, "close", None)
    if callable(close):
        close()
