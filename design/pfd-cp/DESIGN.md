# PFD + charge pump — design rationale (issue #25)

Tri-state phase-frequency detector and three-state charge pump for the
sky130 PLL, block 2 of 4 of the `#14` decomposition. Standalone block: this
document records the design choices behind `pfd_cp.sch`/`pfd_cp.sym`, not a
verified result. **No `sim/` testbench exists for this block yet** (that is
#23 plus whatever sub-issue runs the sky130 PVT campaign once the rows this
design targets are ratified) — every number below is a design target or an
informal, uncommitted sanity check, never a claim against
`spec/target-spec.md`.

## Forward design, not reverse-engineered

This is a textbook tri-state (three-state) edge-triggered PFD driving a
three-state charge pump — the same basic structure described in standard
PLL design texts (Gardner, *Phaselock Techniques*; Best, *Phase-Locked
Loops*; Razavi's PLL/RF-CMOS texts) and used throughout the published
charge-pump PLL literature. The specific gate-level realization here (an
edge-pulse generator plus a NOR-based SR latch, in place of a full
master-slave D flip-flop — see "PFD implementation" below) and the
single-stage, switch-at-output charge pump topology (see "Charge pump
topology" below) were authored fresh against sky130's own device models and
this repo's own 1.8 V headroom constraint; nothing here originates in
another chip's silicon or netlist, per `CLAUDE.md`'s reverse-engineering-free
rule.

## Scope: standalone block, not the closed loop

This issue authors the PFD + charge pump block only. It is not wired to the
VCO (`design/vco/vco_ring5.sch`, issue #24), the loop filter
(`design/loop-filter/loop_filter.sch`, issue #26), or the divider
(`design/divider/divider_intN.sch`, issue #27) here — that is the
integration sub-issue tracked on `#14`. `CP` (this block's current-injection
output) is documented as "drives the loop filter's `CP` input" as the
intended usage — it uses exactly that net name so
`design/loop-filter/loop_filter.sch`'s own `CP` pin lines up — but no
hierarchical instantiation of any sibling symbol happens in this schematic.
`REF` and `DIV` are exposed as plain inputs (intended sources: an external
reference and, respectively, the divider block's `FBCLK` output), out of
this issue's scope to wire up.

## PFD topology: tri-state edge-triggered, SR-latch implementation

### Why tri-state (not an XOR or a mixer)

Three standard phase-detector families were the candidates:

- **Analog mixer / XOR phase detector** — simplest circuit, but its output
  has a strong ripple component at 2x the input frequency even in lock, and
  it is a *phase*-only detector: two clocks at different frequencies do not
  converge (no frequency-acquisition behavior), so a real PLL needs an
  auxiliary frequency-detect/acquisition-aid loop layered on top.
- **Sequential tri-state PFD** (chosen) — the standard choice for charge-pump
  PLLs specifically because it is simultaneously a phase *and* frequency
  detector: when `REF` and `DIV` are at different frequencies, `UP`/`DN`'s
  average duty cycle pushes the loop toward frequency lock on its own, with
  no separate acquisition circuit. Output is three states (`UP` active,
  `DN` active, or neither — "tri-state"), which is exactly what a
  three-state charge pump consumes directly.
- **Bang-bang / early-late phase detector** — the standard choice for
  clock-data-recovery loops with an already-frequency-locked reference; not
  applicable here (this PLL's `REF`/`DIV` are not already frequency-locked
  going into the detector).

**Chosen: sequential tri-state PFD**, feeding a three-state charge pump —
the textbook default for charge-pump integer-N PLLs, and the only one of the
three that gives frequency acquisition without extra circuitry. There is no
existing sky130 precedent for this topology in this repo to build from or
adapt (design/divider/DESIGN.md's `sky130_fd_sc_hd` standard-cell precedent
does not apply here — no PDK standard cell implements a tri-state PFD).

### PFD implementation: edge-triggered SR latch, not a full D flip-flop

Textbook diagrams (e.g. Razavi) usually draw the tri-state PFD's two
sequential elements as generic "D flip-flops" with `D` tied permanently to
logic 1, clocked by `REF`/`DIV`, and asynchronously reset by
`RST = AND(UP, DN)`. A full static CMOS master-slave D flip-flop (the
general-purpose building block, needed when `D` can take any value) is
unnecessarily complex for this specific case: with `D` hardwired to `VDD`,
the flip-flop's actual required behavior collapses to *"set `Q` on my
clock's rising edge; reset `Q` asynchronously on `RST`"* — an edge-triggered
set / level-triggered async-reset circuit, which is directly and compactly
built as an **edge-pulse generator feeding a NOR-based SR latch**, with no
loss of the tri-state PFD's functional behavior. This repo's `CLAUDE.md`
calls for a small transistor-level sequential circuit here (no
`sky130_fd_sc_hd` precedent applies to a tri-state PFD), and this
simplification meaningfully reduces the transistor count and hand-authoring
risk of doing that at the bare-transistor level, while remaining exactly
equivalent (for `D` = constant 1) to the textbook D-flip-flop description.

Per detector branch (`REF` → `UP`, `DIV` → `DN`, structurally identical,
described once for `REF`/`UP`):

1. **Edge-pulse generator**: a 3-inverter delay chain (`REDLY1`–`REDLY3`,
   odd stage count so the chain's output `REFD` is `REF` inverted *and*
   delayed) feeds a static CMOS `AND2(REF, REFD)` gate (`RUP*`). At the
   instant `REF` rises, `REFD` still reflects `REF`'s *old* (low) value,
   inverted — i.e. still high — for one delay-chain propagation time, so
   `AND(REF, REFD)` is high for exactly that duration: a single narrow
   positive pulse (`SETU`) generated once per `REF` rising edge, and only on
   the rising edge (on a falling edge of `REF`, the `AND`'s first input is
   already low, so no pulse). This is a standard, compact rising-edge
   detector.
2. **SR latch** (cross-coupled NOR2 gates, `UPNORA`/`UPNORB`): `UP` is set
   high by `SETU`'s pulse and held (via the cross-coupled feedback) until
   `RST` (shared with the `DN` latch) drives it back to 0. This is the
   classic 2-NOR2-gate SR latch (`Q = NOR(R, QB)`, `QB = NOR(S, Q)`), built
   directly from bare transistors (`UPNORA_P1/P2/N1/N2`,
   `UPNORB_P1/P2/N1/N2` — 2 series PMOS + 2 parallel NMOS per NOR2 gate, the
   standard static CMOS NOR2 structure).

The `DIV`/`DN` branch (`DIDLY1`–`DIDLY3`, `RDN*` AND2, `DNNORA`/`DNNORB` SR
latch) is the structurally identical mirror, so `UP` and `DN` see matched
delay paths — deliberately, to minimize `REF`-vs-`DIV` path-delay skew
between the two branches (a source of static phase offset / reference spur
if the two branches' propagation delays differ).

### Dead-zone avoidance: a deliberate delay element in the reset path

**The dead zone problem.** Without any reset delay, `RST = AND(UP, DN)`
would fire almost immediately after both `UP` and `DN` go high, which
happens whenever `REF` and `DIV` edges are nearly coincident (near-zero
phase error — exactly the PLL's locked condition). That gives `UP`/`DN`
pulses whose width shrinks toward zero as phase error approaches zero. Real
CMOS switches (the charge pump's `MPSW`/`MNSW`, see below) have a finite
turn-on delay and cannot respond linearly to an arbitrarily narrow pulse; as
the commanded pulse width shrinks below that turn-on delay, the charge
pump's *net* injected charge stops tracking phase error linearly and can
even go to zero over a range of small phase errors around lock — the
classical PFD "dead zone," which shows up as excess jitter / a loss of
loop gain right where linear operation matters most (in lock).

**The fix implemented here.** `RST` is not driven directly by
`AND(UP, DN)` (`RSTPRE`); it is driven by `RSTPRE` run through two
additional inverters (`RSTDLY1`, `RSTDLY2` — an even count, so the delay is
non-inverting) deliberately sized with a **longer channel length** (`L =
1.0 µm`, vs. `L = 0.15 µm` for the rest of the PFD's static logic — see
"Device sizing" below) than the block's ordinary logic gates, to add a
material, controllable propagation delay before `RST` actually asserts.
Because `RSTPRE` only starts propagating through this delay once *both*
`UP` and `DN` are already high, this guarantees `UP` and `DN` are asserted
together for **at least** this delay's duration on every reference cycle —
*even at exactly zero phase error* — forcing the charge pump's switches to
always see a pulse wide enough to be inside their linear turn-on region.
This is the standard, textbook fix for tri-state PFD dead zone (an
intentional minimum reset-pulse-width delay in the `AND(UP,DN)` → reset
path), applied here as two long-`L` inverters rather than, e.g., a fixed
RC delay line — a simpler structure to realize purely from bare transistors
consistent with the rest of this block.

The `AND2(UP, DN) → RSTPRE` gate itself (`RSTG*`) is a plain
minimum-length static NAND2+INV, structurally identical to the edge
detectors' own `AND2` — only the two-inverter delay chain that follows it
is deliberately slowed down.

## Charge pump topology

### Single-stage (non-cascoded) mirror + output switch, not a cascode

Two standard current-source/sink topologies for the charge pump's PMOS
(source) and NMOS (sink) legs were the candidates:

- **Cascode current mirror** (a stacked cascode device between the mirror
  transistor and the output node) — the standard way to raise a current
  source's output impedance, reducing how much the sourced/sunk current
  varies with the charge-pump output node's voltage (`VCTRL`'s swing) —
  which matters because output-impedance-driven current mismatch between
  the `UP` and `DN` legs across `VCTRL`'s range is itself a reference-spur
  contributor (see "Reference-spur note" below).
- **Single-stage mirror with a series output switch** (chosen) — the
  mirror transistor (`MPCP`/`MNCP`) drains/sources directly into a switch
  transistor (`MPSW`/`MNSW`), which connects to the `CP` output node. Only
  one device (the mirror transistor) sits between the rail and the switch;
  the switch itself is the only other device between that and `CP`.

**Chosen: single-stage, not cascoded.** This is the headroom trade-off
`spec/target-spec.md` row 13 (supply sensitivity) and `DR-001` explicitly
flag: gf180-pll's 3.3 V rail can afford to spend an extra stacked `VDSsat`
on a cascode device without running out of usable `VCTRL` swing; this
design's 1.8 V rail (row 0, ratified) cannot afford that as comfortably — a
cascode adds a second series `VDSsat` drop on **both** the sourcing and
sinking leg, directly in the path between the rail and the output node
whose swing (`VCTRL`'s usable tuning range) is already the scarcest
resource under this rail (per `DR-001`'s own framing, "roughly a third" of
gf180-pll's headroom). Razavi's own low-voltage CMOS PLL design guidance
makes exactly this trade explicitly: cascoding may not be affordable in a
low-voltage design, and a simple mirror with the switch placed at the
mirror's output is the standard low-voltage alternative. This design takes
that alternative deliberately, accepting the output-impedance / current-
matching cost documented below as the price of the headroom recovered.

### Headroom analysis (row 13's owed analysis, first pass)

**Devices in the compliance path.** From `VDD` to `CP`: `MPCP` (mirror,
saturation, needs `VDS ≥ VOV`) in series with `MPSW` (switch, needs to stay
in the linear/triode region for low `RDSon`, but also needs enough
`VSD` across it not to starve the current in the region right at the edge
of the `CP` swing). From `GND` to `CP`: `MNCP` in series with `MNSW`,
symmetric. Two devices per leg, not three (a cascode topology would have
made it three) — this is the direct headroom benefit of the topology
choice above.

**Compliance range, qualitatively.** For the PMOS (source) leg to keep
sourcing `Icp` at the design point (see below), `MPCP` needs `VSD ≥ VOV,MPCP`
and `MPSW` needs enough `VSD` to stay out of deep triode / cutoff — so `CP`
can swing up to within roughly `VOV,MPCP + VOV,MPSW` of `VDD` before the
source leg starts to compress. The NMOS (sink) leg is symmetric: `CP` can
swing down to within roughly `VOV,MNCP + VOV,MNSW` of `GND`. Both mirror
devices (`MPCP`, `MNCP`) are sized with a long channel (`L = 1.0 µm`, vs.
the switches' `L = 0.15 µm` — see "Device sizing" below) specifically to
push `VOV` down for a given current (longer `L` at fixed `W/L` needs a
smaller `VOV` to hit the same current in the square-law region), trading
`W`/area for headroom instead of trading a second stacked device for output
impedance (the cascode's trade) — i.e. this design pays for output-
impedance-adjacent behavior (a *somewhat* higher output impedance than a
minimum-length single device would give, from the longer channel's own
`1/λ` improvement) without paying a cascode's full headroom cost.

**Switch overdrive.** `MPSW`/`MNSW` are sized at minimum channel length
(`L = 0.15 µm`, matching the PFD's own fast-logic sizing) specifically for
low `RDSon` and fast turn-on/turn-off — the switch's own job is fast, clean
gating, not current-source behavior, so it does not need `MPCP`/`MNCP`'s
long-`L` current-source treatment. `MPSW`/`MNSW` are also sized at the same
`W` as their respective mirror device (`MPSW` `W = 20 µm` matches `MPCP`;
`MNSW` `W = 10 µm` matches `MNCP`) so the switch is not itself the dominant
series resistance in the compliance path.

**Sub-threshold mirror behavior.** The bias branch (`RBIAS`/`MNBIAS` /
`MPBIAS`/`MNBIAS2`, see "Bias generation" below) runs at a deliberately
small reference current (`IREF`, design point below) relative to the
device sizes chosen, which for sky130's 1.8 V core devices at these `W/L`
ratios is plausibly in or near weak/moderate inversion rather than strong
square-law saturation — this shifts the mirror's actual `VOV` and mirror-
ratio accuracy away from the simple square-law estimate above (weak-
inversion mirrors are less accurate but need *less* `VOV` headroom, which
if anything helps this specific compliance-range argument, at some cost to
`UP`/`DN` current-matching precision — itself a reference-spur contributor,
see below). This is a design-time qualitative note, not a verified
operating-point claim: no DC operating-point simulation exists for this
block (see "No simulation performed" below), consistent with `CLAUDE.md`'s
"no claim without a testbench" rule — the levers to firm this up (bias
current increase, device resizing) are visible from this discussion but not
applied speculatively here.

**Design intent stated plainly.** The single-stage, switch-at-output
topology is the specific choice made *because* of the 1.8 V rail's reduced
headroom (row 13) — it is not the topology this design would choose under
gf180-pll's 3.3 V rail, where the cascode's output-impedance benefit is
more affordable. The accepted cost is a real one (lower output impedance
than a cascode would give, meaning more `UP`/`DN` current mismatch as `CP`
swings across `VCTRL`'s range) and is carried forward explicitly into the
reference-spur discussion below rather than hidden.

## Bias generation

A single resistor-set reference current (`RBIAS`, from `VDD` into a
diode-connected NMOS `MNBIAS`) sets `IREF`. `MNBIAS`'s gate node (`NB`) is
then: (a) the bias fed directly to `MNCP`'s gate (the NMOS sink mirror), and
(b) fed to a second diode-connected NMOS `MNBIAS2`, stacked in series below
a diode-connected PMOS `MPBIAS` (`VDD → MPBIAS → PB → MNBIAS2 → GND`).
Because `MNBIAS2` shares `NB`'s gate bias (and, by construction, `MNBIAS`'s
sizing), it draws the same `IREF` that `MNBIAS` does, which forces
`MPBIAS`'s own gate/drain node (`PB`) to settle at exactly the gate voltage
needed to source that same `IREF` — i.e. `PB` becomes a correctly-biased
PMOS mirror gate, translated from the NMOS-side reference with no separate
PMOS-side reference generator needed. This is the standard "diode-stack"
NMOS-to-PMOS bias translation technique — a well-known building block in
bias generation, not specific to any existing chip's design. `MPCP`
(gate = `PB`) and `MNCP` (gate = `NB`) then each mirror `IREF`, scaled by
their `W/L` ratio against the bias devices, to the design-point `Icp`.

## Design-point inputs and sizing

Every input below is a **first-pass design-point assumption**; none is a
ratified spec value, and none was computed from a device-model simulation
(no DC operating-point check exists for this block — see "No simulation
performed").

| Input | Design-point value | Basis |
|---|---|---|
| `Icp` (charge-pump current) | 10 µA | First-pass design point: large enough that the mirror/switch devices above are comfortably away from extreme weak-inversion operation, small enough to keep `RBIAS`'s area and the bias branch's static power modest. This is this block's own answer to the value `design/loop-filter/DESIGN.md` flagged as not yet landed at its own authoring time (it used a 5 µA placeholder) — reconciling the two is integration-sub-issue (`#14`) work, not done here (see "Coordination note" below). |
| `IREF` (bias-branch reference current) | ≈ 2 µA | `Icp / 5` — a 5x mirror ratio between the bias devices and the output mirror devices (see "Device sizing" table), a standard way to keep the bias branch's own static power a fraction of the charge pump's. |
| `RBIAS` | 600 kΩ (`W=1 µm, L=300 µm`, `sky130_fd_pr__res_xhigh_po`) | From `res_xhigh_po`'s own sheet-resistance model (`R = 2000·L/W/mult` Ω, the same formula `design/loop-filter/DESIGN.md` used, read directly off the primitive's `.sym` file), targeting `IREF ≈ (VDD − Vgs,MNBIAS)/RBIAS ≈ (1.8 V − 0.6 V)/600 kΩ ≈ 2 µA` at a roughly estimated `Vgs,MNBIAS ≈ 0.6 V` (an approximate hand estimate, not a simulated operating point). |

## Device sizing

| Role | Devices | W (µm) | L (µm) | Why |
|---|---|---|---|---|
| PFD fast logic (edge-detector `AND2`s, SR latch `NOR2`s, `RST` `AND2`) | all `*NAND*`/`*NOR*`/`*INV*` pairs not listed below | PMOS 2 / NMOS 1 | 0.15 (min) | Minimum channel length for fast switching (this logic's own speed is not a bottleneck for PLL loop dynamics, but a slow PFD adds unnecessary phase-detection latency); 2:1 PMOS:NMOS width ratio for sky130's electron/hole mobility mismatch, the same convention `design/vco/DESIGN.md` and `design/divider/DESIGN.md`'s own custom gates use. |
| Edge-detector delay chains (`REDLY1-3`, `DIDLY1-3`) | inverter pairs | PMOS 2 / NMOS 1 | 0.3 | Deliberately longer than the min-length logic devices, to give the edge-detector's `SETU`/`SETD` pulses a controlled, non-degenerate width (a pulse this narrow at min-`L` risks not fully propagating through the downstream SR latch's own switching threshold) — a design choice, not a simulated/verified pulse width (see "No simulation performed"). |
| `RST` dead-zone delay (`RSTDLY1`, `RSTDLY2`) | inverter pair | PMOS 2 / NMOS 1 | 1.0 | The dead-zone-avoidance delay element itself (see "Dead-zone avoidance" above) — deliberately the longest channel length in the PFD, to maximize the minimum guaranteed `UP`/`DN` pulse width for a given device count, at the cost of proportionally more area per stage. |
| Bias branch (`MNBIAS`, `MNBIAS2`) | NMOS | 2 | 1.0 | Long channel for low mismatch in a low-current bias generator (mismatch here directly sets `UP`/`DN` current-matching accuracy downstream). |
| Bias branch (`MPBIAS`) | PMOS | 4 | 1.0 | 2:1 W ratio vs. `MNBIAS`/`MNBIAS2`, same mobility-compensation convention as the logic gates. |
| Charge-pump mirrors (`MPCP`, `MNCP`) | PMOS 20 / NMOS 10 | 1.0 | 5x the bias devices' `W` at the same `L` — sets the 5x `Icp`/`IREF` mirror ratio (see "Design-point inputs"); long `L` for the headroom/output-impedance reasons in "Headroom analysis" above. |
| Charge-pump switches (`MPSW`, `MNSW`) | PMOS 20 / NMOS 10 | 0.15 (min) | Matched `W` to their respective mirror device (so the switch is not the dominant series resistance in the compliance path), min `L` for fast, low-`RDSon` switching (see "Switch overdrive" above). |
| `UP` → `UPB` polarity inverter (`UPINV`) | PMOS 2 / NMOS 1 | 0.15 (min) | Ordinary fast logic — translates `UP` (active-high, PFD convention) to `UPB` (active-low, needed at `MPSW`'s gate since a PMOS switch turns on with its gate pulled low). |

All PMOS bodies tie to `VDD`, all NMOS bodies tie to `GND` — the same
non-isolated-body convention `design/vco/DESIGN.md` and
`design/divider/DESIGN.md` both use, no body-effect tuning in this v1.

## Current trim: explicitly not implemented in this pass

`spec/target-spec.md` rows 6 (loop bandwidth) and 7 (phase margin) note a
DRAFT ceiling (`f_c < f_ref/10`) that must hold across row 3's reference-
frequency range, adapted (per the issue text) via a charge-pump current
trim — gf180-pll's own Icp trim-code convention, not yet re-derived for
sky130. **This block does not implement a trim mechanism.** `Icp` here is
fixed by `RBIAS`'s value and the mirror ratios in "Device sizing" — there
is no digital trim-code input, no switched-resistor or switched-mirror-leg
array on the bias branch.

**Why deferred, not built speculatively:** a trim mechanism (most simply, a
digital-code-selected parallel resistor/mirror-leg array on the bias
branch) is a real design addition — it needs a trim-code convention, a
digital control interface, and a re-derivation of what `f_c`-vs-`f_ref`
adaptation curve the trim actually needs to hit, none of which is settled
yet (row 6/7 stay DRAFT, and gf180-pll's own trim-code rule is explicitly
flagged as "not yet re-derived for sky130," not portable as-is). Building a
trim array against an underived target risks getting the wrong knob shape
and having to redo it once row 6/7's real range is known. This follows the
same v1-scope-conservatism pattern `design/vco/DESIGN.md` (no auto-
calibration) and `design/divider/DESIGN.md` (static configuration, no
auto-cal FSM) both already established for this project: build the fixed-
value version first, add the trim once a future PVT/loop-bandwidth campaign
defines the range it needs to cover. `RBIAS`'s value (and the mirror ratios
downstream of it) is exactly where that future trim would attach.

## Reference-spur note (row 10, qualitative — no numeric claim)

`spec/target-spec.md` row 10 (reference spur) is DRAFT, with a candidate
≤ −55 dBc figure explicitly flagged (spec text, and this issue's own scope
language) as **not** to be ported from gf180-pll as a target claim — any
real number needs its own re-derivation from this block's own mismatch and
leakage behavior once a testbench exists. This section is a qualitative
inventory of *this* charge pump's own spur contributors, not a re-derived
number:

- **`UP`/`DN` current mismatch across `VCTRL`'s swing.** The single-stage
  (non-cascoded) mirror topology chosen for headroom (see "Charge pump
  topology" above) has lower output impedance than a cascode would, so
  `MPCP`'s and `MNCP`'s currents vary more with `CP`'s instantaneous voltage
  than a cascoded design's would — any residual `UP`-vs-`DN` current
  mismatch shows up as a net charge injected into the loop filter once per
  reference cycle, at `f_ref` and its harmonics.
- **`REF`-vs-`DIV` path-delay skew.** The two edge-detector branches
  (`REDLY*`/`RUP*` vs. `DIDLY*`/`RDN*`) are built structurally identical
  specifically to minimize this (see "PFD implementation" above), but
  device-level mismatch (not simulated here) between the two nominally-
  identical branches would show up as a small, fixed `UP`-vs-`DN` timing
  offset — itself a static phase-offset / spur contributor.
- **Switch charge injection / clock feedthrough.** `MPSW`/`MNSW` are clocked
  digital switches; their gate-to-drain/source overlap capacitance couples
  a small charge kick onto `CP` on every `UP`/`DN` transition, once per
  reference cycle regardless of loop phase error — a standard charge-pump
  spur mechanism, not specific to this topology.
- **Bias-branch / off-state leakage mismatch.** In lock, `MPSW` and `MNSW`
  are both nominally off between correction pulses; sky130 1.8 V core
  device off-state leakage is small but not simulated here, and any
  `PMOS`-vs-`NMOS` leakage asymmetry contributes a slow, small net charge
  drift between correction pulses.

None of the above is quantified — that is exactly the kind of claim
`CLAUDE.md` rules out without a testbench ("no claim without a testbench").
The future PVT/transient testbench campaign (gated on #23's infrastructure)
owns the actual measured number against row 10, once it exists.

## Coordination note: this block's `Icp` vs. the loop filter's placeholder

`design/loop-filter/DESIGN.md` (issue #26) was authored while this issue
(#25) was still `loom:building`, with no `design/pfd-cp/` on `main` yet — it
used a documented 5 µA `Icp` placeholder specifically so its R/C sizing
equations could be recomputed once a real value landed. This issue now
lands `Icp = 10 µA` (see "Design-point inputs" above), independently
justified against this block's own bias-branch/mirror sizing, not chosen to
match the loop filter's placeholder. Reconciling the two (recomputing
`design/loop-filter/loop_filter.sch`'s `R1`/`C1`/`C2`/`R3`/`C3` against this
block's `Icp = 10 µA`) is explicitly **not** done by this issue — per this
issue's own scope text, that reconciliation belongs to the integration
sub-issue tracked on `#14`, which is also where the two blocks' actual
`CP`-node wiring happens.

## No spec edits

Nothing in `spec/target-spec.md` is edited by this issue. Rows 6 (loop
bandwidth), 7 (phase margin), 10 (reference spur), and 13 (supply
sensitivity) all stay DRAFT; the discussion above is design-time rationale
and a first-pass headroom analysis toward a future decision, not a
ratification. Any change to those rows still requires its own decision
record (`spec/decision-records/DR-NNN`), argued on its own merits, per
`CLAUDE.md`.

## Files

- `pfd_cp.sch` — top schematic (60 devices: 29 PMOS + 30 NMOS transistors
  — asymmetric by one device because the NMOS-to-PMOS bias-translation
  branch uses two diode-connected NMOS devices against one diode-connected
  PMOS device, see "Bias generation" — plus 1 resistor; the PFD's two
  structurally-identical edge-detector + SR-latch branches, shared
  reset-generation + dead-zone-delay logic, and the charge pump's bias
  branch + output mirror/switch legs, all at the bare sky130 core-device
  transistor level; no `sky130_fd_sc_hd` standard cells).
- `pfd_cp.sym` — block symbol (`VDD`, `GND` inout; `REF`, `DIV` in; `CP`
  out), for the future integration schematic to instantiate.
- `netlist/pfd_cp.spice` — connectivity-only netlist snapshot, generated
  and verified per the command in `../README.md`.

## No simulation performed

**No `sim/` evidence exists for this block; no DC operating-point,
transient, or AC check was run.** Every current, voltage, and delay number
above (`Icp`, `IREF`, `RBIAS`, the edge-detector/dead-zone delay magnitudes,
the headroom/compliance-range discussion) is a hand-derived design-time
estimate or a stated design intent, not a simulated or measured result —
consistent with `CLAUDE.md`'s "no claim without a testbench" rule and this
issue's own explicit test-plan scope (schematic-authoring only; simulation
is out of scope, deferred to #23 and whatever sub-issue runs the sky130 PVT
campaign). The one check performed for this issue is netlist-generation
correctness (below), not functional or timing verification.

## Verification performed for this issue

- `xschem -n -q -x --rcfile sim/xschemrc design/pfd-cp/pfd_cp.sch -o
  design/pfd-cp/netlist` — exits 0, no stdout/stderr output (no netlister
  errors or warnings). The resulting netlist has 60 device instances (29
  PMOS + 30 NMOS `X...sky130_fd_pr__{p,n}fet_01v8` lines, plus 1
  `X...sky130_fd_pr__res_xhigh_po` line) inside the top-level
  `.subckt pfd_cp VDD GND REF DIV CP` / `.ends` wrapper.
- A scratch connectivity check (not committed, informal — same status as
  `design/vco/DESIGN.md`'s own informal sanity checks) parsed every
  generated `X` device line and confirmed every internal net name appears
  on at least two device terminals (i.e. no accidentally-dangling,
  single-use net from a labeling typo) — 35 distinct internal/external nets
  total, none single-use. Spot-checked device-by-device against the
  intended topology above (e.g. `XMPCP SP PB VDD VDD`, `XMPSW CP UPB SP
  VDD`, `XMNSW CP DN SN GND`, `XUPNORA_P2 UP UPN UPNORA_MID VDD` — all
  match the drain/gate/source/body wiring described in "PFD implementation"
  and "Charge pump topology" above).
- The symbol (`pfd_cp.sym`) was checked by instantiating it from a
  throwaway top-level schematic (not committed) and confirming xschem
  descends into `pfd_cp.sch` and expands the full 60-device (59 transistors
  plus the bias resistor) subcircuit under the instance call `X<name> VDD
  GND REF DIV CP pfd_cp` — i.e. the symbol's pin order matches the schematic's pin
  declaration order and hierarchical instantiation nets correctly, ready
  for the future integration sub-issue. (The same throwaway-instantiation
  check reproduces the same nonzero `xschem` exit code
  `design/loop-filter/DESIGN.md`'s own equivalent check documents and
  attributes to a dangling top-level `ipin`/`opin` port structure in this
  checker pattern, common to all three sibling blocks checked this way, not
  a defect specific to this new symbol.)
