"""Issue #503: the PVT / --mc / Fmax record writers refuse a re-run of an
already-recorded claim without --supersedes, and refuse a --supersedes that
names no record -- the append-only rule the lock-timing lane already enforces
mechanically, now shared.

The guard's collision key is the re-run identity: normalized claim text +
the lane's matrix block + the netlist SHA-256 + the run's analysis identity
(the injected `.options` / `tran` cards and swept values -- the axis the
issue #503 review added, because `sim/integrator-floor`'s tolerance variants
and `sim/vco-2x-duty`'s refined grids differ in none of the other three).
These tests pin, over a temp records dir with synthetic records (no PDK, no
simulation):

- the two refusals and the two acceptances (a correct --supersedes, and a
  same-claim variant whose matrix block, netlist digest or analysis
  identity differs);
- the superseded-chain message (a new run must supersede the chain's tip,
  not a record already superseded; a cyclic chain is reported, not walked
  forever);
- the attested **Supersedes** forms (bare id, backticked id with trailing
  prose, and the two "first record" wordings);
- key parity: the builder each lane calls before simulating produces exactly
  the key the parser extracts from the record the lane would write, over the
  numeric-spelling differences between lanes (%g vs str() temperatures,
  .2f supplies, the "not applicable" supply line), and the analysis
  identity recovered from a pre-`**Analysis identity**` record's own
  rendered text matches what the driver builds;
- the real-records replay: every committed record in sim/*/records/ -- not
  just the families the issue named -- keys such that each collision-key
  group holds at most one current record, so the guard would not have
  refused any legitimate variant when it landed.
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
               temps: str = "-40.0, 27.0, 125.0",
               analysis_identity: str | None = None) -> str:
    supersedes_line = (
        f"- **Supersedes**: {supersedes}" if supersedes is not None
        else "- **Supersedes**: (none -- first record for this claim)"
    )
    subset_line = f"  - **Subset of the manifest's default grid**: {SUBSET}\n"
    identity_line = (
        f"  - **Analysis identity**: {analysis_identity}\n"
        if analysis_identity is not None else ""
    )
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
{subset_line}{identity_line}- **Methodology / criteria / limitations**:
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
              claim: str = CLAIM, analysis: str = ""):
        return rg.check(
            records_dir=self.records_dir,
            claim=claim,
            matrix_key=matrix_key,
            netlist_sha=sha,
            supersedes=supersedes,
            analysis=analysis,
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
        self.assertEqual(parsed.collision_key,
                         (norm(CLAIM), built, NETLIST_SHA_A, ""))

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
                         (norm("row 9's Monte Carlo population"), built,
                          NETLIST_SHA_A, ""))

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
        self.assertEqual(parsed.collision_key,
                         (norm(FMAX_CLAIM), built, NETLIST_SHA_A, ""))
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

    # --- the analysis identity axis (issue #503 review: sim/integrator-floor
    # and sim/vco-2x-duty differ in neither block nor digest) ---

    def test_analysis_identity_separates_same_claim_matrix_netlist_variants(self):
        """Two committed records sharing claim, matrix and netlist digest but
        running different analyses are variants, not re-runs: an exact re-run
        of either is refused naming its own record, and a new analysis lands
        without --supersedes (no false `**Supersedes**` pointer)."""
        write_record(self.records_dir, pvt_record(
            RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A,
            analysis_identity="tran 200p 10u"))
        write_record(self.records_dir, pvt_record(
            RECORD_ID_B, total_points=9, sha=NETLIST_SHA_A,
            analysis_identity=".options reltol=1e-4; tran 200p 10u"))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None, analysis="tran 200p 10u")
        self.assertIn(RECORD_ID_A, str(caught.exception))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None,
                       analysis=".options reltol=1e-4; tran 200p 10u")
        self.assertIn(RECORD_ID_B, str(caught.exception))
        self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                   supersedes=None,
                   analysis=".options reltol=1e-5; tran 200p 10u")

    def test_analysis_identity_recovered_from_committed_record_text(self):
        """A record minted before the `**Analysis identity**` line keys on the
        identity recovered from its own rendered text: the `- Simulator
        accuracy:` bullet's `.options` card, the `- Analysis:` bullet's
        `tran` card, and the `**Swept-axis measurements**` table -- in the
        same canonical form `measure_analysis_identity` builds, so an exact
        re-run of that record still collides."""
        record = f"""# Record {RECORD_ID_A}

