#!/usr/bin/env python3
"""Generate a printable circle test target for TerminalTorque.

The target has two purposes:

* **Detection testing** -- a set of non-overlapping filled circles of known
  diameters at jittered positions, each labelled with its diameter.
* **Known-size calibration** -- two crosshair fiducials (A, B) an exact
  center-to-center distance apart for point-to-point (click-to-measure)
  calibration, plus a 50 mm print-scale check. Every circle's center is also
  listed (mm from the datum) so detected coordinates can be checked.

Print at 100% (Actual size, no scaling). Defaults: US Letter portrait.

Usage:
    python tools/make_test_target.py
    python tools/make_test_target.py --baseline-mm 120 --count 16 --seed 3
"""

from __future__ import annotations

import argparse
import random

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAPERS = {"letter": letter, "a4": A4}
DIAMETERS_MM = [8, 10, 12, 15, 18, 22, 26]   # menu of known circle sizes


def _crosshair(c, x, y, label):
    """Draw a fine '+' fiducial with a center dot at (x, y) points."""
    arm = 5 * mm
    c.setLineWidth(0.6)
    c.line(x - arm, y, x - 1.2 * mm, y)
    c.line(x + 1.2 * mm, y, x + arm, y)
    c.line(x, y - arm, x, y - 1.2 * mm)
    c.line(x, y + 1.2 * mm, x, y + arm)
    c.circle(x, y, 0.4 * mm, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + arm + 1 * mm, y - 1.5 * mm, label)


def make_target(path: str, paper: str = "letter", baseline_mm: float = 150.0,
                count: int = 14, seed: int = 7) -> None:
    rng = random.Random(seed)
    pw, ph = PAPERS[paper]              # portrait
    c = canvas.Canvas(path, pagesize=(pw, ph))

    def top(mx, my):
        """Top-left mm coords -> reportlab points (origin bottom-left)."""
        return mx * mm, ph - my * mm

    # --- title + print-scale check ---
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(pw / 2, ph - 14 * mm, "TerminalTorque circle test target")
    c.setFont("Helvetica", 9)
    c.drawCentredString(pw / 2, ph - 19 * mm,
                        f"Print at 100% (Actual size, no scaling), {paper.upper()} "
                        f"portrait.  Datum is the lower-left '+'.")
    vx, vy = top((pw / mm - 50) / 2, 26)
    c.setLineWidth(1)
    c.line(vx, vy, vx + 50 * mm, vy)
    c.line(vx, vy - 3, vx, vy + 3)
    c.line(vx + 50 * mm, vy - 3, vx + 50 * mm, vy + 3)
    c.setFont("Helvetica", 8)
    c.drawCentredString(pw / 2, vy + 4, "verify print scale: this line = 50 mm")

    # --- calibration baseline (two fiducials, exact center-to-center) ---
    base_y = 40.0
    ax = (pw / mm - baseline_mm) / 2.0
    c.setFont("Helvetica-Bold", 10)
    _crosshair(c, *top(ax, base_y), "A")
    _crosshair(c, *top(ax + baseline_mm, base_y), "B")
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(pw / 2, (ph - base_y * mm) - 9 * mm,
                        f"Calibration baseline  A-B = {baseline_mm:.1f} mm "
                        f"(center to center)")

    # --- datum ---
    datum = (18.0, 70.0)               # mm from page top-left
    _crosshair(c, *top(*datum), "datum (0,0)")

    # --- random non-overlapping circles ---
    area = dict(x0=26.0, x1=pw / mm - 12.0, y0=80.0, y1=ph / mm - 78.0)
    placed = []   # (mx, my, d)
    attempts = 0
    while len(placed) < count and attempts < 5000:
        attempts += 1
        d = rng.choice(DIAMETERS_MM)
        r = d / 2.0
        mx = rng.uniform(area["x0"] + r, area["x1"] - r)
        my = rng.uniform(area["y0"] + r, area["y1"] - r)
        ok = all((mx - px) ** 2 + (my - py) ** 2 > (r + pd / 2 + 9) ** 2
                 for px, py, pd in placed)
        if ok:
            placed.append((mx, my, d))

    c.setFillColorRGB(0, 0, 0)
    for mx, my, d in placed:
        x, y = top(mx, my)
        c.circle(x, y, (d / 2.0) * mm, stroke=0, fill=1)
        c.setFont("Helvetica", 7)
        c.drawString(x + (d / 2.0) * mm + 1.2 * mm, y - 1.2 * mm, f"Ø{d:g}")

    # --- ground-truth table (centers relative to datum, x right / y down) ---
    rows = [(i + 1, mx - datum[0], my - datum[1], d)
            for i, (mx, my, d) in enumerate(placed)]
    c.setFont("Helvetica-Bold", 8)
    ty = 70.0  # mm from bottom upward region; place near bottom margin
    base = 70.0
    c.drawString(*top(14, ph / mm - 64),
                 "Ground truth (center mm from datum, x right / y down):")
    c.setFont("Helvetica", 7.5)
    per_col = (len(rows) + 1) // 2
    for k, (idx, dx, dy, d) in enumerate(rows):
        col = k // per_col
        line = k % per_col
        mx = 14 + col * 100
        my = ph / mm - 60 + line * 4.6
        c.drawString(*top(mx, my),
                     f"#{idx:<2d}  x={dx:6.1f}  y={dy:6.1f}  Ø{d:g} mm")

    c.showPage()
    c.save()
    return placed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="docs/circle_test_target_letter.pdf")
    p.add_argument("--paper", choices=list(PAPERS), default="letter")
    p.add_argument("--baseline-mm", type=float, default=150.0)
    p.add_argument("--count", type=int, default=14)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    placed = make_target(args.out, args.paper, args.baseline_mm, args.count, args.seed)
    print(f"Wrote {args.out} with {len(placed)} circles")


if __name__ == "__main__":
    main()
