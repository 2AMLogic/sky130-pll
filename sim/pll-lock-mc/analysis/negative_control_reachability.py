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
*lower* one. That floor is a Clopper-Pearson quantity and nothing else, so the
whole frontier -- for every nominal size, passing count and control size, not
only the six probed ones -- is arithmetic. This script derives it, and checks
its own arithmetic against every committed `klt yield` output before rendering
a word of it: each probe's nominal interval lower bound, control interval upper
bound, `negative_control.verdict` and `sample_size` must all come back out of
the formulas. A disagreement is a hard failure, not a warning.

Two readings fall out that the probes alone do not give:

1. **The pairing is asymmetric.** Probe 4 (a 5-draw control against a 5-draw
   nominal in which every draw passes) is `not_detected`, and it is tempting to
   read that as "five draws is too few". It is not: the same 5-of-5 nominal
   against a **6**-draw control is `detected` (probe 7). What probe 4 measures
   is the diagonal `n_control = n_nominal`, not a population floor.
2. **Guard 3's two conditions pull against each other.** The citation also needs
   `sample_size.verdict` = `sufficient`, and `required_n` is smallest at a
   pass rate of 0 or 1 and largest in between. The campaign is sized today only
   because *no* draw passes; the first draws that pass make it unsized, and the
   cheapest way back is not part-way but all the way to a design that meets
   row 9 on every draw. Probes 10 and 11 measure both sides of that.

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
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

YIELD_EVIDENCE = HERE / "yield-evidence"
NOMINAL_REPORT = YIELD_EVIDENCE / "klt-yield-report.json"
CENSORED_REPORT = YIELD_EVIDENCE / "klt-yield-report-censored-as-failures.json"
SPEC_LIMITS = YIELD_EVIDENCE / "spec-limits.json"

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

#: `klt yield` refuses a control with fewer than 2 draws ("it needs its own
#: confidence interval to be checkable, exactly like the nominal measurement"),
#: so 2 is the floor on what a control can cost, whatever the nominal looks like.
MIN_CONTROL_DRAWS = 2

#: Wall-clock per Monte Carlo trial. Not derived here -- this is the figure
#: `sim/pll-lock-mc/analysis/README.md` already reads off the record's own
#: execution notes, reused so the cost columns below and that README's
#: "= 400 h" arithmetic cannot drift apart.
HOURS_PER_TRIAL = 4.0 / 3.0

#: Grid the derived frontier is rendered over. Nominal sizes span the committed
#: campaign (3 measurable draws) to `required_n` = 183; control sizes span the
#: 2-draw floor to the 1000-draw control probes 1-3 use.
FRONTIER_NOMINAL_SIZES: tuple[int, ...] = (3, 5, 10, 20, 50, 100, 183)
FRONTIER_CONTROL_SIZES: tuple[int, ...] = (2, 5, 6, 20, 50, 183, 1000)

#: Pass rates the joint-cost table is rendered at, as (passing, measurable)
#: pairs chosen so each row is the *smallest* campaign that is sized at that
#: rate -- see `required_n` below. 183/183 is the cheapest point on the whole
#: joint frontier; the rest show how fast it gets worse away from it.
JOINT_COST_POPULATIONS: tuple[tuple[int, int], ...] = (
    (183, 183),
    (195, 196),
    (386, 390),
    (847, 867),
    (4802, 9604),
    (1800, 7202),
    (345, 3454),
)