- **Record ID**: {RECORD_ID_A}
- **Claim**: {CLAIM}
- **Spec row(s)**: 4 -- divider range (DRAFT)
- **Netlist provenance**: schematic (`sim/vco-2x-duty/testbench/`), frozen at `sim/vco-2x-duty/netlist-snapshots/{RECORD_ID_A}.spice`, SHA-256 `{NETLIST_SHA_A}`
- **Corner matrix run**:
  - Process corners: tt
  - Temperatures (deg C): 27
  - Supplies (V): 1.80
  - Total points: 1
- **Methodology / criteria / limitations**:
  - Measurement method: the harness injects the analysis itself (an ngspice `.control` block built by `sim/harness/measure.py`), `linearize`s `v(clk)` and `wrdata`-dumps it.
  - Simulator accuracy: the transient runs under `.options reltol=1e-4` (manifest `measure.options`), injected ahead of the analysis.
  - Analysis: transient per swept VCTRL value (`tran 50p 800n uic`, three values, one ngspice invocation at tt/27C/1.80V).
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | Detail |
  |---|---|---|---|---|
  | tt | 27 | 1.80 | PASS | 3/3 swept points oscillated |

- **Swept-axis measurements** (VCTRL vs. output frequency, per PVT point):

  | Corner | Temp (C) | Supply (V) | VCTRL (V) | f_out | Duty | Note |
  |---|---|---|---|---|---|---|
  | tt | 27 | 1.80 | 0.300 | 243.8 MHz | 50.7% | - |
  | tt | 27 | 1.80 | 0.650 | 1.1 GHz | 50.1% | - |
  | tt | 27 | 1.80 | 0.940 | 3.4 GHz | 49.8% | - |

