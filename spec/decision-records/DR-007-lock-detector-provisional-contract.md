# DR-007: provisional `LOCK` detector contract (row 16)

- **Status**: proposed. This record does **not** ratify spec row 16, which
  stays **DRAFT**. See "Status notes" for what would ratify it.
- **Date**: 2026-10-09
- **Author**: Builder agent (issue #237)
- **Ratifies against / input to**: #237 (this contract and its executable
  reference); input to #231 (hardware `LOCK` block, top-level port, PVT
  evidence)
- **Supersedes**: none

One decision per record. The decision here is the **behavioral contract** a
hardware `LOCK` output must meet. Thresholds, block architecture and evidence
plan follow from it. The circuit itself belongs to #231.

## Context

`spec/target-spec.md` row 16 (DRAFT) asks for "a digital `lock` output with an
assert window and hysteresis criteria" and gives no numbers. The design has no
such output (`design/top/DESIGN.md`: the top-level ports are `REF`, `CLK`,
`RESETB`, `NSEL0`..`NSEL5`, `VDD`, `GND`). #231 proposed an edge-coincidence
window counter. Its Champion review found that, without a numeric contract,
false-lock behaviour was undefined:

- an edge-coincidence test alone accepts harmonic relationships, because at
  2:1 or 1:2 every `FBCLK` edge (or every `REF` edge) still has a coincident
  partner;
- a counter clocked by `REF` cannot notice that `REF` has stopped, because
  it stops counting at the same moment;
- the relationship between a hardware `LOCK` and the harness's existing
  lock criterion (`sim/harness/measure.py::lock_time`, configured by
  `sim/pll-lock/testbench/tb.json`) was not stated.

The supported operating space the contract must cover comes from DRAFT rows 3
and 4: `REF` 1–25 MHz, rising-edge triggered, 30–70 % duty; N = 4–64. A locked
loop's `FBCLK` (the divider output, `design/divider/DESIGN.md`) has the `REF`
frequency, so N does not appear in the contract. `design/divider/DESIGN.md`
also records that `FBCLK` can go silent when `CLK` runs above the divider's
maximum frequency. A stopped `FBCLK` is a real failure of this loop, not a
hypothetical one.

## Decision

**Proposed, not ratified:** hardware `LOCK` is the causal, per-`REF`-cycle
detector defined below, with the numeric values in Table 1. It has three
parts. A frequency test checks for exactly one `FBCLK` edge per `REF` cycle. A
phase test uses separate acquisition and release windows. A clock-loss
watchdog runs from an independent free-running timing source. All values are
provisional. The executable form of this contract is
`design/lock-detector/lockdet_ref.py`, with tests in
`design/lock-detector/tests/`.

### 1. Signals

| Signal | Direction | Meaning |
|---|---|---|
| `REF` | in | Reference clock (top-level net). Rising and falling edges are both used. |
| `FBCLK` | in | Divider output (top-level internal net). Only rising edges are used. |
| `RESETB` | in | Active-low, asynchronous. This is the existing top-level reset that the divider already uses. |
| `LOCK` | out | Active high. 1 means the loop is phase- and frequency-locked under this contract. |
| watchdog | internal | Free-running tick source, independent of `REF`, `FBCLK` and `CLK` (§5). |

`CLK` is not an input. The detector judges the loop at the phase comparator,
where lock is defined. `CLK` is not independent of the loop being judged, so
it cannot serve as the watchdog (§5).

### 2. Per-`REF`-cycle evaluation

An **evaluation** happens at every `REF` falling edge `f_k` that has a
previous falling edge `f_(k-1)` in the current history. The history starts
empty after reset and after a `REF` timeout. The pairing interval is
`I_k = (f_(k-1), f_k]`. It contains exactly one `REF` rising edge `r_k`. Let
`n_k` be the number of `FBCLK` rising edges in `I_k`.

