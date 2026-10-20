#!/usr/bin/env python3
"""Case-matrix runner for the I/Q /2 behavioral model (issue #344).

Emits one finite, deterministic report. Analytical predictions (closed form,
from model.analytic_*) are kept in their own columns/tables, apart from the
executed model results. No SPICE, no PDK, no network, stdlib only.

  python3 sim/phase-quadrature-model/run_cases.py                 # print report
  python3 sim/phase-quadrature-model/run_cases.py --record-id ID \\
        --out sim/phase-quadrature-model/records/ID.md            # mint record
  python3 sim/phase-quadrature-model/run_cases.py --check records/ID.md
        # re-render from the record's own ID and fail on any byte of drift
"""

import argparse
import hashlib
import os
import sys
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import model as m  # noqa: E402

# ---- run caps (declared, enforced) -----------------------------------------
MAX_CASES = 400
MAX_EDGES_PER_CASE = 20000
MAX_TOTAL_EDGES = 2_000_000
CYCLES = 60                     # 2x-clock periods simulated per steady case

# Output frequencies from DR-009 gap 3 (25/50 MHz required, 100 MHz stretch).
# The VCO / "2x" clock runs at twice that; T2 is its period in picoseconds.
OUT_MHZ = (25, 50, 100)
T2_PS = {f: F(1_000_000, 2 * f) for f in OUT_MHZ}

DUTIES = (F(40, 100), F(45, 100), F(50, 100), F(55, 100), F(60, 100))
DELTAS_PS = (F(-1000), F(-500), F(0), F(250), F(500), F(1000))

# Identity of the reviewed inputs this study qualifies (git blobs at main
# e786d18c1f2d5c24d248ff3e4e0250259085ef77, before this study's corrections).
INPUT_IDENTITIES = (
    ("docs/phase-output-proposal.md", "14c2308c28c84915fa5f18cc86a4d08196051668782fa8cbc740284045c8ddad"),
    ("spec/decision-records/DR-010-phase-or-multiplied-output-proposal.md",
     "45f772c05f2aff78e204600d13c696a697f31a9365a97a44c8025ff9d06ace0b"),
    ("spec/decision-records/DR-009-phase-output-scope-and-consumer-clock-gaps.md",
     "9259dbf6ca407fd0fad32cde076013e923e33a75e8ce01e08833df665de7bf7a"),
)


