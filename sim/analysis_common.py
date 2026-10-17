"""Record-parsing and formatting helpers shared by the stdlib-only
`sim/*/analysis/` scripts.

Every script here reads committed evidence (markdown records) and restates it;
they used to carry byte-identical private copies of these helpers, so a fix to
the record-table parser had to be applied once per script. Lives at `sim/`
(not in any one experiment) because the scripts span several experiments, and
stays stdlib-only: the scripts' "stdlib-only" property is about third-party
dependencies, not about sharing one sibling module.

The scripts put this directory on `sys.path` themselves, because they are run
directly and are also loaded by path via importlib (`sim/tests/`), so
script-directory `sys.path[0]` insertion cannot be relied on.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RECORD_ID_RE = re.compile(r"^- \*\*Record ID\*\*: (?P<record_id>\S+)\s*$", re.M)

#: Column index of the `Detail` cell in a per-point PVT result table.
_DETAIL_COLUMN = 6


class AnalysisError(RuntimeError):
    pass


def repo_rel(path: Path) -> str:
    """`path` relative to the repo root when it is inside it, else as-is.

    Every real input lives under the repo; the fall-back keeps the unit tests'
    synthetic temp-directory inputs readable instead of raising.
    """
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def cells(line: str) -> list[str] | None:
    """Split a markdown table row into its cells, or `None` if it is not one."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def record_id(text: str, path: Path) -> str:
    m = RECORD_ID_RE.search(text)
    if m is None:
        raise AnalysisError(f"{path}: record has no `Record ID` field")
    return m.group("record_id")


def single_point_detail(text: str, path: Path, header: list[str]) -> str:
    """The `Detail` cell of a record whose result table (matched by `header`)
    holds exactly one row."""
    rows, seen = [], False
    for line in text.splitlines():
        row = cells(line)
        if row is None:
            continue
        if row == header:
            seen = True
            continue
        if not seen:
            continue
        if set("".join(row)) <= {"-", ":"}:
            continue
        if len(row) != len(header):
            raise AnalysisError(f"{path}: result row has {len(row)} cells: {line!r}")
        rows.append(row)
    if not seen:
        raise AnalysisError(f"{path}: record has no result table with the expected header")
    if len(rows) != 1:
        raise AnalysisError(f"{path}: expected exactly one PVT point, found {len(rows)}")
    return rows[0][_DETAIL_COLUMN]


def pct(frac: float | None) -> str:
    return "-" if frac is None else f"{100.0 * frac:.3f}%"


def ps(seconds: float | None) -> str:
    return "-" if seconds is None else f"{1e12 * seconds:.1f} ps"
