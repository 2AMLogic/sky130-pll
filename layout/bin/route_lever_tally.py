#!/usr/bin/env python3
"""Derive one routing-lever measurement row from a flow run's own evidence.

Issue #548's deliverable is the measurement: the routed spot-check was
re-run once per lever (cumulatively), and the final record carries a
before/after table. Every number in that table comes from a run's own `klt`
JSON envelopes -- this module is the single place that derivation lives, so
the table's rows and the record's own routing spot-check section can never
disagree about what a run reported.

Two entry points:

* ``tally_row(run_dir, record_id, label, levers)`` -- one row dict (also
  imported by ``render-pll-record.py`` for its cross-check of the final
  row).
* the CLI: ``route-lever-tally.py row --run-dir … --record-id … --label …
  --levers a,b,c`` prints one row as JSON; ``… merge --prior rows.json
  --run-dir …`` appends this run's row to a copy of ``rows.json`` on
  stdout (the flow stores the merged file next to the record, so the
  ladder's evidence travels with it).

Each row carries the sha256 of every envelope its numbers derive from, so
a row in the final record's table is verifiable against the artifact store
(``klt artifact get <sha256>``) with no manifest of its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BIN_DIR = Path(__file__).resolve().parent
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))

# --- leg-reason bucketing (shared with render-pll-record.py) ----------------
#
# How a `gen-compose` leg's own `reason` string is bucketed. Each entry is
# (substring, label); the first matching substring wins, so order matters.
# The strings are the router's own (`legs[].reason` in a compose response),
# not this module's paraphrase -- the label column of a table built from
# these is the router's vocabulary, quoted.

ROUTE_REASON_BUCKETS: tuple[tuple[str, str], ...] = (
    (
        "comes within",
        "would come closer to an already-drawn route than the resolved deck's "
        "own same-layer minimum spacing (the router's spacing-aware collision "
        "check, new at `klayout-tools==0.6.0` -- it is why the routed "
        "spot-check's own DRC no longer reports `met1.space.1`)",
    ),
    (
        "crosses already-routed net",
        "would cross an already-drawn route (the router's own route-vs-route "
        "collision check, klayout-tools#1057)",
    ),
    (
        "bare-poly gate",
        "terminates on a bare-poly gate with no contacted landing pad "
        "(`params.gate_contact`, klayout-tools#492 -- this flow does not opt in)",
    ),
    (
        "through unrelated block",
        "backbone would plough through an unrelated block's bbox (no routing "
        "channel between abutted groups)",
    ),
    (
        "through its own pin's block",
        "backbone would plough through its own pin's block (no routing channel "
        "inside a matched array)",
    ),
)

#: Short forms for the lever table's reason columns -- the full labels above
#: are what the record's spot-check section spells out; a table row only
#: needs the distinguishing head of each.
REASON_SHORT_LABELS: dict[str, str] = {
    ROUTE_REASON_BUCKETS[0][1]: "same-layer spacing",
    ROUTE_REASON_BUCKETS[1][1]: "route-vs-route",
    ROUTE_REASON_BUCKETS[2][1]: "bare-poly gate",
    ROUTE_REASON_BUCKETS[3][1]: "unrelated block",
    ROUTE_REASON_BUCKETS[4][1]: "own pin's block",
}

#: Envelopes whose sha256 a row cites: everything its numbers derive from.
_EVIDENCE_GLOBS = (
    "route-spot-check/compose.*.response.json",
    "route-spot-check/extract.json",
    "route-spot-check/drc.json",
    "route-spot-check/lvs.json",
)

#: A node the extractor labels with more than one declared net name -- the
#: same multi-label pattern `render-pll-record.py` counts for the record's
#: own "no drawn short" claim.
_MULTI_LABEL_NODE_RE = re.compile(r"[A-Za-z_0-9]+(?:\|[A-Za-z_0-9]+)+")


def reason_bucket(reason: str | None) -> str:
    for needle, label in ROUTE_REASON_BUCKETS:
        if needle in (reason or ""):
            return label
    return "other"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def route_stats(spot_dir: Path) -> dict[str, Any]:
    """Aggregate what the routed spot-check's own compose responses report.

    Everything here is read back out of `klt gen-compose`'s responses -- net
    `status`, per-leg `routed`, and the router's own `reason` string for a
    leg it declined to draw. Nothing is inferred from the drawn stream.
    """
    status: Counter = Counter()
    reasons: Counter = Counter()
    legs = drawn = 0
    for path in sorted(spot_dir.glob("compose.*.response.json")):
        for net in _load(path).get("nets", []) or []:
            status[net.get("status") or ("routed" if net.get("routed") else "unrouted")] += 1
            for leg in net.get("legs") or []:
                legs += 1
                if leg.get("routed"):
                    drawn += 1
                else:
                    reasons[reason_bucket(leg.get("reason"))] += 1
    return {"status": status, "legs": legs, "drawn_legs": drawn, "reasons": reasons}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_map(run_dir: Path) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for pattern in _EVIDENCE_GLOBS:
        for path in sorted(run_dir.glob(pattern)):
            evidence[path.relative_to(run_dir).as_posix()] = _sha256(path)
    return evidence


def _supply_status(spot_dir: Path, supplies: list[str]) -> dict[str, dict[str, str]]:
    """Per block, per supply net, the router's own net `status`."""
    out: dict[str, dict[str, str]] = {}
    for path in sorted(spot_dir.glob("compose.*.response.json")):
        block = path.name.split(".")[1]
        if block == "top":
            continue
        statuses = {
            net["net"]: net.get("status", "unrouted")
            for net in _load(path).get("nets", []) or []
            if net.get("net") in supplies
        }
        if statuses:
            out[block] = statuses
    return out


