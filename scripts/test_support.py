"""Helpers shared by the `sim/`, `layout/` and `signoff/` unit-test suites.

Lives at the repo root next to `git_status.py` for the same reason: the three
test trees are otherwise independent and this is the one piece they share. A
test reaches it with `REPO_ROOT` on `sys.path` (`from scripts.test_support
import load_module`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


def load_module(name: str, path: Path, *, register: bool = True):
    """Load a module from its file path and return it.

    The slug directories carry hyphens, so most scripts under test are not
    importable packages. With `register=True` the module is entered in
    `sys.modules[name]` before it executes (needed when it is imported by
    name elsewhere, or defines dataclasses); pass `register=False` to leave
    `sys.modules` untouched.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def sha256_tag(data: bytes) -> str:
    """`sha256:<hex>` digest string, the form evidence manifests carry."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def record_table_rows(record_text: str) -> list:
    """The per-point result rows of a rendered record, in file order."""
    return [
        line.strip()
        for line in record_text.splitlines()
        if line.strip().startswith("| ") and ("PASS" in line or "FAIL" in line)
    ]
