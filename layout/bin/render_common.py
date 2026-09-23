"""Shared boilerplate for `layout/bin/`'s evidence-record renderers.

Factors what `render-record.py` (trivial-cell flow) and `render-pll-record.py`
(PLL layout flow) both compute independently: the JSON-file load helper, the
`klt --version` / `klt pdk find` subprocess pair that resolves `klt_version`
and `pdk_info`, the git provenance block (sha/branch/dirty), and the
rendering of all of that into the record's `## Provenance` section.

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


def render_provenance(
    a: Any,
    args: Any,
    klt_version: str,
    pdk_info: dict[str, Any],
    drc: dict[str, Any],
    sha: str,
    branch: str,
    dirty: bool,
    *,
    netlist_display: str | None = None,
) -> None:
    """Render a record's `## Provenance` section through the line sink `a`.

    `netlist_display` is the repo-relative schematic netlist the layout was
    derived from; the `Schematic netlist:` line is emitted only when it is
    given (the PLL flow passes it, the trivial-cell flow has no schematic).
    """
    a("## Provenance")
    a("")
    a(f"- Record ID: `{args.record_id}`")
    if netlist_display is not None:
        a(f"- Schematic netlist: `{netlist_display}`")
    a(f"- `klt` version: `{klt_version}` (see `layout/requirements.txt`)")
    a(f"- KLayout engine version: `{drc.get('provenance', {}).get('klayout_version')}`")
    a(f"- PDK: `{pdk_info.get('variant')}`, `{pdk_info.get('version')}`")
    a(
        "- PDK pin cross-check: compare `version` above against "
        "`sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself "
        "enforce the pin, so a mismatch is a manual reproducibility note."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else ""))
    a("")


class SpecRowsError(ValueError):
    """A block's `spec-rows.json` declaration is missing or malformed."""


def spec_rows_line(out_dir: Path) -> str:
    """Render the `- **Spec row(s)**: ...` line for a layout block's record.

    The declaration lives in `layout/<block>/spec-rows.json`, the layout-tree
    counterpart of a `sim/<slug>/testbench/tb.json` manifest's `spec_rows`
    key: the block directory is mutable, while the records under
    `reports/<record-id>/` are append-only evidence. Emitting the line from
    here means every record either cites a `spec/target-spec.md` row or says
    in its own body that it measures none -- by construction, not by an author
    remembering to add it (issue #152).

    `out_dir` is the run's own `layout/<block>/reports/<record-id>/`
    directory, so the block directory is two levels up.
    """
    block_dir = out_dir.resolve().parent.parent
    path = block_dir / "spec-rows.json"
    if not path.is_file():
        raise SpecRowsError(
            f"{path} does not exist -- every layout block must declare which "
            "spec/target-spec.md row(s) its records measure (e.g. "
            '`{"spec_rows": [18]}`), or declare `"spec_rows": []` with a '
            '`"spec_rows_note"` saying why it measures none. See '
            "measurements/README.md's citation convention."
        )
    decl = load_json(path)
    raw = decl.get("spec_rows")
    if not isinstance(raw, list):
        raise SpecRowsError(f"{path}: `spec_rows` must be a list of row numbers")
    rows: list[int] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, int) or entry < 0:
            raise SpecRowsError(
                f"{path}: `spec_rows` entry {entry!r} is not a non-negative "
                "spec/target-spec.md row number"
            )
        rows.append(entry)
    note = str(decl.get("spec_rows_note", "") or "").strip()
    if not rows and not note:
        raise SpecRowsError(
            f'{path}: `"spec_rows": []` (this block measures no '
            "spec/target-spec.md row) needs a `spec_rows_note` saying why -- "
            "an explicit 'measures none' is a claim and must be argued, not "
            "left blank"
        )
    body = ", ".join(str(n) for n in rows) if rows else "none"
    return f"{body} -- {note}" if note else body
