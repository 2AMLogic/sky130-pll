# `sim/lf-c2-jitter-sensitivity/` — period jitter vs. the loop filter's `C2`

How much of the closed-loop PLL's post-lock period jitter is set by one
loop-filter component: `design/loop-filter`'s `C2`, the shunt capacitor at the
charge-pump node whose stated design purpose
(`design/loop-filter/DESIGN.md`, "Filter order" and "Topology") is to attenuate
reference-frequency ripple reaching `VCTRL`.

Same DUT as `sim/pll-lock-mc` (`design/top/top.sch`, `NSEL[5:0]`=`011000`/N=25,
10 MHz reference), same sampling point (`tt`/125 °C/1.80 V, `MC_MM_SWITCH` +
`MC_PR_SWITCH`, seed 1), same reducer, same 20 ps dump grid under
`.options reltol=1e-4`. Run as a **family of arms that differ only in `C2`'s
drawn area**, so the family is a measured sensitivity of one quantity to one
component.

**This is not a design claim about the PLL and not ratified row 9's evidence** —
`sim/pll-lock-mc` holds that, and this unit declares no `spec_rows`. It exists
because T1 item 6's negative control (`sim/pll-lock-mc-negative-control/`, issue
#195) needs a deliberately degraded variant of the DUT sized against two
opposing constraints, and picking that size without measuring it would be a
guess:

- **large enough** that *every* control draw misses row 9's ratified 1.0 % bound
  — one passing draw and `klt yield` cannot report the control `detected`;
- **small enough** that *every* control draw still **locks** — row 9 is a
  post-lock quantity, so a draw that never locks carries no period-jitter figure
  at all and is censored out of the control's own denominator, which costs the
  control a draw just as surely as a passing one does.

## Why `C2` is the knob

`design/loop-filter/DESIGN.md` derives all five passives from
`(Icp, Kvco, N, f_c, φm)`, and says outright that they "are outputs of
`(Icp, Kvco, N, f_c, φm)`, not free parameters" — so *any* single-component
change is a departure from the design, which is exactly what a known-bad variant
is meant to be. `C2` is the one whose departure lands on the measured quantity
and nowhere else:

- **It is the ripple pole.** That document adds `C2` specifically to "attenuate
  reference-frequency ripple reaching `VCTRL`", and `VCTRL` ripple is what
  frequency-modulates the ring — the mechanism row 9's period jitter *is*.
- **It does not degrade rows 6/7.** The `C2` pole `1/(2π·R1·Ceff)` (3.07 MHz at
  the design values, against a worst-case crossover of 733.5 kHz) moves *further
  above* the crossover as `C2` shrinks, so the phase margin rows 6 and 7 are
  stated over does not fall. A degradation that destabilised the loop would be
  testing something else.
- **It does not cost the lock.** `C2` is 10.42 pF of the 221.25 pF
  `C1 + C2 + C3` that document identifies as the cold-start acquisition ramp's
  capacitance, so the ramp `sim/pll-lock-mc`'s 50 µs window pays for is
  essentially unchanged.

The first bullet is why the effect should be large; the other two are why it
should be safe. All three are design-time *reasoning about which knob to turn* —
what the knob actually does to period jitter is what this unit measures.

**Area is divided, not the side.** An arm named `c2div<F>` has `C2`'s **area**
divided by `F`, i.e. `W = L = 72/√F` µm, because the MiM cap's capacitance is
(very nearly) proportional to area.

## The arms

Every arm's schematic is committed and **generated**, not hand-edited:
`testbench/gen_c2_variant.py` derives each one from
`design/loop-filter/loop_filter.sch`, `design/top/top.sch` and
`sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch`, replacing only the header
comment and applying exactly one substitution. `--check` re-derives all of them
and fails on a byte of drift, and
`sim/tests/test_negative_control_variant.py` runs it in `npm run check:ci` — so a
future edit to the design that these variants should have inherited cannot pass
silently, and "differs in exactly one parameter" is a checked property rather
than a claim about a careful copy.

| Arm | `C2` geometry | `C2` value | DUT |
| --- | --- | --- | --- |
| `nominal` | `W=L=72 µm` | 10.47 pF | `design/top/top.sym`, unmodified |
| `c2div4` | `W=L=36 µm` | 2.64 pF | `top_c2div4.sym` |
| `c2div9` | `W=L=24 µm` | 1.19 pF | `top_c2div9.sym` |

Values are the `cap_mim_m3_1` subcircuit's own expression, the one
`design/loop-filter/DESIGN.md` states it uses for its component table (and which
reproduces that table's 10.42 pF for the nominal arm to within the rounding it
prints).

## Results

**`C2` is not a lever on this quantity.** An 8.8× reduction in `C2`'s
capacitance moves the measured post-lock period jitter by **8 %** of itself, and
leaves the output frequency, the duty cycle and the time-to-lock unchanged to
the precision the harness prints.

