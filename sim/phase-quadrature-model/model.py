#!/usr/bin/env python3
"""Deterministic event/timing model of the proposed I/Q divide-by-2 (issue #344).

Qualifies a central assumption of DR-010 / docs/phase-output-proposal.md: that a
2x clock feeding a two-flip-flop I/Q divide-by-2 yields CLK and CLK90 at a
quarter-cycle offset. PDK-free, SPICE-free, stdlib only. Time is an exact
`fractions.Fraction` (picoseconds), so every result is exactly reproducible.

Topology (the one DR-010 describes, written out exactly):

  * FF_I  : D flip-flop clocked on the RISING edge of C2X.  D_I = NOT Q_Q.
            Its output is CLK.
  * FF_Q  : D flip-flop clocked on the FALLING edge of C2X. D_Q = Q_I.
            Its output is CLK90.
  * Feedback point: the Johnson (twisted-ring) cross-coupling above; the PLL
            feedback counter is fed from CLK (FF_I output), i.e. after the /2.
  * Reset : RESETB, active low, asynchronous. While low both flops are forced
            to 0 (state I=0,Q=0). Release is synchronous in effect: the first
            clock edge at or after release (see `release_edge_counts`) is the
            first captured edge.

Ideal relationship (analytical, NOT taken from the model):
  input period T2 and high fraction D -> output period 2*T2; Q changes D*T2
  after I does, so CLK90 lags CLK by D*T2 = 180*D degrees of the output
  period (rising-to-rising and falling-to-falling alike). D=0.5 -> 90 deg.

What is NOT modelled: metastability, transistor behaviour, PVT, loading,
supply coupling, silicon jitter. Setup/recovery windows are checked as
flags with parameters that are UNKNOWN for this design (default 0); a flagged
instant is resolved deterministically (old value sampled) and reported as
unresolved, never as a physical prediction.
"""

from bisect import bisect_right, insort
from dataclasses import dataclass, field
from fractions import Fraction as F

MODEL_VERSION = "1"


def fr(x):
    return x if isinstance(x, F) else F(x)


@dataclass(frozen=True)
class Flop:
    """Per-flop timing, picoseconds. `t_*` are clock-to-output delays."""
    tcq_rise: F = F(0)
    tcq_fall: F = F(0)
    tsu: F = F(0)    # setup, UNKNOWN for this design
    thd: F = F(0)    # hold, UNKNOWN for this design

    def tcq(self, new_value):
        return self.tcq_rise if new_value else self.tcq_fall


@dataclass
class ClockSegment:
    """One burst of C2X. Rising edges at start + k*period, falling at +duty*period.

    `first_high` (ps) makes the segment resume mid-high-phase: no rising edge,
    a first falling edge `first_high` after `start` (a runt on restoration).
    """
    start: F
    stop: F
    first_high: F = None


def clock_edges(period, duty, segments):
    """Return sorted [(time, 'R'|'F')] edges of C2X for the given segments."""
    period, duty = fr(period), fr(duty)
    edges = []
    for seg in segments:
        t = fr(seg.start)
        if seg.first_high is not None:
            edges.append((t + fr(seg.first_high), "F"))
            t += period
            # next rising edge one full period after the segment start
        k = t
        while k < seg.stop:
            edges.append((k, "R"))
            f = k + duty * period
            if f < seg.stop:
                edges.append((f, "F"))
            k += period
    edges.sort(key=lambda e: (e[0], e[1]))
    return edges


class Wave:
    """Piecewise-constant digital waveform with exact timestamps."""

    def __init__(self, init=0):
        self.times = []
        self.vals = []
        self.init = init

    def at(self, t):
        """Value at time t (a change stamped exactly t is already visible)."""
        i = bisect_right(self.times, t)
        return self.vals[i - 1] if i else self.init

    def last(self):
        return self.vals[-1] if self.vals else self.init

    def set(self, t, v):
        # replace any later pending change (reset overrides), keep sorted
        i = bisect_right(self.times, t)
        del self.times[i:]
        del self.vals[i:]
        if self.at(t) != v:
            self.times.append(t)
            self.vals.append(v)

    def edges(self, kind):
        """Times of 'rise' or 'fall' transitions."""
        want = 1 if kind == "rise" else 0
        out = []
        prev = self.init
        for t, v in zip(self.times, self.vals):
            if v != prev and v == want:
                out.append(t)
            prev = v
        return out


@dataclass
class Result:
    i: Wave
    q: Wave
    flags: list = field(default_factory=list)  # (kind, time) unresolved instants
    edge_count: int = 0


