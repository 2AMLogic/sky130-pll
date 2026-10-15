#!/usr/bin/env python3
"""Split a power-campaign `klt sim` request into batch-fleet shards (issue #233).

The batch fleet kills a whole job at 3600 s (`max_job_seconds`) and caps the
fleet at 8 instances, so the 45-point request of a slow block cannot go as one
job. `klt sim --hosts` only shards the local backends, so this splits the PVT
grid client-side into independent requests that together cover exactly the 45
ratified points -- no point is dropped, no reduced grid is claimed.

Measured serial cost of one tt/1.80 V/27 C point on a shared worker (local
`ngspice`, 2026-10-15): vco 64 s, divider-n4 95 s, pfd-cp 86 s,
divider-n64 300 s. A shard's serial cost must stay well under 3600 s at the
slow corners, so:

    vco, divider-n4, pfd-cp   one shard per process corner     9 points  (~10-15 min)
    divider-n64               one shard per process x supply   3 points  (~15 min)

    python3 sim/power/shard.py --out DIR            # all blocks
    python3 sim/power/shard.py --out DIR --block pfd-cp --only 0   # one shard

Each shard's `options.timeout_s` is lowered so klt's serial bound fits the 3600 s
ceiling (see `unit_timeout_s`); the canonical request keeps its 7200 s.

For each shard it writes `DIR/<block>.shard<NN>.request.json` (netlist made
absolute so the request can live outside the repo) and prints the file list.
Submit them with `klt sim --batch-set ... --max-in-flight <= 4`; each shard's
report goes to `DIR/<block>.shard<NN>.report.json`, which `mint.py` merges.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TB_DIR = HERE / "testbench"

BLOCKS = ["vco", "divider-n4", "divider-n64", "pfd-cp"]
# Axes a shard is split along (the rest stay whole inside the shard).
SPLIT_AXES = {
    "vco": ("process",),
    "divider-n4": ("process",),
    "pfd-cp": ("process",),
    "divider-n64": ("process", "supply"),
}


MAX_JOB_S = 3600  # fleet_config max_job_seconds
JOB_OVERHEAD_S = 120  # klt's fixed allowance in its serial-bound estimate


def unit_timeout_s(units: int) -> int:
    """Largest per-point timeout whose serial bound (timeout x units + overhead)
    still fits the fleet's whole-job ceiling, with 120 s slack for
    staging. 9 points -> 373 s (>= 4x the measured 64-95 s); 3 points -> 1120 s
    (3.7x the measured 300 s)."""
    return (MAX_JOB_S - 120 - JOB_OVERHEAD_S) // units


def shard_requests(block: str, request: dict) -> list[dict]:
    """Partition `request`'s PVT grid into one request per cell of SPLIT_AXES."""
    axes = SPLIT_AXES[block]
    corners = request["corners"]
    supplies = corners["supply_v"]["v1"]
    procs = corners["process"]
    cells = itertools.product(procs, supplies if "supply" in axes else [None])
    out = []
    for proc, vdd in cells:
        r = copy.deepcopy(request)
        r["corners"]["process"] = [proc]
        if vdd is not None:
            r["corners"]["supply_v"] = {"v1": [vdd]}
        r.setdefault("options", {})["timeout_s"] = unit_timeout_s(len(grid_points(r)))
        out.append(r)
    return out


def grid_points(request: dict) -> set[tuple]:
    c = request["corners"]
    return {(p, v, t) for p in c["process"] for v in c["supply_v"]["v1"]
            for t in c["temperature_c"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--block", choices=BLOCKS)
    ap.add_argument("--only", type=int, help="write only this shard index (one-shard check)")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for block in [args.block] if args.block else BLOCKS:
        full = json.loads((TB_DIR / f"{block}.request.json").read_text())
        shards = shard_requests(block, full)
        covered = [grid_points(s) for s in shards]
        assert set().union(*covered) == grid_points(full) and \
            sum(len(c) for c in covered) == len(grid_points(full)), "shards must partition the grid"
        for i, r in enumerate(shards):
            if args.only is not None and i != args.only:
                continue
            r["netlist"] = str((TB_DIR / r["netlist"]).resolve())
            path = args.out / f"{block}.shard{i:02d}.request.json"
            path.write_text(json.dumps(r, indent=2) + "\n")
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