def _shorted_node_count(spot_dir: Path) -> int:
    spice = spot_dir / "pll_top.spice"
    if not spice.is_file():
        return 0
    merged = set(_MULTI_LABEL_NODE_RE.findall(spice.read_text()))
    return len(merged)


def tally_row(
    run_dir: Path,
    record_id: str,
    label: str,
    levers: list[str],
) -> dict[str, Any]:
    """One measurement row, derived entirely from `run_dir`'s evidence."""
    spot_dir = run_dir / "route-spot-check"
    stats = route_stats(spot_dir)
    drc = _load(spot_dir / "drc.json")
    lvs_path = spot_dir / "lvs.json"
    lvs = _load(lvs_path) if lvs_path.is_file() else {}
    build_path = run_dir / "build.json"
    supplies: list[str] = []
    if build_path.is_file():
        levers_block = (_load(build_path).get("routing_levers") or {})
        supplies = levers_block.get("supply_nets") or ["VDD", "GND"]
    return {
        "record_id": record_id,
        "label": label,
        "levers": list(levers),
        "legs_total": stats["legs"],
        "legs_drawn": stats["drawn_legs"],
        "nets_routed": stats["status"].get("routed", 0),
        "nets_partial": stats["status"].get("partial", 0),
        "nets_unrouted": stats["status"].get("unrouted", 0),
        "declined_reasons": {
            REASON_SHORT_LABELS.get(reason, reason): count
            for reason, count in stats["reasons"].most_common()
        },
        "shorted_nodes": _shorted_node_count(spot_dir),
        "routed_drc_violations": drc.get("violation_count", 0),
        "lvs_status": lvs.get("status"),
        "lvs_mismatches": lvs.get("mismatch_count"),
        "lvs_top_categories": dict(
            Counter(lvs.get("category_counts", {})).most_common(3)
        ),
        "supply_status": _supply_status(spot_dir, supplies),
        "evidence_sha256": _evidence_map(run_dir),
    }


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("row", "merge"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", required=True, type=Path)
        p.add_argument("--record-id", required=True)
        p.add_argument("--label", default="")
        p.add_argument("--levers", default="", help="comma-separated lever names")
    sub.choices["merge"].add_argument(
        "--prior", required=True, type=Path, help="rows JSON from earlier runs"
    )
    return ap.parse_args()


def _expand_levers(spec: str) -> list[str]:
    """Expand a lever spec ("all"/"none"/csv) to canonical names, sorted.

    Shares `pll_layout.parse_route_levers` so the tally row, the flow and
    the generator can never disagree about what a spec spells.
    """
    from pll_layout import parse_route_levers

    return sorted(parse_route_levers(spec))


def main() -> int:
    args = _parse_args()
    levers = _expand_levers(args.levers)
    row = tally_row(args.run_dir, args.record_id, args.label, levers)
    if args.cmd == "row":
        print(json.dumps(row, indent=2) + "\n")
        return 0
    prior = json.loads(args.prior.read_text())
    if not isinstance(prior, list):
        raise SystemExit(f"--prior must be a JSON array of rows: {args.prior}")
    print(json.dumps(prior + [row], indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
