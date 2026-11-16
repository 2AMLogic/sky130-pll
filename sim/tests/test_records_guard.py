"""Issue #503: the PVT / --mc / Fmax record writers refuse a re-run of an
already-recorded claim without --supersedes, and refuse a --supersedes that
names no record -- the append-only rule the lock-timing lane already enforces
mechanically, now shared.

The guard's collision key is the re-run identity: normalized claim text +
the lane's matrix block + the netlist SHA-256. These tests pin, over a temp
records dir with synthetic records (no PDK, no simulation):

- the two refusals and the two acceptances (a correct --supersedes, and a
  same-claim variant whose matrix block or netlist digest differs);
- the superseded-chain message (a new run must supersede the chain's tip,
  not a record already superseded);
- the attested **Supersedes** forms (bare id, backticked id with trailing
  prose, and the two "first record" wordings);
- key parity: the builder each lane calls before simulating produces exactly
  the key the parser extracts from the record the lane would write, over the
  numeric-spelling differences between lanes (%g vs str() temperatures,
  .2f supplies, the "not applicable" supply line);
- the real-records replay: every committed record in sim/divider-n64/ and
  sim/jitter-calibration/ -- the legitimate same-claim families the curator
  measured -- carries a key distinct from every other record in its
  directory, so the guard would not have refused any of them.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners  # noqa: E402
from harness import montecarlo  # noqa: E402
from harness import records_guard as rg  # noqa: E402

CLAIM = "does the DUT divide by 64 cleanly (issue #27)"
FMAX_CLAIM = "highest correct-division frequency per PVT point"
NETLIST_SHA_A = "a" * 64
NETLIST_SHA_B = "b" * 64
RECORD_ID_A = "20260911-074438-073b241"
RECORD_ID_B = "20260911-101305-7d2f839"
SUBSET = "one process-corner row per run (issue #130)"


def pvt_record(record_id: str, *, total_points: int, sha: str,
               supersedes: str | None = None, claim: str = CLAIM,
               temps: str = "-40.0, 27.0, 125.0") -> str:
    supersedes_line = (
        f"- **Supersedes**: {supersedes}" if supersedes is not None
        else "- **Supersedes**: (none -- first record for this claim)"
    )
    subset_line = f"  - **Subset of the manifest's default grid**: {SUBSET}\n"
    return f"""# Record {record_id}

