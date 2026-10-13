#!/usr/bin/env python3
"""Mechanically grade the combined LOCK timing evidence (issue #276).

Reads recorded results (never re-simulates), splits the phase candidate's
verdicts into the acquisition and release products and calls the #273 reducer's
`handoff` over {phase-acq, phase-rel, watchdog}.

    python3 design/lock-detector/timing/grade_combined.py PHASE_RECORD.json WATCHDOG_RECORD.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sim"))
from harness import locktiming as L  # noqa: E402


def result(path):
    return json.loads(Path(path).read_text())["candidates"][0]["result"]


def part(res, product, checks):
    v = [res["verdicts"][c] for c in checks]
    verdict = L.MISS if L.MISS in v else (L.PASS if res["complete"] and set(v) == {L.PASS} else L.INCONCLUSIVE)
    return {**res, "product_id": product, "verdict": verdict, "checks": checks}


def main(phase, wd):
    p, w = result(phase), result(wd)
    results = [part(p, "phase-acq", ["w_acq"]),
               part(p, "phase-rel", ["w_rel", "rel_ceiling_lt_12ns", "hysteresis_max_acq_lt_min_rel"]),
               part(w, "watchdog", ["tick"])]
    out = {"handoff": L.handoff(results, ["phase-acq", "phase-rel", "watchdog"]),
           "products": {r["product_id"]: {"candidate": r["candidate_id"], "complete": r["complete"],
                                          "verdict": r["verdict"],
                                          "checks": {c: r["verdicts"][c] for c in r["checks"]}}
                        for r in results}}
    print(json.dumps(out, indent=1))
    return 0 if out["handoff"]["handoff_ready"] else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
