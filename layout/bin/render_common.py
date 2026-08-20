"""Shared boilerplate for `layout/bin/`'s evidence-record renderers.

Factors what `render-record.py` (trivial-cell flow) and `render-pll-record.py`
(PLL layout flow) both compute independently: the JSON-file load helper, the
`klt --version` / `klt pdk find` subprocess pair that resolves `klt_version`
and `pdk_info`, and the git provenance block (sha/branch/dirty).

Named `render_common.py` (underscore, not hyphen) so it can be imported
normally -- unlike the two `render-*.py` scripts themselves, which are loaded
by path (see `layout/tests/test_record_dirty_flag.py`) because a hyphenated
filename isn't a valid Python module name.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# scripts/git_status.py lives at the repo root (shared with
# sim/harness/report.py -- sim/ and layout/ are otherwise independent trees
# per CLAUDE.md's harness-bootstrap convention).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.git_status import is_dirty, run_git  # noqa: E402


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def klt_info(klt: str, pdk_variant: str) -> tuple[str, dict]:
    """Resolve `(klt_version, pdk_info)` via `klt --version` / `klt pdk find`."""
    klt_version = subprocess.run(
        [klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info_raw = subprocess.run(
        [klt, "pdk", "find", "--pdk", pdk_variant, "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pdk_info = json.loads(pdk_info_raw)
    return klt_version, pdk_info


def git_provenance(repo_root: Path, out_dir: Path) -> tuple[str, str, bool]:
    """Resolve `(sha, branch, dirty)` for the record's "Repo state" line.

    `dirty` ignores the run's own report directory (`out_dir`) -- otherwise
    every record would read dirty, since the run just wrote those files.
    """
    sha = run_git(repo_root, "rev-parse", "HEAD")
    branch = run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    report_rel = out_dir.resolve().relative_to(repo_root.resolve()).as_posix() + "/"
    # --untracked-files=all is load-bearing: git's default collapses a wholly
    # untracked tree to its parent directory ("?? layout/trivial-cell/
    # reports/"), which no per-record prefix can match, so every record would
    # read dirty again.
    dirty = is_dirty(
        run_git(repo_root, "status", "--porcelain", "--untracked-files=all"), report_rel
    )
    return sha, branch, dirty
