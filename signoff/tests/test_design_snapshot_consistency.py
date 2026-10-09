#!/usr/bin/env python3
"""Unit tests for signoff/design-snapshot-consistency.py (PDK-free, xschem-free)."""

import importlib.util
import pathlib
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_spec = importlib.util.spec_from_file_location(
    "design_snapshot_consistency", _ROOT / "signoff" / "design-snapshot-consistency.py"
)
dsc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dsc)

STANDALONE = """\
** sch_path: /a/b/design/loop-filter/loop_filter.sch
**.subckt loop_filter CP GND VCTRL
*.ipin CP
XR1 Z1 CP GND sky130_fd_pr__res_xhigh_po W=1 L=2.53 mult=1 m=1
XC1 Z1 GND sky130_fd_pr__cap_mim_m3_1 W=322 L=322
+ MF=1 m=1
**.ends
.end
"""

TOP = """\
** sch_path: /x/design/top/top.sch
**.subckt top VDD GND
**.ends

* expanding   symbol:  design/loop-filter/loop_filter.sym # of pins=3
** sch_path: /other/worktree/design/loop-filter/loop_filter.sch
.subckt loop_filter CP GND VCTRL
*.ipin CP
XR1 Z1 CP GND sky130_fd_pr__res_xhigh_po W=1.0 L=2.53 mult=1 m=1
XC1   Z1 GND sky130_fd_pr__cap_mim_m3_1  W=322 L=322 MF=1
+ m=1
.ends
.end
"""


def run(top=TOP, standalone=STANDALONE):
    return dsc.check(top, {"loop_filter": standalone})


class TestConsistency(unittest.TestCase):
    def test_agreeing_copies_pass_despite_paths_and_formatting(self):
        self.assertEqual(run(), [])

    def test_stale_capacitor_size_fails_with_block_and_device(self):
        stale = TOP.replace("W=322 L=322", "W=163 L=163")
        diags = run(top=stale)
        self.assertTrue(any("loop_filter/XC1: parameter w" in d for d in diags), diags)
        self.assertTrue(any("loop_filter/XC1: parameter l" in d for d in diags), diags)

    def test_stale_value_in_standalone_only_fails(self):
        diags = run(standalone=STANDALONE.replace("L=2.53", "L=10.3"))
        self.assertTrue(any("loop_filter/XR1: parameter l" in d for d in diags), diags)

    def test_connection_change_fails(self):
        diags = run(top=TOP.replace("XC1   Z1 GND", "XC1   Z1 CP"))
        self.assertTrue(any("loop_filter/XC1: connections" in d for d in diags), diags)

    def test_model_change_fails(self):
        diags = run(top=TOP.replace("res_xhigh_po", "res_high_po"))
        self.assertTrue(any("loop_filter/XR1: connections/model" in d for d in diags), diags)

    def test_pin_order_change_fails(self):
        diags = run(top=TOP.replace("loop_filter CP GND VCTRL", "loop_filter GND CP VCTRL"))
        self.assertTrue(any("pin list differs" in d for d in diags), diags)

    def test_missing_embedded_definition_fails(self):
        top = TOP.split("* expanding")[0]
        diags = run(top=top)
        self.assertTrue(any("loop_filter: no embedded definition" in d for d in diags), diags)

    def test_duplicate_embedded_definition_fails(self):
        block = TOP.split("* expanding")[1]
        diags = run(top=TOP + "* expanding" + block)
        self.assertTrue(any("duplicate embedded definitions" in d for d in diags), diags)

    def test_missing_device_fails(self):
        top = "\n".join(l for l in TOP.splitlines() if not l.startswith("XR1")) + "\n"
        diags = run(top=top)
        self.assertTrue(any("loop_filter/XR1" in d and "missing from top" in d for d in diags), diags)

    def test_unclosed_subckt_fails(self):
        diags = run(top=TOP.replace("\n.ends\n.end", "\n.end"))
        self.assertTrue(any("never closed" in d for d in diags), diags)


class TestCommittedSnapshots(unittest.TestCase):
    def test_repo_snapshots_agree(self):
        self.assertEqual(dsc.main(["--repo-root", str(_ROOT)]), 0)


if __name__ == "__main__":
    unittest.main()
