"""Command-line interface for terminal-well detection.

Examples:
    # Detect on a saved image, print JSON the robot can consume:
    python -m terminaltorque --image lid.png --expected 2

    # Grab from camera 0 and apply a saved calibration (results in mm):
    python -m terminaltorque --camera 0 --calibration cal.json

    # Calibrate mm/px from a feature of known size, save it for reuse:
    python -m terminaltorque --image lid.png --set-scale-from-px 84 \\
        --known-mm 12.0 --save-calibration cal.json

    # Write an annotated debug image:
    python -m terminaltorque --image lid.png --annotate out.png
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .detector import DetectionParams, TerminalWell, detect_terminal_wells, draw_detections
from .calibration import Calibration, default_origin
from . import io_utils


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="terminaltorque",
        description="Detect circular battery terminal wells; report center & diameter.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="Path to an input image.")
    src.add_argument("--camera", type=int, help="Camera device index to capture from.")
    src.add_argument("--demo", action="store_true",
                     help="Run on a built-in synthetic lid image.")

    # Detection tuning
    p.add_argument("--min-radius", type=int, default=10, help="Min well radius (px).")
    p.add_argument("--max-radius", type=int, default=200, help="Max well radius (px).")
    p.add_argument("--min-dist", type=float, default=None,
                   help="Min distance between centers (px).")
    p.add_argument("--accumulator", type=float, default=30.0,
                   help="Hough accumulator threshold (lower = more circles).")
    p.add_argument("--expected", type=int, default=None,
                   help="Keep only the strongest N wells.")

    # Calibration
    p.add_argument("--calibration", help="Load a calibration JSON (results in mm).")
    p.add_argument("--mm-per-px", type=float, default=None,
                   help="Set scale directly (mm per pixel).")
    p.add_argument("--set-scale-from-px", type=float, default=None,
                   help="Reference length in pixels (with --known-mm).")
    p.add_argument("--known-mm", type=float, default=None,
                   help="True length in mm of the reference (with --set-scale-from-px).")
    p.add_argument("--save-calibration", help="Write the active calibration to JSON.")

    # Output
    p.add_argument("--annotate", help="Write an annotated debug image to this path.")
    p.add_argument("--output", help="Write result JSON to this path (default stdout).")

    # Allen-Bradley PLC push (EtherNet/IP via pycomm3)
    plc = p.add_argument_group("Allen-Bradley PLC push")
    plc.add_argument("--plc-ip", help="PLC IP address; enables pushing results.")
    plc.add_argument("--plc-slot", type=int, default=None,
                     help="Processor slot for ControlLogix (omit for CompactLogix).")
    plc.add_argument("--plc-prefix", default="Vision",
                     help="Tag name prefix, e.g. Vision -> Vision_X[i] (default: Vision).")
    plc.add_argument("--plc-max-wells", type=int, default=8,
                     help="Size of the PLC result arrays (default: 8).")
    plc.add_argument("--plc-wait-ack", action="store_true",
                     help="Block until the PLC clears the DataReady bit.")
    plc.add_argument("--plc-ack-timeout", type=float, default=5.0,
                     help="Seconds to wait for the PLC ack (default: 5).")
    return p


def _resolve_calibration(args, image_shape) -> Optional[Calibration]:
    if args.calibration:
        return Calibration.load(args.calibration)
    ou, ov = default_origin(image_shape)
    if args.mm_per_px is not None:
        return Calibration(mm_per_px=args.mm_per_px, origin_u=ou, origin_v=ov)
    if args.set_scale_from_px is not None:
        if args.known_mm is None:
            raise SystemExit("--set-scale-from-px requires --known-mm")
        return Calibration.from_known_length(
            pixels=args.set_scale_from_px, millimeters=args.known_mm,
            origin_u=ou, origin_v=ov,
        )
    return None


def _load_source(args):
    if args.image:
        return io_utils.load_image(args.image)
    if args.camera is not None:
        return io_utils.grab_frame(args.camera)
    # demo
    from .synthetic import make_lid_image
    image, _ = make_lid_image()
    return image


def _push_plc(args, wells) -> dict:
    from .plc import PlcConfig, push_to_plc

    config = PlcConfig.from_ip(
        ip=args.plc_ip,
        slot=args.plc_slot,
        prefix=args.plc_prefix,
        max_wells=args.plc_max_wells,
    )
    return push_to_plc(
        wells,
        config,
        wait_for_ack=args.plc_wait_ack,
        ack_timeout_s=args.plc_ack_timeout,
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    image = _load_source(args)
    calibration = _resolve_calibration(args, image.shape)

    if args.save_calibration:
        if calibration is None:
            raise SystemExit("Nothing to save: provide a calibration or scale option.")
        calibration.save(args.save_calibration)

    params = DetectionParams(
        min_radius_px=args.min_radius,
        max_radius_px=args.max_radius,
        min_dist_px=args.min_dist,
        accumulator_threshold=args.accumulator,
        expected_count=args.expected,
    )
    wells = detect_terminal_wells(image, params, calibration)

    if args.annotate:
        io_utils.save_image(args.annotate, draw_detections(image, wells))

    plc_status = None
    plc_error = None
    if args.plc_ip:
        if calibration is None:
            print(
                "warning: pushing to PLC without calibration; X/Y/diameter are "
                "in PIXELS, not millimeters. Provide --calibration or a scale.",
                file=sys.stderr,
            )
        try:
            plc_status = _push_plc(args, wells)
        except Exception as exc:  # noqa: BLE001 - report any push failure cleanly
            plc_error = f"{type(exc).__name__}: {exc}"
            print(f"error: PLC push failed: {plc_error}", file=sys.stderr)

    result = {
        "image_size": {"width": image.shape[1], "height": image.shape[0]},
        "calibrated": calibration is not None,
        "count": len(wells),
        "wells": [w.to_dict() for w in wells],
    }
    if plc_status is not None:
        result["plc"] = plc_status
    elif plc_error is not None:
        result["plc"] = {"error": plc_error}
    payload = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    else:
        print(payload)

    # Exit codes let the operator/robot side branch:
    #   0 = wells found (and PLC push succeeded, if requested)
    #   2 = no wells detected
    #   3 = wells detected but the PLC push failed
    if not wells:
        return 2
    if plc_error is not None:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
