#!/usr/bin/env python3
"""Unit tests for sim/vco-supply-pushing/analysis/pushing.py.

No PDK, ngspice or xschem required: every test below drives the parsing/
derivation functions from a synthetic **Swept-axis measurements** markdown
table it builds itself, so the arithmetic is checked against numbers whose
true `%/V` slope is known by construction, not read back out of a real
record. `RenderRoundTripTests` covers the `--append`/`--check` CLI paths
end-to-end against a scratch file, mirroring how `sim/run_corners.py` mints
and later verifies the derived section.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUSHING_PATH = REPO_ROOT / "sim" / "vco-supply-pushing" / "analysis" / "pushing.py"

# sim/vco-supply-pushing/analysis/ is not an importable package (the slug
# directory name has hyphens, which are not valid in a Python package path),
# so the module is loaded directly from its file path -- the same pattern
# sim/run_corners.py itself uses to reach sim/harness without an installed
# package.
_spec = importlib.util.spec_from_file_location("pushing", PUSHING_PATH)
pushing = importlib.util.module_from_spec(_spec)
sys.modules["pushing"] = pushing
_spec.loader.exec_module(pushing)  # type: ignore[union-attr]


def swept_table(rows: list[tuple]) -> str:
    """Build a minimal record body carrying just the `Swept-axis
    measurements` section `parse_swept_table` reads.

    Each row is `(corner, temp_c, supply_v, vctrl_v, freq_text, note)`.
    """
    lines = [
        "- **Swept-axis measurements** (VCTRL vs. output frequency, per PVT point):",
        "",
        "  | Corner | Temp (C) | Supply (V) | VCTRL (V) | f_out | Duty | Note |",
        "  |---|---|---|---|---|---|---|",
    ]
    for corner, temp_c, supply_v, vctrl_v, freq_text, note in rows:
        lines.append(
            f"  | {corner} | {temp_c:g} | {supply_v:.2f} | {vctrl_v:.3f} | "
            f"{freq_text} | 50.0% | {note} |"
        )
    lines.append("")
    lines.append("- **Per-point tuning summary** (endpoint-to-endpoint slope over the swept VCTRL range):")
    lines.append("")
    return "\n".join(lines) + "\n"


class ParseHzTests(unittest.TestCase):
    def test_parses_units(self):
        self.assertAlmostEqual(pushing.parse_hz("318.1 MHz"), 318.1e6)
        self.assertAlmostEqual(pushing.parse_hz("1.8 GHz"), 1.8e9)
        self.assertAlmostEqual(pushing.parse_hz("500 kHz"), 500e3)
        self.assertAlmostEqual(pushing.parse_hz("12 Hz"), 12.0)

    def test_dash_is_no_measurement(self):
        self.assertIsNone(pushing.parse_hz("-"))
        self.assertIsNone(pushing.parse_hz(""))

    def test_rejects_garbage(self):
        with self.assertRaises(pushing.AnalysisError):
            pushing.parse_hz("not a frequency")
        with self.assertRaises(pushing.AnalysisError):
            pushing.parse_hz("12 Foo")


class FloorTests(unittest.TestCase):
    def test_floor_is_1_over_vdd(self):
        # DR-006: 1/VDD, i.e. 55.6 %/V at 1.80 V.
        self.assertAlmostEqual(pushing.floor_pct_per_v(1.8), 100.0 / 1.8)
        self.assertAlmostEqual(pushing.floor_pct_per_v(1.8), 55.555555, places=4)
        # Scales with the rail: a lower rail has a higher floor.
        self.assertGreater(pushing.floor_pct_per_v(1.62), pushing.floor_pct_per_v(1.98))


class FractionalSlopeTests(unittest.TestCase):
    def test_known_doubling_slope(self):
        # f doubles (100 MHz -> 200 MHz) as V goes 1.0 -> 2.0: mean f is
        # 150 MHz, delta f is 100 MHz over delta V 1.0 -> 100/150/1.0 = 66.7%/V.
        slope, rail = pushing._fractional_slope(100e6, 200e6, 1.0, 2.0)
        self.assertAlmostEqual(slope, 100.0 * 100e6 / 150e6 / 1.0)
        self.assertAlmostEqual(rail, 1.5)

    def test_flat_frequency_is_zero_slope(self):
        slope, rail = pushing._fractional_slope(500e6, 500e6, 1.62, 1.98)
        self.assertAlmostEqual(slope, 0.0)
        self.assertAlmostEqual(rail, 1.80)

    def test_falling_frequency_is_negative(self):
        slope, _ = pushing._fractional_slope(200e6, 100e6, 1.62, 1.98)
        self.assertLess(slope, 0.0)


class ParseSweptTableTests(unittest.TestCase):
    def test_extracts_rows_in_order(self):
        text = swept_table(
            [
                ("tt", 27, 1.62, 0.900, "300 MHz", "-"),
                ("tt", 27, 1.80, 0.900, "320 MHz", "-"),
                ("tt", 27, 1.98, 0.900, "340 MHz", "-"),
            ]
        )
        rows = pushing.parse_swept_table(text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["corner"], "tt")
        self.assertEqual(rows[0]["temp_c"], 27.0)
        self.assertEqual(rows[0]["supply_v"], 1.62)
        self.assertEqual(rows[0]["vctrl_v"], 0.900)
        self.assertAlmostEqual(rows[0]["freq_hz"], 300e6)
        self.assertTrue(rows[0]["oscillating"])
        self.assertAlmostEqual(rows[2]["freq_hz"], 340e6)

    def test_no_oscillation_row_is_flagged(self):
        text = swept_table([("ss", -40, 1.62, 0.800, "-", "no oscillation")])
        rows = pushing.parse_swept_table(text)
        self.assertFalse(rows[0]["oscillating"])
        self.assertIsNone(rows[0]["freq_hz"])

    def test_missing_section_raises(self):
        with self.assertRaises(pushing.AnalysisError):
            pushing.parse_swept_table("no such section here\n")

    def test_empty_table_raises(self):
        text = "- **Swept-axis measurements** (nothing follows):\n\n- **Other section**:\n"
        with self.assertRaises(pushing.AnalysisError):
            pushing.parse_swept_table(text)


class DeriveTests(unittest.TestCase):
    def test_three_supply_points_yield_one_span(self):
        rows = pushing.parse_swept_table(
            swept_table(
                [
                    ("tt", 27, 1.62, 0.900, "300 MHz", "-"),
                    ("tt", 27, 1.80, 0.900, "300 MHz", "-"),
                    ("tt", 27, 1.98, 0.900, "300 MHz", "-"),
                ]
            )
        )
        derived = pushing.derive(rows)
        self.assertEqual(len(derived), 1)
        entry = derived[0]
        self.assertEqual(entry["corner"], "tt")
        self.assertEqual(entry["vctrl_v"], 0.900)
        self.assertEqual(len(entry["segments"]), 2)  # 1.62->1.80, 1.80->1.98
        self.assertIsNotNone(entry["span"])
        # Flat frequency across the whole supply axis -> zero pushing.
        self.assertAlmostEqual(entry["span"]["slope"], 0.0)
        self.assertAlmostEqual(entry["span"]["rail"], 1.80)

    def test_single_supply_point_has_no_span(self):
        rows = pushing.parse_swept_table(
            swept_table([("tt", 27, 1.80, 0.900, "300 MHz", "-")])
        )
        derived = pushing.derive(rows)
        self.assertEqual(len(derived), 1)
        self.assertIsNone(derived[0]["span"])
        self.assertEqual(derived[0]["segments"], [])

    def test_non_oscillating_point_excluded_from_usable(self):
        rows = pushing.parse_swept_table(
            swept_table(
                [
                    ("tt", 27, 1.62, 0.800, "-", "no oscillation"),
                    ("tt", 27, 1.80, 0.800, "150 MHz", "-"),
                    ("tt", 27, 1.98, 0.800, "160 MHz", "-"),
                ]
            )
        )
        derived = pushing.derive(rows)
        entry = derived[0]
        self.assertEqual(entry["usable"], [1.80, 1.98])
        self.assertIsNotNone(entry["span"])
        self.assertEqual((entry["span"]["v_a"], entry["span"]["v_b"]), (1.80, 1.98))

    def test_distinct_vctrl_and_corner_triples_are_separate_entries(self):
        rows = pushing.parse_swept_table(
            swept_table(
                [
                    ("tt", 27, 1.62, 0.900, "300 MHz", "-"),
                    ("tt", 27, 1.98, 0.900, "340 MHz", "-"),
                    ("tt", 27, 1.62, 1.200, "600 MHz", "-"),
                    ("tt", 27, 1.98, 1.200, "700 MHz", "-"),
                    ("ss", 27, 1.62, 0.900, "250 MHz", "-"),
                    ("ss", 27, 1.98, 0.900, "260 MHz", "-"),
                ]
            )
        )
        derived = pushing.derive(rows)
        keys = {(e["corner"], e["temp_c"], e["vctrl_v"]) for e in derived}
        self.assertEqual(
            keys,
            {("tt", 27.0, 0.900), ("tt", 27.0, 1.200), ("ss", 27.0, 0.900)},
        )


class RenderSectionTests(unittest.TestCase):
    def test_render_reports_above_and_below_floor(self):
        # 1.62->1.98 V, 300->300 MHz: zero pushing, well BELOW the ~55.6 %/V
        # floor.
        rows = pushing.parse_swept_table(
            swept_table(
                [
                    ("tt", 27, 1.62, 0.900, "300 MHz", "-"),
                    ("tt", 27, 1.80, 0.900, "300 MHz", "-"),
                    ("tt", 27, 1.98, 0.900, "300 MHz", "-"),
                    # 1.62->1.98 V, 300->600 MHz: a doubling well ABOVE floor.
                    ("tt", 27, 1.62, 1.200, "300 MHz", "-"),
                    ("tt", 27, 1.80, 1.200, "450 MHz", "-"),
                    ("tt", 27, 1.98, 1.200, "600 MHz", "-"),
                ]
            )
        )
        derived = pushing.derive(rows)
        section = pushing.render_section(derived, "20260101-000000-abcdef0")
        self.assertIn(pushing.SECTION_MARKER, section)
        self.assertIn("BELOW floor", section)
        self.assertIn("ABOVE floor", section)
        self.assertIn("2 (corner, temperature, VCTRL) triples", section)

    def test_render_raises_on_empty_input(self):
        with self.assertRaises(pushing.AnalysisError):
            pushing.render_section([], "20260101-000000-abcdef0")


class RenderRoundTripTests(unittest.TestCase):
    """`--append` then `--check` against a real scratch file, mirroring how
    sim/run_corners.py mints a record and a later reader re-verifies it."""

    def _write_record(self, tmp_path: Path) -> Path:
        record_path = tmp_path / "20260101-000000-abcdef0.md"
        record_path.write_text(
            "# Record 20260101-000000-abcdef0\n\n"
            + swept_table(
                [
                    ("tt", 27, 1.62, 0.900, "300 MHz", "-"),
                    ("tt", 27, 1.80, 0.900, "320 MHz", "-"),
                    ("tt", 27, 1.98, 0.900, "340 MHz", "-"),
                ]
            )
        )
        return record_path

    def test_append_then_check_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = self._write_record(Path(tmp))
            rc = pushing.main(["--append", str(record_path)])
            self.assertEqual(rc, 0)
            self.assertIn(pushing.SECTION_MARKER, record_path.read_text())

            rc = pushing.main(["--check", str(record_path)])
            self.assertEqual(rc, 0)

    def test_append_twice_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = self._write_record(Path(tmp))
            self.assertEqual(pushing.main(["--append", str(record_path)]), 0)
            self.assertEqual(pushing.main(["--append", str(record_path)]), 1)

    def test_check_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = self._write_record(Path(tmp))
            self.assertEqual(pushing.main(["--append", str(record_path)]), 0)
            # Corrupt one digit inside the appended derived section (not the
            # source table above it, which --check re-derives from) so a
            # fresh re-derivation disagrees with what is on disk.
            text = record_path.read_text()
            marker_idx = text.index(pushing.SECTION_MARKER)
            before, after = text[:marker_idx], text[marker_idx:]
            tampered_after = after.replace("BELOW floor", "ABOVE floor", 1)
            self.assertNotEqual(tampered_after, after, "fixture must contain a floor verdict to tamper with")
            record_path.write_text(before + tampered_after)
            self.assertEqual(pushing.main(["--check", str(record_path)]), 1)

    def test_check_without_existing_section_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = self._write_record(Path(tmp))
            self.assertEqual(pushing.main(["--check", str(record_path)]), 1)


if __name__ == "__main__":
    unittest.main()
