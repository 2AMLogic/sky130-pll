#!/usr/bin/env python3
"""Derive a C1-degraded copy of `design/loop-filter` + `design/top` from the
committed design files, for this unit's variant family (issue #195).

Why a generator rather than five hand-edited schematics
------------------------------------------------------

Every file this script writes is a **verbatim copy** of a committed design
file's own body, under a replaced header comment, with exactly one
substitution applied:

* `loop_filter_c1div<F>.sch` — `design/loop-filter/loop_filter.sch` with `C1`'s
  drawn geometry changed from `W=L=322` to `W=L=322/sqrt(F)` (its **area**
  divided by `F`). `R1`, `C2`, `R3` and `C3` are untouched, and no other
  property of `C1` (model, `MF`, `spiceprefix`, placement, net attachment)
  changes.
* `top_c1div<F>.sch` — `design/top/top.sch` with its one `XLF` instance
  re-pointed at the variant symbol above. No other instance, net or property
  changes.
* `tb_lf_c1_jitter_c1div<F>.sch` — `sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch`
  with its one `XXTOP` instance re-pointed at the variant top above. Same
  supply/reference/reset stimulus, same `NSEL[5:0]`=`011000` (N=25) strapping,
  same 10 MHz reference.

A generator makes "the variant differs from the design in exactly one stated
parameter" a **checkable** property rather than a claim about a careful edit:
`--check` re-derives every committed variant file and fails on any byte of
drift, so a future change to `design/loop-filter/loop_filter.sch` or
`design/top/top.sch` that the variants should have inherited cannot pass
silently. `sim/jitter-calibration/testbench/gen_pwl_clock.py` is this repo's
precedent for a generator living inside a `testbench/` directory.

This unit has **no nominal arm of its own**: its comparison point is
`sim/lf-c2-jitter-sensitivity`'s nominal-arm record, run from a byte-identical
`measure` block at the same seed and sampling point against the unmodified
design. `sim/tests/test_negative_control_variant.py` asserts the two manifests'
`measure` blocks are identical, so that citation cannot quietly stop being
valid, and the ~2 h of simulator time a second identical nominal run would cost
buys nothing.

Usage
-----

    python3 sim/lf-c1-jitter-sensitivity/testbench/gen_c1_variant.py --check
    python3 sim/lf-c1-jitter-sensitivity/testbench/gen_c1_variant.py --write 9
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

#: `design/loop-filter/loop_filter.sch`'s own C1 drawn geometry, in um. Read
#: from the file rather than trusted: see `_c1_nominal_side`.
_C1_LINE = "C {sky130_fd_pr/cap_mim_m3_1.sym} -400 100 0 0 {name=C1\n"

#: The area divisors this unit's committed variant family carries. Adding one
#: means running it: a committed variant with no record is a netlist, not
#: evidence.
FACTORS = (9, 12, 16, 25)

_HEADER_MARKER = "}\nG {}\n"


class GenError(RuntimeError):
    pass


def _body(path: Path) -> str:
    """Everything from the `v { ... }` block's closing brace on -- the
    schematic's own content, with only the header comment's text dropped.

    The closing brace belongs to the body rather than to the replacement header,
    so a header written by this generator cannot leave the `v {}` block unclosed.
    """
    text = path.read_text()
    _head, marker, rest = text.partition(_HEADER_MARKER)
    if not marker:
        raise GenError(f"{path}: no `v {{...}}` header block found")
    return _HEADER_MARKER + rest


def _c1_nominal_side(loop_filter: str) -> float:
    """`C1`'s drawn side length, read out of the committed schematic."""
    index = loop_filter.find(_C1_LINE)
    if index < 0:
        raise GenError(
            "design/loop-filter/loop_filter.sch no longer carries the C1 instance "
            "line this generator substitutes into -- re-derive the substitution "
            "against the current schematic rather than editing the committed "
            "variants by hand"
        )
    block = loop_filter[index : index + 200]
    w = l = None
    for line in block.splitlines()[1:]:
        if line.startswith("W="):
            w = float(line[2:])
        elif line.startswith("L="):
            l = float(line[2:])
        elif line.startswith("spiceprefix="):
            break
    if w is None or l is None or w != l:
        raise GenError(f"unexpected C1 geometry in loop_filter.sch: W={w} L={l}")
    return w


