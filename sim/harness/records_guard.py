"""Shared re-run guard for the PVT / Monte Carlo / Fmax record writers.

`CLAUDE.md`: `sim/` results are append-only evidence -- a re-run mints a new
record that names the one it supersedes. The lock-timing lane enforces that
mechanically (`locktiming_cli.write_record` refuses a re-run without
`--supersedes`); the PVT / `--mc` / Fmax lanes only refused re-minting the
*same record id*, so a re-run that forgot `--supersedes` minted a record
whose `**Supersedes**:` line falsely said "(none -- first record for this
claim)" (issue #503).

`cli._run_experiment` (PVT and `--mc`) and `fmax_cli.cmd` call `check()`
before any simulation starts, with two checks:

1. a given `--supersedes` must name a record that exists in the lane's
   `records/` directory (a typo'd pointer must not land);
2. with no `--supersedes`, no existing record may carry the new run's
   collision key.

The collision key is the *re-run identity*: normalized claim text + the
lane's matrix block + the netlist SHA-256. It is deliberately not "any prior
record in the directory": a directory legitimately holds same-claim records
that do not supersede one another (`sim/divider-n64`'s incremental corner
subsets, `sim/jitter-calibration`'s one-netlist-per-variant sweep) -- those
differ in the matrix block and/or the netlist digest, so a dir-level guard
would refuse them.

Digest discipline (issue #441): this module hashes nothing. It compares
digest strings the caller obtained through `report.sha256_bytes` /
`report.sha256_file`.

Parsing reads the committed record schema (sim/README.md): the `- **Claim**:`
line, one of the three matrix blocks (`**Corner matrix run**` for PVT,
`**Statistical sampling point**` for Monte Carlo, `**Search / corner matrix
run**` for Fmax), the `- **Netlist provenance**` line's SHA-256, and the
`- **Supersedes**:` line in any of its attested forms (bare id, backticked id
with trailing prose, or one of the two "first record" wordings).

Stdlib only; no PDK, no simulation -- the unit tests over `sim/tests/` run
without either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RECORD_ID_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{7}")
NETLIST_SHA_RE = re.compile(r"SHA-256 `([0-9a-f]{64})`")

_PVT_HEADER = "- **Corner matrix run**:"
_MC_HEADER = "- **Statistical sampling point**:"
_FMAX_HEADER = "- **Search / corner matrix run**:"


class RecordsGuardError(RuntimeError):
    """A record-write the append-only rule refuses; the caller turns this
    into a non-zero exit naming what to do."""


@dataclass(frozen=True)
class ExistingRecord:
    id: str
    supersedes: str | None
    claim: str
    matrix_key: tuple
    netlist_sha: str

    @property
    def collision_key(self) -> tuple:
        return (_norm_ws(self.claim), self.matrix_key, self.netlist_sha)


def _norm_ws(text: str | None) -> str:
    return " ".join((text or "").split())


def _canon_temp(v) -> str:
    """One canonical spelling of a temperature, independent of which lane's
    `%g` / `str()` formatting produced the record line."""
    return repr(float(v))


def _canon_supply(v) -> str:
    return f"{float(v):.2f}"


def _csv(values: str):
    return [v.strip() for v in values.split(",") if v.strip()]


def _canon_pvt_block(lines: list[str]) -> tuple:
    corners, temps, supplies, total, note, subset = None, None, None, None, "", ""
    for line in lines:
        text = line.strip()
        if text.startswith("- Process corners:"):
            corners = tuple(sorted(set(_csv(text.split(":", 1)[1]))))
        elif text.startswith("- Temperatures (deg C):"):
            temps = tuple(sorted({_canon_temp(v) for v in _csv(text.split(":", 1)[1])}))
        elif text.startswith("- Supplies (V):"):
            value = text.split(":", 1)[1]
            supplies = (
                "n/a"
                if "not applicable" in value
                else tuple(sorted({_canon_supply(v) for v in _csv(value)}))
            )
        elif text.startswith("- Total points:"):
            total = int(text.split(":", 1)[1])
        elif text.startswith("- Corner-set note:"):
            note = _norm_ws(text.split(":", 1)[1])
        elif text.startswith("- **Subset of the manifest's default grid**:"):
            subset = _norm_ws(text.split(":", 1)[1])
    missing = [
        name
        for name, value in (
            ("Process corners", corners),
            ("Temperatures (deg C)", temps),
            ("Supplies (V)", supplies),
            ("Total points", total),
        )
        if value is None
    ]
    if missing:
        raise RecordsGuardError(
            f"record's **Corner matrix run** block lacks {', '.join(missing)}"
        )
    return ("pvt", corners, temps, supplies, total, note, subset)


def _canon_mc_block(lines: list[str]) -> tuple:
    corner, temp, supply, mismatch, process, trials, subset = (
        None,
        None,
        None,
        None,
        None,
        None,
        "",
    )
    for line in lines:
        text = line.strip()
        if text.startswith("- Base process corner:"):
            corner = text.split(":", 1)[1].split("(netlisted")[0].strip()
        elif text.startswith("- Temperature (deg C):"):
            temp = _canon_temp(text.split(":", 1)[1])
        elif text.startswith("- Supply (V):"):
            supply = _canon_supply(text.split(":", 1)[1])
        elif text.startswith("- Mismatch sampling"):
            mismatch = text.rsplit(":", 1)[1].strip() == "on"
        elif text.startswith("- Process sampling"):
            process = text.rsplit(":", 1)[1].strip() == "on"
        elif text.startswith("- Trials:"):
            head = text.split(":", 1)[1]
            trials = int(head.split("(")[0].strip())
        elif text.startswith("- **Subset/override of the manifest's default"):
            subset = _norm_ws(text.split(":", 1)[1])
    missing = [
        name
        for name, value in (
            ("Base process corner", corner),
            ("Temperature (deg C)", temp),
            ("Supply (V)", supply),
            ("Mismatch sampling", mismatch),
            ("Process sampling", process),
            ("Trials", trials),
        )
        if value is None
    ]
    if missing:
        raise RecordsGuardError(
            f"record's **Statistical sampling point** block lacks {', '.join(missing)}"
        )
    return ("mc", corner, temp, supply, mismatch, process, trials, subset)


def _canon_fmax_block(lines: list[str]) -> tuple:
    moduli, corners, temps, supplies, cells, subset = (None, None, None, None, None, "")
    for line in lines:
        text = line.strip()
        if text.startswith("- Moduli:"):
            moduli = tuple(sorted({int(v) for v in _csv(text.split(":", 1)[1])}))
        elif text.startswith("- Process corners:"):
            corners = tuple(sorted(set(_csv(text.split(":", 1)[1]))))
        elif text.startswith("- Temperatures (deg C):"):
            temps = tuple(sorted({_canon_temp(v) for v in _csv(text.split(":", 1)[1])}))
        elif text.startswith("- Supplies (V):"):
            supplies = tuple(sorted({_canon_supply(v) for v in _csv(text.split(":", 1)[1])}))
        elif text.startswith("- Cells (modulus x PVT point):"):
            cells = int(text.split(":", 1)[1].split(";")[0].strip())
        elif text.startswith("- **Subset of the manifest's default grid**:"):
            subset = _norm_ws(text.split(":", 1)[1])
    missing = [
        name
        for name, value in (
            ("Moduli", moduli),
            ("Process corners", corners),
            ("Temperatures (deg C)", temps),
            ("Supplies (V)", supplies),
            ("Cells (modulus x PVT point)", cells),
        )
        if value is None
    ]
    if missing:
        raise RecordsGuardError(
            f"record's **Search / corner matrix run** block lacks {', '.join(missing)}"
        )
    return ("fmax", moduli, corners, temps, supplies, cells, subset)


def _parse_supersedes(line: str, path: Path) -> str | None:
    value = line.split(":", 1)[1].strip()
    if value.startswith("(none") or re.match(r"none\b", value):
        return None
    found = RECORD_ID_RE.search(value)
    if found is None:
        raise RecordsGuardError(
            f"{path}: unparseable **Supersedes** value {value!r}"
        )
    return found.group(0)


def parse_record(path: Path) -> ExistingRecord | None:
    """Parse one committed record file; `None` for a file in `records/` that
    is not a SPICE-lane record -- a stray note, or a different record genre
    like sim/phase-quadrature-model's PDK-free model records, which carry
    neither a netlist digest nor a matrix block. A file carrying exactly one
    of those two markers (a truncated lane record) is refused."""
    lines = path.read_text().splitlines()
    record_id, claim_parts, netlist_sha, supersedes = None, None, None, None
    matrix_key: tuple | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("- **Record ID**:"):
            record_id = line.split(":", 1)[1].strip()
        elif line.startswith("- **Claim**:"):
            claim_parts = [line.split(":", 1)[1]]
            j = i + 1
            while (
                j < len(lines)
                and lines[j].strip()
                and not lines[j].startswith("- **")
            ):
                claim_parts.append(lines[j])
                j += 1
        elif line.startswith("- **Netlist provenance**:"):
            found = NETLIST_SHA_RE.search(line)
            if found is not None:
                netlist_sha = found.group(1)
        elif line.startswith((_PVT_HEADER, _MC_HEADER, _FMAX_HEADER)):
            j = i + 1
            block: list[str] = []
            while j < len(lines) and (
                lines[j].startswith(("  ", "\t")) or not lines[j].strip()
            ):
                if lines[j].strip():
                    block.append(lines[j])
                j += 1
            header = _PVT_HEADER if line.startswith(_PVT_HEADER) else (
                _MC_HEADER if line.startswith(_MC_HEADER) else _FMAX_HEADER
            )
            if header == _PVT_HEADER:
                matrix_key = _canon_pvt_block(block)
            elif header == _MC_HEADER:
                matrix_key = _canon_mc_block(block)
            else:
                matrix_key = _canon_fmax_block(block)
        elif line.startswith("- **Supersedes**:"):
            supersedes = _parse_supersedes(line, path)
        i += 1
    if record_id is None:
        return None
    if netlist_sha is None and matrix_key is None:
        # A different record genre: e.g. sim/phase-quadrature-model's
        # PDK-free model records live in a records/ dir too but carry neither
        # a netlist digest nor a matrix block, and no lane writer targets
        # them. Skip, don't refuse.
        return None
    problems = []
    if netlist_sha is None:
        problems.append("a **Netlist provenance** line with a SHA-256")
    if matrix_key is None:
        problems.append("a matrix block (**Corner matrix run**, **Statistical "
                        "sampling point** or **Search / corner matrix run**)")
    if problems:
        raise RecordsGuardError(f"{path}: committed record lacks {' and '.join(problems)}")
    return ExistingRecord(
        id=record_id,
        supersedes=supersedes,
        claim=_norm_ws(" ".join(claim_parts)) if claim_parts is not None else "",
        matrix_key=matrix_key,
        netlist_sha=netlist_sha,
    )


def scan_records(records_dir: Path) -> list[ExistingRecord]:
    if not records_dir.is_dir():
        return []
    records = []
    for path in sorted(records_dir.glob("*.md")):
        parsed = parse_record(path)
        if parsed is not None:
            records.append(parsed)
    return sorted(records, key=lambda r: r.id)


def pvt_matrix_key(*, points, manifest_has_supply: bool, corner_note, subset_reason) -> tuple:
    """The new run's PVT matrix key, in the exact shape `_canon_pvt_block`
    produces from a committed record's block."""
    return (
        "pvt",
        tuple(sorted({p.corner for p in points})),
        tuple(sorted({_canon_temp(p.temp_c) for p in points})),
        "n/a"
        if not manifest_has_supply
        else tuple(sorted({_canon_supply(p.supply_v) for p in points})),
        len(points),
        _norm_ws(corner_note),
        _norm_ws(subset_reason),
    )