| Class | Condition |
|---|---|
| BAD | `n_k ≠ 1` (frequency test), **or** `n_k = 1` and `|e_k| > W_rel` |
| GOOD | `n_k = 1` and `|e_k| ≤ W_acq` |
| MARGINAL | `n_k = 1` and `W_acq < |e_k| ≤ W_rel` (hysteresis band) |

Here `e_k = t_FBCLK − r_k`. A positive value means `FBCLK` lags `REF`.

Why the interval is bounded by `REF` falling edges: at lock, `FBCLK` edges sit
close to `REF` *rising* edges. Bounding the count at the falling edges keeps
every edge within ±`W_rel` of `r_k` well inside `I_k`, so an edge jittering
around `r_k` is never split between adjacent cycles. This bound costs no
delay line and scales with the `REF` period automatically. It is safe at
every supported duty if `W_rel < 0.3 · T_ref,min = 12 ns`. Table 2 meets that
across the hardware band.

### 3. State machine

- **Unlocked** (`LOCK = 0`): GOOD increments the qualification count `q`.
  MARGINAL or BAD clears `q`. `LOCK` rises at the evaluation where `q`
  reaches `Q`.
- **Locked** (`LOCK = 1`): BAD increments the release count `m`. GOOD or
  MARGINAL clears `m`. `LOCK` falls at the evaluation where `m` reaches `R`.
  `q` restarts from 0.

**Table 1 — provisional values (nominal; the model runs at these)**

| Quantity | Value | Unit |
|---|---|---|
| Acquisition phase window `W_acq` (half-width, inclusive) | 2.5 | ns |
| Release phase window `W_rel` (half-width, inclusive; wider) | 6.0 | ns |
| Frequency test | exactly 1 `FBCLK` rising edge per pairing interval | — |
| Qualification count `Q` (consecutive GOOD) | 32 | `REF` cycles |
| Release count `R` (consecutive BAD) | 4 | `REF` cycles |
| Watchdog tick period `T_wd` | 250 | ns |
| Missing-clock timeout `K` | 16 | watchdog ticks (4.0 µs nominal) |

