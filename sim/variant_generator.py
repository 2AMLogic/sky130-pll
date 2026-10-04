"""Mechanics shared by the `gen_c<N>_variant.py` loop-filter variant generators.

Only the campaign-independent parts live here: extracting a schematic's body,
the MIM-cap geometry arithmetic, reading a capacitor's nominal drawn side, and
the write-or-check loop over generated schematics and symbol copies. Each
generator keeps its own variant derivation, headers, factors and CLI.
"""

from __future__ import annotations

import difflib
import shutil
import sys
from pathlib import Path
from typing import Callable

_HEADER_MARKER = "}\nG {}\n"


class GenError(RuntimeError):
    pass


def body(path: Path) -> str:
    """Everything from the `v { ... }` block's closing brace on -- the
    schematic's own content, with only the header comment's text dropped.

    The closing brace belongs to the body rather than to the replacement header,
    so a header written by a generator cannot leave the `v {}` block unclosed.
    """
    text = path.read_text()
    _head, marker, rest = text.partition(_HEADER_MARKER)
    if not marker:
        raise GenError(f"{path}: no `v {{...}}` header block found")
    return _HEADER_MARKER + rest


def nominal_side(loop_filter: str, line: str, name: str) -> float:
    """Capacitor `name`'s drawn side length, read out of the committed schematic.

    `line` is the instance line that opens the capacitor's block.
    """
    index = loop_filter.find(line)
    if index < 0:
        raise GenError(
            f"design/loop-filter/loop_filter.sch no longer carries the {name} instance "
            "line this generator substitutes into -- re-derive the substitution "
            "against the current schematic rather than editing the committed "
            "variants by hand"
        )
    block = loop_filter[index : index + 200]
    w = l = None
    for text in block.splitlines()[1:]:
        if text.startswith("W="):
            w = float(text[2:])
        elif text.startswith("L="):
            l = float(text[2:])
        elif text.startswith("spiceprefix="):
            break
    if w is None or l is None or w != l:
        raise GenError(f"unexpected {name} geometry in loop_filter.sch: W={w} L={l}")
    return w


def side_for(repo: Path, nominal_side_of: Callable[[str], float], factor: int) -> str:
    """A variant's drawn side, i.e. the nominal side / sqrt(factor)."""
    nominal = nominal_side_of((repo / "design/loop-filter/loop_filter.sch").read_text())
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


def run(
    factors: tuple[int, ...],
    *,
    write: bool,
    here: Path,
    repo: Path,
    variant_files: Callable[[int], dict[str, str]],
    symbol_copies: Callable[[int], dict[str, Path]],
) -> int:
    """Write (or re-derive and diff) every factor's schematics, then symbol copies."""
    drift = 0
    for factor in factors:
        for name, content in variant_files(factor).items():
            dst = here / name
            if write:
                dst.write_text(content)
                print(f"wrote {dst.relative_to(repo)}")
                continue
            have = dst.read_text() if dst.exists() else ""
            if have != content:
                drift += 1
                print(f"DRIFT: {dst.relative_to(repo)}", file=sys.stderr)
                sys.stderr.writelines(
                    difflib.unified_diff(
                        have.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile="committed",
                        tofile="re-derived",
                    )
                )
        for name, src in symbol_copies(factor).items():
            dst = here / name
            if write:
                shutil.copy(src, dst)
                print(f"wrote {dst.relative_to(repo)}")
            elif not dst.exists() or dst.read_bytes() != src.read_bytes():
                drift += 1
                print(
                    f"DRIFT: {dst.relative_to(repo)} is not a copy of "
                    f"{src.relative_to(repo)}",
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