def side_for(factor: int) -> str:
    """The variant's C1 drawn side, i.e. the nominal side / sqrt(factor)."""
    nominal = _c1_nominal_side((REPO / "design/loop-filter/loop_filter.sch").read_text())
    return f"{nominal / factor ** 0.5:.6g}"


def mim_cap_ff(side_um: float) -> float:
    """`sky130_fd_pr__cap_mim_m3_1`'s own capacitance expression, in fF.

    `C = camimc*wc*lc + 2*cpmimc*(wc+lc)*2` with `wc = W + m3_dw`,
    `m3_dw = -0.025 um`, typical `camimc = 2 fF/um^2`, `cpmimc = 0.19 fF/um` --
    the same expression `design/loop-filter/DESIGN.md` states it uses for its
    own component-value table (and which reproduces that table's 10.42 pF for
    the nominal W=L=322 um).
    """
    wc = side_um - 0.025
    return 2.0 * wc * wc + 2.0 * 0.19 * (wc + wc) * 2.0


def _variant_files(factor: int) -> dict[str, str]:
    side = side_for(factor)
    lf_name = f"loop_filter_c1div{factor}"
    top_name = f"top_c1div{factor}"
    tb_name = f"tb_lf_c1_jitter_c1div{factor}"

    lf_src = (REPO / "design/loop-filter/loop_filter.sch").read_text()
    lf_body = _body(REPO / "design/loop-filter/loop_filter.sch")
    old = _C1_LINE + "model=cap_mim_m3_1\nW=322\nL=322\n"
    new = _C1_LINE + f"model=cap_mim_m3_1\nW={side}\nL={side}\n"
    if old not in lf_body:
        raise GenError(
            "design/loop-filter/loop_filter.sch's C1 block is not the one this "
            f"generator substitutes into (expected {old!r})"
        )
    lf_body = lf_body.replace(old, new, 1)
    del lf_src

    lf_header = f"""v {{xschem version=3.4.7 file_version=1.2
* {lf_name}.sch -- a DELIBERATELY DEGRADED copy of the sky130 PLL loop filter.
* NOT part of the design: nothing under design/ instantiates it, and no spec
* row is claimed for it.
*
* Generated by sim/lf-c1-jitter-sensitivity/testbench/gen_c1_variant.py from
* design/loop-filter/loop_filter.sch. The body below is that file's own,
* verbatim, with exactly one substitution: C1's drawn geometry W=L=322 um ->
* W=L={side} um, i.e. C1's AREA divided by {factor}. R1, C2, R3 and C3 are
* untouched, and no other property of C1 changes.
*
* Why C1, and why an area divisor: C1 is the series capacitor of the R1/C1
* branch that forms the loop's compensation zero, and per
* design/loop-filter/DESIGN.md's own sizing derivation it is the single
* component that sets BOTH quantities the loop's dynamics are stated over --
* `C1 = Icp*Kv*sec(phi_m)/(2*pi*N*wc^2)` fixes the crossover, `R1*C1 =
* tan(phi_m)/wc` places the zero. Shrinking C1 therefore raises the crossover
* and drags the zero up with it, collapsing the phase margin rows 6/7 are
* stated over and leaving a badly under-damped loop whose residual phase error
* rings. That is a deliberate degradation of the loop's dynamics rather than of
* one filtering path.
*
* Why not C2 (the reference-ripple pole, the intuitive candidate):
* sim/lf-c2-jitter-sensitivity MEASURED it, and it is not a lever on this
* quantity -- see that unit's README. This arm exists because that one came
* back negative.
*
* The risk this arm carries, stated because it is the one that decides whether
* the arm is usable as a negative control at all: C1 is 94 % of the C1+C2+C3
* the cold-start acquisition ramp charges, and a loop with little phase margin
* may not reach lock inside the campaign's window. A draw that does not lock
* carries no period-jitter figure, so an arm degraded past lock is useless as a
* control however badly it behaves. Which side of that line each factor falls
* on is measured, not predicted.
*
* Verification: `--check` mode of the generator re-derives this file from the
* committed design schematic and fails on any drift, so this copy cannot fall
* out of step with the design it degrades.
"""
    tb_src = _body(REPO / "sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch")
    top_body = _body(REPO / "design/top/top.sch")
    old_lf = "C {design/loop-filter/loop_filter.sym} 900 0 0 0 {name=XLF}"
    new_lf = (
        f"C {{sim/lf-c1-jitter-sensitivity/testbench/{lf_name}.sym}} "
        "900 0 0 0 {name=XLF}"
    )
    if old_lf not in top_body:
        raise GenError("design/top/top.sch's XLF instance line is not the expected one")
    top_body = top_body.replace(old_lf, new_lf, 1)

    top_header = f"""v {{xschem version=3.4.7 file_version=1.2
* {top_name}.sch -- design/top/top.sch with its loop filter replaced by the
* DELIBERATELY DEGRADED {lf_name}.sym (C1 area / {factor}). NOT part of the
* design.
*
* Generated by sim/lf-c1-jitter-sensitivity/testbench/gen_c1_variant.py from
* design/top/top.sch. The body below is that file's own, verbatim, with
* exactly one substitution: the XLF instance's symbol. Every other instance,
* net, label and property -- the VCO, the PFD/charge pump, the divider, and
* all of the top-level wiring -- is unchanged, so this variant differs from the
* real closed-loop PLL in one loop-filter capacitor's area and in nothing else.
"""
    old_top = "C {design/top/top.sym} 0 0 0 0 {name=XXTOP}"
    new_top = (
        f"C {{sim/lf-c1-jitter-sensitivity/testbench/{top_name}.sym}} "
        "0 0 0 0 {name=XXTOP}"
    )
    if old_top not in tb_src:
        raise GenError(
            "sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch's XXTOP instance line is "
            "not the expected one"
        )
    tb_body = tb_src.replace(old_top, new_top, 1)

    tb_header = f"""v {{xschem version=3.4.7 file_version=1.2
* {tb_name}.sch -- this unit's C1-area/{factor} arm.
*
* Generated by sim/lf-c1-jitter-sensitivity/testbench/gen_c1_variant.py from
* sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch. The body below is that file's
* own, verbatim, with exactly one substitution: the XXTOP instance's symbol
* ({top_name}.sym instead of design/top/top.sym). Supply, 10 MHz reference,
* power-on reset stimulus and the NSEL[5:0]=011000 (N=25) strapping are
* therefore bit-identical to the Monte Carlo campaign's own testbench, and
* like it this schematic carries no `.tran` card of its own -- the window comes
* from this unit's tb.json via sim/harness/measure.py.
"""
    return {
        f"{lf_name}.sch": lf_header + lf_body,
        f"{top_name}.sch": top_header + top_body,
        f"{tb_name}.sch": tb_header + tb_body,
    }


