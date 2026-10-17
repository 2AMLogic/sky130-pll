"""Record-parsing and formatting helpers shared by the stdlib-only
`sim/*/analysis/` scripts.

Every script here reads committed evidence (markdown records and the per-point
netlists beside them) and restates it; they used to carry byte-identical
private copies of these helpers, so a fix to the record-table or SPICE-literal
parser had to be applied once per script. Lives at `sim/`
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


# --- per-point netlist reading -------------------------------------------------

_SUFFIXES = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
_LITERAL_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)$")

#: The period-jitter figure a floor/calibration record's `Detail` cell reports.
JITTER_IN_DETAIL_RE = re.compile(
    r"period jitter (?P<pct>[\d.]+)% RMS over (?P<cycles>\d+) cycles"
)
PULSE_RE = re.compile(
    r"^VCLK\s+\S+\s+\S+\s+pulse\(\s*(?P<v1>\S+)\s+(?P<v2>\S+)\s+(?P<td>\S+)\s+"
    r"(?P<tr>\S+)\s+(?P<tf>\S+)\s+(?P<pw>\S+)\s+(?P<per>[^)\s]+)\s*\)",
    re.M | re.I,
)
#: Tolerates a trailing `uic`, which the `sim/vco-clk-transition` netlist carries.
TRAN_RE = re.compile(r"^tran\s+(?P<step>\S+)\s+(?P<stop>\S+)(?:\s+uic)?\s*$", re.M)
_PWL_HEAD_RE = re.compile(r"^VCLK\s+\S+\s+\S+\s+pwl\([ \t]*\r?\n", re.M | re.I)


def spice_literal(text: str) -> float:
    """Parse a SPICE literal (`200p`, `3.9170n`, `1.8`, `0`).

    Deliberately a local parser rather than an import of
    `sim/harness/measure.parse_spice_time`: an `analysis/` script reads
    committed evidence and must keep running when the harness moves, so it
    takes no dependency on the harness package. `meg` is not accepted -- no
    literal in this evidence trail uses it, and mapping `m` to milli (SPICE's
    convention, which this does) is the only footgun that matters for the
    cards read here.
    """
    m = _LITERAL_RE.match(text.strip())
    if not m:
        raise AnalysisError(f"not a SPICE literal: {text!r}")
    value, suffix = float(m.group(1)), m.group(2).lower()
    if not suffix:
        return value
    scale = _SUFFIXES.get(suffix[0])
    if scale is None:
        raise AnalysisError(f"unknown SPICE suffix in {text!r}")
    return value * scale


def point_netlist(experiment: Path, record_id: str) -> Path:
    """The one committed per-point netlist of record `record_id`."""
    corners = experiment / "corners" / record_id
    netlists = sorted(p for p in corners.glob("*.spice") if not p.name.startswith("tb_"))
    if len(netlists) != 1:
        raise AnalysisError(
            f"{corners}: expected exactly one committed per-point netlist, found "
            f"{len(netlists)}"
        )
    return netlists[0]


def tran_card(netlist: str, path: Path) -> tuple[float, float]:
    """`(step_s, stop_s)` of the netlist's injected `tran <step> <stop>` card."""
    m = TRAN_RE.search(netlist)
    if m is None:
        raise AnalysisError(f"{path}: no injected `tran <step> <stop>` card")
    return spice_literal(m.group("step")), spice_literal(m.group("stop"))


def pulse_floor_point(experiment: Path, record_id: str) -> dict:
    """What a null-control (`pulse` clock) per-point netlist injected.

    Requires exactly one committed netlist, a `VCLK ... pulse(...)` card with a
    symmetric edge (TR == TF) and a `tran` card.
    """
    path = point_netlist(experiment, record_id)
    netlist = path.read_text()
    pulse = PULSE_RE.search(netlist)
    if pulse is None:
        raise AnalysisError(f"{path}: no `VCLK ... pulse(...)` card")
    if pulse.group("tr") != pulse.group("tf"):
        raise AnalysisError(
            f"{path}: this restatement assumes a symmetric edge (TR == TF), "
            f"got {pulse.group('tr')} / {pulse.group('tf')}"
        )
    step_s, stop_s = tran_card(netlist, path)
    return {
        "netlist_path": path,
        "period_s": spice_literal(pulse.group("per")),
        "edge_s": spice_literal(pulse.group("tr")),
        "step_s": step_s,
        "stop_s": stop_s,
    }


def pwl_points(netlist: str, path: Path) -> list[tuple[float, float]]:
    """The `(time_s, volts)` pairs of the committed `VCLK ... pwl(...)` card."""
    m = _PWL_HEAD_RE.search(netlist)
    if m is None:
        raise AnalysisError(
            f"{path}: no `VCLK <n+> <n-> pwl(` card -- is this a "
            "sim/jitter-calibration per-point netlist?"
        )
    points: list[tuple[float, float]] = []
    closed = False
    for line in netlist[m.end():].splitlines():
        body = line.strip()
        if not body.startswith("+"):
            raise AnalysisError(f"{path}: `pwl(` card ends without a closing `+ )` line")
        body = body[1:].strip()
        if body == ")":
            closed = True
            break
        fields = body.split()
        if len(fields) % 2:
            raise AnalysisError(
                f"{path}: `pwl(` continuation line has an odd field count: {line!r}"
            )
        for t_text, v_text in zip(fields[0::2], fields[1::2]):
            points.append((spice_literal(t_text), spice_literal(v_text)))
    if not closed:
        raise AnalysisError(f"{path}: `pwl(` card is never closed")
    if len(points) < 4:
        raise AnalysisError(f"{path}: `pwl(` card holds only {len(points)} points")
    times = [t for t, _ in points]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise AnalysisError(f"{path}: `pwl(` times are not strictly increasing")
    return points
