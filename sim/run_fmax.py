#!/usr/bin/env python3
"""Divider Fmax characterization campaign runner (issue #244).

    python3 sim/run_fmax.py divider-fmax --dry-run
    python3 sim/run_fmax.py divider-fmax --executor remote

See sim/harness/fmax_cli.py and sim/divider-fmax/testbench/fmax.json.
Stdlib only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.fmax_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
