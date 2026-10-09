#!/usr/bin/env python3
"""
Check that each block's embedded definition in the top-level netlist snapshot
agrees with that block's own standalone snapshot.

Scope and non-claims
--------------------
This compares two *generated snapshots* of the same hierarchy. It needs neither
xschem nor a PDK. It does NOT prove that either snapshot matches the authored
``.sch`` schematic; only regenerating with xschem (design/README.md) does that.
It detects the failure where a child block changed and its parent snapshot was
not regenerated.

Parsing
-------
* A standalone snapshot holds its block as a commented ``**.subckt NAME ...`` /
  ``**.ends`` pair; the top snapshot holds embedded children as live
  ``.subckt NAME ...`` / ``.ends`` pairs. Both forms are recognised; the
  top-level ``top`` definition (commented) is not a child and is ignored.
* ``+`` continuation lines are joined; ``*`` comment lines (generated
  ``sch_path``/``sym_path`` lines, pin annotations) and blank lines are ignored.
* Whitespace, and number spelling (``1`` vs ``1.0``), are immaterial. Pin
  order, every device's name, node connections, model/cell name and parameter
  values are compared.

Exit status 0 = consistent, 1 = inconsistent (diagnostics on stderr).
"""

import argparse
import pathlib
import re
import sys

# block name -> standalone snapshot (relative to repo root)
BLOCKS = {
    "pfd_cp": "design/pfd-cp/netlist/pfd_cp.spice",
    "loop_filter": "design/loop-filter/netlist/loop_filter.spice",
    "vco_ring5": "design/vco/netlist/vco_ring5.spice",
    "divider_intN": "design/divider/netlist/divider_intN.spice",
}
TOP_SNAPSHOT = "design/top/netlist/top.spice"

_SUBCKT = re.compile(r"^\*{0,2}\.subckt\s+(\S+)(.*)$", re.IGNORECASE)
_ENDS = re.compile(r"^\*{0,2}\.ends\b", re.IGNORECASE)


def _logical_lines(text):
    """Yield (physical line number, text) with continuations joined.

    Comment lines are kept only when they are the commented subckt/ends
    delimiters; every other comment is dropped.
    """
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("+"):
            if not out or out[-1][1] is None:
                out.append((no, None))  # orphan continuation; reported later
                continue
            out[-1] = (out[-1][0], out[-1][1] + " " + line[1:].strip())
            continue
        if line.startswith("*"):
            if _SUBCKT.match(line) or _ENDS.match(line):
                out.append((no, line))
            continue
        out.append((no, line))
    return out


def _norm_value(tok):
    """Canonicalise a parameter value so 1 and 1.0 compare equal."""
    try:
        return repr(float(tok))
    except ValueError:
        return tok


def _norm_card(line):
    toks = line.split()
    nodes, params = [], {}
    for t in toks[1:]:
        if "=" in t:
            k, _, v = t.partition("=")
            params[k.lower()] = _norm_value(v)
        else:
            nodes.append(t)
    return toks[0], (tuple(nodes), tuple(sorted(params.items())))


def parse_definitions(text):
    """Return ({name: [definition, ...]}, [parse errors]).

    A definition is {"pins": tuple, "devices": {card name: (nodes, params)},
    "line": int}. Duplicate card names within a definition are errors.
    """
    defs, errors = {}, []
    cur = None
    for no, line in _logical_lines(text):
        if line is None:
            errors.append(f"line {no}: continuation line with nothing to continue")
            continue
        m = _SUBCKT.match(line)
        if m:
            if cur is not None:
                errors.append(f"line {no}: .subckt {m.group(1)} opens inside {cur[0]}")
            cur = (m.group(1), {"pins": tuple(m.group(2).split()), "devices": {}, "line": no})
            continue
        if _ENDS.match(line):
            if cur is None:
                errors.append(f"line {no}: .ends with no open .subckt")
            else:
                defs.setdefault(cur[0], []).append(cur[1])
                cur = None
            continue
        if cur is None or line.startswith("."):
            continue
        name, card = _norm_card(line)
        if name in cur[1]["devices"]:
            errors.append(f"line {no}: {cur[0]}: duplicate device {name}")
        cur[1]["devices"][name] = card
    if cur is not None:
        errors.append(f"{cur[0]}: .subckt at line {cur[1]['line']} never closed by .ends")
    return defs, errors


def compare_block(name, standalone, embedded):
    """Diagnostics for one block; each names the block and the device."""
    diags = []
    if standalone["pins"] != embedded["pins"]:
        diags.append(
            f"{name}: pin list differs: standalone {' '.join(standalone['pins'])} "
            f"vs top {' '.join(embedded['pins'])}"
        )
    sd, ed = standalone["devices"], embedded["devices"]
    for dev in sorted(set(sd) - set(ed)):
        diags.append(f"{name}/{dev}: present in standalone snapshot, missing from top")
    for dev in sorted(set(ed) - set(sd)):
        diags.append(f"{name}/{dev}: present in top, missing from standalone snapshot")
    for dev in sorted(set(sd) & set(ed)):
        (sn, sp), (en, ep) = sd[dev], ed[dev]
        if sn != en:
            diags.append(
                f"{name}/{dev}: connections/model differ: standalone {' '.join(sn)} "
                f"vs top {' '.join(en)}"
            )
        if sp != ep:
            sdict, edict = dict(sp), dict(ep)
            for k in sorted(set(sdict) | set(edict)):
                if sdict.get(k) != edict.get(k):
                    diags.append(
                        f"{name}/{dev}: parameter {k}: standalone "
                        f"{sdict.get(k, '<absent>')} vs top {edict.get(k, '<absent>')}"
                    )
    return diags


def check(top_text, standalone_texts):
    """standalone_texts: {block name: text}. Returns list of diagnostics."""
    diags = []
    top_defs, errs = parse_definitions(top_text)
    diags += [f"{TOP_SNAPSHOT}: {e}" for e in errs]
    for name, text in sorted(standalone_texts.items()):
        s_defs, errs = parse_definitions(text)
        diags += [f"{name} standalone snapshot: {e}" for e in errs]
        s_list = s_defs.get(name, [])
        t_list = top_defs.get(name, [])
        if len(s_list) != 1:
            diags.append(
                f"{name}: standalone snapshot has {len(s_list)} definitions of the block, expected 1"
            )
        if len(t_list) == 0:
            diags.append(f"{name}: no embedded definition in top snapshot (regenerate top)")
        elif len(t_list) > 1:
            diags.append(f"{name}: {len(t_list)} duplicate embedded definitions in top snapshot")
        if len(s_list) == 1 and len(t_list) == 1:
            diags += compare_block(name, s_list[0], t_list[0])
    return diags


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-root", type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root = args.repo_root
    try:
        top_text = (root / TOP_SNAPSHOT).read_text()
        standalone = {n: (root / p).read_text() for n, p in BLOCKS.items()}
    except OSError as exc:
        print(f"design-snapshot-consistency: cannot read snapshot: {exc}", file=sys.stderr)
        return 1
    diags = check(top_text, standalone)
    if diags:
        print("design-snapshot-consistency: FAIL (top snapshot disagrees with block snapshots;"
              " regenerate parents per design/README.md)", file=sys.stderr)
        for d in diags:
            print(f"  - {d}", file=sys.stderr)
        return 1
    print(f"design-snapshot-consistency: OK ({len(BLOCKS)} embedded blocks agree with their "
          "standalone snapshots; snapshot-to-snapshot only, not a schematic equivalence proof)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
