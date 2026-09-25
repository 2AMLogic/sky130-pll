#!/usr/bin/env python3
"""Restate a `sim/pll-lock-mc` record as a `klt yield` sample-set document.

`klt yield` (klayout-tools issue #816) turns a Monte Carlo sample set plus its
spec limits into a yield estimate that always carries its confidence interval,
its Cpk/sigma-to-spec and a sample-size verdict. It consumes either a `klt sim
--format json` Monte Carlo report or a plain **sample-set document**. This
repo's campaigns are run by `sim/run_corners.py`, not by `klt sim`, so the
second shape is the one that applies: this script writes it.

It is an `analysis/` script in the sense `sim/README.md` defines -- it reads a
committed record and restates what the record already says. It **never**
simulates, never reads a waveform dump, and never introduces a number that is
not already in the record it was handed or in the testbench manifest that
produced that record. Every figure below is traceable to one of:

  * `sim/pll-lock-mc/records/<record-id>.md` -- the per-trial lock verdicts and
    period-jitter figures, at the record's own printed precision (three
    decimals of a percent, i.e. +/-0.0005 pp; the raw reduction is not
    committed, per `sim/README.md`'s retention policy, so the record's table is
    the repo's source of truth for these values);
  * `sim/pll-lock-mc/testbench/tb.json` -- the gated bound
    (`measure.jitter.max_frac`), the post-lock population floor
    (`measure.jitter.min_cycles`), and the single statistical sampling point
    (`monte_carlo.corner`/`temp_c`/`supply_v`/`mismatch`/`process`/`trials`/
    `seed_base`).

`measure.jitter.max_frac` is the machine-readable copy of **ratified** spec row
9 (`spec/target-spec.md`: "<= 1.0 % of the output period, RMS, at `CLK` in
lock", RATIFIED via `DR-006`). The script asserts the two agree rather than
hardcoding the bound: a manifest that drifted from the ratified row would fail
here instead of silently grading against the wrong number.

## The two no-lock draws, and why there are two documents

Three of the five draws locked and carry a period-jitter figure. Two never
locked inside the 50 us window, so -- per row 9's own wording, which is a
post-lock quantity -- they carry **no** jitter figure at all, and the record
explicitly declines to charge them as jitter failures.

`klt yield` has two ways to declare a draw that produced no value
(`docs/cli/yield.md`, "Errored samples and conditional yield"), and neither is
an exact description of a draw censored by a *conditioning* event:

  * `errored` -- a tooling failure. Excluded from every statistic *including
    the empirical yield's denominator*, so the published estimate is explicitly
    conditional on the draws that produced a value, and the tool warns that it
    is, quoting the whole-draw figure the yield would have if every excluded
    draw were counted as a failure instead.
  * `failed_unmeasurable` -- a design failure whose failure mode *is* the
    absence of a value. Counted as a failure in the empirical yield's
    numerator's complement and denominator.

A draw that never locked is neither: nothing failed in the tooling (ngspice
exited 0 and the harness reduced the run exactly as it reduced the others), and
row 9 -- the row being graded -- is undefined for it rather than violated by
it. `errored`'s *behaviour* is the one that matches the record's own treatment
(exclude, and say out loud that the estimate is conditional), so it is the
primary mapping; `failed_unmeasurable` is written out too, as a committed
sensitivity check on that choice rather than a claim resolved by assertion.
Both reports are committed side by side, and both put the empirical yield at
0 %: the mapping choice moves the sample size and the interval width, never the
verdict. See `sim/pll-lock-mc/analysis/README.md`.

No `target_yield` is declared. Row 9 states a jitter bound; neither it nor
`DR-006` states a yield target, and inventing one here would be a spec claim an
`analysis/` script has no standing to make (`CLAUDE.md`: spec changes go
through `spec/` with a decision record). `klt yield` reports a measurement with
no `target_yield` as `reported` -- it can never "fail" -- which is why
`sim/pll-lock-mc/analysis/README.md` records why this report is **not** cited
as `signoff/block-manifest.json` evidence for T1 item 6 today.

Usage:

    # print the derived documents to stdout
    python3 sim/pll-lock-mc/analysis/yield_evidence.py RECORD.md

    # (re)write them under sim/pll-lock-mc/analysis/yield-evidence/
    python3 sim/pll-lock-mc/analysis/yield_evidence.py RECORD.md --write

    # re-derive and verify the committed documents (exit 1 on any drift)
    python3 sim/pll-lock-mc/analysis/yield_evidence.py RECORD.md --check

Standard library only, same convention as `sim/run_corners.py`,
`sim/vco-supply-pushing/analysis/pushing.py` and `measurements/aggregate.py`.
No PDK, ngspice, xschem or `klt` required to run this script -- `klt yield`
itself consumes what it writes, in a separate step the README documents.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Name the sample set gives the measured quantity. Deliberately carries its
#: unit in the name as well as in `unit`: a bare `period_jitter` would not say
#: whether 1.0 means one percent or one period.
MEASUREMENT_NAME = "period_jitter_rms_pct"

#: Written by `--write`, verified by `--check`, relative to this file.
OUTPUT_DIR = Path(__file__).resolve().parent / "yield-evidence"

_PRIMARY_SAMPLES = "mc-samples.json"
_VARIANT_SAMPLES = "mc-samples-censored-as-failures.json"
_SPEC_LIMITS = "spec-limits.json"

#: `docs/cli/yield.md`'s own documented defaults, restated explicitly in the
#: spec-limits file so the committed report's confidence level and sample-size
#: target are readable from the repo rather than from a tool version.
CONFIDENCE = 0.95
TARGET_CI_HALFWIDTH = 0.01

_RECORD_ID_RE = re.compile(r"^- \*\*Record ID\*\*: (?P<record_id>\S+)\s*$", re.M)
_TRIALS_RE = re.compile(
    r"^\s*- Trials: (?P<trials>\d+) \(seeds (?P<first>\d+)\.\.(?P<last>\d+),", re.M
)
_OVERALL_RE = re.compile(
    r"^\s*- \*\*Overall: (?P<verdict>PASS|FAIL)\*\* "
    r"\((?P<passed>\d+)/(?P<total>\d+) trials passed\)\s*$",
    re.M,
)
_HEADER_CELLS = [
    "Trial",
    "Seed",
    "Verdict",
    "Locked",
    "Time-to-lock",
    "f_out (post-lock)",
    "Duty",
    "Period jitter",
    "Detail",
]
_JITTER_RE = re.compile(r"^(?P<pct>[\d.]+)% \((?P<cycles>\d+) cycles\)$")


class AnalysisError(RuntimeError):
    pass


def _cells(line: str) -> list[str] | None:
    """Split a markdown table row into its cells, or `None` if it is not one."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def parse_record(text: str) -> dict:
    """Read the per-trial result table and the campaign's own declared shape."""
    record_id = _RECORD_ID_RE.search(text)
    if record_id is None:
        raise AnalysisError("record has no `Record ID` field")

    trials = _TRIALS_RE.search(text)
    if trials is None:
        raise AnalysisError(
            "record has no `Trials: N (seeds a..b, ...)` line -- is this a `--mc` "
            "record?"
        )

    overall = _OVERALL_RE.search(text)
    if overall is None:
        raise AnalysisError("record has no `Overall:` verdict line")

    rows: list[dict] = []
    seen_header = False
    for line in text.splitlines():
        cells = _cells(line)
        if cells is None:
            if seen_header and rows:
                continue
            continue
        if cells == _HEADER_CELLS:
            seen_header = True
            continue
        if not seen_header:
            continue
        if set("".join(cells)) <= {"-", ":"}:
            continue  # the header separator row
        if len(cells) != len(_HEADER_CELLS):
            raise AnalysisError(f"result row has {len(cells)} cells: {line!r}")
        rows.append(
            {
                "trial": int(cells[0]),
                "seed": int(cells[1]),
                "verdict": cells[2],
                "locked": cells[3].replace("*", ""),
                "jitter": cells[7],
            }
        )
    if not seen_header:
        raise AnalysisError("record has no per-trial result table")

    return {
        "record_id": record_id.group("record_id"),
        "declared_trials": int(trials.group("trials")),
        "seed_first": int(trials.group("first")),
        "seed_last": int(trials.group("last")),
        "overall": overall.group("verdict"),
        "passed": int(overall.group("passed")),
        "rows": rows,
    }


