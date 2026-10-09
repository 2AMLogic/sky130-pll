"""Executable behavioral reference for the PROPOSED lock-detector contract.

This module is the executable form of
`spec/decision-records/DR-007-lock-detector-provisional-contract.md`
(status: proposed). It is a deterministic, event-driven model of the `LOCK`
output that spec row 16 (DRAFT) asks for. It is **behavioral-reference
evidence only**: it says what a conforming detector must do on an ideal edge
stream. It is not a circuit, it models no cell delay, and it says nothing
about silicon or PVT behaviour. The hardware block and its PVT campaign are
owed by issue #231.

Units and exactness
-------------------
Every time is an **integer number of picoseconds**. Integer time makes every
boundary convention below exact: there is no floating-point rounding to
decide whether an edge sits on or just outside a window.

Inputs (edge streams, not waveforms)
------------------------------------
- `REF` rising and falling edges (strictly alternating),
- `FBCLK` rising edges (the divider output; falling edges carry no
  information for this contract),
- `RESETB` level changes (active low, asynchronous),
- an independent watchdog tick stream (`Watchdog`): a free-running timing
  source that is **not** derived from REF, FBCLK or CLK. It is the only thing
  that can see REF stop (a REF-clocked counter stops counting exactly when
  REF stops).

Per-REF-cycle evaluation
------------------------
An evaluation happens at every REF **falling** edge `f_k` that has a valid
previous falling edge `f_(k-1)` in the current history. The pairing interval
is the half-open interval `I_k = (f_(k-1), f_k]`; it contains exactly one REF
rising edge `r_k`. With `n_k` FBCLK rising edges in `I_k`:

- `n_k != 1`                        -> BAD (frequency test fails)
- `n_k == 1`, `e_k = t_fb - r_k`:
  - `|e_k| <= w_acq`                -> GOOD
  - `|e_k| >  w_rel`                -> BAD
  - otherwise (`w_acq < |e_k| <= w_rel`) -> MARGINAL (hysteresis band)

State update at each evaluation:

- unlocked: GOOD increments `q`; MARGINAL or BAD clears `q`. `LOCK` rises
  at the evaluation where `q` reaches `qualify_cycles`.
- locked: BAD increments `m`; GOOD or MARGINAL clears `m`. `LOCK` falls at
  the evaluation where `m` reaches `release_cycles`; `q` restarts from 0.

Watchdog timeouts (independent timing source)
---------------------------------------------
Two counters count watchdog ticks: one since the last REF rising edge, one
since the last FBCLK rising edge (both also restart at reset release). A
counter that reaches `timeout_ticks` sets its *missing* flag: `LOCK` falls at
that tick, `q` and `m` clear and, for REF, the evaluation history clears (the
interval spanning the gap is never evaluated). The flag clears at the next
rising edge of that clock; re-qualification then needs `qualify_cycles`
fresh GOOD evaluations.

Simultaneous events (boundary convention)
-----------------------------------------
Events at the same picosecond are processed in this fixed order:
`RESETB` change, watchdog tick, FBCLK rise, REF rise, REF fall. Hence

- an FBCLK edge exactly at `f_k` belongs to `I_k` (closed right end) and an
  edge exactly at `f_(k-1)` belongs to `I_(k-1)`;
- a watchdog tick coincident with an edge counts toward the gap that edge
  ends (the edge restarts the counter after the tick), so the timeout fires
  at the `timeout_ticks`-th tick *strictly after* the last edge;
- a `RESETB` fall coincident with any edge wins (the edge is ignored); a
  `RESETB` rise coincident with an edge lets the edge be processed;
- when both missing flags would assert on the same tick, REF is processed
  first and is the reported cause.

Ablations (negative controls only; never a conforming configuration)
-------------------------------------------------------------------
- `frequency_qualification=False` turns the detector into a pure
  edge-coincidence detector: the count test is dropped, the FBCLK edge
  nearest `r_k` is phase-tested, and an interval with no FBCLK edge carries
  no information (state unchanged). This accepts 2:1 and 1:2 harmonics.
- `timeouts_enabled=False` removes the watchdog. A stopped REF then leaves
  `LOCK` asserted forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PS_PER_NS = 1_000
PS_PER_US = 1_000_000

# Event priorities at equal timestamps (lower is processed first).
_P_RESETB = 0
_P_WD = 1
_P_FB = 2
_P_REF_RISE = 3
_P_REF_FALL = 4

# Supported REF range (spec row 3, DRAFT): 1-25 MHz, duty 30-70 %.
REF_PERIOD_MIN_PS = 40_000        # 25 MHz
REF_PERIOD_MAX_PS = 1_000_000     # 1 MHz
REF_DUTY_MIN_PCT = 30
REF_DUTY_MAX_PCT = 70

# DR-007 realization bands: the range each delay/timer must stay inside over
# PVT in hardware (#231 verifies them). The model runs at the nominal values in
# `Contract`/`Watchdog`; these bands are what the invariants below protect.
W_ACQ_BAND_PS = (1_500, 4_000)
W_REL_BAND_PS = (4_500, 10_000)
WD_PERIOD_BAND_PS = (125_000, 500_000)   # 0.5x - 2x of the 250 ns nominal

GOOD = "good"
MARGINAL = "marginal"
BAD = "bad"
NONE = "none"  # ablation only: no FBCLK edge, coincidence-only detector


@dataclass(frozen=True)
class Contract:
    """Provisional DR-007 values (nominal). Times in ps, counts in cycles."""

    w_acq_ps: int = 2_500          # acquisition phase half-window
    w_rel_ps: int = 6_000          # release phase half-window (wider)
    qualify_cycles: int = 32       # consecutive GOOD evaluations to assert
    release_cycles: int = 4        # consecutive BAD evaluations to release
    timeout_ticks: int = 16        # watchdog ticks for a missing clock
    frequency_qualification: bool = True  # False = ablation (negative control)
    timeouts_enabled: bool = True         # False = ablation (negative control)

    def __post_init__(self):
        if not (0 <= self.w_acq_ps < self.w_rel_ps):
            raise ValueError("need 0 <= w_acq_ps < w_rel_ps (hysteresis)")
        if self.qualify_cycles < 1 or self.release_cycles < 1:
            raise ValueError("cycle counts must be >= 1")
        if self.timeout_ticks < 1:
            raise ValueError("timeout_ticks must be >= 1")


@dataclass(frozen=True)
class Watchdog:
    """Independent free-running tick source: ticks at phase + j * period."""

    period_ps: int = 250_000       # nominal 4 MHz tick
    phase_ps: int = 0

    def __post_init__(self):
        if self.period_ps <= 0 or not (0 <= self.phase_ps < self.period_ps):
            raise ValueError("need period_ps > 0 and 0 <= phase_ps < period_ps")


@dataclass(frozen=True)
class Stimulus:
    ref_rise: tuple
    ref_fall: tuple
    fb_rise: tuple
    t_end_ps: int
    # (time_ps, level) RESETB changes. The level before the first entry is 0
    # (the contract requires RESETB asserted at power-up).
    resetb: tuple = ((0, 1),)


@dataclass(frozen=True)
class Transition:
    t_ps: int
    level: int
    cause: str


@dataclass(frozen=True)
class Evaluation:
    t_ps: int
    n_fb: int
    e_ps: int | None
    cls: str
    q: int
    m: int


@dataclass
class Result:
    transitions: list = field(default_factory=list)
    evaluations: list = field(default_factory=list)
    final_lock: int = 0

    def lock_at(self, t_ps: int) -> int:
        level = 0
        for tr in self.transitions:
            if tr.t_ps <= t_ps:
                level = tr.level
        return level


def _validate(stim: Stimulus) -> None:
    for name in ("ref_rise", "ref_fall", "fb_rise"):
        seq = getattr(stim, name)
        if any(b <= a for a, b in zip(seq, seq[1:])):
            raise ValueError(f"{name} must be strictly increasing")
        if any(not isinstance(t, int) for t in seq):
            raise ValueError(f"{name} times must be integer picoseconds")
    merged = sorted([(t, 1) for t in stim.ref_rise] + [(t, 0) for t in stim.ref_fall])
    for (ta, la), (tb, lb) in zip(merged, merged[1:]):
        if ta == tb or la == lb:
            raise ValueError("REF rising and falling edges must strictly alternate")


def simulate(stim: Stimulus, contract: Contract = Contract(),
             wd: Watchdog = Watchdog()) -> Result:
    """Run the reference over `stim` up to and including `stim.t_end_ps`."""
    _validate(stim)
    c = contract
    events = []
    for t, lvl in stim.resetb:
        events.append((t, _P_RESETB, lvl))
    if c.timeouts_enabled:
        t = wd.phase_ps
        while t <= stim.t_end_ps:
            events.append((t, _P_WD, None))
            t += wd.period_ps
    events += [(t, _P_FB, None) for t in stim.fb_rise]
    events += [(t, _P_REF_RISE, None) for t in stim.ref_rise]
    events += [(t, _P_REF_FALL, None) for t in stim.ref_fall]
    events = [ev for ev in events if ev[0] <= stim.t_end_ps]
    events.sort(key=lambda ev: (ev[0], ev[1]))

    res = Result()
    st = {
        "in_reset": True, "lock": 0, "q": 0, "m": 0,
        "prev_fall": None, "last_rise": None, "fbs": [],
        "ref_ticks": 0, "fb_ticks": 0, "ref_missing": False, "fb_missing": False,
    }

    def set_lock(t, level, cause):
        if st["lock"] != level:
            st["lock"] = level
            res.transitions.append(Transition(t, level, cause))

    def clear_all():
        st.update(q=0, m=0, prev_fall=None, last_rise=None, fbs=[],
                  ref_ticks=0, fb_ticks=0, ref_missing=False, fb_missing=False)

    def classify(t_fall):
        r = st["last_rise"]
        fbs = st["fbs"]
        n = len(fbs)
        if c.frequency_qualification:
            if n != 1:
                return n, None, BAD
            e = fbs[0] - r
        else:
            if n == 0:
                return n, None, NONE
            e = min(fbs, key=lambda tf: (abs(tf - r), tf)) - r
        if abs(e) <= c.w_acq_ps:
            return n, e, GOOD
        if abs(e) > c.w_rel_ps:
            return n, e, BAD
        return n, e, MARGINAL

    for t, prio, arg in events:
        if prio == _P_RESETB:
            if arg == 0:
                st["in_reset"] = True
                set_lock(t, 0, "reset")
                clear_all()
            else:
                st["in_reset"] = False
                clear_all()
            continue
        if st["in_reset"]:
            continue

        if prio == _P_WD:
            st["ref_ticks"] = min(st["ref_ticks"] + 1, c.timeout_ticks)
            st["fb_ticks"] = min(st["fb_ticks"] + 1, c.timeout_ticks)
            if st["ref_ticks"] >= c.timeout_ticks and not st["ref_missing"]:
                st["ref_missing"] = True
                set_lock(t, 0, "ref_timeout")
                st.update(q=0, m=0, prev_fall=None, last_rise=None, fbs=[])
            if st["fb_ticks"] >= c.timeout_ticks and not st["fb_missing"]:
                st["fb_missing"] = True
                set_lock(t, 0, "fb_timeout")
                st.update(q=0, m=0)
        elif prio == _P_FB:
            st["fb_ticks"] = 0
            st["fb_missing"] = False
            st["fbs"].append(t)
        elif prio == _P_REF_RISE:
            st["ref_ticks"] = 0
            st["ref_missing"] = False
            st["last_rise"] = t
        elif prio == _P_REF_FALL:
            pf, r = st["prev_fall"], st["last_rise"]
            if pf is not None and r is not None and pf < r < t:
                n, e, cls = classify(t)
                if st["lock"] == 0:
                    if cls == GOOD:
                        st["q"] += 1
                    elif cls in (MARGINAL, BAD):
                        st["q"] = 0
                    if (st["q"] >= c.qualify_cycles and not st["ref_missing"]
                            and not st["fb_missing"]):
                        set_lock(t, 1, "qualified")
                        st["m"] = 0
                else:
                    if cls == BAD:
                        st["m"] += 1
                    elif cls in (GOOD, MARGINAL):
                        st["m"] = 0
                    if st["m"] >= c.release_cycles:
                        set_lock(t, 0, "release")
                        st.update(q=0, m=0)
                res.evaluations.append(Evaluation(t, n, e, cls, st["q"], st["m"]))
            st["prev_fall"] = t
            st["fbs"] = []

    res.final_lock = st["lock"]
    return res


# --------------------------------------------------------------------------
# Stimulus helpers (deterministic, integer ps)
# --------------------------------------------------------------------------

def ref_clock(first_rise_ps: int, period_ps: int, cycles: int,
              duty_pct: int = 50) -> tuple:
    """`cycles` REF periods: rises at first + k*period, falls duty% later."""
    if period_ps * duty_pct % 100:
        raise ValueError("period * duty must be an integer number of ps")
    high = period_ps * duty_pct // 100
    rises = tuple(first_rise_ps + k * period_ps for k in range(cycles))
    falls = tuple(r + high for r in rises)
    return rises, falls


def fb_from_offsets(ref_rises, offsets) -> tuple:
    """One FBCLK edge per REF rise at `r + offset`; an offset of None drops
    that edge. `offsets` is a callable k -> offset or a sequence."""
    out = []
    for k, r in enumerate(ref_rises):
        off = offsets(k) if callable(offsets) else offsets[k]
        if off is not None:
            out.append(r + off)
    return tuple(out)
