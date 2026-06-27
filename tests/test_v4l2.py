"""Parser tests using real `v4l2-ctl` output from the operator's camera."""

from terminaltorque.gui.v4l2 import (
    AUTO_EXPOSURE_AUTO,
    AUTO_EXPOSURE_MANUAL,
    parse_controls,
    parse_formats,
)

LIST_CTRLS = """
User Controls

                     brightness 0x00980900 (int)    : min=-64 max=64 step=1 default=0 value=0
                       contrast 0x00980901 (int)    : min=0 max=95 step=1 default=3 value=95
                     saturation 0x00980902 (int)    : min=0 max=100 step=1 default=64 value=100
                            hue 0x00980903 (int)    : min=-2000 max=2000 step=1 default=0 value=0
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1
                          gamma 0x00980910 (int)    : min=100 max=300 step=1 default=100 value=100
           power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=1 value=1 (50 Hz)
      white_balance_temperature 0x0098091a (int)    : min=2800 max=6500 step=1 default=4600 value=4600 flags=inactive
                      sharpness 0x0098091b (int)    : min=1 max=7 step=1 default=2 value=2
         backlight_compensation 0x0098091c (int)    : min=0 max=1 step=1 default=1 value=1

Camera Controls

                  auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=1 (Manual Mode)
         exposure_time_absolute 0x009a0902 (int)    : min=3 max=2047 step=1 default=166 value=2047
"""

LIST_FORMATS = """
ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 2592x1944
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.200s (5.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
"""


def test_parse_controls_ranges():
    ctrls = parse_controls(LIST_CTRLS)
    assert ctrls["brightness"].minimum == -64
    assert ctrls["brightness"].maximum == 64
    assert ctrls["contrast"].maximum == 95
    assert ctrls["hue"].minimum == -2000 and ctrls["hue"].maximum == 2000
    # No 'gain' control exists on this camera -- the old nominal slider was wrong.
    assert "gain" not in ctrls


def test_parse_controls_types_and_flags():
    ctrls = parse_controls(LIST_CTRLS)
    assert ctrls["white_balance_automatic"].type == "bool"
    assert ctrls["auto_exposure"].type == "menu"
    # auto_exposure is currently Manual (value=1) -> the dark-image culprit.
    assert ctrls["auto_exposure"].value == AUTO_EXPOSURE_MANUAL
    assert ctrls["auto_exposure"].maximum == AUTO_EXPOSURE_AUTO
    # WB temperature is inactive while auto WB is on.
    assert ctrls["white_balance_temperature"].inactive is True
    assert ctrls["exposure_time_absolute"].maximum == 2047


def test_parse_formats_real_modes():
    modes = parse_formats(LIST_FORMATS)
    pairs = {(m.width, m.height, m.fourcc): m.fps for m in modes}
    assert pairs[(1920, 1080, "MJPG")] == 30.0
    assert pairs[(2592, 1944, "MJPG")] == 30.0
    assert pairs[(640, 480, "MJPG")] == 30.0
    assert pairs[(1920, 1080, "YUYV")] == 5.0


def test_parse_formats_prefers_mjpg_and_largest_first():
    modes = parse_formats(LIST_FORMATS)
    # MJPG modes sort ahead of YUYV; largest area first.
    assert modes[0].fourcc == "MJPG"
    assert (modes[0].width, modes[0].height) == (2592, 1944)
    mjpg = [m for m in modes if m.fourcc == "MJPG"]
    assert [(m.width, m.height) for m in mjpg] == \
        sorted(((m.width, m.height) for m in mjpg), key=lambda s: -s[0] * s[1])
