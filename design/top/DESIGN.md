# Top-level integration — design rationale (issue #28)

Top-level closed-loop schematic for the sky130 PLL, the integration step of
the `#14` decomposition. This document records the wiring rationale behind
`top.sch`/`top.sym` — how the four already-standalone blocks (#24 VCO, #25
PFD + charge pump, #26 loop filter, #27 divider) are connected into the
standard integer-N charge-pump PLL closed loop. **No `sim/` evidence record
exists for this schematic** (that is #23 plus the PVT campaign gated on the
spec rows each block still targets) — this issue's own scope is connectivity,
not verified closed-loop behavior. Issue #44 fixed a SPICE instance-naming
defect inside the divider block that had been blocking any ngspice run of
this netlist (see "Verification performed for this issue" below) and
confirmed, with an ad hoc (not committed) ngspice transient run, that the
regenerated `top.spice` now elaborates and simulates to completion — still
not a `sim/` evidence record or a performance claim, just confirmation the
netlist is simulatable.

## Forward design, not reverse-engineered

This is the textbook charge-pump integer-N PLL loop topology — PFD compares
a reference clock against a divided feedback clock, drives a charge pump,
which drives a loop filter, which drives a VCO, whose output both is the PLL
output and feeds the divider that closes the loop — described in every
standard PLL text (Gardner, Best, Razavi) and used throughout the published
charge-pump PLL literature. Nothing here originates in another chip's
silicon or netlist, per `CLAUDE.md`'s reverse-engineering-free rule. This
issue adds **no new active or passive devices** — it is purely a
hierarchical instantiation and wiring of the four block schematics already
authored (and independently reviewed/merged) by #24, #25, #26, #27.

## Scope: wiring the closed loop, not re-deriving any block's sizing

This issue's job is schematic-level connectivity: instantiate the four
existing block symbols and connect them into the closed loop described
below. It does **not** re-open, resize, or resimulate any individual
block's own devices — every block's own `DESIGN.md` (topology choice, sizing
rationale, device tables) stands as authored by its own issue. See "Known
coordination gap not resolved here" below for the one place this
deliberately stops short of a full reconciliation.

## Topology and wiring

```
        REF                                    CP                 VCTRL
top --------> [ PFD + charge pump ] --------> [ loop filter ] -----------> [ VCO ] ---> CLK ---> top
                     ^        (#25)                  (#26)                  (#24)        |
                     | DIV                                                                |
                     |                                                                    |
                     +------------------------------ FBCLK <---------- CLK -------- [ divider ] <--- RESETB, NSEL[5:0]
                                                                                        (#27)              (from top)
```

Concretely, in `top.sch`:

| Net | From | To |
|---|---|---|
| `REF` | top-level input pin | `pfd_cp.REF` |
| `FBCLK` | `divider_intN.FBCLK` | `pfd_cp.DIV` |
| `CP` | `pfd_cp.CP` | `loop_filter.CP` |
| `VCTRL` | `loop_filter.VCTRL` | `vco_ring5.VCTRL` |
| `CLK` | `vco_ring5.CLK` | top-level output pin **and** `divider_intN.CLK` |
| `RESETB` | top-level input pin | `divider_intN.RESETB` |
| `NSEL0`..`NSEL5` | top-level input pins | `divider_intN.NSEL0`..`NSEL5` |
| `VDD`, `GND` | top-level supply pins | `pfd_cp`, `vco_ring5`, `divider_intN` (all three; `loop_filter` has no `VDD` pin — purely passive, see `design/loop-filter/DESIGN.md`) |

This is exactly the topology the issue text specifies (`REF -> PFD <-
divider feedback; PFD -> charge pump -> loop filter -> VCO control input;
VCO output -> CLK and -> divider input`) — no additional signal paths, no
auxiliary acquisition circuitry, matching the tri-state PFD's own
self-contained frequency-acquisition behavior documented in
`design/pfd-cp/DESIGN.md` (a tri-state PFD needs no separate
frequency-acquisition aid).

## Schematic-capture method: net labels, not drawn wires

Every net above is realized in `top.sch` using this repo's established
label-based wiring convention (the same one all four block schematics
already use internally, with **zero** explicit wire/`N` segments in any of
them): a `devices/ipin.sym` / `opin.sym` / `iopin.sym` / `lab_pin.sym`
instance is placed exactly coincident with each block instance's own pin
location (computed from the block's placement offset plus its symbol's own
pin coordinates), tagged with a `lab=<net>` attribute. Two pins carrying the
same `lab=` value are the same net, regardless of their placement distance
from each other — the standard xschem net-label mechanism this repo already
relies on throughout `design/vco/vco_ring5.sch`, `design/pfd-cp/pfd_cp.sch`,
`design/loop-filter/loop_filter.sch`, and `design/divider/divider_intN.sch`.
Each hierarchical port name (`VDD`, `GND`, `REF`, `RESETB`, `NSEL0..NSEL5`,
`CLK`) has exactly one `ipin`/`opin`/`iopin` declaration (the actual port
declarator xschem's netlister emits `.ipin`/`.opin`/`.iopin` for); any
additional touch point on the same net elsewhere in the schematic uses a
plain `lab_pin.sym` copy, matching the convention every other `.sym`'s own
schematic already established for reusing one label at multiple physical
locations.

## Interface adaptation: none needed

Every signal crossing a block boundary in this schematic needed **no**
level shifting, buffering, or other adaptation, because all four blocks were
independently designed against the identical ratified supply flavor
(`DR-001`, `spec/target-spec.md` row 0: sky130 1.8 V core devices,
`sky130_fd_pr__{n,p}fet_01v8` for the VCO and PFD/charge pump,
`sky130_fd_sc_hd` standard cells — themselves built from the same core
devices — for the divider):

- **Digital signals** (`REF`, `FBCLK`/`DIV`, `CLK`, `RESETB`, `NSEL[5:0]`)
  are all already rail-to-rail `VDD`/`GND` sky130 1.8 V logic on both sides
  of every boundary they cross. In particular:
  - `vco_ring5.CLK` is driven by the VCO's own tapered output buffer
    (`MBUFB_*`, sized `W=16/8 µm` specifically "for adequate drive into
    whatever external/testbench load `CLK` sees," per
    `design/vco/DESIGN.md`) — a fan-out of two (the top-level `CLK` output
    pin plus `divider_intN.CLK`'s standard-cell input) is exactly the kind
    of external load that buffer was already sized to drive; no additional
    buffering is added here.
  - `divider_intN.FBCLK` is a registered standard-cell output
    (`sky130_fd_sc_hd__dfxtp_2`, `design/divider/DESIGN.md` "Output
    register") — already a clean, glitch-free, full-swing digital signal,
    suitable to drive `pfd_cp.DIV`'s edge-detector input directly.
  - `pfd_cp.REF`/`pfd_cp.DIV` are plain PFD inputs feeding a 3-inverter
    edge-detector delay chain (`design/pfd-cp/DESIGN.md` "PFD
    implementation") — no special drive-strength requirement beyond a
    standard sky130 1.8 V logic input.
- **Analog signals** (`CP`, `VCTRL`) are already in the `0`–`VDD` range each
  neighboring block's own device sizing assumes:
  - `pfd_cp.CP` is the charge pump's own current-injection output node,
    whose compliance range (`design/pfd-cp/DESIGN.md` "Headroom analysis")
    is exactly what `loop_filter.CP` is designed to accept as an input
    (`design/loop-filter/DESIGN.md` documents `CP` as "driven by the charge
    pump's output" as its intended usage).
  - `loop_filter.VCTRL` drives `vco_ring5.VCTRL` directly — a MOSFET gate
    (no static current, per `design/loop-filter/DESIGN.md`'s "Vctrl headroom
    analysis," "no static current flows through `R3` in steady state"), so
    the loop filter's own output impedance does not need to drive any real
    load current, and the VCO's ~0.8–1.6 V demonstrated free-running
    `VCTRL` range (`design/vco/DESIGN.md`'s sanity-check table) is the same
    range the loop filter's own DC operating-point analysis assumes
    `VCTRL` settles into.

No new device (level shifter, buffer, resistor divider) is added anywhere in
`top.sch` — the four blocks' own device-level design choices already made
them electrically compatible at their shared boundaries.

## Programming interface: `NSEL[5:0]` and `RESETB` exposed as top-level pins

Consistent with `design/divider/DESIGN.md`'s own scope note ("Whoever
instantiates this block ... is responsible for strapping `NSEL[5:0]` to
`VDD`/`GND` ... to select N," naming this integration sub-issue explicitly),
`top.sch` exposes `NSEL0`..`NSEL5` and `RESETB` as plain top-level input
pins rather than hardwiring them to a fixed value internally. This keeps the
divide ratio and reset configurable by whatever testbench or higher-level
integration eventually instantiates `top.sym` (a future closed-loop
testbench, #23), rather than baking a specific `N` into the schematic here —
consistent with row 4's own "static configuration" v1 scope (a testbench or
board-level strap sets the value, not this schematic).

## Known coordination gap not resolved here: loop filter's `Icp` placeholder

`design/loop-filter/DESIGN.md` (issue #26) was authored before
`design/pfd-cp/` existed on `main`, using a documented **`Icp = 5 µA`
placeholder** (its own "Coordination note" section) specifically because the
real value from #25 was not yet available; its R1/C1/C2/R3/C3 sizing
equations are parameterized precisely so a real `Icp` could be dropped in
and the values recomputed once available. `design/pfd-cp/DESIGN.md` (#25)
subsequently landed **`Icp = 10 µA`** — 2x the loop filter's placeholder —
independently justified against its own bias-branch/mirror sizing, and its
own "Coordination note" section explicitly assigns reconciling the two to
"the integration sub-issue tracked on `#14`" (this issue).

**This issue does not perform that reconciliation.** Recomputing
`loop_filter.sch`'s component values is a sizing change to an
already-reviewed, already-merged sibling schematic (#26), not a wiring /
connectivity change — conflating the two in one PR would mix a pure
integration change with a design-value change to a different block, harder
to review and revert independently. `top.sch` wires `pfd_cp.CP` directly to
`loop_filter.CP` exactly as designed by each block; the mismatch between the
loop filter's `Icp` design point (5 µA) and the charge pump's actual output
current (10 µA) means the loop filter's realized zero/pole frequencies and
phase margin (`design/loop-filter/DESIGN.md`'s "Component values" /
"Realized loop performance" tables) are computed against a design point
that is now known to be off by 2x from the actual upstream block — a real,
open gap, not silently glossed over here. **This is flagged as a natural
follow-up** (recompute `design/loop-filter/loop_filter.sch`'s `R1`/`C1`/
`C2`/`R3`/`C3` against `Icp = 10 µA`) rather than built into this
connectivity-only PR. No `spec/target-spec.md` row is affected either way —
rows 5 (Kvco), 6 (loop bandwidth), 7 (phase margin) all stay DRAFT.

## No closed-loop simulation performed

**No `sim/` evidence exists for this schematic; no transient, AC, or
lock-time simulation was run.** Per this issue's own scope (and the
constraint given to this Builder), closed-loop verification is #23 (a
testbench for this exact hierarchy) plus whatever PVT campaign follows
once the DRAFT spec rows each block targets are ratified. Nothing in this
document is a claim against `spec/target-spec.md` — consistent with
`CLAUDE.md`'s "no claim without a testbench" rule.

## Known gap: closed-loop cold-start convergence (issue #98)

A later campaign than the one above now exists: `sim/pll-lock` (issue #52,
widened to the full DR-003 45-point PVT grid by #89/#99) is a real, committed
closed-loop cold-start evidence record against this schematic — the
statement in "No closed-loop simulation performed" above was accurate for
issue #28's own authoring-time scope, not for the repository's current
state. The current record,
`sim/pll-lock/records/20260905-193322-0f1934d.md` (against `top.sch` at or
after #95's loop-filter re-size), shows **3 of 45** points locking within
the manifest's 3 µs transient window; the other 42 fail, split between two
dominant modes: "no oscillation" (0 rising edges observed) and "no lock
within window" (the loop free-runs at a frequency far from 250 MHz and
never satisfies the lock criterion before the transient ends).

Issue #98 asked, before any `Icp`/loop-filter/VCO-bias redesign is
attempted, whether these failures are a real cold-start convergence problem
or a `tran_stop` measurement-window artifact (the manifest's 3 µs window is
far shorter than `spec/target-spec.md` row 8's DRAFT <100 µs lock-time
budget). A small number of informal, uncommitted single-point diagnostics
(ad hoc ngspice runs in a scratch directory, not a `sim/` evidence record —
same convention as `design/vco/DESIGN.md`'s own "informal sanity check"
table) were run against two of the 45 points to probe this, both at
`tt`/27 °C and `tt`/125 °C, 1.80 V, both baseline "no oscillation" verdicts:

1. **Re-running the exact committed manifest for `tt`/27 °C/1.80 V**
   reproduces "no oscillation" in ~2 minutes of wall time (well under the
   manifest's 1800 s per-point timeout) — this is a fast, clean convergence
   to a non-oscillating DC operating point, not a slow/stiff simulation
   that might resolve given more time. This is consistent with SPICE's
   exact-device-symmetry idealization: an odd-stage ring oscillator with
   perfectly identical devices and no explicit asymmetry can settle at (and
   never depart from) a degenerate fixed point that real, mismatched,
   noisy silicon would not sit at indefinitely — a known simulation
   artifact for symmetric ring oscillators, though not something this pass
   fully separates from a genuine silicon startup risk (that needs Monte
   Carlo mismatch/noise injection, out of this issue's scope).
2. **Forcing the harness's own documented cold-start nudge**
   (`measure.ic: ["v(xxxtop.xxvco.ring0)=0"]`, `sim/harness/measure.py`'s
   already-supported `ic` manifest field) breaks that degeneracy: the VCO
   free-runs from the start of the transient in both diagnostics below.
3. **`tt`/125 °C/1.80 V, kicked, `tran_stop` widened to 30 µs**: **locks at
   26.32 µs**, f_out 251.5 MHz, 50.1% duty — inside the DRAFT <100 µs row-8
   budget. For this corner, the baseline "no oscillation" verdict was
   entirely explained by the combination of (1) and the 3 µs window being
   too short to see the eventual lock — not a real design defect.
4. **`tt`/27 °C/1.80 V, kicked, a direct 5 µs ngspice transient** (not run
   through the harness) shows a different, un-window-fixable failure: the
   VCO free-runs at ~1.07 GHz — near the top of its own informally-measured
   tuning range (`design/vco/DESIGN.md`'s sanity-check table) — and `VCTRL`
   creeps monotonically toward `VDD` for the entire window with no sign of
   correction. Inspecting the divider's `FBCLK` output directly shows it
   pulses exactly once, at reset release, and then **never toggles again**
   for the rest of the 5 µs window (~5000 VCO cycles, versus the ~25-cycle
   period `FBCLK` should show if the divider were counting normally). With
   `FBCLK` dead, the PFD/charge pump has no negative-feedback signal at all
   and keeps pumping `VCTRL` toward the rail — a genuine loss-of-feedback
   lockup, not a slow convergence. No amount of additional simulated time
   would fix this corner as currently designed; root-causing *why*
   `divider_intN`'s counter chain (`sky130_fd_sc_hd__dfrtp_2`-based, see
   `design/divider/DESIGN.md`) stops toggling once driven at a free-running
   VCO frequency well above the 250 MHz target was not completed in this
   pass.

**Conclusion**: both of #98's competing hypotheses are real, and — at least
across these two probed corners — they compound *differently* per corner;
neither "it's just the window" nor "it's just VCO self-start" is a correct
blanket explanation. This means the existing `sim/pll-lock` manifest (3 µs
window, no cold-start nudge) cannot currently distinguish "would lock given
a fair chance" from "genuinely broken" for most of the 42 failing points —
attempting an `Icp`/loop-filter/VCO-bias redesign against that evidence risks
tuning against a measurement artifact rather than the real defect. Widening
`tran_stop` and adding a committed cold-start nudge to `sim/pll-lock`'s
manifest, then re-running the full 45-point grid, is a harness-fix
prerequisite to any such redesign — tracked as a follow-up (#100:
`sim/pll-lock/testbench/tb.json`, `sim/run_corners.py`), together with
root-causing the `divider_intN` `FBCLK` dropout above, rather than attempted
in this pass. This section reflects issue #98's own acceptance criterion
("determine whether failures are real, artifact, or both") as its complete,
evidence-based answer for the two corners probed; it is not itself a
45-point re-run and does not substitute for one.

### Harness-defaults follow-up (issue #100, item 1)

The harness-fix prerequisite named above has now landed:
`sim/pll-lock/testbench/tb.json` carries the cold-start nudge and widened
window as **permanent manifest defaults** rather than one-off diagnostic
overrides — `measure.ic: ["v(xxxtop.xxvco.ring0)=0"]`, `measure.tran_stop`
`3u` → `100u` (matching row 8's own DRAFT budget), and `measure.timeout_s`
`1800` → `10800` to accommodate the larger per-point wall-clock cost.
`spec/decision-records/DR-004-pll-lock-cold-start-nudge-and-window.md`
argues the full justification for why the nudge is representative of real
silicon startup behavior (breaking a SPICE exact-device-symmetry
idealization no real, mismatched, noisy device has) rather than papering
over a genuine defect, including why it does not risk manufacturing a false
lock (point 4 above — a nudged corner that still fails to lock for an
unrelated reason still correctly reports "no lock within window").

This change was smoke-tested, not full-grid-verified, before landing: the
new `.control` block (`sim/harness/measure.py`'s `build_control_block`)
generates the expected `.ic v(xxxtop.xxvco.ring0)=0` / `tran 200p 100u`
cards from the updated manifest, and a bounded (900 s), uncommitted
single-point run at `tt`/27 °C/1.80 V — the exact corner the nudge targets
— launched a real ngspice invocation against the widened-window netlist
that ran for the full bounded window without a netlist/parse error before
being cut off (100 µs is well beyond what fits in a 900 s smoke-test
budget; the existing 30 µs diagnostic above already cost 25–40 minutes of
wall time). This confirms the new defaults are syntactically and
operationally valid, not that any specific corner's verdict changed — that
determination is `#100` item 2's full re-run, not this pass.

This change is **methodology only** — no design file changed, and
`spec/target-spec.md` row 8 stays DRAFT. It does not itself constitute a
new `sim/pll-lock` evidence record: `20260905-193322-0f1934d.md` (recorded
against the prior 3 µs/no-nudge defaults) remains the most recent committed
full-grid baseline until a fresh 45-point re-run against these new defaults
lands. That re-run, and root-causing the `divider_intN` `FBCLK` dropout
(point 4 above), are `#100`'s items 2 and 3 — still open, still tracked
there, and still not attempted in this pass.

### Divider `FBCLK` dropout, root-caused (issue #100, item 3)

`design/divider/DESIGN.md`'s new "Measured finding (issue #98/#100)" section
answers what point 4 above left open. A standalone digital-only diagnostic —
`divider_intN` alone, driven by an **ideal** clock source at a fixed
frequency, completely decoupled from the VCO/PFD/charge pump/loop filter —
reproduces the exact failure mode: clean divide-by-25 operation through at
least 800 MHz input clock, and a complete, deterministic `FBCLK` dropout
(zero rising edges over hundreds of input cycles) at 950 MHz and above. This
is a real synchronous-counter timing-closure limit of the
`sky130_fd_sc_hd`-based borrow chain/output register (see that section for
the full per-frequency table and methodology) — **not** a cold-start reset
race, not an analog loop-dynamics artifact, and not a measurement-window
artifact, since the isolated digital testbench has none of those things:
`RESETB` releases once at the start and the clock runs clean and steady for
the rest of each run.

This closes item 3's open question ("a fundamental timing limit of the
chosen standard cells... a bug in the borrow-chain/zero-detect logic, or a
cold-start reset-release race") with a measured answer: **a fundamental
timing limit**, somewhere between 800 MHz and 950 MHz input clock — well
below the ~1.09 GHz ceiling the VCO's own sanity-check table demonstrated
and below `design/divider/DESIGN.md`'s own original (now-corrected)
plausibility claim that closure held "comfortably inside" that range.

**What this means for #98's redesign direction.** The divider's ceiling is
comfortably above the 250 MHz closed-loop lock target itself (demonstrated
clean through 800 MHz) — a locked loop is not at risk. The risk is entirely
a **cold-start transient** one: `sim/pll-lock`'s baseline record's dominant
failure signature (`VCTRL` pinned near a rail, output frequency far above
250 MHz, `FBCLK` presumably dead) is now explained end-to-end — the VCO's
very steep, wide-open tuning range (`design/vco/DESIGN.md`: ~145 MHz–
~1.09 GHz across its own demonstrated `VCTRL` span, far exceeding row 5's
DRAFT `Kvco` bound) lets an uncontrolled cold-start `VCTRL` reach the
divider's broken band before the loop has any working feedback to correct
it, at which point feedback is permanently gone and `VCTRL` has nothing
pulling it back. Two independent classes of fix follow from this, not yet
attempted:

1. **Keep the divider as-is; bound the cold-start `VCTRL` excursion**
   below ~800 MHz-equivalent via the VCO-bias/`Icp`/loop-filter levers issue
   #98 already scoped (e.g. a charge-pump current or loop-filter time
   constant that slows or clamps the initial `VCTRL` ramp so the VCO never
   transits the divider's broken band during acquisition). This does not
   touch an already-reviewed digital block's standard-cell sizing.
2. **Fix the divider's own timing closure** (faster-drive-strength cells on
   the borrow-chain/output-register critical path, a retimed/pipelined
   counter, or the dual-modulus-prescaler escalation `design/divider/
   DESIGN.md`'s "Retiming" section already named as a candidate) so the
   divider tracks the VCO's full demonstrated range regardless of what the
   loop does during acquisition.

Neither is implemented in this pass — this section is the root-cause finding
`#100` item 3 asked for, not the redesign itself. `#100`'s remaining scope
(full 45-point re-run) is only informative **after** one of the two paths
above is chosen and implemented; re-running the full grid against the
harness-only defaults change (item 1, landed) without addressing this root
cause would be expected to reproduce substantially the same failure pattern,
since the underlying mechanism (cold-start `VCTRL` transiting a digitally-
broken frequency band) is unaffected by a wider window or a startup nudge.

**A note on per-point cost, measured directly in this pass**: a single
`sim/pll-lock` point (`tt`/27 °C/1.80 V) run to completion against the new
100 µs-window/nudge defaults did not finish inside 57 minutes of wall time
on a heavily contended multi-agent host before being stopped as no longer
needed (the digital-only diagnostic above had already isolated the real
defect by then) — consistent with, and considerably more pessimistic than,
this document's own earlier "25-40 minutes" smoke-test estimate for a 30 µs
window. A full 45-point re-run at these defaults is realistically a
multi-hour-to-multi-day serial campaign on a shared host, not a
single-sitting task; `#100` item 2 should budget accordingly (dedicated/
batch execution, or parallelized across points, rather than a single
interactive run).

### The campaign was not measuring a cold start at all (issue #98)

Everything above — including this section's own two-corner diagnostics, and
`DR-004`'s startup-nudge/window reasoning — assumed that `sim/pll-lock`'s
transients begin at a power-on state. They do not, and that assumption is
now measured to be false.

`sim/harness/measure.py`'s `build_control_block` emits `tran <step> <stop>`
with no `uic`, so every point starts from ngspice's **transient operating
point**. For this closed loop that operating point is not a cold start: in
DC the ring sits at its metastable midrail equilibrium, so `CLK` is static,
the divider's `FBCLK` never toggles, the PFD's `UP`/`DN` are static, and the
charge pump's output node settles wherever the static leakage balance puts
it with only the (DC-open) loop-filter capacitors attached. Measured over
fifteen PVT points, the `VCTRL` every transient has actually been starting
from ranges across **the entire supply rail** — 1.9 µV at `ff`/−40 °C/
1.80 V, 0.900 V at `ss`/−40 °C/1.80 V, 1.601 V at `ss`/27 °C/1.98 V,
1.800 V at `fs`/125 °C/1.80 V — as a function of PVT corner, and it moves
when an unrelated node's `.ic` card is added.

Cross-referencing those starting voltages against the committed open-loop
VCO record (`sim/vco/records/20260904-163130-f3ae976.md`) accounts for
essentially every verdict in the current committed closed-loop baseline:
the "no oscillation" points are the ones whose operating point put `VCTRL`
at ~0 V (a genuine cold start, but with a then-3 µs window far too short to
ramp anywhere); the high-frequency "no lock" points started above the
divider's 800 MHz ceiling with the feedback path already dead, and their
reported final-window frequencies match the open-loop record's frequency at
that same control voltage to within a few percent; and **all three
"locks" started with `VCTRL` already inside the loop's pull-in range of that
corner's own 250 MHz control voltage** — the loop was initialized
approximately locked, and the reported 1.38–1.71 µs "time-to-lock" is the
lock detector's settle-plus-hold latency, not an acquisition transient.

This also explains the pattern issue #98 flagged as suspicious — that the
locking-corner set changed almost completely between records rather than
growing outward. What is fragile to small parameter shifts is not the loop's
cold-start trajectory; it is the DC operating-point solution, which has no
physical meaning here.

**Fix, landed with this section**: `sim/pll-lock/testbench/tb.json`'s
`measure.ic` now also pins the loop filter's three storage nodes discharged
— `v(xxxtop.vctrl)=0`, `v(xxxtop.cp)=0`, `v(xxxtop.xxlf.z1)=0` (`C1`'s
internal node; `C1` is 20x `C2` and 64x `C3`, so initializing only the
output node would leave the dominant capacitor arbitrarily charged).
Verified: t = 0 `VCTRL` is then exactly 0.000 V at all six corners re-probed,
the same corners that previously started between 0.900 V and 1.800 V. Full
argument, evidence tables and rejected alternatives (including why `uic` is
the wrong tool for this manifest):
`spec/decision-records/DR-005-pll-lock-cold-start-initial-conditions.md`.

**Consequence for the existing records.** Per `CLAUDE.md`'s append-only
rule the four committed `sim/pll-lock` records stay exactly as they are, and
this section does not supersede them — but their per-point verdicts are not
cold-start lock measurements, and the "1 of 45" / "3 of 45" lock counts
cited by issue #98, by `docs/chipalooza/challenge-4-proposal.md` § 6 and by
this document's own text above should be read as artifacts of the
operating-point solver until the re-run tracked in #103 lands.

### What a cold-start settling-time fix would actually have to target (#98)

With the initialization defect understood, the cold-start acquisition
problem can be stated quantitatively for the first time. Three measured
inputs, all from committed evidence or from informal probes described below:

1. **Cold-start charge-pump current.** During acquisition the divider's
   `FBCLK` is absent or far slower than `REF`, so the PFD holds `UP`
   asserted and the pump sources a near-constant current. Measured by
   driving `design/pfd-cp/`'s `pfd_cp` block open-loop (`REF` at the
   testbench's own 10 MHz stimulus, `DIV` strapped to `GND`, the `CP` node
   clamped by a DC source, averaged over 800 ns): **7.05 µA at `tt`/27 °C/
   1.80 V**, essentially flat in the pump's output-voltage compliance range
   (7.048 / 7.040 / 7.032 / 7.019 / 6.945 µA at `V(CP)` = 0.1 / 0.4 / 0.7 /
   0.9 / 1.2 V). Across PVT extremes: 4.91 µA (`ss`/−40 °C/1.62 V),
   6.50 µA (`ss`/125 °C/1.62 V), 7.08 µA (`fs`/−40 °C/1.98 V), 7.50 µA
   (`ff`/−40 °C/1.98 V) — a 1.53x spread, far tighter than the VCO's own
   2.53x `Kvco` spread. Note this is meaningfully below the 10 µA design
   point `design/loop-filter/DESIGN.md` sizes against.
2. **Loop-filter charge store.** `C1 + C2 + C3` = 207.6 + 10.42 + 3.23 =
   **221.25 pF** (`design/loop-filter/DESIGN.md`'s component table). On the
   ~10 µs timescale of acquisition all three are effectively in parallel
   (`R1·C1` = 1.09 µs, `R3·C3` = 34 ns, both short against it).
3. **Where the VCO's frequency lands per control voltage**, per corner —
   the committed 45-point open-loop record
   `sim/vco/records/20260904-163130-f3ae976.md`.

**The acquisition ramp.** `dVCTRL/dt = Icp/(C1+C2+C3)` = 22.2 mV/µs at the
slowest measured corner (`ss`/−40 °C/1.62 V) to 33.9 mV/µs at the fastest
(`ff`/−40 °C/1.98 V). Ramping from 0 V to that corner's own 250 MHz control
voltage therefore takes:

| PVT point | measured cold-start `Icp` | `dVCTRL/dt` | `VCTRL` at 250 MHz | ramp time |
|---|---|---|---|---|
| `ff`/−40 °C/1.98 V | 7.50 µA | 33.9 mV/µs | 0.870 V | 25.7 µs |
| `tt`/27 °C/1.80 V | 7.05 µA | 31.9 mV/µs | 0.869 V | 27.3 µs |
| `fs`/−40 °C/1.98 V | 7.08 µA | 32.0 mV/µs | 0.925 V | 28.9 µs |
| `ss`/125 °C/1.62 V | 6.50 µA | 29.4 mV/µs | 0.873 V | 29.7 µs |
| `ss`/−40 °C/1.62 V | 4.91 µA | 22.2 mV/µs | 0.914 V | 41.2 µs |

**Confirmed in the closed loop.** Those numbers are built from an open-loop
pump measurement and a component table, so they were checked against the
real thing: a 6 µs closed-loop transient of the committed netlist snapshot
with the corrected initial conditions in place starts at `VCTRL` = 0.0000 V
and ramps linearly — 0.0517 V at 0.6 µs, 0.1282 V at 3 µs, 0.2237 V at 6 µs
— i.e. **31.8 mV/µs measured at `tt`/27 °C/1.80 V against 31.9 mV/µs
predicted**, a 0.3 % agreement between two independent measurements. The
same run at `sf`/125 °C/1.80 V (the corner whose operating point previously
started `VCTRL` at 1.790 V) likewise starts at exactly 0.0000 V and ramps at
37.3 mV/µs. Both runs completed in about 7 minutes of wall time — the ring
is off for the whole window, so there is no GHz-rate oscillation to resolve,
which is worth knowing when budgeting the full re-run: a genuine cold-start
point is cheap for its first ~25 µs and only becomes expensive once the ring
starts.

This is a **hard floor** on cold-start lock time — no loop can lock before
its control node has been charged to the voltage the lock frequency needs.
It is 26–41 µs, versus `spec/target-spec.md` row 8's DRAFT `< 100 µs`
budget: the design fits, but with only 2.4x margin at the worst measured
corner, and the campaign's original 3 µs window was 9–14x too short to have
ever observed a lock. It also directly quantifies the mechanism #81
hypothesized: #95's `C1` re-size (53.25 pF → 207.6 pF) multiplied this
acquisition ramp by ~3.7x.

**The capture window.** The ramp does not stop at 250 MHz — it keeps going
until the loop captures. `design/divider/DESIGN.md` measures the divider
clean through 800 MHz and completely dead at 950 MHz, and once `FBCLK` dies
the loop has no feedback and `VCTRL` runs to the rail irrecoverably. So the
loop has exactly the `VCTRL` interval between its own 250 MHz point and its
own 800 MHz point to capture in. Log-interpolating the committed open-loop
VCO record at all 45 ratified PVT points:

| Corner | T (°C) | VDD (V) | `VCTRL` @ 250 MHz | `VCTRL` @ 800 MHz | capture window ΔV | f at `VCTRL` = VDD* |
|---|---|---|---|---|---|---|
| tt | −40 | 1.62 | 0.883 | 1.591 | 0.708 | 807 MHz |
| tt | −40 | 1.80 | 0.883 | 1.172 | 0.289 | 1182 MHz |
| tt | −40 | 1.98 | 0.888 | 1.138 | 0.249 | 1608 MHz |
| tt | 27 | 1.62 | 0.863 | 1.523 | 0.660 | 828 MHz |
| tt | 27 | 1.80 | 0.869 | 1.198 | 0.329 | 1123 MHz |
| tt | 27 | 1.98 | 0.881 | 1.168 | 0.287 | 1466 MHz |
| tt | 125 | 1.62 | 0.849 | 1.599 | 0.750 | 806 MHz |
| tt | 125 | 1.80 | 0.865 | 1.316 | 0.451 | 1038 MHz |
| tt | 125 | 1.98 | 0.882 | 1.252 | 0.370 | 1303 MHz |
| ff | −40 | 1.62 | 0.856 | 1.230 | 0.373 | 931 MHz |
| ff | −40 | 1.80 | 0.861 | 1.110 | 0.250 | 1366 MHz |
| ff | −40 | 1.98 | 0.870 | 1.092 | **0.222** | 1814 MHz |
| ff | 27 | 1.62 | 0.835 | 1.251 | 0.416 | 949 MHz |
| ff | 27 | 1.80 | 0.848 | 1.140 | 0.293 | 1270 MHz |
| ff | 27 | 1.98 | 0.863 | 1.128 | 0.264 | 1659 MHz |
| ff | 125 | 1.62 | 0.826 | 1.344 | 0.518 | 902 MHz |
| ff | 125 | 1.80 | 0.846 | 1.199 | 0.353 | 1141 MHz |
| ff | 125 | 1.98 | 0.866 | 1.188 | 0.322 | 1465 MHz |
| ss | −40 | 1.62 | 0.914 | never within the rail | 0.706 (to the rail) | 695 MHz |
| ss | −40 | 1.80 | 0.907 | 1.282 | 0.375 | 1035 MHz |
| ss | −40 | 1.98 | 0.911 | 1.180 | 0.269 | 1429 MHz |
| ss | 27 | 1.62 | 0.890 | never within the rail | 0.730 (to the rail) | 718 MHz |
| ss | 27 | 1.80 | 0.891 | 1.344 | 0.453 | 993 MHz |
| ss | 27 | 1.98 | 0.899 | 1.223 | 0.325 | 1317 MHz |
| ss | 125 | 1.62 | 0.873 | never within the rail | 0.747 (to the rail) | 719 MHz |
| ss | 125 | 1.80 | 0.884 | 1.472 | 0.588 | 925 MHz |
| ss | 125 | 1.98 | 0.898 | 1.337 | 0.439 | 1186 MHz |
| sf | −40 | 1.62 | 0.855 | never within the rail | 0.765 (to the rail) | 765 MHz |
| sf | −40 | 1.80 | 0.852 | 1.154 | 0.302 | 1149 MHz |
| sf | −40 | 1.98 | 0.858 | 1.107 | 0.249 | 1607 MHz |
| sf | 27 | 1.62 | 0.828 | 1.564 | 0.737 | 815 MHz |
| sf | 27 | 1.80 | 0.834 | 1.178 | 0.345 | 1124 MHz |
| sf | 27 | 1.98 | 0.846 | 1.139 | 0.293 | 1469 MHz |
| sf | 125 | 1.62 | 0.805 | 1.531 | 0.726 | 826 MHz |
| sf | 125 | 1.80 | 0.824 | 1.258 | 0.434 | 1057 MHz |
| sf | 125 | 1.98 | 0.845 | 1.194 | 0.349 | 1327 MHz |
| fs | −40 | 1.62 | 0.916 | 1.506 | 0.591 | 832 MHz |
| fs | −40 | 1.80 | 0.916 | 1.189 | 0.273 | 1193 MHz |
| fs | −40 | 1.98 | 0.925 | 1.166 | 0.240 | 1616 MHz |
| fs | 27 | 1.62 | 0.894 | 1.539 | 0.645 | 825 MHz |
| fs | 27 | 1.80 | 0.901 | 1.247 | 0.347 | 1115 MHz |
| fs | 27 | 1.98 | 0.917 | 1.196 | 0.278 | 1477 MHz |
| fs | 125 | 1.62 | 0.887 | never within the rail | 0.733 (to the rail) | 784 MHz |
| fs | 125 | 1.80 | 0.900 | 1.370 | 0.470 | 1000 MHz |
| fs | 125 | 1.98 | 0.922 | 1.313 | 0.390 | 1271 MHz |

*Derivation, so it can be checked or redone: each row log-interpolates that
PVT point's own six swept `(VCTRL, f)` pairs from
`sim/vco/records/20260904-163130-f3ae976.md`. Columns marked "never within
the rail" are corners whose ring does not reach 800 MHz anywhere in the
supply range — those six points cannot enter the divider's dead band at all,
and the ΔV shown is the whole remaining rail. The last column extrapolates
off the record's top swept segment (the sweep stops at `VCTRL` = 1.6 V), so
it is an estimate, not a measurement. This is arithmetic on committed
evidence, not a new measurement, and it is not a `sim/` record.

Read against the ramp rates above, the narrowest capture window —
`ff`/−40 °C/1.98 V, 0.222 V — is **6.5 µs** of cold-start ramp. The widest
is over 50 µs. At 39 of 45 points the ring would free-run above 800 MHz if
`VCTRL` ever reached the rail, so at 39 of 45 points a failure to capture
inside that window is unrecoverable.

**Which design levers actually move this, and which do not.** Working from
`design/loop-filter/DESIGN.md`'s own sizing derivation, `C1 = Icp·Kv·
sec(φm)/(2π·N·ωc²)` with `Kv = 2π·Kvco`, so the acquisition ramp time is

```
t_ramp = V_op · C1 / Icp = V_op · Kvco · sec(φm) / (N · ωc²)
```

— **`Icp` cancels**. Raising the charge-pump current does not shorten
cold-start acquisition at all, as long as the loop filter is re-sized to
hold loop bandwidth and phase margin fixed, because `C1` scales with `Icp`
by construction. The same cancellation makes the individual loop-filter
component values non-levers: they are outputs of `(Icp, Kvco, N, f_c, φm)`,
not free parameters. That rules out two of the three directions issue #98
named. What is left:

- **`Kvco` (linear).** The only unconstrained lever, and it improves three
  independent things at once: it shortens the acquisition ramp
  proportionally, it *widens* the capture window (a gentler tuning slope
  puts more `VCTRL` between the 250 MHz point and the 800 MHz cliff), and it
  shrinks the 2.53x loop-gain spread `design/loop-filter/DESIGN.md` is
  currently paying 3.7x capacitor area to absorb. `spec/target-spec.md`
  row 5 already carries an instruction to re-derive a `Kvco` bound, and
  `design/vco/DESIGN.md` already names the sizing levers (longer tail-device
  `L`, source degeneration, or a narrower usable `VCTRL` range).
- **`ωc` (quadratic)** — but row 6 caps it at `f_ref/10`, and
  `design/loop-filter/DESIGN.md`'s worst-corner crossover already sits ~8 %
  under that ceiling. Essentially no headroom.
- **`N` (linear)**, and the divider's own timing closure (#107) as an
  independent way to remove the 800 MHz cliff rather than avoid it.

**Not attempted here, and why.** No sizing change is made in this pass. A
`Kvco` re-size is a real design change, and this issue's own acceptance
criteria require any design change to be substantiated by a fresh full
45-point `sim/pll-lock` re-run — which must in turn run against the
corrected initialization this section lands, not against the defective one
every existing record was produced under. The correct order is: land the
initialization fix (this pass), re-run the grid (#103), then argue a `Kvco`
target against that record. Sizing a VCO against the existing evidence would
be tuning against a measurement artifact.

## No spec edits

Nothing in `spec/target-spec.md` is edited by this issue. All DRAFT rows
(2, 4, 5, 6, 7, 9, 10, 13, 14, 17, 18) referenced by any block's own
`DESIGN.md` stay DRAFT; the discussion above is design-time wiring
rationale, not a ratification. Any change to those rows still requires its
own decision record (`spec/decision-records/DR-NNN`), argued on its own
merits, per `CLAUDE.md`.

## Files

- `top.sch` — top-level schematic (4 hierarchical block instances: `pfd_cp`,
  `loop_filter`, `vco_ring5`, `divider_intN`; no new active/passive devices),
  wired per the topology table above using this repo's established
  net-label convention.
- `top.sym` — block symbol (`VDD`, `GND` inout; `REF`, `RESETB`,
  `NSEL0`..`NSEL5` in; `CLK` out), generated for consistency with the
  per-block convention (`design/README.md`) in case a future higher-level
  schematic (e.g. a closed-loop testbench, #23) needs to instantiate the
  whole PLL hierarchically — not instantiated anywhere in this issue's own
  scope.
- `netlist/top.spice` — connectivity-only netlist snapshot, generated and
  verified per the command in `../README.md`; expands the full four-block
  hierarchy (`pfd_cp` 60 devices, `loop_filter` 5 devices, `vco_ring5` 26
  devices, `divider_intN` 29 standard-cell instances).

## Verification performed for this issue

- `xschem -n -q -x --rcfile sim/xschemrc design/top/top.sch -o
  design/top/netlist` — exits 0, no stdout/stderr output (no netlister
  errors or warnings). The resulting `top.spice` shows the top-level
  `.subckt top VDD GND REF RESETB NSEL0 NSEL1 NSEL2 NSEL3 NSEL4 NSEL5 CLK`
  instantiating all four blocks with the exact connectivity in the topology
  table above:
  ```
  XXPFDCP VDD GND REF FBCLK CP pfd_cp
  XXLF CP GND VCTRL loop_filter
  XXVCO VDD GND VCTRL CLK vco_ring5
  XXDIV VDD GND CLK RESETB NSEL0 NSEL1 NSEL2 NSEL3 NSEL4 NSEL5 FBCLK divider_intN
  ```
  confirming: `pfd_cp.CP` -> `loop_filter.CP`; `loop_filter.VCTRL` ->
  `vco_ring5.VCTRL`; `vco_ring5.CLK` -> both the top-level `CLK` output and
  `divider_intN.CLK` (the feedback tap); `divider_intN.FBCLK` ->
  `pfd_cp.DIV` (closing the loop); and each block's own internal 60/5/26/29
  device expansion is unchanged from its own standalone netlist snapshot.
- The symbol (`top.sym`) was checked the same way the four sibling blocks'
  own `DESIGN.md`s document: instantiating it from a throwaway top-level
  schematic (not committed) and confirming xschem descends into `top.sch`
  and expands the full four-block hierarchy under the instance call
  `X<name> VDD GND REF RESETB NSEL0 NSEL1 NSEL2 NSEL3 NSEL4 NSEL5 CLK top`
  — i.e. the symbol's pin order matches the schematic's pin declaration
  order and hierarchical instantiation nets correctly. (The same
  throwaway-instantiation check reproduces the same nonzero `xschem` exit
  code (`10`) `design/pfd-cp/DESIGN.md`, `design/loop-filter/DESIGN.md`, and
  `design/vco/DESIGN.md` each already document and attribute to a dangling
  top-level `ipin`/`opin` port structure in this checker pattern, common to
  all sibling blocks checked this way, not a defect specific to this new
  symbol.)

## Issue #44: divider standard-cell instance names broke ngspice, fixed

The first time anyone actually pointed ngspice at this netlist (while
building #23's `sim/pll/testbench/tb_pll.sch`), the run failed immediately:
29 `sky130_fd_sc_hd__*` standard-cell instances inside
`design/divider/divider_intN.sch` were named with plain descriptive names
(`CNT0`, `LDMUX0`, `QINV0`, `DECXOR1`, `BORAND2`, `ZDET`, `FBFF`, ...) that
collide with SPICE's implicit element-type-by-first-letter convention (`C`
is a capacitor prefix, `L` an inductor, `Q` a BJT, `D` a diode, `B` a
behavioral source, `Z` a MESFET, `F` a CCCS), instead of the `X` prefix
SPICE requires for a subcircuit call — `mal formed B source instance`,
`warning, can't find model`, and `unknown parameter` errors, all traced to
this issue.

`xschem`'s netlister does not enforce SPICE's device-type-by-prefix rule, so
this defect was invisible to every netlisting-only check this document and
`design/divider/DESIGN.md` previously recorded — this document's own
"Verification performed" section above only ever ran `xschem -n -q -x`, not
ngspice, against `top.spice`, so it could not have caught this.

**Fixed by #44**: all 29 instances in `design/divider/divider_intN.sch`
renamed with an `X` prefix (pure instance-name rename, no connectivity,
pin-order, or device change); `design/divider/netlist/divider_intN.spice`
and this directory's `netlist/top.spice` regenerated from the updated
schematic via the same `xschem -n -q -x` command above (still exits 0). A
diff of the regenerated `top.spice` against its pre-fix version shows only
the instance-name column changing for the 29 renamed lines (identical
nodes, identical `sky130_fd_sc_hd__*` subcircuit calls, identical pin
order) plus the expected `sch_path`/`sym_path` comment lines (these always
reflect the absolute path of whichever machine/worktree last ran the
netlister — not a content change).

**ngspice verification (ad hoc, not a `sim/` evidence record)**: copied
`sim/pll/testbench/tb_pll.sch` (from the in-flight #23 PR) into a scratch
directory, netlisted it against this fixed `design/top/top.sch` with the
same `xschem -n -q -x --rcfile sim/xschemrc` invocation, added the
`sky130_fd_sc_hd` PDK spice deck (`libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice`)
alongside the existing `sky130.lib.spice tt` corner include, and ran
`ngspice -b` with a `.control run .endc` block. The transient (`.tran 50p
200n`) ran to completion (`ngspice` exit 0); grepping the run log for `mal
formed`, `can't find model`, and `unknown parameter` found none. This
confirms the closed-loop netlist is simulatable end to end post-fix — it is
not a lock-time, frequency, or jitter claim, and it does not replace the
`sim/pll/` evidence record #23 is responsible for minting.

## `sim/pll/testbench/tb_pll.sch` was still missing the stdcell include (issue #52)

The ad hoc verification above added the `sky130_fd_sc_hd` PDK spice deck to
its own **scratch copy** of `tb_pll.sch` — that addition never landed in the
committed testbench. `sim/pll/testbench/tb_pll.sch` (the real, committed
manifest #23's own evidence record ran against) kept only the primitive-device
`.lib .../sky130.lib.spice tt` include, which does not define the
`sky130_fd_sc_hd__*` subcircuit bodies `design/divider/divider_intN.sch`
instantiates — so the committed testbench still failed with `Error: unknown
subckt: ... sky130_fd_sc_hd__dfrtp_2` even after #47's X-prefix fix, and
`sim/pll/records/20260819-061455-f61b6d4.md` (0/27 FAIL) is stale evidence of
that gap, not of #47's own defect. Fixed by issue #52: `.include
$::SKYWATER_STDCELLS/sky130_fd_sc_hd.spice` added to `tb_pll.sch`'s own
`MODELS` code block (the same `$::SKYWATER_STDCELLS` xschemrc variable the
PDK's own `libs.tech/xschem/xschemrc` already defines) — see
`sim/pll/records/` for the re-run that supersedes the stale FAIL record.

The re-run (`sim/pll/records/20260819-123508-fe0e6df.md`) shows 17/27 points
PASS. The remaining 10 fail in two ways, both traced in the raw per-point
logs rather than left unexplained: 6 exceed this manifest's 300 s per-point
timeout (the transient makes very slow progress rather than erroring out),
and 4 hit an ngspice numeric-overflow error (`Error: <huge value>, 2 out of
range for ^`) inside the loop filter's `R1` resistor body-diode model
(`b.xxxtop.xxlf.xr1.brbody` in the per-point logs) — i.e. `VCTRL` (or an
adjacent loop-filter node) is being driven to a bias extreme outside that
primitive device model's well-conditioned range. Both failure modes are
consistent with the open `Icp`/loop-filter/`Kvco` coordination gap described
below (the `sim/pll-lock` cold-start lock campaign) rather than with a new
testbench or harness defect: this testbench's 200 ns window captures the loop
in its initial, uncontrolled transient, which is exactly where an
under-damped or badly-conditioned loop would produce large swings and slow
convergence. Reconciling that coordination gap is out of scope for issue #52
(measurement/campaign work only, no block redesign) — see the `sim/pll-lock`
section below for the tracking context.

## `sim/pll-lock` (issue #52): the closed loop does not lock within a few
microseconds of cold start, at the corners run so far

A new sibling testbench, `sim/pll-lock/testbench/tb_pll_lock.sch` +
`sim/harness/measure.py`'s injected `.control`-block analysis, drives this
same closed loop from a cold start (RESETB power-on, `VCTRL` starting
wherever the loop filter's own initial condition lands) for several
microseconds instead of #23's 200 ns plumbing window, and measures whether
`CLK` locks to `N * Fref` = 250 MHz. The first committed record
(`sim/pll-lock/records/20260819-122135-fe0e6df.md`, a 3-point tt/ss/ff
subset at 27 °C/1.80 V — the full PVT grid is deferred to a follow-up issue
given the per-point simulation cost observed in this environment) shows:

- **tt**: `CLK` never oscillates within the 3 µs window at all — consistent
  with `VCTRL` still ramping up from a discharged loop filter capacitor
  toward the VCO's own documented ~0.8 V oscillation threshold
  (`design/vco/DESIGN.md`), not yet having crossed it.
- **ss**: `CLK` does oscillate, but at 941 MHz — far above the 250 MHz
  target — and never settles into the lock tolerance band within the window.
- **ff**: the point exceeded this manifest's per-point simulation timeout
  before finishing.

This is exactly the "Coordination note" gap above made visible in
simulation: `Icp` (charge-pump current) vs. the loop filter's `R`/`C` sizing
vs. the VCO's `Kvco` were each sized in their own block's issue without a
closed-loop time-constant check, and that gap plausibly shows up here as
"lock takes longer than a few microseconds" (or does not happen within this
window at all) rather than as a netlisting or convergence defect. This
observation is evidence for a future decision record / design issue against
spec rows 6 (loop bandwidth) and 8 (lock time) — reconciling the
`Icp`/loop-filter/`Kvco` coordination gap is explicitly **not** done by
issue #52 (its own Non-goals section: measurement/campaign work only, no
block redesign).