- **Supersedes**: (none -- first record for this claim)
"""
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        recovered = rg.analysis_identity(
            options_card=".options reltol=1e-4",
            tran_card="tran 50p 800n uic",
            sweep_groups=(
                (("tt", "27.0", "1.80"), ("0.300", "0.650", "0.940")),
            ),
        )
        self.assertEqual(parsed.analysis, recovered)
        matrix_key = rg.pvt_matrix_key(
            points=[corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.80)],
            manifest_has_supply=True, corner_note=None, subset_reason=None,
        )
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=matrix_key, sha=NETLIST_SHA_A, supersedes=None,
                       analysis=recovered)
        self.assertIn(RECORD_ID_A, str(caught.exception))
        self.check(matrix_key=matrix_key, sha=NETLIST_SHA_A, supersedes=None,
                   analysis=rg.analysis_identity(
                       options_card=".options reltol=1e-4",
                       tran_card="tran 50p 800n uic",
                       sweep_groups=(
                           (("tt", "27.0", "1.80"), ("0.715", "0.720")),
                       ),
                   ))

    def test_record_without_a_measure_lane_renders_empty_analysis(self):
        """A plumbing / AC / charge-pump record (no `Measurement method`
        bullet citing `sim/harness/measure.py`) keys on the empty identity --
        what `measure_analysis_identity` builds for a `spec=None` run -- so
        the guard's re-run protection for those lanes is unchanged."""
        record = pvt_record(RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A).replace(
            "  - Per-point criterion: ngspice exits 0 and the loop locks.",
            "  - Measurement method: the harness injects the analysis itself "
            "(an ngspice `.control` block built by `sim/harness/acmeasure.py`).\n"
            "  - Analysis: one `ac dec 10 1k 100MEG` + one `tran 1n 2u` sweep.",
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        self.assertEqual(parsed.analysis, "")
        with self.assertRaises(rg.RecordsGuardError):
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None, analysis="")

    def test_mc_analysis_identity_recovered_from_the_analysis_bullet(self):
        """A Monte Carlo record renders the injected `.options` card inside
        its `- Analysis:` bullet (no `- Simulator accuracy:` bullet), so the
        recovered identity must include it -- equal to what a fresh re-run
        of that manifest config builds, keeping the re-run refusal honest
        for legacy MC records (the `sim/pll-lock-mc` shape)."""
        record = mc_record(RECORD_ID_A, sha=NETLIST_SHA_A).replace(
            "  - Sampling mechanism: sky130's own MC_MM_SWITCH / MC_PR_SWITCH.",
            "  - Measurement method: the manifest-owned `.control` block "
            "(`sim/harness/measure.py`'s `build_control_block`) is appended "
            "after each trial's seed cards.\n"
            "  - Analysis: cold-start transient, closed loop, one sky130 "
            "statistical draw per trial (`tran 20p 50u 0 200p` under "
            "`.options reltol=1e-4`, injected by sim/harness/measure.py).",
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        self.assertEqual(
            parsed.analysis, ".options reltol=1e-4; tran 20p 50u 0 200p"
        )
        trials = [
            montecarlo.McTrial(trial=i, seed=i, corner="tt", temp_c=125.0,
                               supply_v=1.80, mismatch=True, process=True)
            for i in range(1, 6)
        ]
        built = rg.mc_matrix_key(trials=trials, subset_reason=None)
        with self.assertRaises(rg.RecordsGuardError):
            self.check(matrix_key=built, sha=NETLIST_SHA_A, supersedes=None,
                       claim="row 9's Monte Carlo population",
                       analysis=".options reltol=1e-4; tran 20p 50u 0 200p")
        self.check(matrix_key=built, sha=NETLIST_SHA_A, supersedes=None,
                   claim="row 9's Monte Carlo population",
                   analysis=".options reltol=1e-5; tran 20p 50u 0 200p")

    def test_measure_analysis_identity_matches_the_tran_card_injected(self):
        """`measure_analysis_identity` builds the identity from the same
        `tran_card` property `build_control_block` injects, so guard and
        netlisted analysis cannot drift."""
        from harness import measure as measure_mod

        spec = measure_mod.MeasureSpec.from_manifest({
            "measure": {
                "node": "clk", "tran_step": "20p", "tran_stop": "10u",
                "tran_max_step": "200p", "options": {"reltol": "1e-4"},
            }
        })
        point = corners.PvtPoint(corner="tt", temp_c=125.0, supply_v=1.80)
        self.assertEqual(
            rg.measure_analysis_identity(spec, [point]),
            ".options reltol=1e-4; tran 20p 10u 0 200p",
        )
        self.assertIn(spec.tran_card, measure_mod.build_control_block(spec))

    def test_fmax_search_identity_separates_a_refined_grid(self):
        """The Fmax lane's refinement axis: the same cells on the same
        netlist under a finer search grid are a variant, and an exact re-run
        of the recorded grid still collides."""
        class _Search:
            f_min_hz, f_max_hz = 800e6, 2600e6
            resolution_hz, coarse_stride = 25e6, 8

        class _Spec:
            search = _Search()
            mandatory_probes_hz = ()

        recorded = rg.fmax_search_identity(_Spec())
        self.assertEqual(recorded, "search 800-2600 MHz @ 25 MHz, stride 8")
        refined = _Search()
        refined.resolution_hz = 12.5e6

        class _RefinedSpec:
            search = refined
            mandatory_probes_hz = ()

        self.assertNotEqual(recorded, rg.fmax_search_identity(_RefinedSpec()))
        # The identity a committed record renders is recovered from its own
        # `- Search:` bullet, so a re-run of the recorded grid still collides
        # and a refined one does not.
        record = fmax_record(RECORD_ID_A, sha=NETLIST_SHA_A, cells=18).replace(
            "  - Search: grid 800-2600 MHz at 25 MHz resolution.",
            "  - Search: grid 800-2600 MHz at 25 MHz resolution; stage 1 "
            "probes every 8th grid point plus the top.",
        )
        write_record(self.records_dir, record)
        parsed = rg.scan_records(self.records_dir)[0]
        self.assertEqual(parsed.analysis, recorded)
        built = rg.fmax_matrix_key(cells=fmax_cells(), subset_reason=None)
        with self.assertRaises(rg.RecordsGuardError):
            self.check(matrix_key=built, sha=NETLIST_SHA_A, supersedes=None,
                       claim=FMAX_CLAIM, analysis=recorded)
        self.check(matrix_key=built, sha=NETLIST_SHA_A, supersedes=None,
                   claim=FMAX_CLAIM,
                   analysis=recorded.replace("@ 25 MHz", "@ 12.5 MHz"))

    def test_supersede_cycle_is_reported_not_hung(self):
        """A cyclic `**Supersedes**` pair in committed records must surface
        as a refusal naming the malformed chain, not spin the pre-simulation
        gate forever (issue #503 review, non-blocking robustness)."""
        write_record(self.records_dir, pvt_record(
            RECORD_ID_A, total_points=9, sha=NETLIST_SHA_A,
            supersedes=RECORD_ID_B))
        write_record(self.records_dir, pvt_record(
            RECORD_ID_B, total_points=9, sha=NETLIST_SHA_A,
            supersedes=RECORD_ID_A))
        with self.assertRaises(rg.RecordsGuardError) as caught:
            self.check(matrix_key=pvt_key(total_points=9), sha=NETLIST_SHA_A,
                       supersedes=None)
        self.assertIn("cycle", str(caught.exception))


class RealRecordsReplayTestCase(unittest.TestCase):
    """AC 6, widened per the #503 review: replaying the committed records
    through the key must show every collision-key group in every
    `sim/*/records/` dir holding at most one *current* record (a record no
    other record of the group supersedes) -- the property that keeps the
    guard honest: a legitimate same-claim variant has a distinct key (it
    would have been accepted when it landed), and a genuine re-run chain has
    one tip (the guard's `--supersedes` message names it)."""

    def _records(self, slug: str) -> list:
        records_dir = REPO_ROOT / "sim" / slug / "records"
        records = rg.scan_records(records_dir)
        self.assertTrue(records, f"no records parsed under {records_dir}")
        return records

    def _family(self, slug: str) -> list[tuple]:
        return [r.collision_key for r in self._records(slug)]

    def test_divider_n64_records_are_pairwise_distinct(self):
        keys = self._family("divider-n64")
        self.assertEqual(len(keys), 7)
        self.assertEqual(len(set(keys)), len(keys))

    def test_jitter_calibration_records_are_pairwise_distinct(self):
        keys = self._family("jitter-calibration")
        self.assertEqual(len(keys), 18)
        self.assertEqual(len(set(keys)), len(keys))

    def test_integrator_floor_tolerance_variants_are_pairwise_distinct(self):
        """The #503 review's first collision: three same-claim records
        differing in neither matrix block nor netlist digest -- only in the
        injected `.options` card and `tran` card -- must key apart via the
        analysis identity recovered from their own rendered text."""
        keys = self._family("integrator-floor")
        self.assertEqual(len(keys), 3)
        self.assertEqual(len(set(keys)), len(keys))

    def test_vco_2x_duty_grid_rounds_are_pairwise_distinct(self):
        """The #503 review's second collision: an 11-value grid and its
        10-value refinement round share claim, block and digest; the swept
        values recovered from the `**Swept-axis measurements**` tables key
        them apart."""
        keys = self._family("vco-2x-duty")
        self.assertEqual(len(keys), 2)
        self.assertEqual(len(set(keys)), len(keys))

    def test_every_committed_dir_has_at_most_one_current_record_per_key(self):
        """The whole-tree sweep: for every `sim/*/records/` dir, every
        collision-key group holds at most one record not superseded by
        another record of the group. A group with two or more current
        records is a lane whose legitimate variants the key cannot tell
        apart -- exactly what the review's replay found here before the
        analysis identity axis existed."""
        multi_tip = []
        for records_dir in sorted((REPO_ROOT / "sim").glob("*/records")):
            records = rg.scan_records(records_dir)
            groups: dict[tuple, list] = {}
            for r in records:
                groups.setdefault(r.collision_key, []).append(r)
            for key, rs in groups.items():
                superseded = {r.supersedes for r in rs if r.supersedes}
                tips = [r.id for r in rs if r.id not in superseded]
                if len(tips) > 1:
                    multi_tip.append(
                        f"{records_dir.parent.name}: {tips} share one key"
                    )
        self.assertEqual(multi_tip, [])

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