# --------------------------------------------------------------------------
# Clopper-Pearson, and `klt yield`'s sample-size rule
#
# Both are re-derived here rather than read off the reports, because the
# question this script answers is about populations that have NOT been run.
# Neither is trusted on sight: `check_arithmetic_against_probes` below drives
# every formula through every committed `klt yield` output first, and the
# document does not render if any of them disagrees.
# --------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction expansion for the incomplete beta function."""
    maxit, eps, fpmin = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _betainv(p: float, a: float, b: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def cp_low(k: int, n: int, alpha: float) -> float:
    """Lower end of the two-sided Clopper-Pearson interval for k of n."""
    if k <= 0:
        return 0.0
    return _betainv(alpha / 2.0, k, n - k + 1)


def cp_high(k: int, n: int, alpha: float) -> float:
    """Upper end of the two-sided Clopper-Pearson interval for k of n."""
    if k >= n:
        return 1.0
    return _betainv(1.0 - alpha / 2.0, k + 1, n - k)


def required_n(k: int, n: int, alpha: float, halfwidth: float) -> int:
    """`klt yield`'s own `sample_size.required_n`, re-derived.

    Two branches, both confirmed against committed reports: at an observed
    proportion of exactly 0 or exactly 1 it uses the exact zero-failures
    interval (whose halfwidth depends only on `n`), otherwise the normal
    approximation z^2 p(1-p) / h^2.
    """
    p = k / n
    if p in (0.0, 1.0):
        return math.ceil(math.log(alpha / 2.0) / math.log(1.0 - 2.0 * halfwidth))
    z = _normal_quantile(1.0 - alpha / 2.0)
    return math.ceil(z * z * p * (1.0 - p) / (halfwidth * halfwidth))


def _normal_quantile(p: float) -> float:
    """Inverse standard-normal CDF, by bisection on `math.erf`."""
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def is_sized(k: int, n: int, alpha: float, halfwidth: float) -> bool:
    """Would `klt yield` call this population's estimate `sufficient`?"""
    return required_n(k, n, alpha, halfwidth) <= n


def is_detected(k: int, n: int, nc: int, alpha: float) -> bool:
    """`klt yield`'s negative-control verdict for an all-failing control.

    Mirrors `estimate.rs` exactly: the control's point estimate strictly below
    the nominal's, and the control's interval upper bound strictly below the
    nominal's interval lower bound. An all-failing control has a point estimate
    of 0, so the first conjunct reduces to "the nominal has at least one pass".
    """
    if k <= 0:
        return False
    return cp_high(0, nc, alpha) < cp_low(k, n, alpha)


def min_passing(n: int, nc: int, alpha: float) -> int | None:
    """Fewest passing draws of `n` at which an `nc`-draw control is `detected`."""
    lo, hi = 1, n
    if not is_detected(hi, n, nc, alpha):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if is_detected(mid, n, nc, alpha):
            hi = mid
        else:
            lo = mid + 1
    return lo


def min_control(k: int, n: int, alpha: float) -> int | None:
    """Smallest control population at which k of n nominal draws is `detected`."""
    if k <= 0:
        return None
    target = cp_low(k, n, alpha)
    nc = MIN_CONTROL_DRAWS
    guess = math.ceil(math.log(alpha / 2.0) / math.log(1.0 - target))
    nc = max(nc, guess)
    while not is_detected(k, n, nc, alpha):
        nc += 1
        if nc > 10 ** 7:
            return None
    return nc


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
    (
        "p7-small-nominal-asymmetric-control",
        "the same 5-of-5 nominal as probe 4, against a **6**-draw control -- is probe 4's "
        "`not_detected` a property of the population size, or only of the `n_control = "
        "n_nominal` diagonal it sits on?",
        5,
        0,
        0,
        6,
        "detected",
    ),
    (
        "p8-sized-cheap-control-below",
        "183 nominal draws, 20 passing, against a 50-draw control -- one draw below the "
        "threshold probe 9 finds, off the diagonal probes 5 and 6 straddle",
        20,
        163,
        0,
        50,
        "not_detected",
    ),
    (
        "p9-sized-cheap-control-at",
        "183 nominal draws, 21 passing, against the same 50-draw control -- a control less "
        "than a third the size of probe 6's, bought with 12 more passing nominal draws",
        21,
        162,
        0,
        50,
        "detected",
    ),
    (
        "p10-both-guard-3-conditions",
        "183 nominal draws, **every one** passing, against a control at `klt yield`'s own "
        "2-draw floor -- the only population probed here that is `detected` **and** whose "
        "`sample_size.verdict` is `sufficient`, i.e. the cheapest campaign guard 3 would "
        "actually accept",
        183,
        0,
        0,
        2,
        "detected",
    ),
    (
        "p11-one-failing-draw",
        "the same campaign with a single draw missing row 9 -- still `detected`, but no "
        "longer sized: one failure moves `required_n` off the exact zero-failures branch, "
        "which is what makes the two guard-3 conditions pull against each other",
        182,
        1,
        0,
        2,
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


def load_spec_limits() -> tuple[float, float]:
    """The campaign's own declared confidence and target interval halfwidth.

    Read rather than hardcoded: these two numbers set every threshold below,
    and `yield-evidence/spec-limits.json` is the document `klt yield` itself
    was run with.
    """
    limits = json.loads(SPEC_LIMITS.read_text())
    confidence = float(limits["confidence"])
    halfwidth = float(limits["target_ci_halfwidth"])
    return 1.0 - confidence, halfwidth


def check_arithmetic_against_probes(
    probe_reports: dict[str, dict], alpha: float, halfwidth: float, tol: float = 1e-9
) -> list[str]:
    """Drive every formula above through every committed `klt yield` output.

    The derived frontier describes populations nobody has run, so the only
    thing that makes it evidence rather than assertion is that the same
    formulas reproduce the tool's answers on the populations that *have* been
    run -- interval bounds, negative-control verdict, `required_n` and the
    sample-size verdict, on all of them.
    """
    problems: list[str] = []
    for probe in PROBES:
        pid, _q, passing, failing, _errored, nc_n, _expected = probe
        n = passing + failing
        m = probe_reports[pid]["measurements"][0]
        nom = m["yield"]["empirical"]
        ctl = m["negative_control"]["yield"]["empirical"]
        size = m["sample_size"]

        checks = (
            ("nominal interval lower bound", cp_low(passing, n, alpha), nom["confidence_interval"]["low"]),
            ("nominal interval upper bound", cp_high(passing, n, alpha), nom["confidence_interval"]["high"]),
            ("control interval upper bound", cp_high(0, nc_n, alpha), ctl["confidence_interval"]["high"]),
        )
        for what, derived, reported in checks:
            if abs(derived - reported) > tol:
                problems.append(
                    f"probe {pid}: derived {what} {derived!r} disagrees with the committed "
                    f"klt yield output's {reported!r}"
                )

        derived_verdict = "detected" if is_detected(passing, n, nc_n, alpha) else "not_detected"
        if derived_verdict != m["negative_control"]["verdict"]:
            problems.append(
                f"probe {pid}: derived negative-control verdict {derived_verdict!r} disagrees "
                f"with the committed klt yield output's {m['negative_control']['verdict']!r}"
            )

        derived_required = required_n(passing, n, alpha, halfwidth)
        if derived_required != size["required_n"]:
            problems.append(
                f"probe {pid}: derived required_n {derived_required} disagrees with the "
                f"committed klt yield output's {size['required_n']}"
            )
        derived_sized = "sufficient" if is_sized(passing, n, alpha, halfwidth) else "insufficient"
        if derived_sized != size["verdict"]:
            problems.append(
                f"probe {pid}: derived sample-size verdict {derived_sized!r} disagrees with "
                f"the committed klt yield output's {size['verdict']!r}"
            )
    return problems


def _draws_for(measurable: int, lock_rate: float) -> int:
    """Drawn trials needed to land `measurable` draws at the observed lock rate."""
    return math.ceil(measurable / lock_rate)


def render_frontier(alpha: float) -> list[str]:
    """Table A: how many nominal draws must pass, by nominal and control size."""
    lines: list[str] = []
    a = lines.append
    a("## What would make it reachable")
    a("")
    a(
        "The rule is a comparison of two Clopper-Pearson intervals and nothing else, so the "
        "answer for populations nobody has run is arithmetic rather than opinion. This script "
        "derives it -- and checks its own arithmetic against **every** committed `klt yield` "
        "output above before rendering: each probe's two nominal interval bounds, its control's "
        "interval upper bound, its `negative_control.verdict`, its `required_n` and its "
        "`sample_size.verdict` all have to come back out of the formulas. They do, on all "
        f"{len(PROBES)} of them; a single disagreement makes this document refuse to render."
    )
    a("")
    a(
        "Each cell is the **fewest nominal draws that must meet row 9** for an all-failing "
        "control of that size to be reported `detected`. `--` means no passing count works at "
        "that pairing, even if every draw passes."
    )
    a("")
    header = " | ".join(f"control = {nc}" for nc in FRONTIER_CONTROL_SIZES)
    a(f"| nominal measurable draws | {header} |")
    a("| --- |" + " --- |" * len(FRONTIER_CONTROL_SIZES))
    for n in FRONTIER_NOMINAL_SIZES:
        cells = []
        for nc in FRONTIER_CONTROL_SIZES:
            k = min_passing(n, nc, alpha)
            cells.append("--" if k is None else f"{k} ({k / n * 100:.0f} %)")
        a(f"| {n} | " + " | ".join(cells) + " |")
    a("")
    a(
        "**Probe 4 measures the diagonal, not a floor.** Its 5-draw control against a 5-of-5 "
        "nominal is `not_detected`, which reads like \"five draws is too few\" -- and the row "
        "above says it is not. The same 5-of-5 nominal against a **6**-draw control is "
        "`detected`, and probe 7 is that run: one extra control draw, opposite verdict. What "
        "probe 4 settles is that a control sized to match its nominal cannot separate from it "
        "at these counts, which is a statement about the pairing `#195` was about to buy, not "
        "about small populations in general."
    )
    a("")
    a(
        "The table also prices the trade the other way. Probe 6 needs a 183-draw control and 9 "
        "passing nominal draws; probe 9 gets the same `detected` from a control less than a "
        "third that size, bought with 12 more passing draws (21 of 183). Probe 8 is the same "
        "pairing one passing draw lower, so that threshold is straddled too rather than "
        "asserted."
    )
    return lines


def render_joint_cost(alpha: float, halfwidth: float, lock_rate: float, drawn: int, measurable: int) -> list[str]:
    """Table B: what a campaign guard 3 would actually accept costs."""
    lines: list[str] = []
    a = lines.append
    a("## Both of guard 3's conditions at once")
    a("")
    a(
        "`signoff/run-signoff.sh`'s guard 3 wants two things of a cited report, and the "
        "reachability question above is only the second of them: every measurement's "
        "`sample_size.verdict` must be `sufficient`, **and** its `negative_control.verdict` "
        "must be `detected`. Those two conditions are not independent, and the direction they "
        "pull in is the opposite of the obvious one."
    )
    a("")
    a(
        f"`klt yield` sizes an estimate against the {halfwidth:.2f} absolute interval halfwidth "
        f"`{SPEC_LIMITS.relative_to(REPO)}` declares. At an observed pass rate of exactly 0 or "
        "exactly 1 it uses the exact zero-failures interval, whose halfwidth depends only on "
        f"the draw count -- hence `required_n` = {required_n(0, 183, alpha, halfwidth)}, the "
        "figure every document here quotes. At any rate in between it switches to the normal "
        "approximation, where `required_n` scales with `p(1-p)` and therefore **peaks in the "
        "middle**. Measured across the committed probes rather than argued:"
    )
    a("")
    a("| Probe | Nominal | `required_n` | `sample_size.verdict` | `negative_control.verdict` | both? |")
    a("| --- | --- | --- | --- | --- | --- |")
    for probe in PROBES:
        pid, _q, passing, failing, _errored, nc_n, _expected = probe
        n = passing + failing
        rn = required_n(passing, n, alpha, halfwidth)
        sized = is_sized(passing, n, alpha, halfwidth)
        det = is_detected(passing, n, nc_n, alpha)
        both = "**yes**" if (sized and det) else "no"
        a(
            f"| `{pid}` | {passing}/{n} passing | {rn} | "
            f"{'`sufficient`' if sized else '`insufficient`'} | "
            f"{'`detected`' if det else '`not_detected`'} | {both} |"
        )
    a("")
    a(
        "Probe 10 is the only row with a **yes**, and it is the cheapest one there is: 183 "
        "measurable draws with *every* draw meeting row 9, against a control at `klt yield`'s "
        f"own {MIN_CONTROL_DRAWS}-draw minimum. Probe 11 is that same campaign with a single "
        "draw missing the bound -- still `detected`, no longer sized, because one failure moves "
        f"it off the zero-failures branch and `required_n` goes to "
        f"{required_n(182, 183, alpha, halfwidth)}."
    )
    a("")
    a(
        "So the cost of a citable item 6 is a function of how well the design does, and it is "
        "**not monotone**. Each row below is the smallest campaign that is sized at that pass "
        f"rate, the smallest control that is then `detected`, and what the pair costs at the "
        f"{measurable}-of-{drawn} lock rate this campaign observed and the ~1 h 20 m per trial "
        "its record's execution notes give:"
    )
    a("")
    a(
        "| Nominal pass rate | measurable draws needed | control draws | total drawn trials | "
        "simulator time |"
    )
    a("| --- | --- | --- | --- | --- |")
    cheapest = None
    peak = None
    for passing, n in JOINT_COST_POPULATIONS:
        if not is_sized(passing, n, alpha, halfwidth):
            raise SystemExit(
                f"JOINT_COST_POPULATIONS entry {passing}/{n} is not sized "
                f"(required_n {required_n(passing, n, alpha, halfwidth)} > {n}) -- "
                "every row of this table must be a campaign klt yield would call sufficient"
            )
        nc = min_control(passing, n, alpha)
        total = _draws_for(n, lock_rate) + (nc or 0)
        if cheapest is None or total < cheapest[0]:
            cheapest = (total, passing, n)
        if peak is None or total > peak[0]:
            peak = (total, passing, n)
        a(
            f"| {passing / n * 100:.2f} % ({passing}/{n}) | {n} (`required_n` "
            f"{required_n(passing, n, alpha, halfwidth)}) | {nc} | ~{total} | "
            f"~{total * HOURS_PER_TRIAL:,.0f} h |"
        )
    a("")
    a(
        f"The cheapest row is {cheapest[1]}/{cheapest[2]} -- every draw passing -- at ~"
        f"{cheapest[0] * HOURS_PER_TRIAL:,.0f} h, roughly the ~400 h this directory has been "
        f"quoting all along. The dearest is {peak[1]}/{peak[2]} at ~"
        f"{peak[0] * HOURS_PER_TRIAL:,.0f} h, about "
        f"{peak[0] / cheapest[0]:.0f}x as much, and it is *in the middle* rather than at the "
        "bad end: the bottom row, a design meeting row 9 one time in ten, is cheaper than the "
        "one above it. **Part-way is the expensive place to stop.** That is the opposite of the "
        "intuition that any improvement in row 9 brings the citation nearer, and it is the "
        "single fact worth carrying out of this document into the design work."
    )
    return lines


def render(
    nominal: dict,
    censored: dict,
    probe_reports: dict[str, dict],
    alpha: float,
    halfwidth: float,
) -> str:
    nom = _empirical(nominal)
    cen = _empirical(censored)
    ok, nom_verdict = reachability(nom["estimate"], nom["confidence_interval"]["low"])
    _, cen_verdict = reachability(cen["estimate"], cen["confidence_interval"]["low"])

    # Named apart from the probe loop's own `drawn` below, which is a different
    # population entirely -- these are the real campaign's counts.
    nm = nominal["measurements"][0]
    campaign_measurable = int(nm["n"])
    campaign_drawn = (
        campaign_measurable + int(nm["errored"]) + int(nm["failed_unmeasurable"])
    )
    lock_rate = campaign_measurable / campaign_drawn

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
        "nominal in which *every* draw passes, is still `not_detected` -- a 5-draw control's own "
        "95 % interval still reaches "
        f"{probe_reports['p4-control-same-size-best-case']['measurements'][0]['negative_control']['yield']['empirical']['confidence_interval']['high']:.6f}, "
        "while the best lower bound a 5-draw nominal can reach, at 5 of 5 passing, is "
        f"{probe_reports['p4-control-same-size-best-case']['measurements'][0]['yield']['empirical']['confidence_interval']['low']:.6f}. "
        "This is a statement about a control **sized to match its nominal**, and the next "
        "section shows it is not a statement about small populations: probe 7 is the identical "
        "5-of-5 nominal against a 6-draw control, and it is `detected`."
    )
    a("")
    a(
        "Probes 5 and 6 are the positive control for the set: one passing draw apart, at 183 "
        "draws a side, they straddle the threshold and probe 6 reports `detected`. Probes 8 and "
        "9 straddle a second threshold off that diagonal, and probes 10 and 11 a third at the "
        "top of the range -- so the `not_detected` rows report their populations rather than a "
        "broken probe."
    )
    a("")
    lines.extend(render_frontier(alpha))
    a("")
    lines.extend(
        render_joint_cost(alpha, halfwidth, lock_rate, campaign_drawn, campaign_measurable)
    )
    a("")
    a("## What this changes")
    a("")
    a(
        "Item 6's negative control is **not gated on simulator time**, and buying it first would "
        "buy a control that cannot fire. It is gated on the nominal campaign having a yield whose "
        "interval clears the control's -- which is to say on **the design meeting ratified row 9**, "
        "a design precondition rather than a sampling or tooling one. What the two derived "
        "sections above add is *how well* it has to do, and what that costs:"
    )
    a("")
    a(
        "- **The target is a pass rate, and it is ~100 %.** The cheapest campaign guard 3 would "
        "accept is probe 10's: 183 measurable draws, every one meeting row 9, against a "
        f"{MIN_CONTROL_DRAWS}-draw control -- roughly the ~400 h this directory has quoted all "
        "along, but conditional on a pass rate nobody had stated. Stopping part-way is not a "
        "partial saving, it is the expensive region: `required_n` peaks in the middle, so a "
        "design meeting row 9 half the time costs ~50x the campaign of one that meets it "
        "always. The design gap itself is **#202**, filed from this document because until "
        "this derivation there was no target to file it against."
    )
    a(
        "- **#195** (the degraded-design control) is cheaper than its own estimate said, and "
        "still cannot be bought first. At the 5-draw nominal it was sized against it needs 6 "
        "control draws rather than 5 (probe 7); against a nominal that is also *sized*, "
        f"`klt yield`'s {MIN_CONTROL_DRAWS}-draw minimum is enough (probe 10). Either way it "
        "buys nothing while row 9 is missed by every draw: the control is the cheap half of "
        "this precondition, and the nominal is the whole cost."
    )
    a(
        "- **The sized campaign** (~400 h for `required_n` = 183) does not unlock the control as "
        "a side effect: probe 2 is exactly that campaign with row 9 still missed on every draw, "
        "and it is `not_detected`. Worse, the `required_n` = 183 that figure rests on is the "
        "*zero-failures* branch -- it is the size of a campaign that fails everywhere, and it "
        "stops being the right size the moment the design starts passing."
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

    alpha, halfwidth = load_spec_limits()

    # The derived frontier describes populations nobody ran, so it is only
    # evidence if the same formulas reproduce klt yield's answers on the ones
    # that were. Refuse to render otherwise.
    problems = check_arithmetic_against_probes(probe_reports, alpha, halfwidth)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        print(
            "the derived reachability arithmetic no longer agrees with the committed klt "
            "yield outputs -- a klt version change or a moved upstream tag would do this, "
            "and either invalidates every derived table in the document",
            file=sys.stderr,
        )
        return 1

    text = render(nominal, censored, probe_reports, alpha, halfwidth)

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
