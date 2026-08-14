#!/usr/bin/env python3
"""PVT corner runner for sky130-pll.

    python3 sim/run_corners.py --check-env
    python3 sim/run_corners.py --list
    python3 sim/run_corners.py pdk-smoke

Stdlib only, no virtualenv required. See sim/README.md for the evidence
schema every run produces, and sim/harness/README.md for the testbench
manifest format.

Provenance: entry-point shape (and the `sim/harness/` package split it
delegates to) follows 2AMLogic/gf180-pll's sim/run_corners.py /
sim/harness/cli.py convention (source commit
3e3814c11ce6f0781ecfbefb0d109981c4e5eb21), per this repo's CLAUDE.md
harness-bootstrap rule. The implementation here is written fresh and scoped
down to what issue #2's plumbing needs -- see sim/harness/__init__.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
