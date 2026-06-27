#!/usr/bin/env python3
"""Generate a camera-calibration checkerboard PDF sized for a sheet of paper.

The defaults match the HMI Lens tab: 9x6 inner corners (a 10x7-square board)
with 25 mm squares, laid out landscape on US Letter with a generous white quiet
zone (chessboard detection needs the border). A 50 mm reference line lets you
confirm the print came out at true scale.

Usage:
    python tools/make_checkerboard.py                 # default Letter board
    python tools/make_checkerboard.py --square-mm 20 --inner-cols 7 --inner-rows 5
"""

from __future__ import annotations

import argparse

from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


PAPERS = {"letter": letter, "a4": A4}


def make_checkerboard(path: str, inner_cols: int = 9, inner_rows: int = 6,
                      square_mm: float = 25.0, paper: str = "letter") -> None:
    cols, rows = inner_cols + 1, inner_rows + 1          # squares
    page = landscape(PAPERS[paper])
    pw, ph = page
    sq = square_mm * mm
    board_w, board_h = cols * sq, rows * sq
    if board_w > pw or board_h > ph:
        raise SystemExit(
            f"Board {cols}x{rows} squares @ {square_mm} mm is too big for "
            f"{paper} landscape. Reduce the square size or corner count.")

    x0 = (pw - board_w) / 2.0
    y0 = (ph - board_h) / 2.0

    c = canvas.Canvas(path, pagesize=page)

    # Checkerboard (black squares on the white page).
    c.setFillColorRGB(0, 0, 0)
    for r in range(rows):
        for col in range(cols):
            if (r + col) % 2 == 0:
                c.rect(x0 + col * sq, y0 + r * sq, sq, sq, stroke=0, fill=1)

    # Caption in the bottom quiet zone.
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(
        pw / 2, y0 / 2 + 6,
        f"Camera calibration checkerboard  -  {inner_cols} x {inner_rows} "
        f"inner corners ({cols} x {rows} squares)  -  {square_mm:g} mm squares")
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        pw / 2, y0 / 2 - 8,
        f"Print at 100% (Actual size, no scaling), {paper.upper()} landscape.  "
        f"In the Lens tab set inner corners = {inner_cols} x {inner_rows} and "
        f"square size = {square_mm:g} mm.")

    # 50 mm verification line in the top quiet zone.
    vlen = 50 * mm
    vx = (pw - vlen) / 2.0
    vy = (y0 + board_h + ph) / 2.0
    c.setLineWidth(1)
    c.line(vx, vy, vx + vlen, vy)
    c.line(vx, vy - 3, vx, vy + 3)
    c.line(vx + vlen, vy - 3, vx + vlen, vy + 3)
    c.setFont("Helvetica", 8)
    c.drawCentredString(pw / 2, vy + 5, "verify print scale: this line should measure 50 mm")

    c.showPage()
    c.save()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="docs/checkerboard_9x6_25mm_letter.pdf")
    p.add_argument("--inner-cols", type=int, default=9)
    p.add_argument("--inner-rows", type=int, default=6)
    p.add_argument("--square-mm", type=float, default=25.0)
    p.add_argument("--paper", choices=list(PAPERS), default="letter")
    args = p.parse_args()
    make_checkerboard(args.out, args.inner_cols, args.inner_rows,
                      args.square_mm, args.paper)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