def sha256_file(name):
    with open(os.path.join(HERE, name), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def fmt(x, nd=4):
    return "n/a" if x is None else f"{float(x):.{nd}f}"


def deg_eq(a, b):
    return a is not None and a == b


class Counter:
    edges = 0


def sim(period, duty, segments, **kw):
    res = m.simulate(period, duty, segments, max_edges=MAX_EDGES_PER_CASE, **kw)
    Counter.edges += res.edge_count
    return res


def steady(t2):
    return [m.ClockSegment(F(0), t2 * CYCLES)]


def defeating_control(t2):
    """An assumed perfect-quarter-cycle generator must be caught.

    The control substitutes `ideal_quadrature_phase_deg` for the model at
    D=45 % and checks it against the closed form; the check must FAIL it.
    """
    d = F(45, 100)
    want = m.analytic_phase_deg(d, t2)
    ideal = m.ideal_quadrature_phase_deg(d, t2)
    model_val = m.measure(sim(t2, d, steady(t2)))["phase_rise_deg"]
    return {
        "analytic": want, "ideal": ideal, "model": model_val,
        "detected": ideal != want and model_val == want,
    }


# ---- case groups -----------------------------------------------------------

def group_duty():
    rows = []
    for f in OUT_MHZ:
        t2 = T2_PS[f]
        for d in DUTIES:
            r = m.measure(sim(t2, d, steady(t2)))
            ap, ap_per = m.analytic_phase_deg(d, t2), m.analytic_output_period(t2)
            ok = (deg_eq(r["phase_rise_deg"], ap) and deg_eq(r["phase_fall_deg"], ap)
                  and r["period"] == ap_per and r["ordering_q_lags_i"]
                  and r["duty_i"] == F(1, 2) and r["duty_q"] == F(1, 2))
            rows.append(dict(
                group="A duty", case=f"{f} MHz out, D_in={float(d)*100:.0f}%",
                analytic=f"phase {fmt(ap)} deg, period {fmt(ap_per, 1)} ps, out duty 50%",
                executed=(f"rise {fmt(r['phase_rise_deg'])} / fall {fmt(r['phase_fall_deg'])} deg, "
                          f"period {fmt(r['period'], 1)} ps, duty_i {fmt(r['duty_i'])} duty_q {fmt(r['duty_q'])}"),
                verdict="PASS" if ok else "FAIL"))
    return rows


def group_path():
    rows = []
    for f in OUT_MHZ:
        t2 = T2_PS[f]
        for d in (F(1, 2), F(45, 100)):
            for dl in DELTAS_PS:
                ffq = m.Flop(tcq_rise=max(dl, F(0)) + F(100), tcq_fall=max(dl, F(0)) + F(100))
                ffi = m.Flop(tcq_rise=max(-dl, F(0)) + F(100), tcq_fall=max(-dl, F(0)) + F(100))
                r = m.measure(sim(t2, d, steady(t2), ff_i=ffi, ff_q=ffq))
                ap = m.analytic_phase_deg(d, t2, dl)
                lim = 0 < ap < 180
                ok = (deg_eq(r["phase_rise_deg"], ap) and deg_eq(r["phase_fall_deg"], ap)
                      and r["ordering_q_lags_i"] == lim)
                rows.append(dict(
                    group="B path", case=f"{f} MHz, D_in={float(d)*100:.0f}%, FF_Q-FF_I delay {fmt(dl, 0)} ps",
                    analytic=f"phase {fmt(ap)} deg ({fmt(ap - 90)} vs 90)",
                    executed=f"rise {fmt(r['phase_rise_deg'])} / fall {fmt(r['phase_fall_deg'])} deg, ordering ok={r['ordering_q_lags_i']}",
                    verdict="PASS" if ok else "FAIL"))
        # rise/fall asymmetric clock-to-q: rise lag and fall lag differ
        t2f = t2
        ffi = m.Flop(tcq_rise=F(0), tcq_fall=F(200))
        ffq = m.Flop(tcq_rise=F(300), tcq_fall=F(0))
        r = m.measure(sim(t2f, F(1, 2), steady(t2f), ff_i=ffi, ff_q=ffq))
        apr = m.analytic_phase_deg(F(1, 2), t2f, F(300))
        apf = m.analytic_phase_deg(F(1, 2), t2f, F(-200))
        ok = deg_eq(r["phase_rise_deg"], apr) and deg_eq(r["phase_fall_deg"], apf)
        rows.append(dict(
            group="B path", case=f"{f} MHz, D_in=50%, asymmetric tcq (rise +300 ps, fall -200 ps FF_Q-FF_I)",
            analytic=f"rise {fmt(apr)} / fall {fmt(apf)} deg",
            executed=f"rise {fmt(r['phase_rise_deg'])} / fall {fmt(r['phase_fall_deg'])} deg",
            verdict="PASS" if ok else "FAIL"))
    return rows


def group_startup():
    rows = []
    t2 = T2_PS[50]
    firsts = {}
    for d in (F(1, 2), F(45, 100)):
        for s in ((0, 0), (0, 1), (1, 0), (1, 1)):
            res = sim(t2, d, steady(t2), init_state=s)
            r = m.measure(res)
            ap = m.analytic_phase_deg(d, t2)
            ok = deg_eq(r["phase_rise_deg"], ap) and r["ordering_q_lags_i"]
            first = res.i.edges("rise")[0]
            firsts[(d, s)] = first
            rows.append(dict(
                group="C startup (no reset)", case=f"50 MHz out, D_in={float(d)*100:.0f}%, power-up I,Q={s}",
                analytic=f"steady phase {fmt(ap)} deg, Q lags I",
                executed=f"steady {fmt(r['phase_rise_deg'])} deg, ordering ok={r['ordering_q_lags_i']}; first CLK rise at {fmt(first / t2, 2)} T2",
                verdict="PASS" if ok else "FAIL"))
    d = F(1, 2)
    vals = sorted({firsts[(d, s)] / t2 for s in ((0, 0), (0, 1), (1, 0), (1, 1))})
    rows.append(dict(
        group="C startup (no reset)", case="CLK alignment to the 2x-clock grid vs power-up state (50 MHz out, D_in=50%)",
        analytic="not predicted: depends on the unreset state",
        executed=f"first CLK rise at {', '.join(fmt(v, 2) + ' T2' for v in vals)} across the 4 power-up states",
        verdict="FINDING"))
    return rows


def group_reset():
    rows = []
    t2 = T2_PS[50]
    base = t2 * 4
    spread = []
    bad = 0
    for counts in (True, False):
        for j in range(0, 17):
            rel = base + t2 * F(j, 8)
            res = sim(t2, F(1, 2), steady(t2), reset=(F(0), rel), init_state=(1, 1),
                      release_edge_counts=counts)
            r = m.measure(res)
            first = res.i.edges("rise")[0] - rel
            spread.append(first)
            ok = deg_eq(r["phase_rise_deg"], 90) and r["ordering_q_lags_i"] and res.q.at(rel - F(1, 1000)) == 0 and res.i.at(rel - F(1, 1000)) == 0
            bad += not ok
            rows.append(dict(
                group="D reset release", case=f"50 MHz, RESETB release at +{j}/8 T2 after a rising edge, edge-at-release counted={counts}",
                analytic="state (0,0) at release; Q lags I by 90.0 deg after release",
                executed=f"first CLK rise {fmt(first / t2, 3)} T2 after release; steady {fmt(r['phase_rise_deg'])} deg, ordering ok={r['ordering_q_lags_i']}",
                verdict="PASS" if ok else "FAIL"))
    rows.append(dict(
        group="D reset release", case="release-to-first-CLK-edge latency across the sweep (50 MHz)",
        analytic="not predicted: depends on release phase and the coincident-edge convention",
        executed=f"min {fmt(min(spread) / t2, 3)} T2, max {fmt(max(spread) / t2, 3)} T2 over {len(spread)} cases; the phase of CLK relative to REF is therefore set by release timing",
        verdict="FINDING"))
    return rows


def group_absence():
    rows = []
    t2 = T2_PS[50]
    stop = t2 * 20
    for gap_t2, runt in ((F(3, 2), None), (F(2), None), (F(13, 4), None), (F(6), None),
                         (F(5), F(1, 10)), (F(5), F(1, 2))):
        start2 = stop + t2 * gap_t2
        segs = [m.ClockSegment(F(0), stop),
                m.ClockSegment(start2, start2 + t2 * 40,
                               first_high=None if runt is None else runt * t2)]
        res = sim(t2, F(1, 2), segs)
        r = m.measure(res, since=start2 + t2 * 4, skip=0)
        pre = [e for e in res.i.edges("rise") if e < stop]
        post = [e for e in res.i.edges("rise") if e >= start2]
        slip_deg = None
        if pre and post:
            slip_deg = 360 * (((post[0] - pre[0]) / (2 * t2)) % 1)
        ok = deg_eq(r.get("phase_rise_deg"), 90) and r.get("ordering_q_lags_i")
        label = "clean restart" if runt is None else f"runt first high {fmt(runt)} T2"
        rows.append(dict(
            group="E clock absence", case=f"50 MHz, stop at 20 T2, absent {fmt(gap_t2, 2)} T2, {label}",
            analytic="after restoration: Q lags I by 90.0 deg; outputs hold during absence",
            executed=f"post-restoration steady {fmt(r.get('phase_rise_deg'))} deg, ordering ok={r.get('ordering_q_lags_i')}; "
                     f"CLK phase vs pre-stop grid {fmt(slip_deg)} deg (mod 360)",
            verdict="PASS" if ok else "FAIL"))
    rows.append(dict(
        group="E clock absence", case="CLK phase continuity across absence",
        analytic="not predicted",
        executed="CLK phase relative to the pre-stop grid is not preserved in general (see per-case column): "
                 "the output holds its state and resumes on the first restored edge, so any consumer or loop "
                 "reference that assumed continuity must re-synchronise",
        verdict="FINDING"))
    return rows


def group_window():
    """Data-window (setup) margins; hold is not exercised (no data change near sampling edge by construction)."""
    rows = []
    for f in OUT_MHZ:
        t2 = T2_PS[f]
        for d, tcq_i, tcq_q, tsu in ((F(1, 2), F(0), F(0), F(0)),
                                     (F(45, 100), F(100), F(100), F(100)),
                                     (F(45, 100), t2 * F(2, 5), F(100), t2 * F(1, 10)),
                                     (F(55, 100), F(100), t2 * F(2, 5), t2 * F(1, 10))):
            ffi = m.Flop(tcq_rise=tcq_i, tcq_fall=tcq_i, tsu=tsu)
            ffq = m.Flop(tcq_rise=tcq_q, tcq_fall=tcq_q, tsu=tsu)
            res = sim(t2, d, steady(t2), ff_i=ffi, ff_q=ffq)
            m_q = d * t2 - tcq_i - tsu          # FF_Q samples I at the falling edge
            m_i = (1 - d) * t2 - tcq_q - tsu    # FF_I samples ~Q at the next rising edge
            flagged = len(res.flags)
            want_flag = m_q < 0 or m_i < 0
            ok = (flagged > 0) == want_flag
            rows.append(dict(
                group="F data window", case=f"{f} MHz out, D_in={float(d)*100:.0f}%, tcq_I={fmt(tcq_i, 0)} tcq_Q={fmt(tcq_q, 0)} tsu={fmt(tsu, 0)} ps (tsu/tcq are placeholders, UNKNOWN for this design)",
                analytic=f"margins FF_Q {fmt(m_q, 0)} ps, FF_I {fmt(m_i, 0)} ps -> violation={want_flag}",
                executed=f"{flagged} flagged setup instants (unresolved, not metastability-modelled)",
                verdict="PASS" if ok else "FAIL"))
    return rows


def group_control():
    rows = []
    for f in OUT_MHZ:
        t2 = T2_PS[f]
        c = defeating_control(t2)
        rows.append(dict(
            group="G defeating control", case=f"{f} MHz out, D_in=45%: substitute an ideal quarter-cycle generator",
            analytic=f"closed form {fmt(c['analytic'])} deg",
            executed=f"ideal generator {fmt(c['ideal'])} deg (off by {fmt(c['ideal'] - c['analytic'])} deg); model {fmt(c['model'])} deg",
            verdict="PASS" if c["detected"] else "FAIL"))
    return rows


GROUPS = (group_duty, group_path, group_startup, group_reset, group_absence,
          group_window, group_control)


def build_matrix():
    """Declared case list (names only), used to check the cap before running."""
    n = len(OUT_MHZ) * len(DUTIES)                      # A
    n += len(OUT_MHZ) * (2 * len(DELTAS_PS) + 1)         # B
    n += 8 + 1                                           # C
    n += 2 * 17 + 1                                      # D
    n += 6 + 1                                           # E
    n += len(OUT_MHZ) * 4                                # F
    n += len(OUT_MHZ)                                    # G
    return list(range(n))


def run_matrix():
    cases = build_matrix()
    if len(cases) > MAX_CASES:
        raise SystemExit(f"case cap exceeded: {len(cases)} > {MAX_CASES}")
    Counter.edges = 0
    rows = []
    for g in GROUPS:
        rows.extend(g())
    if len(rows) != len(cases):
        raise SystemExit(f"declared {len(cases)} cases but ran {len(rows)}")
    if Counter.edges > MAX_TOTAL_EDGES:
        raise SystemExit(f"total edge cap exceeded: {Counter.edges}")
    return Counter.edges, rows


# ---- budget (parameterized, not a requirement) ------------------------------

WINDOWS_DEG = (F(1), F(2), F(5), F(10))


def budget_tables():
    out = []
    out.append("| Output freq | 2x clock period T2 | Output period | ps per degree of output | 1 deg of D_in-induced error needs |")
    out.append("|---|---|---|---|---|")
    for f in OUT_MHZ:
        t2 = T2_PS[f]
        out.append(f"| {f} MHz | {fmt(t2, 0)} ps | {fmt(2 * t2, 0)} ps | {fmt(2 * t2 / 360, 2)} ps | duty offset {fmt(F(1, 180) * 100, 3)} points (D_in) |")
    out.append("")
    out.append("Allowed phase-window half-width W is a PARAMETER, not a requirement. "
               "Phase error (deg of output) = 180*(D_in-0.5) + 180*delta/T2, with delta = FF_Q minus FF_I clock-to-out. "
               "Columns: largest |D_in-50%| (in duty points) with delta=0, and largest |delta| (ps) with D_in=50%.")
    out.append("")
    out.append("| W (deg, parameter) | " + " | ".join(f"{f} MHz: duty pts / delta ps" for f in OUT_MHZ) + " |")
    out.append("|---|" + "---|" * len(OUT_MHZ))
    for w in WINDOWS_DEG:
        cells = []
        for f in OUT_MHZ:
            t2 = T2_PS[f]
            cells.append(f"{fmt(w / 180 * 100, 2)} / {fmt(w * t2 / 180, 1)}")
        out.append(f"| +/-{fmt(w, 0)} | " + " | ".join(cells) + " |")
    return out


def render_report(record_id):
    edges, rows = run_matrix()
    npass = sum(r["verdict"] == "PASS" for r in rows)
    nfail = sum(r["verdict"] == "FAIL" for r in rows)
    nfind = sum(r["verdict"] == "FINDING" for r in rows)
    L = []
    a = L.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a("- **Claim**: A PDK-free deterministic event model of the proposed two-flip-flop I/Q /2 (DR-010, Proposed) reproduces the closed-form quadrature relationship under the declared case matrix, and exposes the conditions under which the relationship is not 90 degrees. It is a behavioral model: it does not select a topology, ratify or relax any spec row, or establish physical readiness.")
    a("- **Supersedes**: none (first record for this experiment)")
    a("- **Model version**: " + m.MODEL_VERSION)
    a(f"- **Model identity**: model.py sha256 `{sha256_file('model.py')}`; run_cases.py sha256 `{sha256_file('run_cases.py')}`")
    a("- **Command**: `python3 sim/phase-quadrature-model/run_cases.py --record-id " + record_id + " --out sim/phase-quadrature-model/records/" + record_id + ".md` (re-check: `python3 sim/phase-quadrature-model/run_cases.py --check sim/phase-quadrature-model/records/" + record_id + ".md`)")
    a("- **Input identities** (reviewed inputs qualified; git blobs at main `e786d18c1f2d5c24d248ff3e4e0250259085ef77`, before this study's corrections):")
    for p, h in INPUT_IDENTITIES:
        a(f"  - `{p}` sha256 `{h}`")
    a("- **Environment**: Python 3 standard library only; times are exact `fractions.Fraction` picoseconds, so results do not depend on interpreter version or host. No ngspice, xschem, PDK or network.")
    a(f"- **Run caps** (declared in run_cases.py, enforced): at most {MAX_CASES} cases, {MAX_EDGES_PER_CASE} 2x-clock edges per case, {MAX_TOTAL_EDGES} edges total. This run: {len(rows)} cases, {edges} edges, {CYCLES} 2x periods per steady case.")
    a(f"- **Overall: {'PASS' if nfail == 0 else 'FAIL'}** ({npass} of {npass + nfail} criterion-bearing cases passed; {nfind} informational FINDING cases carry no pass/fail criterion; {len(rows)} cases total). " + ("All declared model properties hold." if nfail == 0 else "THERE ARE FAILURES."))
    a("")
    a("## 1. Topology, edge definitions and reset semantics")
    a("")
    a("- Two D flip-flops. FF_I: rising-edge triggered on the 2x clock C2X, D = NOT Q_Q, output = CLK. FF_Q: falling-edge triggered on C2X, D = Q_I, output = CLK90. Feedback counter input taken from CLK (after the /2).")
    a("- State order on alternating R,F edges from (I,Q)=(0,0): (1,0) -> (1,1) -> (0,1) -> (0,0). All four states lie on this one cycle; the Johnson cross-coupling fixes the Q-lags-I ordering for every power-up state.")
    a("- RESETB: active low, asynchronous; forces I=Q=0 while low. Release: the first C2X edge at or after release is captured (a parameter selects whether an edge exactly at release counts). Recovery-window instants are flagged, not resolved.")
    a("- Phase of an output edge pair = 360 * (CLK90 edge - preceding CLK edge) / output period, in degrees of the output period; positive = CLK90 lags CLK; reported for rising-to-rising and falling-to-falling separately. Period = mean CLK rising-to-rising time. Duty = mean high time / period.")
    a("- Skipped transient: first 2 CLK rising edges (steady cases); post-restoration cases measure from 4 T2 after restart.")
    a("")
    a("## 2. Analytical predictions (closed form; not produced by the model)")
    a("")
    a("- Output period = 2*T2. CLK90 lags CLK by D*T2 + delta, i.e. phase = 180*D + 180*delta/T2 degrees. D=50 %, delta=0 -> 90 deg; D=45 % -> 81 deg; D=55 % -> 99 deg.")
    a("- Output duty of each output = (T2 + tcq_fall - tcq_rise)/(2*T2) = 50 % for equal rise/fall clock-to-out, **independent of input duty**. The /2 therefore restores output duty while transferring the input duty error into the CLK-CLK90 phase.")
    a("- Setup margins: FF_Q samples CLK at the falling edge: D*T2 - tcq_I - tsu; FF_I samples NOT CLK90 at the next rising edge: (1-D)*T2 - tcq_Q - tsu. tsu/tcq of this design are UNKNOWN.")
    a("")
    a("## 3. Executed results (case matrix)")
    a("")
    a("| # | Group | Case | Analytical prediction | Executed model result | Verdict |")
    a("|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        a(f"| {i} | {r['group']} | {r['case']} | {r['analytic']} | {r['executed']} | {r['verdict']} |")
    a("")
    a("## 4. Defeating control")
    a("")
    a("Group G substitutes an assumed perfect-quarter-cycle generator (always 90.000 deg) for the model at D_in=45 % and checks it against the closed form. The check must fail it; a harness that cannot do so would not detect an assumed-quadrature design. All three frequencies detect it (see rows in group G).")
    a("")
    a("## 5. Timing-error budget (parameterized; no consumer tolerance is recorded)")
    a("")
    a("DR-009 records the consumer's operating points (25 and 50 MHz output, 100 MHz stretch) and that the consumer today derives a quarter-cycle clock with a delay element. **It records no setup/hold time, data window, permitted CLK-to-CLK90 phase window, or jitter allowance at the consumer.** The missing requirement is therefore exactly: (a) the allowed CLK90-CLK phase window (degrees or ps) at each of 25/50/100 MHz, (b) the consumer flop setup/hold times that window protects, and (c) the allowance for CLK and CLK90 jitter. Nothing below is an approved tolerance.")
    a("")
    L.extend(budget_tables())
    a("")
    a("Components, kept separate: **clock phase / duty** term 180*(D_in-0.5) deg (modelled, exact); **path mismatch** term 180*delta/T2 deg (modelled, delta is a free parameter); **setup/hold/data-window** (model flags only, tsu/tcq unknown); **jitter** (not modelled, no number derived); the recorded row-9 result (1.58-3.07 % RMS period jitter on 3 locked of 5 draws, `sim/pll-lock-mc`) is a recorded miss and is not used here as a budget input.")
    a("")
    a("## 6. Limitations (not modelled)")
    a("")
    a("- Metastability, setup/hold physics, and recovery behaviour: flagged instants are resolved deterministically (old value) and reported as unresolved.")
    a("- Transistor behaviour, PVT, process mismatch, loading, supply coupling, edge-rate and threshold effects.")
    a("- Silicon jitter and duty distortion of the actual VCO; the 45/55 % duty cases are analytical control scenarios, not characterized distributions or ratified bounds.")
    a("- The loop: Kvco, loop gain and lock dynamics are not simulated, so this record neither supports nor refutes the proposal's loop-gain argument (see the correction in the proposal).")
    a("- Nothing here characterizes the design's row 2/14/15 (DRAFT) or row 9 (ratified; recorded miss unchanged).")
    a("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record-id", default="UNRECORDED")
    ap.add_argument("--out")
    ap.add_argument("--check")
    args = ap.parse_args(argv)
    if args.check:
        rid = os.path.splitext(os.path.basename(args.check))[0]
        with open(args.check, encoding="utf-8") as fh:
            have = fh.read()
        want = render_report(rid)
        if have != want:
            print(f"DRIFT: {args.check} does not reproduce byte-for-byte", file=sys.stderr)
            return 1
        print(f"OK: {args.check} reproduces byte-for-byte")
        return 0
    text = render_report(args.record_id)
    if args.out:
        if os.path.exists(args.out):
            print(f"refusing to overwrite existing record {args.out} (append-only)", file=sys.stderr)
            return 1
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 1 if "THERE ARE FAILURES" in text else 0


if __name__ == "__main__":
    sys.exit(main())
