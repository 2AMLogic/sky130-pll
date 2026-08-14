"""Build the PVT (process / voltage / temperature) point matrix for a run.

A point is (process corner name, temperature in deg C, supply in V). The
default grid comes from the testbench manifest (tb.json); CLI flags can
narrow it (e.g. for a fast selftest pass) but never widen it beyond what the
manifest declares as valid for that DUT.
"""

from __future__ import annotations

from dataclasses import dataclass


class CornerError(ValueError):
    pass


@dataclass(frozen=True)
class PvtPoint:
    corner: str
    temp_c: float
    supply_v: float

    @property
    def corner_id(self) -> str:
        """Filename-safe id: `<corner>_<temp>c_<supply>v`, matching the
        sim/README.md naming convention (supply to two decimals)."""
        temp_txt = f"{self.temp_c:g}"
        return f"{self.corner}_{temp_txt}c_{self.supply_v:.2f}v"


def supply_points(nominal: float, tolerance: float) -> list:
    if tolerance <= 0:
        return [round(nominal, 6)]
    lo = round(nominal * (1 - tolerance), 6)
    hi = round(nominal * (1 + tolerance), 6)
    # De-duplicate in case tolerance rounds to the same value at this scale.
    points = sorted({lo, round(nominal, 6), hi})
    return points


def build_matrix(
    manifest: dict,
    valid_process_corners: tuple,
    corners_override: list | None = None,
    temps_override: list | None = None,
    supply_tol_override: float | None = None,
) -> list:
    corners = corners_override or manifest["process_corners"]
    for c in corners:
        # Always checked against sim/pdk.json (the corners the installed PDK
        # actually defines .lib sections for) -- an override may pick any of
        # those, not just the ones this manifest lists as its own default
        # grid, since the harness applies corner substitution generically
        # (see runner.patch_netlist) rather than per-manifest.
        if c not in valid_process_corners:
            raise CornerError(
                f"corner {c!r} is not in sim/pdk.json's process_corners {valid_process_corners}"
            )

    temps = temps_override if temps_override is not None else manifest["temps_c"]

    tol = manifest["supply_tolerance"] if supply_tol_override is None else supply_tol_override
    supplies = supply_points(manifest["supply_nominal"], tol)

    points = []
    for corner in corners:
        for temp in temps:
            for supply in supplies:
                points.append(PvtPoint(corner=corner, temp_c=float(temp), supply_v=float(supply)))
    return points
