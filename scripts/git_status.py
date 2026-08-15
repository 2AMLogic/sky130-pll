"""Shared `git status --porcelain` parsing for evidence-record renderers.

Used by both `sim/harness/report.py` (the simulation evidence trail) and
`layout/bin/render-record.py` (the layout DRC/LVS evidence trail) to answer
the same question for two independent record renderers: "was the tree dirty
when this run started, ignoring the run's own new output files?"

Lives at the repo root (not under `sim/` or `layout/`) because those two
trees are otherwise independent per this repo's harness-bootstrap provenance
convention (see CLAUDE.md) -- this is the one piece of logic both need.
"""

from __future__ import annotations


def porcelain_paths(status_text: str) -> list:
    """Repo-relative paths out of `git status --porcelain` (v1) output.

    Two status chars, a space, then the path -- or `old -> new` for a rename,
    whose *new* path is the one a caller wants, and quoted when the path
    contains characters git chooses to escape.
    """
    paths = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        paths.append(line[3:].split(" -> ")[-1].strip().strip('"'))
    return paths


def is_dirty(status_text: str, ignore_prefixes: str | tuple[str, ...] = ()) -> bool:
    """Was anything modified/untracked other than this run's own outputs?

    `ignore_prefixes` are repo-relative path prefixes excluded from the
    check -- specifically, the run's own output paths (a single prefix, or a
    tuple when a run writes to more than one output path). Without this,
    every record would be stamped "dirty" simply because the record (and
    whatever else the run itself just wrote) are new files, which would make
    the flag useless: a reader could not tell "the code that produced this
    evidence differed from the named commit" (which invalidates
    reproducibility) from "the evidence is new" (which is always true).

    `str.startswith` natively accepts either a single prefix or a tuple of
    prefixes, so `ignore_prefixes` is passed straight through.
    """
    return any(
        not path.startswith(ignore_prefixes) for path in porcelain_paths(status_text)
    )
