# Top-level integration — design rationale (issue #28)

Top-level closed-loop schematic for the sky130 PLL, the integration step of
the `#14` decomposition. This document records the wiring rationale behind
`top.sch`/`top.sym` — how the four already-standalone blocks (#24 VCO, #25
PFD + charge pump, #26 loop filter, #27 divider) are connected into the
standard integer-N charge-pump PLL closed loop. **No `sim/` evidence exists
for this schematic** (that is #23 plus the PVT campaign gated on the spec
rows each block still targets) — this issue's own scope is connectivity, not
verified closed-loop behavior.

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