def _symbol_copies(factor: int) -> dict[str, Path]:
    return {
        f"loop_filter_c1div{factor}.sym": REPO / "design/loop-filter/loop_filter.sym",
        f"top_c1div{factor}.sym": REPO / "design/top/top.sym",
    }


def run(factors: tuple[int, ...], *, write: bool) -> int:
    drift = 0
    for factor in factors:
        for name, content in _variant_files(factor).items():
            dst = HERE / name
            if write:
                dst.write_text(content)
                print(f"wrote {dst.relative_to(REPO)}")
                continue
            have = dst.read_text() if dst.exists() else ""
            if have != content:
                drift += 1
                print(f"DRIFT: {dst.relative_to(REPO)}", file=sys.stderr)
                sys.stderr.writelines(
                    difflib.unified_diff(
                        have.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile="committed",
                        tofile="re-derived",
                    )
                )
        for name, src in _symbol_copies(factor).items():
            dst = HERE / name
            if write:
                shutil.copy(src, dst)
                print(f"wrote {dst.relative_to(REPO)}")
            elif not dst.exists() or dst.read_bytes() != src.read_bytes():
                drift += 1
                print(
                    f"DRIFT: {dst.relative_to(REPO)} is not a copy of "
                    f"{src.relative_to(REPO)}",
                    file=sys.stderr,
                )
    if drift:
        print(
            f"{drift} generated variant file(s) differ from what this generator "
            "derives from the committed design schematics",
            file=sys.stderr,
        )
        return 1
    if not write:
        print(f"OK: {len(factors)} variant arm(s) match the committed design files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="(re-)write the variant files")
    mode.add_argument(
        "--check",
        action="store_true",
        help="re-derive and diff against the committed files (default)",
    )
    parser.add_argument(
        "factors",
        nargs="*",
        type=int,
        default=None,
        help=f"C1 area divisors (default: this unit's committed family, {list(FACTORS)})",
    )
    args = parser.parse_args(argv)
    factors = tuple(args.factors) if args.factors else FACTORS
    try:
        return run(factors, write=args.write)
    except (GenError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