def simulate(period, duty, segments, ff_i=Flop(), ff_q=Flop(), reset=None,
             init_state=(0, 0), release_edge_counts=True, trec=F(0),
             max_edges=100000):
    """Simulate the I/Q /2.

    period, duty : C2X period (ps) and high fraction D.
    segments     : list[ClockSegment] (clock absence = gaps between them).
    reset        : None (no reset, flops start at `init_state`) or
                   (t_assert, t_release): RESETB low in [t_assert, t_release).
    release_edge_counts : an edge at exactly t_release is captured (True) or
                   ignored (False). Edges within `trec` after release are
                   flagged as recovery-window instants.
    max_edges    : hard cap; raises if exceeded (run cap).
    """
    edges = clock_edges(period, duty, segments)
    if len(edges) > max_edges:
        raise ValueError(f"run cap exceeded: {len(edges)} edges > {max_edges}")
    wi, wq = Wave(init_state[0]), Wave(init_state[1])
    res = Result(wi, wq, edge_count=len(edges))
    ta = tr = None
    if reset is not None:
        ta, tr = fr(reset[0]), fr(reset[1])
        # reset assertion forces both flops low (instant, zero reset-to-q delay)
        if ta <= 0:
            wi.init = wq.init = 0
        else:
            edges = sorted(edges + [(ta, "A")], key=lambda e: (e[0], e[1]))
    for t, kind in edges:
        if kind == "A":  # RESETB asserted: force both flops low from here on
            wi.set(t, 0)
            wq.set(t, 0)
            continue
        if reset is not None and ta <= t:
            held = t < tr or (t == tr and not release_edge_counts)
            if held:
                continue
            if tr <= t < tr + fr(trec):
                res.flags.append(("recovery", t))
        if kind == "R":
            d_time = t - ff_i.tsu
            d = 1 - wq.at(d_time)
            if _changing(wq, t - ff_i.tsu, t + ff_i.thd):
                res.flags.append(("setup/hold FF_I", t))
            dest, ff = wi, ff_i
        else:
            d_time = t - ff_q.tsu
            d = wi.at(d_time)
            if _changing(wi, t - ff_q.tsu, t + ff_q.thd):
                res.flags.append(("setup/hold FF_Q", t))
            dest, ff = wq, ff_q
        # compare against the value the flop will hold once earlier pending
        # changes land (waves are time-ordered so `last()` suffices)
        if d != dest.last():
            insort_change(dest, t + ff.tcq(d), d)
    return res


def _changing(wave, lo, hi):
    """True if `wave` changes strictly inside (lo, hi]."""
    if lo == hi:
        return False
    i = bisect_right(wave.times, lo)
    return i < len(wave.times) and wave.times[i] <= hi


def insort_change(wave, t, v):
    wave.times.append(t)
    wave.vals.append(v)
    if len(wave.times) > 1 and wave.times[-2] > t:
        pairs = sorted(zip(wave.times, wave.vals))
        wave.times[:] = [p[0] for p in pairs]
        wave.vals[:] = [p[1] for p in pairs]


# ---------------------------------------------------------------- measurement

def _mean(xs):
    return sum(xs, F(0)) / len(xs)


def measure(res, skip=2, until=None, since=None):
    """Steady-state measurements from output edges, skipping the first `skip`
    CLK rising edges. Edge definitions (all on the model outputs):

      period    : mean rising-to-rising time of CLK
      duty      : mean high time of an output / its period
      lag_rise  : for each CLK rising edge, time to the next CLK90 rising edge
      lag_fall  : same for falling edges
      phase     : 360 * lag / period  (degrees of the output period; positive
                  = CLK90 lags CLK)
    """
    ri, fi = res.i.edges("rise"), res.i.edges("fall")
    rq, fq = res.q.edges("rise"), res.q.edges("fall")
    if since is not None:
        ri, fi, rq, fq = ([t for t in x if t >= since] for x in (ri, fi, rq, fq))
    if until is not None:
        ri, fi, rq, fq = ([t for t in x if t <= until] for x in (ri, fi, rq, fq))
    ri = ri[skip:]
    out = {"n_rise_i": len(ri)}
    if len(ri) < 3:
        out["ok"] = False
        return out
    periods = [b - a for a, b in zip(ri, ri[1:])]
    p = _mean(periods)
    out.update(ok=True, period=p, period_min=min(periods), period_max=max(periods))

    def high_time(rise, fall):
        hs = []
        for r in rise:
            nxt = [f for f in fall if f > r]
            if nxt:
                hs.append(nxt[0] - r)
        return hs

    hi = high_time(ri, fi)
    rq_ = [t for t in rq if t >= ri[0]]
    hq = high_time(rq_, fq)
    out["duty_i"] = _mean(hi) / p if hi else None
    out["duty_q"] = _mean(hq) / p if hq else None

    def lag(a_edges, b_edges):
        ls = []
        for a in a_edges:
            nxt = [b for b in b_edges if b > a]
            if nxt:
                ls.append(nxt[0] - a)
        return ls

    lr = lag(ri, rq)
    fi_ = [t for t in fi if t >= ri[0]]
    lf = lag(fi_, fq)
    out["lag_rise_ps"] = _mean(lr) if lr else None
    out["lag_fall_ps"] = _mean(lf) if lf else None
    out["phase_rise_deg"] = 360 * _mean(lr) / p if lr else None
    out["phase_fall_deg"] = 360 * _mean(lf) / p if lf else None
    # ordering: CLK90 must lag CLK by less than half the output period
    out["ordering_q_lags_i"] = bool(lr) and all(0 < l < p / 2 for l in lr) \
        and bool(lf) and all(0 < l < p / 2 for l in lf)
    return out


# ---------------------------------------------------------------- analytical

def analytic_phase_deg(duty, t2, d_tcq=F(0)):
    """Predicted CLK90 lag in degrees of the output period.

    sep = D*t2 + d_tcq, period = 2*t2  ->  180*D + 180*d_tcq/t2.
    `d_tcq` = (FF_Q clock-to-out) - (FF_I clock-to-out) for the same edge sense.
    """
    return 180 * fr(duty) + 180 * fr(d_tcq) / fr(t2)


def analytic_output_period(t2):
    return 2 * fr(t2)


def ideal_quadrature_phase_deg(duty, t2, d_tcq=F(0)):
    """DEFEATING CONTROL: an assumed perfect quarter-cycle generator.

    Ignores input duty and path delay by construction. It must be caught
    disagreeing with `analytic_phase_deg` whenever duty != 0.5 or d_tcq != 0.
    """
    return F(90)


def to_float(x, nd=6):
    return f"{float(x):.{nd}f}"
