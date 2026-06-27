import pytest

from terminaltorque.detector import TerminalWell
from terminaltorque.plc import PlcConfig, build_writes, push_to_plc


class FakePlc:
    """Records writes and serves scripted reads, mimicking pycomm3's driver."""

    def __init__(self, read_sequence=None):
        self.writes = []          # flat list of (tag, value) in call order
        self.write_calls = []     # one entry per write() call (a list of tuples)
        self.closed = False
        self._reads = list(read_sequence or [])

    def write(self, *tags):
        self.write_calls.append(list(tags))
        self.writes.extend(tags)
        return True

    def read(self, tag):
        # Pop until one remains, then hold the last value (a real PLC keeps
        # returning the current tag state, it does not run "empty").
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0] if self._reads else False

    def close(self):
        self.closed = True

    def as_dict(self):
        return dict(self.writes)


def _well(x, y, dia):
    return TerminalWell(center_px=(0, 0), diameter_px=dia, confidence=1.0,
                        center_mm=(x, y), diameter_mm=dia)


def test_from_ip_builds_paths_and_tags():
    c = PlcConfig.from_ip("10.0.0.5", slot=0, prefix="Cell1", max_wells=4)
    assert c.path == "10.0.0.5/0"
    assert c.x_tag == "Cell1_X[{i}]"
    assert c.count_tag == "Cell1_Count"

    c2 = PlcConfig.from_ip("10.0.0.5")  # CompactLogix, no slot
    assert c2.path == "10.0.0.5"


def test_build_writes_pads_and_marks_invalid():
    config = PlcConfig.from_ip("1.2.3.4", max_wells=3)
    wells = [_well(10.0, 20.0, 12.0)]
    writes = dict(build_writes(wells, config))

    assert writes["Vision_Count"] == 1
    assert writes["Vision_X[0]"] == 10.0
    assert writes["Vision_Y[0]"] == 20.0
    assert writes["Vision_Dia[0]"] == 12.0
    assert writes["Vision_Valid[0]"] is True
    # Unused slots zeroed and invalid -> no stale geometry.
    assert writes["Vision_Valid[1]"] is False
    assert writes["Vision_X[1]"] == 0.0
    assert writes["Vision_Valid[2]"] is False


def test_push_sets_handshake_after_data():
    config = PlcConfig.from_ip("1.2.3.4", max_wells=2)
    plc = FakePlc()
    status = push_to_plc([_well(1, 2, 3)], config, plc=plc)

    assert status == {"written": 1, "handshake_set": True, "acked": False}
    # DataReady cleared first, set last; data written in between.
    assert plc.writes[0] == ("Vision_DataReady", False)
    assert plc.writes[-1] == ("Vision_DataReady", True)


def test_push_caps_to_max_wells():
    config = PlcConfig.from_ip("1.2.3.4", max_wells=2)
    plc = FakePlc()
    wells = [_well(i, i, 5) for i in range(5)]
    status = push_to_plc(wells, config, plc=plc)
    assert status["written"] == 2


def test_wait_for_ack_succeeds_when_plc_clears_bit():
    config = PlcConfig.from_ip("1.2.3.4", max_wells=1)
    plc = FakePlc(read_sequence=[True, False])  # cleared on 2nd poll
    status = push_to_plc([_well(1, 2, 3)], config, plc=plc,
                         wait_for_ack=True, ack_timeout_s=1.0,
                         poll_interval_s=0.0)
    assert status["acked"] is True


def test_wait_for_ack_times_out():
    config = PlcConfig.from_ip("1.2.3.4", max_wells=1)
    plc = FakePlc(read_sequence=[True, True, True])
    status = push_to_plc([_well(1, 2, 3)], config, plc=plc,
                         wait_for_ack=True, ack_timeout_s=0.05,
                         poll_interval_s=0.0)
    assert status["acked"] is False


def test_uncalibrated_well_pushes_pixels():
    config = PlcConfig.from_ip("1.2.3.4", max_wells=1)
    well = TerminalWell(center_px=(100, 200), diameter_px=40, confidence=1.0)
    writes = dict(build_writes([well], config))
    assert writes["Vision_X[0]"] == 100.0
    assert writes["Vision_Dia[0]"] == 40.0