**Table 2 — hardware realization bands (#231 must show these hold over PVT)**

| Quantity | Band | Invariant it protects |
|---|---|---|
| `W_acq` | 1.5 – 4.0 ns | ≥ locked static phase offset + `FBCLK` jitter (to be measured in #231) |
| `W_rel` | 4.5 – 10.0 ns | `W_acq,max < W_rel,min` keeps the hysteresis; `W_rel,max < 12 ns` keeps the release window inside `I_k` at 25 MHz and 30 %/70 % duty |
| `T_wd` | 125 – 500 ns (0.5× – 2× nominal) | timeout window below |
| Missing-clock timeout (hardware, including synchronizer latency) | no false timeout for any rising-edge gap ≤ 1.5 µs; timeout declared ≤ 10 µs after the last edge | the slowest legal `REF` has a 1.0 µs gap |

`design/lock-detector/tests/test_lockdet_ref.py::ContractValues` pins Table 1
and checks the Table 2 invariants.

### 4. Startup and reset

- `RESETB = 0` forces `LOCK = 0` **asynchronously** and clears `q`, `m`, the
  evaluation history and both watchdog counters and flags. The model's
  reset-to-`LOCK` latency is 0. Hardware requirement: `LOCK` low within 10 ns
  of `RESETB` falling (one asynchronous clear path).
- The contract requires `RESETB` to be asserted at power-up, as the divider
  already does. `LOCK` is undefined before the first reset.
- After `RESETB` rises, the first `REF` falling edge `f_0` opens the history
  and is **not** evaluated. The earliest `LOCK` assertion is therefore
  `f_0 + Q · T_ref`. For example: 3.35 µs in the 10 MHz test scenario, and
  33.5 µs for a 1 MHz `REF` whose first rising edge is at 1 µs.

### 5. Clock loss: the independent timing source

**Why a separate source is required.** Evaluations are clocked by `REF`. If
`REF` stops, no evaluation ever happens again and `LOCK` would hold its last
value indefinitely. `CLK` cannot stand in. When `REF` is lost, the VCO is
driven by a one-sided phase detector and wanders, and it can itself stop (a
degenerate ring state, or the divider dropout that silences `FBCLK`). If `REF`
and `CLK`/`FBCLK` stop together, no loop-derived clock is left to notice. The
negative controls show this: with the watchdog removed, a stopped `REF` and a
both-stopped case each leave `LOCK = 1` for the rest of the run.

**Contract.** Two counters count watchdog ticks. One counts since the last
`REF` rising edge, the other since the last `FBCLK` rising edge. Both also
restart at reset release.

- When a counter reaches `K`, its *missing* flag sets. `LOCK` falls at that
  tick and `q` and `m` clear. A `REF` timeout also clears the evaluation
  history, so the interval spanning the gap is never evaluated.
- A flag clears at the next rising edge of its clock. **Recovery** then
  needs `Q` fresh GOOD evaluations. After `REF` returns, the first falling
  edge only reopens the history, so `LOCK` returns at the earliest
  `f_0' + Q · T_ref`.
- When `FBCLK` is lost but `REF` keeps running, the per-cycle frequency test
  also catches it after `R` BAD cycles. The watchdog matters for `FBCLK` only
  at low `REF` frequency, where `R · T_ref` exceeds the timeout. At 1 MHz the
  REF-side release takes `R · T_ref` = 4 µs and the timeout (1.875, 8.0] µs across the `T_wd` band, so
  whichever is first wins. The tests pin both orders.
- During acquisition with a very slow VCO, the `FBCLK` period can exceed the
  timeout and the `FBCLK` flag can set. That is harmless: `LOCK` is already
  0, and the flag clears on the next `FBCLK` edge.

**Timer quantization.** The model fires at the `K`-th tick *strictly after*
the last edge. The elapsed time is therefore in `((K−1)·T_wd, K·T_wd]`, i.e.
(3.75, 4.0] µs nominal and (1.875, 8.0] µs across the `T_wd` band. A
realistic implementation samples an "edge seen" flag on each tick through a
two-flop synchronizer. That adds up to 3 ticks of latency, giving at most
19 × 500 ns = 9.5 µs and staying within the 10 µs bound. The lower bound only
grows. The slowest legal `REF` gap is 1.0 µs, so the minimum timeout of
1.875 µs leaves a margin of more than 1.8×.

**Realization within a standard-cell architecture.** The watchdog is a
free-running ring oscillator built from `sky130_fd_sc_hd` cells: an odd
inverter or delay-cell chain with a NAND enable tied on, followed by a ripple
divider down to about 250 ns per tick. It needs no new analog device. Its
frequency varies with PVT, which is why the contract is written as a band,
not a single time. #231 must show the ring's period stays inside the
0.5×–2× band over the row 19 × 20 × 1 grid. If it cannot, the fix is a
superseding DR that changes `K` or the band. Changing the model alone is not
a fix.

**Architecture revision.** #231's original recommendation was an
edge-coincidence window counter fed by the PFD's `UP`/`DN`. This contract
revises it in three ways before any implementation starts:

1. **Inputs.** The detector reads `REF` and `FBCLK` directly instead of
   `UP`/`DN`. `UP`/`DN` are internal to `pfd_cp`, whose ports are `VDD`,
   `GND`, `REF`, `DIV`, `CP`, and their pulse widths include the PFD reset
   delay.
2. **Frequency test.** A per-cycle `FBCLK` edge count is added. Coincidence
   alone accepts harmonics; see the negative control below.
3. **Timing source.** An independent watchdog oscillator and two timeout
   counters are added.

The block stays all standard-cell.

### 6. Boundary conventions

- Phase windows are inclusive: `|e| = W_acq` is GOOD and `|e| = W_rel` is
  not BAD. One picosecond beyond either boundary changes the class.
- The pairing interval `I_k` is open at `f_(k-1)` and closed at `f_k`.
- Events at the same time are ordered `RESETB` change, watchdog tick,
  `FBCLK` rise, `REF` rise, `REF` fall. Consequences:
  - an `FBCLK` edge exactly at `f_k` is counted in `I_k`;
  - a tick coincident with an edge counts toward the gap that edge ends;
  - a `RESETB` fall coincident with an edge wins, and the edge is ignored;
  - an edge coincident with a `RESETB` rise is processed;
  - simultaneous `REF` and `FBCLK` timeouts are reported as `REF`.
- All model times are integer picoseconds, so every boundary above is exact.

### 7. Units and scaling across the supported `REF` range

The phase windows are absolute times. A std-cell delay realizes a time, not a
phase. The counts are `REF` cycles. The timeouts are absolute times.

| `f_ref` | `W_acq` = 2.5 ns | `W_rel` = 6.0 ns | `Q` time | `R` time | Largest constant FBCLK/REF frequency error that can still qualify |
|---|---|---|---|---|---|
| 1 MHz (`T` = 1 µs) | 0.25 % of T, ±0.9° | 0.6 %, ±2.2° | 32 µs | 4 µs | 161 ppm |
| 10 MHz (`T` = 100 ns) | 2.5 %, ±9° | 6 %, ±21.6° | 3.2 µs | 0.4 µs | 0.16 % |
| 25 MHz (`T` = 40 ns) | 6.25 %, ±22.5° | 15 %, ±54° | 1.28 µs | 0.16 µs | 0.40 % |

The last column is `2·W_acq / ((Q−1)·T)`. A constant fractional frequency
error δ moves the phase by δ·T each cycle, so it cannot stay inside ±`W_acq`
for `Q` consecutive evaluations when δ is larger than that value.
`CycleSlip::test_persistent_frequency_error_never_locks` shows this at 2 %.
At 1 MHz, `Q` costs 32 µs of `LOCK` latency on top of the loop's own
settling. That matters if `LOCK` is ever chosen as row 8's "stated lock
criterion" (< 100 µs), and it is flagged here rather than decided.

## Relationship to the harness lock criterion

`measure.py::lock_time` with `tb.json`'s block (`target_hz` 250 MHz,
`tolerance_frac` 0.05, `window_cycles` 20, `min_hold_cycles` 20) is the
**harness frequency-lock**. It is not hardware `LOCK`, and no record should
call it that.

| Aspect | Harness frequency-lock (`measure.py`) | Hardware `LOCK` (this DR) |
|---|---|---|
| Observes | `CLK` rising edges only | `REF` and `FBCLK` edges, plus the watchdog |
| Quantity | mean `CLK` frequency over every 20-`CLK`-cycle sliding window | per-`REF`-cycle edge count and phase error |
| Tolerance | ±5 % of a fixed `N·f_ref` target | one edge per cycle; phase within ±2.5 ns to assert, ±6.0 ns to hold |
| Window | 20 `CLK` cycles (80 ns at 250 MHz, shorter than one 10 MHz `REF` period) | 32 `REF` cycles to assert, 4 to release |
| Causality | non-causal: needs the rest of the run ("through the end of the simulated window") | causal: decides at each `REF` falling edge |
| Hysteresis or release | none; one time-to-lock per run | yes, and `LOCK` can release and re-assert |
| Reset / clock loss | not modelled | defined (§4, §5) |
| Needs target `N` | yes (`target_hz`) | no |

**When they agree.** On an ideally locked loop both report lock, and the
harness lock instant comes first: hardware `LOCK` needs 32 further `REF`
cycles and phase alignment, not just frequency. The hardware criterion is
much tighter (≤ 0.4 % at 25 MHz, last column of the §7 table, against ±5 %). So whenever `LOCK`
holds over a stretch, the mean `FBCLK` frequency over that stretch is within
that bound of `f_ref`. The mean `CLK` frequency over the same stretch is then
within it of `N·f_ref`, provided the divider divides correctly. Agreement is
therefore expected only when three things hold: the loop is phase-locked, the
divider is correct, and the short-term `CLK` frequency inside a `REF` cycle
stays within ±5 %.

**Where they must differ.**
`design/lock-detector/tests/test_harness_comparison.py` runs both criteria on
the same synthetic streams:

- `CLK` 1 % off target: harness lock yes, `LOCK` no, because the phase walks
  1 ns per `REF` cycle.
- `CLK` on target with `FBCLK` silent (divider dropout): harness lock yes,
  `LOCK` no.

The reverse also occurs: a correctly phase-locked loop run with a different
`N` than the manifest's `target_hz` is `LOCK`-locked but not harness-locked.
The test pins `tb.json`'s numbers, so a later manifest change surfaces here.
`tb.json` and `measure.py` are unchanged by this record. Existing `sim/`
records are untouched and stay append-only.

## Executable reference and its evidential limits

`design/lock-detector/lockdet_ref.py` implements §2–§6 exactly, in integer
picoseconds. The tests give literal expected `LOCK` transition times and
causes for every case below:

- acquisition and sustained lock;
- just inside and just outside both windows, on both sides, including 25 MHz
  at 30 % and 70 % duty and at 1 MHz;
- reset during qualification and during lock;
- dropped and extra `FBCLK` edges, and a dropped `REF` cycle;
- `REF`, `FBCLK`, and both stopped, and restart of each;
- watchdog quantization at the fast, nominal and slow ends of the band, and
  at a tick phase offset;
- a full cycle slip, and a persistent frequency error;
- 2:1 and 1:2 harmonics with perfectly coincident edges.

Two **negative controls** show what each mechanism is for:

- With frequency qualification removed (pure coincidence), a 2:1 harmonic
  asserts `LOCK` at 3.35 µs and a 1:2 harmonic at 6.55 µs. With it, neither
  ever asserts.
- With the watchdog removed, a stopped `REF` (and a both-stopped case) leaves
  `LOCK = 1` to the end of a 100 µs run. With it, `LOCK` falls at 12.0 µs.

This is **behavioral-reference evidence only**. It shows that the contract is
self-consistent and that the stated values reject the stated false-lock
cases on ideal edges. It shows nothing about cell delays, metastability,
PVT, or whether the real loop's locked phase offset fits inside `W_acq`. Row
16 has no hardware evidence, and `measurements/report.md` must not cite this
as row 16 evidence.

## Implementation handoff for #231 (bounded)

1. **Block** (`design/lock-detector/`, standard-cell, following
   `design/README.md`): ports `VDD`, `GND`, `REF`, `FBCLK`, `RESETB` in;
   `LOCK` out. Internals:
   - the phase test. It needs `REF` and `FBCLK` each delayed by `W_acq` and
     by `W_rel`, from `sky130_fd_sc_hd` delay-cell chains, with sample flops
     deciding "edge after `r − W`" and "edge before `r + W`";
   - a 2-bit saturating `FBCLK` edge counter, captured and cleared at the
     `REF` falling edge;
   - a 6-bit `q` counter, a 3-bit `m` counter and the `LOCK` flop, clocked by
     the `REF` falling edge;
   - the watchdog ring oscillator and divider;
   - two 5-bit saturating timeout counters with "edge seen" capture flops and
     a two-flop synchronizer;
   - async clear from `RESETB`.

   Metastability note for verification: `FBCLK` edges come near a `REF`
   falling edge only when `|e| ≥ 12 ns`, which is already BAD by phase. In a
   2:1 harmonic, a wrong resolution of the boundary count can at most make
   alternate cycles look GOOD, and that cannot produce `Q` consecutive GOOD
   evaluations.
2. **Top level**: add `LOCK` to `top.sch`/`top.sym`. The block reads the
   existing `REF`, `FBCLK` and `RESETB` nets. No other block changes.
3. **PVT verification** (append-only `sim/` records, over the ratified
   rows 19 × 20 × 1 grid):
   - (a) extract `W_acq`, `W_rel` and `T_wd` per point against Table 2;
   - (b) a block-level testbench that replays this reference's stimulus set
     as PWL sources and compares `LOCK` transitions with the reference. The
     tolerance is evaluation instants within the block's own clock-to-`LOCK`
     delay, and timeouts within the Table 2 bounds;
   - (c) in the closed loop, record `LOCK` assertion time beside the harness
     frequency-lock time as separate columns, never merged;
   - (d) measure the locked static phase offset and `FBCLK` jitter, and show
     they fit inside `W_acq,min`.

   A miss in (a) or (d) is recorded as a miss. A superseding DR then argues
   any change of values on its merits.
4. **Out of scope for #231 unless a DR adds it**: any change to the harness
   criterion or to row 8's choice of lock criterion.

## Alternatives considered

- **Edge-coincidence counter only (#231's original).** Rejected. It accepts
  2:1 and 1:2 harmonics (negative control) and cannot see `REF` loss.
- **Mutual watchdogs** (`CLK` times `REF`, `REF` times `FBCLK`). Rejected.
  When both stop, nothing is left to time them, and the VCO can stop or run
  at an unbounded frequency in exactly the faults of interest.
- **Phase window in `CLK` periods** (for example, sample the divider state at
  the `REF` edge). Deferred. The window would scale as `T_ref/N`, not with
  `f_ref`. It would need divider internals as a new port, and `CLK` is not
  independent of the loop. Revisit if the Table 2 delay-cell bands cannot be
  met over PVT.
- **Phase window as a fixed fraction of `T_ref`.** Deferred. It needs a timing
  source that scales with `f_ref`. Only `REF` provides one, and the
  falling-edge pairing interval already uses it for the frequency test.
- **Analog lock detection** (RC monostable, or a `VCTRL` window). Rejected. It
  adds analog, and #231 already rejected the `VCTRL` approach.
- **Multi-cycle frequency counter** (count `FBCLK` against `REF` over M
  cycles). Not adopted separately. With phase gating, the per-cycle count is
  its M = 1 case, and a longer window only adds latency.
- **Immediate release on a frequency fault (R = 1 for `n ≠ 1`).** Rejected for
  v1. One `R` for every BAD cause keeps the contract uniform and filters a
  single glitch. Persistent loss is still caught within `R` cycles or the
  timeout.

## Consequences

- Gives #231 a concrete, testable contract and an executable oracle. #231
  must be re-curated against Table 1, Table 2 and the handoff before Builder
  dispatch.
- Costs:
  - four delay chains, a free-running ring oscillator and about 20 flops of
    area;
  - the ring is a new on-chip aggressor on the single shared `VDD` (row 1).
    Its spur and supply interaction is relevant to the deliberately open
    rows 10 and 13 and must be considered when those rows are argued;
  - `LOCK` latency of 32 `REF` cycles (32 µs at 1 MHz).
- Risk: delay-cell spread over PVT may not fit the Table 2 bands. If not, a
  superseding DR is needed, possibly adopting the `CLK`-period alternative.
- Row 16 text in `spec/target-spec.md` is unchanged and stays DRAFT. It only
  gains a pointer to this proposed record. Row 8 is unchanged.

## Status notes

- Stays `proposed` at least until #231 produces the PVT evidence listed in
  the handoff. Ratification of row 16 is an operator action, for example
  approval of a ratifying DR or PR, as with DR-002/DR-003. This record does
  not ratify anything by being merged.
- Any change to a number in Table 1 or Table 2 goes through a superseding DR
  and the matching test update in `design/lock-detector/tests/`. The tests
  are pinned to these values on purpose.
