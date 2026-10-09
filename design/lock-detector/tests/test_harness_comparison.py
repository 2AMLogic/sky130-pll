"""Executable comparison: proposed hardware LOCK (DR-007) vs. the harness lock.

The harness criterion is `sim/harness/measure.py::lock_time` parameterised by
`sim/pll-lock/testbench/tb.json`'s `measure.lock` block. This file imports both
read-only; it changes neither. The two criteria answer different questions
(DR-007, "Relationship to the harness lock criterion"), and these cases show
where they agree and where they must not be conflated:

- agreement: an ideally locked loop is locked by both, and the harness lock
  instant precedes the hardware assertion (which needs 32 REF cycles);
- disagreement A: CLK 1 % off target is "locked" for the harness (inside
  +/-5 %) but the REF/FBCLK phase walks 1 ns per REF cycle, so LOCK never
  asserts;
- disagreement B: CLK on target but FBCLK silent (a divider dropout): the
  harness only looks at CLK, so it reports lock; LOCK never asserts.

The harness flag is therefore never a stand-in for hardware LOCK.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(REPO / "sim"))

from harness import measure  # noqa: E402
from lockdet_ref import Stimulus, ref_clock, simulate  # noqa: E402

TB_JSON = REPO / "sim" / "pll-lock" / "testbench" / "tb.json"
NS = 1_000
N = 25
T_REF = 100 * NS          # 10 MHz, the tb.json operating point (N=25 -> 250 MHz)
T_END = 20_000 * NS


def harness_spec():
    block = json.loads(TB_JSON.read_text())["measure"]["lock"]
    return measure.LockSpec(**block)


def clk_edges(freq_hz):
    """Integer-ps CLK rising edges from t=100 ns at `freq_hz` up to T_END."""
    edges, k = [], 0
    while True:
        t = 100 * NS + round(k * 1e12 / freq_hz)
        if t > T_END:
            return edges
        edges.append(t)
        k += 1


def both(clk, fb):
    rr, rf = ref_clock(100 * NS, T_REF, (T_END - 100 * NS) // T_REF)
    hw = simulate(Stimulus(rr, rf, tuple(fb), t_end_ps=T_END, resetb=((0, 0), (50 * NS, 1))))
    locked, t_lock = measure.lock_time([t * 1e-12 for t in clk], harness_spec())
    return hw, locked, t_lock


class HarnessBaseline(unittest.TestCase):
    def test_tb_json_lock_block_is_the_documented_baseline(self):
        # DR-007 quotes these numbers; if tb.json changes, the comparison
        # section of DR-007 must be revisited (a new DR, never an edit to a
        # ratified record).
        spec = harness_spec()
        self.assertEqual(spec.target_hz, 250_000_000)
        self.assertEqual(spec.tolerance_frac, 0.05)
        self.assertEqual(spec.window_cycles, 20)
        self.assertEqual(spec.min_hold_cycles, 20)


class Comparison(unittest.TestCase):
    def test_agreement_ideal_lock(self):
        clk = clk_edges(250e6)
        fb = clk[::N]                      # ideal divide-by-25: FBCLK == REF grid
        hw, locked, t_lock = both(clk, fb)
        self.assertTrue(locked)
        self.assertEqual(hw.final_lock, 1)
        self.assertEqual([tr.t_ps for tr in hw.transitions], [3_350_000])
        # Harness lock instant (first CLK edge, 100 ns) precedes LOCK.
        self.assertAlmostEqual(t_lock, 100e-9, places=15)
        self.assertLess(t_lock * 1e12, hw.transitions[0].t_ps)

    def test_disagreement_small_frequency_error(self):
        clk = clk_edges(252.5e6)           # +1 %: inside the harness +/-5 % band
        fb = clk[::N]
        hw, locked, _ = both(clk, fb)
        self.assertTrue(locked)
        self.assertEqual(hw.transitions, [])

    def test_disagreement_silent_fbclk(self):
        clk = clk_edges(250e6)
        hw, locked, _ = both(clk, fb=())
        self.assertTrue(locked)
        self.assertEqual(hw.transitions, [])


if __name__ == "__main__":
    unittest.main()