def parse_manifest(manifest: dict) -> dict:
    """Read the bound, the population floor and the sampling point from tb.json."""
    try:
        measure = manifest["measure"]
        jitter = measure["jitter"]
        mc = manifest["monte_carlo"]
        out = {
            "max_frac": float(jitter["max_frac"]),
            "min_cycles": int(jitter["min_cycles"]),
            "node": measure["node"],
            "tran_step": measure["tran_step"],
            "tran_stop": measure["tran_stop"],
            "corner": mc["corner"],
            "temp_c": mc["temp_c"],
            "supply_v": float(mc["supply_v"]),
            "mismatch": bool(mc["mismatch"]),
            "process": bool(mc["process"]),
            "trials": int(mc["trials"]),
            "seed_base": int(mc["seed_base"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisError(f"tb.json is missing or malformed: {exc}") from exc
    if out["max_frac"] != 0.01:
        raise AnalysisError(
            f"tb.json gates period jitter at {out['max_frac']} of the output period, "
            "but ratified spec row 9 (DR-006) is 1.0 % (0.01). The manifest and the "
            "ratified row disagree -- fix the manifest or the spec, do not grade "
            "against the drifted bound"
        )
    return out


def corner_id(manifest: dict) -> str:
    """The `<lib-corner>_<temp>c_<supply>v` id `sim/README.md` documents for a
    Monte Carlo trial's raw log, minus the per-trial `mc<n>_seed<n>_` prefix --
    the *population's* single sampling point, which is what
    `klt yield`'s `source_corners` names.
    """
    lib_corner = manifest["corner"] + ("_mm" if manifest["mismatch"] else "")
    return f"{lib_corner}_{manifest['temp_c']}c_{manifest['supply_v']:.2f}v"


def derive(record: dict, manifest: dict) -> dict:
    """Cross-check the record against its manifest and split the draws."""
    rows = record["rows"]
    if len(rows) != record["declared_trials"]:
        raise AnalysisError(
            f"record declares {record['declared_trials']} trials but its result "
            f"table has {len(rows)} rows"
        )
    if len(rows) != manifest["trials"]:
        raise AnalysisError(
            f"record's table has {len(rows)} rows but tb.json declares "
            f"{manifest['trials']} trials"
        )
    expected_seeds = list(
        range(manifest["seed_base"], manifest["seed_base"] + manifest["trials"])
    )
    if [row["seed"] for row in rows] != expected_seeds:
        raise AnalysisError(
            f"record's seeds {[r['seed'] for r in rows]} are not tb.json's "
            f"{expected_seeds}"
        )
    if (record["seed_first"], record["seed_last"]) != (
        expected_seeds[0],
        expected_seeds[-1],
    ):
        raise AnalysisError("record's declared seed range disagrees with its table")

    samples: list[float] = []
    sample_seeds: list[int] = []
    censored_seeds: list[int] = []
    for row in rows:
        locked = row["locked"]
        if locked not in {"yes", "no"}:
            raise AnalysisError(f"trial {row['trial']}: unreadable Locked cell")
        if locked == "no":
            if row["jitter"] != "-":
                raise AnalysisError(
                    f"trial {row['trial']}: no lock, but a period-jitter figure is "
                    "recorded -- row 9's population is post-lock"
                )
            censored_seeds.append(row["seed"])
            continue
        match = _JITTER_RE.match(row["jitter"])
        if match is None:
            raise AnalysisError(
                f"trial {row['trial']}: locked, but its period-jitter cell "
                f"{row['jitter']!r} is not `<pct>% (<n> cycles)`"
            )
        cycles = int(match.group("cycles"))
        if cycles < manifest["min_cycles"]:
            raise AnalysisError(
                f"trial {row['trial']}: {cycles} post-lock cycles is below the "
                f"manifest's jitter.min_cycles ({manifest['min_cycles']})"
            )
        samples.append(float(match.group("pct")))
        sample_seeds.append(row["seed"])

    if len(samples) < 2:
        raise AnalysisError(
            f"only {len(samples)} draw(s) produced a period-jitter figure -- "
            "`klt yield`'s hard floor is 2 usable samples, below which no "
            "confidence interval exists"
        )
    return {
        "samples": samples,
        "sample_seeds": sample_seeds,
        "censored_seeds": censored_seeds,
    }


def _provenance(record: dict, manifest: dict, derived: dict, mapping: str) -> dict:
    """Metadata `klt yield` ignores, carried so the document is self-describing
    if it is ever read (or content-hashed by `klt signoff`) on its own.
    """
    return {
        "generated_by": "sim/pll-lock-mc/analysis/yield_evidence.py",
        "source_record": f"sim/pll-lock-mc/records/{record['record_id']}.md",
        "source_manifest": "sim/pll-lock-mc/testbench/tb.json",
        "spec_row": 9,
        "spec_row_status": "RATIFIED (DR-006)",
        "sampling_point": corner_id(manifest),
        "seeds_with_a_measurement": derived["sample_seeds"],
        "seeds_censored_no_lock": derived["censored_seeds"],
        "censored_draw_mapping": mapping,
        "sample_precision_pp": 0.0005,
        "note": (
            "Derived, not measured: every value restates "
            f"sim/pll-lock-mc/records/{record['record_id']}.md at the precision "
            "that record prints. No target_yield is declared -- spec row 9 states "
            "a jitter bound, not a yield target."
        ),
    }


def samples_doc(record: dict, manifest: dict, derived: dict, *, as_failures: bool) -> dict:
    censored = len(derived["censored_seeds"])
    measurement = {
        "name": MEASUREMENT_NAME,
        "unit": "%",
        "samples": derived["samples"],
        "errored": 0 if as_failures else censored,
        "failed_unmeasurable": censored if as_failures else 0,
        "limits": {"max": manifest["max_frac"] * 100.0},
        "source_corners": [corner_id(manifest)],
    }
    mapping = "failed_unmeasurable" if as_failures else "errored"
    return {
        "provenance": _provenance(record, manifest, derived, mapping),
        "measurements": [measurement],
    }


def spec_limits_doc(manifest: dict) -> dict:
    return {
        "confidence": CONFIDENCE,
        "target_ci_halfwidth": TARGET_CI_HALFWIDTH,
        "measurements": {
            MEASUREMENT_NAME: {"max": manifest["max_frac"] * 100.0},
        },
    }


def _render(doc: dict) -> str:
    return json.dumps(doc, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Restate a sim/pll-lock-mc record as a `klt yield` sample-set document."
        )
    )
    parser.add_argument("record", type=Path, help="path to the record markdown")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "testbench" / "tb.json",
        help="path to the campaign's tb.json (default: this campaign's own)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help=f"write the documents to {OUTPUT_DIR}"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="re-derive the documents and fail if the committed copies differ",
    )
    args = parser.parse_args(argv)

    try:
        record = parse_record(args.record.read_text())
        manifest = parse_manifest(json.loads(args.manifest.read_text()))
        derived = derive(record, manifest)
    except (AnalysisError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    documents = {
        _PRIMARY_SAMPLES: samples_doc(record, manifest, derived, as_failures=False),
        _VARIANT_SAMPLES: samples_doc(record, manifest, derived, as_failures=True),
        _SPEC_LIMITS: spec_limits_doc(manifest),
    }

    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, doc in documents.items():
            (OUTPUT_DIR / name).write_text(_render(doc))
            print(f"wrote {OUTPUT_DIR / name}")
        return 0

    if args.check:
        drift = []
        for name, doc in documents.items():
            path = OUTPUT_DIR / name
            try:
                committed = path.read_text()
            except OSError as exc:
                drift.append(f"{path}: {exc}")
                continue
            if committed != _render(doc):
                drift.append(f"{path}: differs from what this record derives")
        if drift:
            print(
                "error: the committed yield-evidence documents no longer match what "
                f"{args.record} derives:",
                file=sys.stderr,
            )
            for line in drift:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"{OUTPUT_DIR} is current.")
        return 0

    for name, doc in documents.items():
        print(f"=== {name}")
        print(_render(doc), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