def mc_matrix_key(*, trials, subset_reason) -> tuple:
    """The new run's Monte Carlo matrix key (one `**Statistical sampling
    point**` block: all trials share the point, seeds vary)."""
    first = trials[0]
    return (
        "mc",
        first.corner,
        _canon_temp(first.temp_c),
        _canon_supply(first.supply_v),
        bool(first.mismatch),
        bool(first.process),
        len(trials),
        _norm_ws(subset_reason),
    )


def fmax_matrix_key(*, cells, subset_reason) -> tuple:
    """The new run's Fmax matrix key. The block's "probes run" count is an
    *outcome* (unknown before the search runs), so the key carries the cell
    set but not it -- a re-run of the same cells on the same netlist is the
    collision this guard exists for, whatever the probe count turns out to
    be."""
    return (
        "fmax",
        tuple(sorted({c.modulus.n for c in cells})),
        tuple(sorted({c.point.corner for c in cells})),
        tuple(sorted({_canon_temp(c.point.temp_c) for c in cells})),
        tuple(sorted({_canon_supply(c.point.supply_v) for c in cells})),
        len(cells),
        _norm_ws(subset_reason),
    )


def check(
    *,
    records_dir: Path,
    claim: str,
    matrix_key: tuple,
    netlist_sha: str,
    supersedes: str | None,
) -> None:
    """Refuse a record write that would violate the append-only rule:
    `--supersedes` naming no record in `records_dir`, or -- when no
    `--supersedes` is given -- an existing record carrying this run's
    collision key. Raises `RecordsGuardError`; a caller catches it and
    exits non-zero before simulating."""
    records = scan_records(records_dir)
    if supersedes is not None:
        if supersedes not in {r.id for r in records}:
            raise RecordsGuardError(
                f"--supersedes {supersedes!r} names no record in {records_dir}"
            )
        return
    key = (_norm_ws(claim), matrix_key, netlist_sha)
    matching = [r for r in records if r.collision_key == key]
    if not matching:
        return
    successor_of = {r.supersedes: r.id for r in records if r.supersedes}
    current, matched = matching[-1].id, matching[-1].id
    while current in successor_of:
        current = successor_of[current]
    message = (
        f"same claim, matrix and netlist are already recorded in {records_dir} "
        f"({matched}); records are append-only -- a re-run mints a new record "
        f"naming the one it supersedes: pass --supersedes {current}"
    )
    if current != matched:
        message += (
            f" (the claim's current record -- {matched} is already superseded by it)"
        )
    raise RecordsGuardError(message)
