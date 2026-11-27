"""Read the variable names and sample rows from a klt waveform artifact."""

from __future__ import annotations

import json
from pathlib import Path


def read_klt_waveform(path: str | Path) -> tuple[list[str], list[list]]:
    """Return names in file order and rows with one column per variable."""
    wave = json.loads(Path(path).read_text())
    names = [var["name"] for var in wave["variables"]]
    points = wave["points"]
    width = len(names)
    for row, point in enumerate(points, start=1):
        actual = len(point) if isinstance(point, list) else "a non-array sample"
        if actual != width:
            raise ValueError(
                f"{path}: row {row}: expected {width} columns, got {actual}"
            )
    return names, points
