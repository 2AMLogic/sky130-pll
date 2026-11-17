#!/usr/bin/env python3
"""Import-isolation guard for sim/tests (issue #463): every `test_*.py`
module in this directory must import cleanly in a fresh interpreter with
`cwd=sim/tests`.

`unittest discover` imports sibling test modules in alphabetical order, so a
module that leans on a *sibling's* import-time side effect -- a `sys.path`
bootstrap, a captured real implementation -- can pass the full suite while
failing the documented targeted run (`cd sim/tests && python3 -m unittest
<module>`). This guard turns "every module stands on its own at import time"
into a checked invariant for all of them at once.

It checks imports only. It deliberately does not run each module's tests
standalone: that would roughly double suite wall-clock on the shared workers
for no new signal -- a module whose *tests* (not its imports) depend on sort
order is caught by the snapshot guard in test_executor.py, not here.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

MODULES = sorted(p.stem for p in TESTS_DIR.glob("test_*.py"))


class EveryTestModuleImportsStandalone(unittest.TestCase):
    def test_every_test_module_imports_in_a_fresh_interpreter(self):
        broken = []
        for mod in MODULES:
            proc = subprocess.run(
                [sys.executable, "-c", f"import {mod}"],
                cwd=TESTS_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                broken.append(
                    f"--- {mod}: import failed (rc={proc.returncode}) ---\n"
                    f"{proc.stderr.strip()}"
                )
        self.assertEqual(
            [],
            broken,
            "test modules that do not import standalone:\n" + "\n".join(broken),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
