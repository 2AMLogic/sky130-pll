#!/usr/bin/env python3
"""LOCK timing fixed-stimulus batch runner (issue #274); see
sim/harness/locktiming_cli.py and sim/lockdet-timing/README.md."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness.locktiming_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