- **Record ID**: {record_id}
- **Claim**: {claim}
- **Spec row(s)**: 4 -- divider range (DRAFT)
- **Netlist provenance**: schematic (`sim/divider-n64/testbench/`), frozen at `sim/divider-n64/netlist-snapshots/{record_id}.spice`, SHA-256 `{sha}`
- **Environment provenance**:
  - PDK: ciel `sky130A`, open_pdks `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
  - Repo commit: `073b24121018bcb1ba8d83914149799237c76c71`
- **Corner matrix run**:
  - Process corners: tt
  - Temperatures (deg C): {temps}
  - Supplies (V): 1.62, 1.80, 1.98
  - Total points: {total_points}
{subset_line}- **Methodology / criteria / limitations**:
  - Per-point criterion: ngspice exits 0 and the loop locks.
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict |
  |---|---|---|---|
  | tt | 27 | 1.80 | PASS |

  - **Overall: PASS** ({total_points}/{total_points} points passed)
- **Links**:
  - Testbench: `sim/divider-n64/testbench/`
  - Netlist snapshot: `sim/divider-n64/netlist-snapshots/{record_id}.spice`
  - Raw logs: `sim/divider-n64/corners/{record_id}/`
- **Timestamp / author**: 2026-09-11T11:14:25Z, agent-builder
{supersedes_line}
"""


def mc_record(record_id: str, *, sha: str, supersedes: str | None = None) -> str:
    supersedes_line = (
        f"- **Supersedes**: {supersedes}" if supersedes is not None
        else "- **Supersedes**: (none -- first record for this claim)"
    )
    return f"""# Record {record_id}

- **Record ID**: {record_id}
- **Claim**: row 9's Monte Carlo population
- **Spec row(s)**: 9 -- period jitter
- **Netlist provenance**: schematic (`sim/pll-lock-mc/testbench/`), frozen at `sim/pll-lock-mc/netlist-snapshots/{record_id}.spice`, SHA-256 `{sha}`
- **Statistical sampling point**:
  - Base process corner: tt (netlisted as `tt_mm`)
  - Temperature (deg C): 125
  - Supply (V): 1.80
  - Mismatch sampling (`MC_MM_SWITCH`): on
  - Process sampling (`MC_PR_SWITCH`): on
  - Trials: 5 (seeds 1..5, one ngspice `.options seed=<N>` per trial)
- **Methodology / criteria / limitations**:
  - Sampling mechanism: sky130's own MC_MM_SWITCH / MC_PR_SWITCH.
- **Result**: 5/5 trials passed
{supersedes_line}
"""


def fmax_record(record_id: str, *, sha: str, cells: int,
                supersedes: str | None = None, moduli: str = "4, 5") -> str:
    supersedes_line = (
        f"- **Supersedes**: {supersedes}" if supersedes is not None
        else "- **Supersedes**: (none -- first record for this claim)"
    )
    return f"""# Record {record_id}

- **Record ID**: {record_id}
- **Claim**: {FMAX_CLAIM}
- **Spec row(s)**: 4 -- multiplication ratio (DRAFT)
- **Netlist provenance**: schematic (`sim/divider-fmax/testbench/`), frozen at `sim/divider-fmax/netlist-snapshots/{record_id}.spice`, SHA-256 `{sha}`
- **Search / corner matrix run**:
  - Moduli: {moduli}
  - Process corners: tt
  - Temperatures (deg C): -40, 27, 125
  - Supplies (V): 1.62, 1.80, 1.98
  - Cells (modulus x PVT point): {cells}; probes run: 737
- **Methodology / criteria / limitations**:
  - Search: grid 800-2600 MHz at 25 MHz resolution.
- **Result**: BRACKETED
{supersedes_line}
"""


def write_record(records_dir: Path, text: str) -> None:
    records_dir.mkdir(parents=True, exist_ok=True)
    stem = text.splitlines()[0].replace("# Record ", "")
    (records_dir / f"{stem}.md").write_text(text)


def pvt_key(*, total_points: int, subset_reason: str | None = SUBSET) -> tuple:
    """The matrix key `cli._run_experiment` would build for a run whose
    record block matches the synthetic record above."""
    points = [
        corners.PvtPoint(corner="tt", temp_c=t, supply_v=s)
        for t in (-40.0, 27.0, 125.0)
        for s in (1.62, 1.80, 1.98)
    ][:total_points]
    return rg.pvt_matrix_key(
        points=points, manifest_has_supply=True, corner_note=None,
        subset_reason=subset_reason,
    )


def norm(text: str) -> str:
    return " ".join(text.split())


class FmaxCell:
    """Duck-typed stand-in for `fmax_cli.Cell`: the key builder only reads
    `.modulus.n` and `.point`."""

    class _Modulus:
        def __init__(self, n):
            self.n = n

    def __init__(self, n, corner, temp_c, supply_v):
        self.modulus = self._Modulus(n)
        self.point = corners.PvtPoint(corner=corner, temp_c=temp_c, supply_v=supply_v)


def fmax_cells(moduli=(4, 5)):
    return [FmaxCell(n, "tt", t, s)
            for n in moduli for t in (-40.0, 27.0, 125.0) for s in (1.62, 1.80, 1.98)]


class RecordsGuardTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="records-guard-test-")
        self.addCleanup(self._tmp.cleanup)
        self.records_dir = Path(self._tmp.name) / "records"

    def check(self, *, matrix_key: tuple, sha: str, supersedes: str | None,
              claim: str = CLAIM):
        return rg.check(
            records_dir=self.records_dir,
            claim=claim,
            matrix_key=matrix_key,
            netlist_sha=sha,
            supersedes=supersedes,
        )

    # --- the two refusals (ACs 1 and 2) ---

    def test_rerun_without_supersedes_is_refused_and_names_the_id(self):
        """AC 1: a re-run of a recorded claim exits non-zero before
        simulating, naming the record id to pass."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None)
        message = str(caught.exception)
        self.assertIn(RECORD_ID_A, message)
        self.assertIn("--supersedes", message)

    def test_supersedes_nonexistent_id_is_refused_and_names_the_dir(self):
        """AC 2: a typo'd pointer must not land; the message names the dir."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes="20260101-000000-0000000")
        self.assertIn(str(self.records_dir), str(caught.exception))

    def test_supersedes_nonexistent_id_refused_even_without_a_collision(self):
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        with self.assertRaises(rg.RecordsGuardError):
            self.check(matrix_key=pvt_key(total_points=3), sha=NETLIST_SHA_B,
                       supersedes="20260101-000000-0000000")

    # --- the acceptances (ACs 3 and 4) ---

    def test_supersedes_current_record_succeeds(self):
        """AC 3: the correct pointer passes."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                   supersedes=RECORD_ID_A)

    def test_new_claim_without_supersedes_succeeds(self):
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                   supersedes=None)

    def test_different_corner_block_accepted_without_supersedes(self):
        """AC 4, arm 1: a different subset (different Total points) in the
        same dir is a variant, not a re-run -- the divider-n64 family's
        incremental corner rows must keep landing."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        self.check(matrix_key=pvt_key(total_points=3), sha=NETLIST_SHA_A,
                   supersedes=None)

    def test_different_netlist_sha_accepted_without_supersedes(self):
        """AC 4, arm 2: same matrix, re-netlisted DUT (different SHA) is a
        variant -- the jitter-calibration family's one-netlist-per-variant
        sweep must keep landing."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_B,
                   supersedes=None)

    def test_different_claim_accepted_without_supersedes(self):
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                   claim="a different claim entirely", supersedes=None)

    # --- superseded chains and the attested Supersedes forms ---

    def test_chain_refusal_names_the_tip_not_the_superseded_record(self):
        """Edge case: A, B supersedes A (same key). The next re-run must be
        told to supersede B, the claim's current record."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_B, total_points=9, sha=NETLIST_SHA_A,
                                supersedes=RECORD_ID_A))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None)
        message = str(caught.exception)
        self.assertIn("--supersedes " + RECORD_ID_B, message)
        self.assertNotIn("--supersedes " + RECORD_ID_A + "\n", message)

    def test_tip_of_chain_via_backticked_annotated_supersedes(self):
        """One committed record carries a backticked id with trailing prose
        (`vco`'s widening note); the parser must still chain through it."""
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_B, total_points=45, sha=NETLIST_SHA_B,
                                supersedes=f"`{RECORD_ID_A}` (widens that record's "
                                           "single-corner subset to the full grid)"))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None)
        message = str(caught.exception)
        self.assertIn("--supersedes " + RECORD_ID_B, message)

    def test_legacy_first_record_wording_parses_as_none(self):
        """`phase-quadrature-model` still carries the older wording."""
        record = pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A).replace(
            "- **Supersedes**: (none -- first record for this claim)",
            "- **Supersedes**: none (first record for this experiment)",
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        self.assertIsNone(parsed.supersedes)
        with self.assertRaises(rg.RecordsGuardError):
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None)

    def test_non_record_file_is_skipped(self):
        self.records_dir.mkdir(parents=True, exist_ok=True)
        (self.records_dir / "NOTE.md").write_text(
            "# NOTE\n\nSupersedes the empty row in README.md.\n"
        )
        self.assertEqual(rg.scan_records(self.records_dir), [])
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                   supersedes=None)

    def test_record_missing_netlist_sha_is_an_error_not_a_skip(self):
        record = pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A).replace(
            f"SHA-256 `{NETLIST_SHA_A}`", "SHA-256 (lost)"
        )
        write_record(self.records_dir, record)
        with self.assertRaises(rg.RecordsGuardError):
            rg.scan_records(self.records_dir)

    def test_different_record_genre_is_skipped_not_refused(self):
        """sim/phase-quadrature-model's PDK-free model records live in a
        records/ dir too, with neither a netlist digest nor a matrix block;
        no lane writer targets them, so the guard skips them."""
        self.records_dir.mkdir(parents=True, exist_ok=True)
        (self.records_dir / "20261020-001830-e786d18.md").write_text(
            "# Record 20261020-001830-e786d18\n\n"
            "- **Record ID**: 20261020-001830-e786d18\n"
            "- **Claim**: a PDK-free deterministic event model reproduces the "
            "closed-form quadrature relationship\n"
            "- **Supersedes**: none (first record for this experiment)\n"
            "- **Model version**: 1\n"
            "- **Overall: PASS** (117 of 117 criterion-bearing cases passed)\n"
        )
        self.assertEqual(rg.scan_records(self.records_dir), [])
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                   supersedes=None)

    def test_missing_records_dir_is_empty(self):
        self.assertEqual(rg.scan_records(self.records_dir), [])

    # --- key parity: builder (pre-sim) vs parser (committed record) ---

    def test_pvt_key_parity_with_committed_record(self):
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        parsed = rg.scan_records(self.records_dir)[0]
        built = pvt_key(total_points=9)
        self.assertEqual(built, parsed.matrix_key)
        self.assertEqual(norm(CLAIM), parsed.claim)
        self.assertEqual(parsed.collision_key, (norm(CLAIM), built, NETLIST_SHA_A))

    def test_pvt_key_parity_temperature_spellings(self):
        """PVT renders `str(float)` ("-40.0"), Fmax renders `%g` ("-40");
        both must canonicalize to one spelling."""
        committed = pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A).replace(
            "Temperatures (deg C): -40.0, 27.0, 125.0",
            "Temperatures (deg C): -40, 27, 125",
        )
        write_record(self.records_dir, committed)
        parsed = rg.scan_records(self.records_dir)[0]
        self.assertEqual(pvt_key(total_points=9), parsed.matrix_key)

    def test_pvt_null_supply_pattern_parity(self):
        record = pvt_record(RECORD_ID_A, total_points=1, sha=NETLIST_SHA_A, temps="27.0")
        record = record.replace(
            f"  - **Subset of the manifest's default grid**: {SUBSET}\n", ""
        ).replace(
            "  - Supplies (V): 1.62, 1.80, 1.98\n",
            "  - Supplies (V): **not applicable** -- this manifest declares a\n"
            "    `null` `supply_pattern` because its DUT has no supply terminal.\n",
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        built = rg.pvt_matrix_key(
            points=[corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.80)],
            manifest_has_supply=False, corner_note=None, subset_reason=None,
        )
        self.assertEqual(built, parsed.matrix_key)

    def test_corner_note_is_part_of_the_key(self):
        record = pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A).replace(
            "- **Corner matrix run**:",
            "- **Corner matrix run**:\n  - Corner-set note: custom corner set",
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        built = rg.pvt_matrix_key(
            points=[
                corners.PvtPoint(corner="tt", temp_c=t, supply_v=s)
                for t in (-40.0, 27.0, 125.0) for s in (1.62, 1.80, 1.98)
            ],
            manifest_has_supply=True, corner_note="custom corner set",
            subset_reason=SUBSET,
        )
        self.assertEqual(built, parsed.matrix_key)

    def test_mc_key_parity_with_committed_record(self):
        write_record(self.records_dir, mc_record(RECORD_ID_A, sha=NETLIST_SHA_A))
        parsed = rg.scan_records(self.records_dir)[0]
        trials = [
            montecarlo.McTrial(trial=i, seed=i, corner="tt", temp_c=125.0,
                               supply_v=1.80, mismatch=True, process=True)
            for i in range(1, 6)
        ]
        built = rg.mc_matrix_key(trials=trials, subset_reason=None)
        self.assertEqual(built, parsed.matrix_key)
        self.assertEqual(parsed.collision_key,
                         (norm("row 9's Monte Carlo population"), built, NETLIST_SHA_A))

    def test_mc_rerun_refused_and_variant_accepted(self):
        write_record(self.records_dir, mc_record(RECORD_ID_A, sha=NETLIST_SHA_A))
        trials = [
            montecarlo.McTrial(trial=i, seed=i, corner="tt", temp_c=125.0,
                               supply_v=1.80, mismatch=True, process=True)
            for i in range(1, 6)
        ]
        key = rg.mc_matrix_key(trials=trials, subset_reason=None)
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=key, sha=NETLIST_SHA_A, supersedes=None,
                       claim="row 9's Monte Carlo population")
        self.assertIn(RECORD_ID_A, str(caught.exception))
        self.check(matrix_key=key, sha=NETLIST_SHA_A, supersedes=RECORD_ID_A,
                   claim="row 9's Monte Carlo population")
        other = [
            montecarlo.McTrial(trial=i, seed=i, corner="ss", temp_c=125.0,
                               supply_v=1.80, mismatch=True, process=True)
            for i in range(1, 6)
        ]
        self.check(matrix_key=rg.mc_matrix_key(trials=other, subset_reason=None),
                   sha=NETLIST_SHA_A, supersedes=None,
                   claim="row 9's Monte Carlo population")

    def test_fmax_key_parity_with_committed_record(self):
        write_record(self.records_dir, fmax_record(RECORD_ID_A, sha=NETLIST_SHA_A, cells=18))
        parsed = rg.scan_records(self.records_dir)[0]
        built = rg.fmax_matrix_key(cells=fmax_cells(), subset_reason=None)
        self.assertEqual(built, parsed.matrix_key)
        self.assertEqual(parsed.collision_key, (norm(FMAX_CLAIM), built, NETLIST_SHA_A))
        with self.assertRaises(rg.RecordsGuardError):
            self.check(matrix_key=built, sha=NETLIST_SHA_A, supersedes=None,
                       claim=FMAX_CLAIM)

    def test_fmax_probes_run_count_is_not_part_of_the_key(self):
        """The probe count is an outcome (unknown pre-sim); a re-run of the
        same cells on the same netlist is the collision this guard exists
        for, whatever this run's probe count turns out to be."""
        record = fmax_record(RECORD_ID_A, sha=NETLIST_SHA_A, cells=18).replace(
            "probes run: 737", "probes run: 700"
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        built = rg.fmax_matrix_key(cells=fmax_cells(), subset_reason=None)
        self.assertEqual(built, parsed.matrix_key)

    def test_subset_reason_is_part_of_the_key(self):
        write_record(self.records_dir,
                     pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A))
        self.check(matrix_key=pvt_key(total_points=9, subset_reason="a different prose"),
                   sha=NETLIST_SHA_A, supersedes=None)


class RealRecordsReplayTestCase(unittest.TestCase):
    """AC 6: the committed same-claim families must replay through the key
    with every record distinct from the others -- the guard, had it existed,
    would not have refused any of them."""

    def _family(self, slug: str) -> list[tuple]:
        records_dir = REPO_ROOT / "sim" / slug / "records"
        records = rg.scan_records(records_dir)
        self.assertTrue(records, f"no records parsed under {records_dir}")
        return [r.collision_key for r in records]

    def test_divider_n64_records_are_pairwise_distinct(self):
        keys = self._family("divider-n64")
        self.assertEqual(len(keys), 7)
        self.assertEqual(len(set(keys)), len(keys))

    def test_jitter_calibration_records_are_pairwise_distinct(self):
        keys = self._family("jitter-calibration")
        self.assertEqual(len(keys), 18)
        self.assertEqual(len(set(keys)), len(keys))

    def test_every_committed_supersedes_pointer_resolves(self):
        """Across all lanes: every **Supersedes** id in sim/*/records/ names
        a record that exists -- the invariant the new guards' arm 1 checks
        for runs about to land."""
        broken = []
        for records_dir in sorted((REPO_ROOT / "sim").glob("*/records")):
            records = rg.scan_records(records_dir)
            ids = {r.id for r in records}
            for r in records:
                if r.supersedes is not None and r.supersedes not in ids:
                    broken.append(f"{records_dir.parent.name}/{r.id} -> {r.supersedes}")
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
