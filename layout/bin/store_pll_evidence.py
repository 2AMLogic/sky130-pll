#!/usr/bin/env python3
"""Store the PLL layout flow's raw outputs in the artifact store (issue #371).

`run-pll-layout-flow.sh` stages everything (GDS, extracted SPICE, JSON
envelopes, renders) in the git-ignored `layout/pll/build/<record-id>/`. This
script hands that tree to `sim/harness/evidence_store.py` (DR-012, #370), which
puts every file through `klt artifact put` and commits only

* `manifests/artifacts/layout-pll-<record-id>.manifest.json`, and
* `layout/pll/reports/<record-id>/record.md` (the scratch `record.md` plus a
  "Stored evidence" section naming every object).

Fail closed: any failure exits nonzero having committed nothing; the staged
bytes stay in the scratch dir. There is no fallback that commits the bytes.

    store_pll_evidence.py preflight [--klt KLT]
    store_pll_evidence.py store --stage-dir DIR --record-id ID [--klt KLT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sim.harness import evidence_store  # noqa: E402

BENCH = "layout-pll"
REPORTS_REL = Path("layout") / "pll" / "reports"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preflight", "store"):
        p = sub.add_parser(name)
        p.add_argument("--klt", default="klt")
    sub.choices["store"].add_argument("--stage-dir", type=Path, required=True)
    sub.choices["store"].add_argument("--record-id", required=True)
    args = ap.parse_args(argv)

    try:
        evidence_store.preflight(REPO_ROOT, klt=args.klt)
        if args.cmd == "preflight":
            return 0
        record = args.stage_dir / "record.md"
        if not record.is_file():
            raise evidence_store.StoreError(f"no {record} to publish")
        files = evidence_store.stage_files(
            args.stage_dir, (REPORTS_REL / args.record_id).as_posix(), exclude=[record])
        summary_path = REPO_ROOT / REPORTS_REL / args.record_id / "record.md"
        mpath = evidence_store.store_files(
            files, repo_root=REPO_ROOT, bench=BENCH, rid=args.record_id,
            summary_text=record.read_text(encoding="utf-8"),
            summary_path=summary_path)
    except evidence_store.StoreError as exc:
        print(f"store_pll_evidence.py: evidence NOT stored, nothing committed: {exc}. "
              f"Staged bytes are kept in {args.stage_dir if args.cmd == 'store' else 'scratch'} "
              "(DR-012: no fallback to committing bytes)", file=sys.stderr)
        return 1
    print(f"store_pll_evidence.py: wrote {mpath.relative_to(REPO_ROOT)} and "
          f"{summary_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
