# TerminalTorque

Vision-based detection of **circular terminal wells on a battery lid**. Given a
camera image of the lid, TerminalTorque reports each well's **center** and
**diameter** — in pixels, and in real-world **millimeters** once calibrated — so
a robot can position over each terminal and torque the nut.

![demo detection](docs/demo_annotated.png)

## How it works

1. **Grayscale + blur** to suppress sensor noise.
2. **Hough gradient circle transform** (`cv2.HoughCircles`) finds candidate
   circles. It is robust to uneven lighting and partial occlusion and is the
   standard tool for circular-feature detection.
3. **Sub-pixel center refinement.** The raw Hough center is only accurate to
   ~1 px, which can be a millimeter or more of robot error. Each candidate is
   refined to the intensity-weighted centroid of its edge ring, tightening
   repeatability to a fraction of a pixel on a clean machined well.
4. **Calibration** maps pixel centers and diameters to millimeters in the
   robot's work plane.

## Install

```bash
pip install -r requirements.txt        # runtime (numpy + opencv)
pip install -e ".[dev]"                # editable install + pytest
```

## Quick start

Try it with no hardware using the built-in synthetic lid:

```bash
python -m terminaltorque --demo --min-radius 25 --max-radius 70 --expected 2 \
    --mm-per-px 0.1429 --annotate out/demo_annotated.png
```

Detect on a saved photo and keep only the two strongest wells:

```bash
python -m terminaltorque --image lid.png --expected 2
```

Grab a frame from a camera and report results in millimeters:

```bash
python -m terminaltorque --camera 0 --calibration cal.json
```

### Output

JSON to stdout (or `--output file.json`), ready for the robot controller:

```json
{
  "image_size": { "width": 640, "height": 480 },
  "calibrated": true,
  "count": 2,
  "wells": [
    {
      "center_px": [448.22, 239.93],
      "diameter_px": 79.52,
      "confidence": 1.0,
      "refined": true,
      "center_mm": [18.39, -0.06],
      "diameter_mm": 11.36
    }
  ]
}
```

Wells are sorted strongest-first. The process exits `0` when at least one well
is found and `2` when none are, so the robot side can branch on the exit code.

## Calibration

For a flat lid imaged roughly perpendicular to the camera at a fixed working
distance, a single **millimeters-per-pixel** scale plus an origin offset maps
image pixels to the robot plane.

Measure the pixel size of a feature whose true size you know (e.g. a gauge or a
terminal of known machined diameter) and save a reusable calibration:

```bash
python -m terminaltorque --image lid.png \
    --set-scale-from-px 84 --known-mm 12.0 \
    --save-calibration cal.json
```

`cal.json` stores `mm_per_px`, the pixel `origin` that maps to robot `(0, 0)`
(defaults to the image's optical center), and `invert_y` (default `true`, since
image rows increase downward while robot Y usually increases upward). Edit the
origin to a fiducial you have taught the robot, or set it directly in code via
`Calibration`.

> The scalar-scale model assumes a fronto-parallel lid and negligible lens
> distortion. For a tilted lid, wide-angle lens, or large field of view, replace
> it with a homography or a full `cv2.calibrateCamera` intrinsics + pose
> estimate. The detector returns pixel geometry either way; only the
> pixel→world step changes.

## Library use

```python
from terminaltorque import detect_terminal_wells, DetectionParams, Calibration
from terminaltorque.io_utils import load_image

image = load_image("lid.png")
cal = Calibration.load("cal.json")
params = DetectionParams(min_radius_px=30, max_radius_px=60, expected_count=2)

for well in detect_terminal_wells(image, params, calibration=cal):
    x_mm, y_mm = well.center_mm
    print(f"terminal at ({x_mm:.2f}, {y_mm:.2f}) mm, "
          f"diameter {well.diameter_mm:.2f} mm")
```

## Tuning

The most important parameter is the **radius range** (`--min-radius` /
`--max-radius`): set it to your physical well size in pixels to reject spurious
circles from bolt heads, text, or reflections. Then:

- Missing wells → lower `--accumulator`.
- False circles → raise `--accumulator`, tighten the radius range, or set
  `--expected N` to keep only the strongest N.

## Tests

```bash
pytest
```

Tests run entirely on synthetic lids (no camera needed) and assert detection
count, center accuracy, diameter accuracy, and calibration math.

## Project layout

| File | Purpose |
|------|---------|
| `terminaltorque/detector.py` | Hough detection + sub-pixel refinement |
| `terminaltorque/calibration.py` | Pixel ↔ millimeter mapping |
| `terminaltorque/io_utils.py` | Load image / grab camera frame |
| `terminaltorque/synthetic.py` | Synthetic lid generator for demos & tests |
| `terminaltorque/cli.py` | Command-line interface |
