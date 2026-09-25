#!/usr/bin/env python3
"""Can a negative control on THIS campaign ever be reported `detected`?

T1 item 6 wants a deterministic negative control, and `signoff/run-signoff.sh`'s
guard 3 will only accept a cited `klt yield` report whose `negative_control`
carries `verdict: "detected"`. Issue #195 was filed to build that control -- a
seeded, deliberately degraded variant of the DUT, re-drawn through
`sim/pll-lock-mc` -- and its own open question 3 asks, before any of that
simulator time is spent, whether `klt yield` *could* report `detected` at all
over a nominal population whose empirical yield is 0 %.

This script answers that question, and the answer is **no**.

## The rule

`klt yield` decides the verdict with two comparisons and nothing else
(`native/yield/src/estimate.rs:1193-1199` at upstream tag `v0.6.0`, commit
`c622e8ad` -- the revision that built the reports committed under
`yield-evidence/`, see that directory's README):

    let degradation_detected = empirical.estimate < nominal_empirical.estimate
        && empirical.confidence_interval.high < nominal_empirical.confidence_interval.low;

`empirical` there is the control's own Clopper-Pearson yield, `nominal_empirical`
the nominal measurement's. Both are proportions of a draw count, so both the
control's point estimate and the upper end of its interval are **>= 0 by
construction** -- no sample set can produce a negative one.

This campaign's committed report gives the nominal side as `estimate` = 0.0 with
a 95 % interval of [0.0, 0.7076]: not one of the three measurable draws met
ratified row 9's 1.0 % bound. Substituting those two zeros leaves

    (something >= 0) < 0   AND   (something >= 0) < 0

which is unsatisfiable. **No negative control -- at any population size, at any
degradation, however deliberate -- can be reported `detected` over a campaign
whose empirical yield is zero.** A floor-bounded yield has nothing below it to
degrade toward.

## Why this is committed as evidence rather than asserted

Reading the rule out of the tool's source is a claim about the tool, so this
directory also commits six executed probes (`negative-control/probes/*.json`
as inputs, `negative-control/reports/*.json` as `klt yield`'s own outputs over
them). They are evidence about **`klt yield`**, not about the PLL: their
populations are synthetic, and the only two sample values they use are 0.500 %
(inside row 9's bound) and 2.169 % (outside it -- the campaign's own fitted
mean, so even the synthetic failing draw is anchored to a committed figure).
Probe 6 reports `detected`, which is what makes probes 1-5's `not_detected` a
property of the populations under test rather than of a broken probe harness.

Reproduce them with `bash sim/pll-lock-mc/analysis/klt-yield-env.sh`, which
builds the pinned extension and re-runs every committed `klt yield` output in
this directory, the probes included.

## What it takes to make `detected` reachable

The control's own population size sets a floor on the nominal yield, because the
rule compares the control's interval *upper* bound against the nominal's
*lower* one. Probes 4-6 measure that floor directly, and probe 4 is the one
worth reading before spending anything on #195: a 5-draw control against a
5-draw nominal cannot be `detected` **even when every nominal draw passes**.
The population #195 costs at 5 draws is unreachable by construction, not merely
expensive.

Usage:

    # print the reachability document to stdout
    python3 sim/pll-lock-mc/analysis/negative_control_reachability.py

    # (re)write the probe input documents
    python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --write-probes

    # (re)write sim/pll-lock-mc/analysis/negative-control/reachability.md
    python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --write

    # re-derive and verify everything committed (exit 1 on any drift)
    python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --check

It is an `analysis/` script in the sense `sim/README.md` defines: mutable,
stdlib-only, it reads committed artifacts and restates what they already say,
and it never simulates. No PDK, ngspice, xschem or `klt` required -- the `klt
yield` outputs it reads are committed, exactly like the campaign's own report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

YIELD_EVIDENCE = HERE / "yield-evidence"
NOMINAL_REPORT = YIELD_EVIDENCE / "klt-yield-report.json"
CENSORED_REPORT = YIELD_EVIDENCE / "klt-yield-report-censored-as-failures.json"

OUTDIR = HERE / "negative-control"
PROBE_DIR = OUTDIR / "probes"
PROBE_REPORT_DIR = OUTDIR / "reports"
OUTPUT = OUTDIR / "reachability.md"

MEASUREMENT = "period_jitter_rms_pct"
BOUND_PCT = 1.0

#: A synthetic draw inside ratified row 9's bound. No draw of the real campaign
#: is; this value exists only to give the probes a passing sample.
PASSING = 0.500
#: A synthetic draw outside the bound -- the campaign's own fitted mean, so the
#: failing sample is anchored to a committed figure rather than invented.
FAILING = 2.169

#: The strongest degradation `klt yield`'s schema can express: every draw leaves
#: the regime the measurement is defined in, so the control's empirical yield is
#: 0 passes out of `failed_unmeasurable` draws. `estimate.rs`'s own unit test
#: `a_negative_control_seeded_entirely_with_failed_unmeasurable_is_detected`
#: expects this shape to be `detected` -- against a nominal that leaves room.
def control(n: int) -> dict:
    return {
        "description": f"{n} draws, none measurable -- the strongest degradation the schema expresses",
        "samples": [],
        "errored": 0,
        "failed_unmeasurable": n,
    }


def measurement(passing: int, failing: int, errored: int, nc: dict) -> dict:
    return {
        "name": MEASUREMENT,
        "unit": "%",
        "samples": [PASSING] * passing + [FAILING] * failing,
        "errored": errored,
        "failed_unmeasurable": 0,
        "limits": {"max": BOUND_PCT},
        "source_corners": ["tt_mm_125c_1.80v"],
        "negative_control": nc,
    }


#: (id, question it answers, nominal passing/failing/errored, control size,
#:  the verdict the committed report must carry)
PROBES: tuple[tuple[str, str, int, int, int, int, str], ...] = (
    (
        "p1-campaign-as-is",
        "the committed campaign itself (3 measurable draws, none passing, 2 censored as "
        "`errored`) against the strongest control the schema can express",
        0,
        3,
        2,
        1000,
        "not_detected",
    ),
    (
        "p2-campaign-sized-all-missing",
        "the same campaign widened to `required_n` = 183 measurable draws, still missing "
        "row 9 on every one -- does sizing the population make the control fire?",
        0,
        183,
        0,
        1000,
        "not_detected",
    ),
    (
        "p3-campaign-sized-one-passing",
        "183 draws of which exactly one meets row 9 -- is 'some draw passed' enough, or is "
        "the threshold on the nominal interval's lower bound?",
        1,
        182,
        0,
        1000,
        "not_detected",
    ),
    (
        "p4-control-same-size-best-case",
        "a 5-draw control against a 5-draw nominal in which **every** draw passes -- the best "
        "a campaign of this size can possibly do, against the control size #195 costs at "
        "5 draws",
        5,
        0,
        0,
        5,
        "not_detected",
    ),
    (
        "p5-sized-threshold-below",
        "183 nominal draws, 8 passing, against a same-size 183-draw control -- one draw below "
        "the threshold probe 6 finds",
        8,
        175,
        0,
        183,
        "not_detected",
    ),
    (
        "p6-sized-threshold-at",
        "183 nominal draws, 9 passing, against the same 183-draw control -- the smallest "
        "passing count at which this pairing is `detected`, and the positive control for "
        "the whole probe set",
        9,
        174,
        0,
        183,
        "detected",
    ),
)


def probe_document(probe: tuple) -> dict:
    _id, question, passing, failing, errored, nc_n, _verdict = probe
    return {
        "provenance": {
            "generated_by": "sim/pll-lock-mc/analysis/negative_control_reachability.py",
            "purpose": "a probe of `klt yield`'s negative-control detection rule, not evidence "
            "about the PLL -- the population is synthetic",
            "question": question,
            "nominal_population": {
                "passing_draws": passing,
                "failing_draws": failing,
                "errored_draws": errored,
                "passing_sample_pct": PASSING,
                "failing_sample_pct": FAILING,
            },
            "negative_control_draws": nc_n,
            "limit": f"period jitter <= {BOUND_PCT} % RMS (ratified spec row 9, DR-006)",
        },
        "measurements": [measurement(passing, failing, errored, control(nc_n))],
    }


def render_probe(probe: tuple) -> str:
    return json.dumps(probe_document(probe), indent=2) + "\n"


def _empirical(report: dict) -> dict:
    return report["measurements"][0]["yield"]["empirical"]


def reachability(estimate: float, ci_low: float) -> tuple[bool, str]:
    """Is `detected` satisfiable against a nominal with these two figures?

    The rule needs a control whose point estimate is strictly below `estimate`
    *and* whose interval's upper bound is strictly below `ci_low`. Both control
    quantities are proportions of a draw count, hence >= 0, so a nominal that
    is 0 on either side makes that conjunct unsatisfiable.
    """
    if estimate <= 0.0 or ci_low <= 0.0:
        return False, "**unreachable** -- no control can be below both"
    return True, (
        f"reachable -- a control needs a yield below {estimate:.6f} and an interval "
        f"upper bound below {ci_low:.6f}"
    )


def load_probe_reports() -> dict[str, dict]:
    out = {}
    for probe in PROBES:
        path = PROBE_REPORT_DIR / f"{probe[0]}.json"
        if not path.is_file():
            raise SystemExit(
                f"missing committed klt yield output {path.relative_to(REPO)} -- "
                f"regenerate with `bash sim/pll-lock-mc/analysis/klt-yield-env.sh`"
            )
        out[probe[0]] = json.loads(path.read_text())
    return out


def render(nominal: dict, censored: dict, probe_reports: dict[str, dict]) -> str:
    nom = _empirical(nominal)
    cen = _empirical(censored)
    ok, nom_verdict = reachability(nom["estimate"], nom["confidence_interval"]["low"])
    _, cen_verdict = reachability(cen["estimate"], cen["confidence_interval"]["low"])

    lines: list[str] = []
    a = lines.append
    a("# Can this campaign's negative control ever be `detected`?")
    a("")
    a(
        "**Generated** by `sim/pll-lock-mc/analysis/negative_control_reachability.py` -- do not "
        "edit. `python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --check` "
        "re-derives every figure below from the committed artifact that carries it and fails on "
        "any drift; it runs in `npm run check:ci`."
    )
    a("")
    a(
        "T1 item 6 requires a deterministic negative control, and "
        "`signoff/run-signoff.sh`'s guard 3 will only accept a citation whose "
        "`negative_control.verdict` is `detected`. #195 was filed to build that control as a "
        "seeded, degraded variant of the DUT re-drawn through this campaign, and its own open "
        "question 3 asks whether `detected` is reachable at all before that simulator time is "
        "spent. This document answers it."
    )
    a("")
    a(f"**Verdict: `detected` is {'REACHABLE' if ok else 'UNREACHABLE'} over this campaign.**")
    a("")
    a("## The rule")
    a("")
    a(
        "`klt yield` decides the verdict with two comparisons and nothing else "
        "(`native/yield/src/estimate.rs:1193-1199`, upstream tag `v0.6.0` / commit `c622e8ad` -- "
        "the revision that built every `klt yield` output committed in this directory):"
    )
    a("")
    a("```rust")
    a("let degradation_detected = empirical.estimate < nominal_empirical.estimate")
    a(
        "    && empirical.confidence_interval.high < nominal_empirical.confidence_interval.low;"
    )
    a("```")
    a("")
    a(
        "`empirical` is the control's own Clopper-Pearson yield, `nominal_empirical` the nominal "
        "measurement's. Both of the control's quantities are proportions of a draw count, so "
        "both are **>= 0 by construction**."
    )
    a("")
    a("## The two fields that settle it")
    a("")
    a("| Mapping of the two censored draws | `yield.empirical.estimate` | interval lower bound | reachability |")
    a("| --- | --- | --- | --- |")
    a(
        f"| `errored` (primary) -- `{NOMINAL_REPORT.relative_to(REPO)}` | {nom['estimate']:.6f} | "
        f"{nom['confidence_interval']['low']:.6f} | {nom_verdict} |"
    )
    a(
        f"| `failed_unmeasurable` (sensitivity check) -- `{CENSORED_REPORT.relative_to(REPO)}` | "
        f"{cen['estimate']:.6f} | {cen['confidence_interval']['low']:.6f} | {cen_verdict} |"
    )
    a("")
    a(
        "Both mappings put the nominal estimate and its interval's lower bound at zero: not one "
        "of the draws that produced a measurement met ratified row 9's 1.0 % bound. Substituting "
        "those zeros leaves `(something >= 0) < 0` on both sides of the `&&`, which no control "
        "can satisfy."
    )
    a("")
    a("## The probes")
    a("")
    a(
        "Reading a rule out of the tool's source is a claim about the tool, so it is checked "
        "rather than asserted. Each row is an executed `klt yield` run whose input and output "
        "are both committed under `negative-control/`. The populations are **synthetic** -- "
        "these are evidence about `klt yield`, not about the PLL -- and use exactly two sample "
        f"values: {PASSING:.3f} % (inside row 9's bound) and {FAILING:.3f} % (outside it, the "
        "campaign's own fitted mean). Every control is the strongest degradation the schema can "
        "express: every draw `failed_unmeasurable`, i.e. 0 passes out of N."
    )
    a("")
    a("| Probe | Nominal | Control | Verdict | What it settles |")
    a("| --- | --- | --- | --- | --- |")
    for probe in PROBES:
        pid, question, passing, failing, errored, nc_n, _expected = probe
        report = probe_reports[pid]
        m = report["measurements"][0]
        nc = m["negative_control"]
        nominal_e = m["yield"]["empirical"]
        nc_e = nc["yield"]["empirical"]
        drawn = passing + failing
        nom_cell = (
            f"{passing}/{drawn} passing"
            + (f", {errored} errored" if errored else "")
            + f"<br>est {nominal_e['estimate']:.6f}, CI low {nominal_e['confidence_interval']['low']:.6f}"
        )
        nc_cell = (
            f"{nc_n} draws, none measurable"
            f"<br>est {nc_e['estimate']:.6f}, CI high {nc_e['confidence_interval']['high']:.6f}"
        )
        a(f"| `{pid}` | {nom_cell} | {nc_cell} | **`{nc['verdict']}`** | {question} |")
    a("")
    a("Three things those rows establish that prose could not:")
    a("")
    a(
        "1. **Probe 1**: the campaign as committed cannot produce `detected`, and the control it "
        "is checked against is not a weak one -- it is 1000 draws, every one of them outside the "
        "measurable regime. There is no stronger control to build."
    )
    a(
        "2. **Probes 2 and 3**: neither widening the population to `required_n` = 183 nor "
        "landing a single passing draw changes that. The threshold is on the nominal interval's "
        "*lower* bound, which a near-zero yield does not lift past even a 1000-draw control's "
        "upper bound."
    )
    a(
        "3. **Probe 4**: a control the size #195 costs at 5 draws, checked against a 5-draw "
        "nominal in which *every* draw passes, is still `not_detected`. At these population "
        "sizes the pairing is unreachable no matter how good the design or how bad the control: "
        "a 5-draw control's own 95 % interval still reaches "
        f"{probe_reports['p4-control-same-size-best-case']['measurements'][0]['negative_control']['yield']['empirical']['confidence_interval']['high']:.6f}, "
        "while the best lower bound a 5-draw nominal can reach -- at 5 of 5 passing -- is "
        f"{probe_reports['p4-control-same-size-best-case']['measurements'][0]['yield']['empirical']['confidence_interval']['low']:.6f}. "
        "Five draws a side is simply too few for two exact binomial intervals to separate."
    )
    a("")
    a(
        "Probes 5 and 6 are the positive control for the set: one passing draw apart, at 183 "
        "draws a side, they straddle the threshold and probe 6 reports `detected`. The harness "
        "can produce both verdicts, so probes 1-4 report their populations rather than a broken "
        "probe."
    )
    a("")
    a("## What this changes")
    a("")
    a(
        "Item 6's negative control is **not gated on simulator time**, and buying it first would "
        "buy a control that cannot fire. It is gated on the nominal campaign having a yield whose "
        "interval clears the control's -- which is to say on **the design meeting ratified row 9 "
        "in enough draws**, a design precondition rather than a sampling or tooling one. Both "
        "halves of this issue's remaining spend are affected:"
    )
    a("")
    a(
        "- **#195** (the degraded-design control, ~6.7 h at 5 draws) cannot close item 6's "
        "negative-control precondition while row 9 is missed by every draw, and at 5 draws a side "
        "cannot close it even if row 9 were met by all of them. Probe 4 is the number to read "
        "before sizing it."
    )
    a(
        "- **The sized campaign** (~400 h for `required_n` = 183) does not help either: probe 2 "
        "is that campaign, and it is still `not_detected`. `sim/pll-lock-mc/analysis/README.md` "
        "already argued that spend sharpens an interval rather than changing a verdict; this adds "
        "that it does not unlock the negative-control precondition as a side effect."
    )
    a("")
    a(
        "The escape hatch `signoff/run-signoff.sh`'s guard 3 names -- an argued record of why "
        "`not_detected` is honest for the limit it is checked against -- is therefore the *only* "
        "outcome this campaign can currently reach, and this document is the argument it would "
        "rest on. It is not enough on its own to cite item 6: guard 3 still requires a sized "
        "population (`signoff/item6-preconditions.md` row 5), and `klt yield` still cannot be "
        "reached from this repo's own pin (klayout-tools#2466), so no report *declaring* a "
        "control can be produced under it. What this settles is the ordering question #195 asked, "
        "and it settles it against spending the simulator time first."
    )
    a("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--write-probes", action="store_true", help="write the probe input documents"
    )
    mode.add_argument("--write", action="store_true", help=f"write {OUTPUT.name}")
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify the committed probes and document, exit 1 on drift",
    )
    args = ap.parse_args(argv)

    if args.write_probes:
        PROBE_DIR.mkdir(parents=True, exist_ok=True)
        for probe in PROBES:
            path = PROBE_DIR / f"{probe[0]}.json"
            path.write_text(render_probe(probe))
            print(f"wrote {path.relative_to(REPO)}")
        return 0

    nominal = json.loads(NOMINAL_REPORT.read_text())
    censored = json.loads(CENSORED_REPORT.read_text())
    probe_reports = load_probe_reports()

    # The committed klt yield outputs must be the ones these probes describe,
    # or the table below would report a different experiment than it names.
    for probe in PROBES:
        pid, _q, passing, failing, errored, nc_n, expected = probe
        m = probe_reports[pid]["measurements"][0]
        got = m["negative_control"]["verdict"]
        if got != expected:
            print(
                f"ERROR: probe {pid}: committed report says verdict {got!r}, "
                f"this script expects {expected!r}",
                file=sys.stderr,
            )
            return 1
        if m["n"] != passing + failing or m["errored"] != errored:
            print(
                f"ERROR: probe {pid}: committed report is over a different population "
                f"(n={m['n']}, errored={m['errored']}) than this script describes "
                f"(n={passing + failing}, errored={errored})",
                file=sys.stderr,
            )
            return 1
        if m["negative_control"]["failed_unmeasurable"] != nc_n:
            print(
                f"ERROR: probe {pid}: committed report's control has "
                f"{m['negative_control']['failed_unmeasurable']} draws, not {nc_n}",
                file=sys.stderr,
            )
            return 1

    text = render(nominal, censored, probe_reports)

    if args.write:
        OUTDIR.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO)}")
        return 0

    if args.check:
        failures = []
        for probe in PROBES:
            path = PROBE_DIR / f"{probe[0]}.json"
            if not path.is_file():
                failures.append(f"{path.relative_to(REPO)} is missing")
            elif path.read_text() != render_probe(probe):
                failures.append(f"{path.relative_to(REPO)} has drifted")
        if not OUTPUT.is_file():
            failures.append(f"{OUTPUT.relative_to(REPO)} is missing")
        elif OUTPUT.read_text() != text:
            failures.append(f"{OUTPUT.relative_to(REPO)} has drifted")
        if failures:
            for f in failures:
                print(f"ERROR: {f}", file=sys.stderr)
            print(
                "re-derive with `--write-probes` / `--write` (and re-run "
                "`bash sim/pll-lock-mc/analysis/klt-yield-env.sh` if a probe input changed)",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT.relative_to(REPO)} and {len(PROBES)} probe inputs are current.")
        return 0

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