| Arm | `C2` | Record | Locked | f_out | Duty | Period jitter (RMS) | vs. `nominal` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nominal` | 10.47 pF | [`20260926-084846-e572408`](records/20260926-084846-e572408.md) | 867 ps | 250.2 MHz | 49.2 % | **0.523 %** (5003 cycles) | — |
| `c2div4` | 2.64 pF | [`20260926-084414-e572408`](records/20260926-084414-e572408.md) | 867 ps | 250.2 MHz | 49.2 % | **0.551 %** (5003 cycles) | ×1.054 |
| `c2div9` | 1.19 pF | [`20260926-084935-e572408`](records/20260926-084935-e572408.md) | 867 ps | 250.2 MHz | 49.2 % | **0.566 %** (5003 cycles) | ×1.082 |

1/1 trial PASS in each (the `PASS` is the harness's plumbing-plus-measurement
criterion; `gate_on_bound` is false here, so it is not a statement about row 9's
bound — every arm is in fact under it).

**Two readings, and one of them is the reason this unit exists.**

1. **The method is sound.** The `nominal` arm measures **0.523 %** where
   `sim/pll-lock-mc`'s own cold-start 50 µs draw at the same seed and sampling
   point measures **0.554 %** (record `20260925-224917-3a2dd6e`, trial 1) — 5.6 %
   apart. So the pre-charged 20 µs window reproduces the campaign's own figure
   closely enough to size a degradation against, which is the one thing this
   unit had to establish before its degraded arms meant anything.
2. **The candidate degradation fails, and it fails by a wide margin.** The
   control needs every draw *above* the 1.0 % bound, i.e. roughly **+91 %** on
   the nominal figure. Two arms spanning an 8.8× capacitance reduction bought
   **+8 %**, monotonically but weakly. Nothing in the measured family suggests
   the remaining reduction available — `C2` is a physical capacitor, so the
   factor left before it is gone entirely is finite — delivers the other +83 %.
   **`C2` is therefore rejected as the negative control's knob, by measurement
   rather than by opinion.**

**What that says beyond this issue** (stated because it is a real design finding
and it is not what `design/loop-filter/DESIGN.md` would lead a reader to expect):
this DUT's measured period jitter is **not** set by the loop filter's
reference-ripple rejection. That document's `Vctrl` headroom section owes a
verified transient ripple number and names `C2`/`C3`'s smoothing of the
charge-pump pulse as a mechanism that could bind on row 9; this measurement says
the `C2` half of that path is not what row 9's figure is made of at this
operating point. It does **not** identify what is — that question belongs to
`sim/loop-ripple` and to row 9's own design work, not to a sizing probe — and
nothing here changes a component value in `design/`.

The knob that replaced it is `C1`, measured in the sibling unit
`sim/lf-c1-jitter-sensitivity`.

## The window is not `sim/pll-lock-mc`'s, and that is a stated trade

`sim/pll-lock-mc` runs a 50 µs window because it pays for a **cold start from a
fully discharged loop filter** (`DR-005`) — 24.32–29.72 µs of acquisition ramp in
its own record — before any post-lock population exists, at hours of simulator
time per trial. A sensitivity family cannot afford that per arm.

So this unit **pre-charges** the loop filter's three storage nodes to 0.865 V —
the fixed control voltage
`sim/vco-clk-transition/records/20260925-110645-810cd82.md` states "puts the ring
near the row-9 operating point" — and runs a 20 µs window. The ramp is skipped
and what is left is a long post-lock population.

Two consequences, stated rather than hidden:

1. **An absolute figure here is not interchangeable with a `sim/pll-lock-mc`
   draw's.** A pre-charged start is not the `DR-005` cold start row 9's evidence
   is taken under. That is why this unit runs its own `nominal` arm: the family
   is read as a **ratio measured under one set of conditions**, not as absolute
   numbers borrowed across two.
2. **`gate_on_bound` is false here.** Every degraded arm is expected to exceed
   row 9's bound by construction — that is the finding, not a failure. Same
   setting and the same reasoning as `sim/integrator-floor`, this repo's other
   control unit. (`sim/pll-lock-mc-negative-control`, by contrast, leaves it
   *true*: there "misses the bound" is the result, and having the harness assert
   it per trial is stronger than a reading of a table.)

`measure.ic` is otherwise `sim/pll-lock-mc`'s own, and so is every field that
decides *what* is measured: the node, the grid, the internal-step cap, `reltol`,
the lock criterion, the 20-cycle population floor, the bound, and the sampling
point.

## Reproducing

```sh
# every arm's schematic still derives from the committed design files
python3 sim/lf-c2-jitter-sensitivity/testbench/gen_c2_variant.py --check

# one arm: point the manifest's `schematic` field at it, then run one draw
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("sim/lf-c2-jitter-sensitivity/testbench/tb.json")
m = json.loads(p.read_text()); m["schematic"] = "tb_lf_c2_jitter_c2div4.sch"
p.write_text(json.dumps(m, indent=2) + "\n")
EOF
python3 sim/run_corners.py lf-c2-jitter-sensitivity --mc
```

Arms are run one at a time out of one testbench directory, the same way
`sim/jitter-floor` and `sim/integrator-floor` run their variant families: each
record names the arm it drew and its own `corners/<record-id>/*.spice` pins the
netlist, so the committed value of `schematic` is a convenience for the next run
and never the authority for a past one.
