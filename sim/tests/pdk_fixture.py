"""The shared `ResolvedPdk` test fixture for sim/tests (issue #454).

Every test that needs a resolved PDK builds the real frozen dataclass from
`sim/harness/pdk.py` -- no duck-typed stand-ins -- so a field rename or
removal there fails here with a `TypeError` instead of silently leaving the
tests green. Field overrides are the `dataclasses.replace` mechanism: pass
keyword overrides to specialise a field, never subclass or re-stub.
`as_env()` is the real one, so `PDK_ROOT`/`PDK` reach any child environment
exactly as production would.
"""

from __future__ import annotations

import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness.pdk import ResolvedPdk  # noqa: E402


def make_resolved_pdk(**overrides) -> ResolvedPdk:
    """A well-formed fake `ResolvedPdk`; pass field overrides to vary it."""
    fields = dict(
        pdk_root=Path("/fake/pdk-root"),
        variant="sky130A",
        variant_dir=Path("/fake/pdk-root/sky130A"),
        ngspice_lib=Path("/fake/pdk-root/sky130A/libs.tech/combined/sky130.lib.spice"),
        process_corners=("tt", "ss", "ff"),
        pinned_commit="0" * 40,
        resolved_commit="0" * 40,
        commit_mismatch=False,
    )
    fields.update(overrides)
    return ResolvedPdk(**fields)
