"""LOCK-detector timing measurement contract: manifest validation, waveform
reduction and band grading (issue #273, part of #259).

PDK-free and simulator-free. Everything here is arithmetic over a declared
manifest and over normalized waveforms handed in by a caller; the execution
half (netlisting, running, writing records) belongs to a later child. Schema
and fixtures are documented in `sim/lockdet-timing/README.md`.

Design rules the results repeat verbatim:

* Malformed input is rejected (`LockTimingError`), never coerced.
* A point is either a valid measurement or carries a status saying why not
  (`ABSENT_CROSSING`, `INSUFFICIENT_SETTLING`, `SIM_FAILED`, `MALFORMED`).
* All 45 grid coordinates are accounted for per candidate; missing, duplicate,
  unexpected and failed points keep the report incomplete and are listed.
* A measured band miss (`MISS`) is distinct from missing evidence
  (`INCONCLUSIVE`). Thresholds are DR-007 Table 2 constants, never relaxed.
"""

from __future__ import annotations

import math
from itertools import product as _product

MANIFEST_SCHEMA = "sky130-pll.lockdet-timing.manifest/1"
RESULT_SCHEMA = "sky130-pll.lockdet-timing.result/1"

PROCESSES = ("tt", "ff", "ss", "fs", "sf")
TEMPS_C = (-40.0, 27.0, 125.0)
VDDS_V = (1.62, 1.8, 1.98)
GRID = tuple(_product(PROCESSES, TEMPS_C, VDDS_V))  # 45 coordinates
REQUIRED_PRODUCT_COUNT = 3

# Inclusive bands in seconds (DR-007 Table 2, proposed) and the strict limits.
BANDS_S = {
    "w_acq": (1.5e-9, 4.0e-9),
    "w_rel": (4.5e-9, 10.0e-9),
    "tick": (125e-9, 500e-9),
}
W_REL_CEILING_S = 12e-9

# Point statuses.
OK = "OK"
ABSENT_CROSSING = "ABSENT_CROSSING"
INSUFFICIENT_SETTLING = "INSUFFICIENT_SETTLING"
SIM_FAILED = "SIM_FAILED"
MALFORMED = "MALFORMED"

# Verdicts.
PASS = "PASS"
MISS = "MISS"
INCONCLUSIVE = "INCONCLUSIVE"

EDGES = ("rising", "falling")
_UNITS = {"time": "s", "voltage": "V", "temperature": "C", "capacitance": "F"}
_INVENTORY_KEYS = ("cells", "taps", "dividers")
_WINDOW_KEYS = ("enable_s", "settle_s", "window_start_s", "window_stop_s",
                "step_s", "timeout_s")


class LockTimingError(ValueError):
    """Malformed manifest, waveform or request."""


class _Absent(Exception):
    pass


class _Unsettled(Exception):
    pass


def _num(x, what):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise LockTimingError(f"{what} must be a finite number, got {x!r}")
    return float(x)


def _name(x, what):
    if not isinstance(x, str) or not x:
        raise LockTimingError(f"{what} must be a non-empty string")
    return x


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #


def _check_probe(p, what, keys):
    if not isinstance(p, dict):
        raise LockTimingError(f"{what} must be an object")
    for k in keys:
        if k not in p:
            raise LockTimingError(f"{what} missing {k!r}")
    _num(p["threshold_v"], f"{what}.threshold_v")
    for k in p:
        if k.endswith("edge") and p[k] not in EDGES:
            raise LockTimingError(f"{what}.{k} must be one of {EDGES}")


def validate_manifest(m):
    """Return `m` if it satisfies the versioned handoff, else raise."""
    if not isinstance(m, dict) or m.get("schema") != MANIFEST_SCHEMA:
        raise LockTimingError(f"schema must be {MANIFEST_SCHEMA!r}")
    _name(m.get("product_id"), "product_id")
    _name(m.get("candidate_id"), "candidate_id")
    if m.get("units") != _UNITS:
        raise LockTimingError(f"units must be exactly {_UNITS}")
    inv = m.get("inventory")
    if not isinstance(inv, dict):
        raise LockTimingError("inventory must be an object")
    for k in _INVENTORY_KEYS:
        items = inv.get(k)
        if not isinstance(items, list) or not items:
            raise LockTimingError(f"inventory.{k} must be a non-empty list")
    for c in inv["cells"]:
        if not isinstance(c, dict) or not all(
                isinstance(c.get(k), str) and c.get(k) for k in ("name", "drive", "stage")):
            raise LockTimingError("each inventory cell needs name, drive and stage")
    names = [t if isinstance(t, str) else None for t in inv["taps"]]
    if None in names or len(set(names)) != len(names):
        raise LockTimingError("inventory.taps must be unique strings")
    meas = m.get("measurement")
    if not isinstance(meas, dict):
        raise LockTimingError("measurement must be an object")
    if _num(meas.get("load_f"), "measurement.load_f") < 0 or \
            _num(meas.get("slew_s"), "measurement.slew_s") <= 0:
        raise LockTimingError("load_f must be >= 0 and slew_s > 0")
    for k in ("acq", "rel"):
        _check_probe(meas.get(k), f"measurement.{k}",
                     ("input", "tap", "threshold_v", "input_edge", "tap_edge"))
    for k in ("tick", "raw", "startup"):
        _check_probe(meas.get(k), f"measurement.{k}", ("signal", "threshold_v", "edge"))
    w = m.get("windows")
    if not isinstance(w, dict):
        raise LockTimingError("windows must be an object")
    wv = {k: _num(w.get(k), f"windows.{k}") for k in _WINDOW_KEYS}
    if min(wv["enable_s"], wv["settle_s"]) < 0 or wv["step_s"] <= 0 or wv["timeout_s"] <= 0:
        raise LockTimingError("windows: enable/settle >= 0, step and timeout > 0")
    if not wv["window_start_s"] < wv["window_stop_s"]:
        raise LockTimingError("windows: window_start_s must precede window_stop_s")
    if wv["window_start_s"] < wv["enable_s"] + wv["settle_s"]:
        raise LockTimingError("windows: window_start_s must be >= enable_s + settle_s")
    exp = m.get("grid")
    if not isinstance(exp, list):
        raise LockTimingError("grid must be a list of coordinates")
    got = [coord_key(c) for c in exp]
    if sorted(got) != sorted(GRID) or len(set(got)) != len(got):
        raise LockTimingError("grid must be exactly the 45 fixed coordinates")
    return m


def coord_key(c):
    """Canonical (process, temp_c, vdd_v) tuple from a coordinate object."""
    if not isinstance(c, dict):
        raise LockTimingError("coordinate must be an object")
    p = c.get("process")
    t, v = _num(c.get("temp_c"), "temp_c"), _num(c.get("vdd_v"), "vdd_v")
    return (p, t, round(v, 6))


# --------------------------------------------------------------------------- #
# waveform reduction
# --------------------------------------------------------------------------- #


def validate_waveform(w, what="waveform"):
    if not isinstance(w, dict) or not isinstance(w.get("t"), list) \
            or not isinstance(w.get("v"), list):
        raise LockTimingError(f"{what} needs lists 't' and 'v'")
    t = [_num(x, f"{what}.t") for x in w["t"]]
    v = [_num(x, f"{what}.v") for x in w["v"]]
    if len(t) != len(v) or len(t) < 2:
        raise LockTimingError(f"{what}: t and v must match and hold >= 2 samples")
    if any(b <= a for a, b in zip(t, t[1:])):
        raise LockTimingError(f"{what}: timestamps must be strictly increasing")
    return t, v


def crossings(t, v, threshold, edge, t_from=-math.inf, t_to=math.inf):
    """Linearly interpolated crossing times in [t_from, t_to].

    Rising: v[i-1] < thr <= v[i]; falling: v[i-1] > thr >= v[i]. A sample
    exactly on the threshold is a crossing at that sample, counted once.
    """
    if edge not in EDGES:
        raise LockTimingError(f"edge must be one of {EDGES}")
    out = []
    for i in range(1, len(t)):
        a, b = v[i - 1], v[i]
        hit = (a < threshold <= b) if edge == "rising" else (a > threshold >= b)
        if hit:
            tc = t[i] if b == threshold else t[i - 1] + (threshold - a) * (t[i] - t[i - 1]) / (b - a)
            if t_from <= tc <= t_to:
                out.append(tc)
    return out


def _wave(waves, name):
    if name not in waves:
        raise LockTimingError(f"missing waveform {name!r}")
    return validate_waveform(waves[name], name)


def _check_span(t, w):
    if t[0] > w["window_start_s"] or t[-1] < w["window_stop_s"]:
        raise _Unsettled()
    if w["window_start_s"] < w["enable_s"] + w["settle_s"]:
        raise _Unsettled()


def delay(waves, probe, win):
    """First input crossing in the window to the first following tap crossing."""
    ti, vi = _wave(waves, probe["input"])
    tt, vt = _wave(waves, probe["tap"])
    _check_span(ti, win)
    _check_span(tt, win)
    a = crossings(ti, vi, probe["threshold_v"], probe["input_edge"],
                  win["window_start_s"], win["window_stop_s"])
    if not a:
        raise _Absent()
    b = crossings(tt, vt, probe["threshold_v"], probe["tap_edge"], a[0], win["window_stop_s"])
    if not b:
        raise _Absent()
    return b[0] - a[0]


def period(waves, probe, win):
    """Mean period from same-edge crossings in the window (>= 2 needed)."""
    t, v = _wave(waves, probe["signal"])
    _check_span(t, win)
    c = crossings(t, v, probe["threshold_v"], probe["edge"],
                  win["window_start_s"], win["window_stop_s"])
    if len(c) < 2:
        raise _Absent()
    return (c[-1] - c[0]) / (len(c) - 1)


def startup_latency(waves, probe, win):
    """First crossing after enable_s, measured from enable_s."""
    t, v = _wave(waves, probe["signal"])
    if t[-1] < win["window_stop_s"]:
        raise _Unsettled()
    c = crossings(t, v, probe["threshold_v"], probe["edge"], win["enable_s"], win["window_stop_s"])
    if not c:
        raise _Absent()
    return c[0] - win["enable_s"]


def reduce_point(manifest, point):
    """Reduce one coordinate's raw record to a result row (never raises on bad data).

    `point` = {"coord": {...}, "sim_ok": bool, "waveforms": {name: {"t","v"}}}.
    """
    row = {"coord": point.get("coord"), "status": OK, "error": None,
           "w_acq_s": None, "w_rel_s": None, "tick_s": None,
           "raw_period_s": None, "startup_latency_s": None}
    try:
        coord_key(point.get("coord"))
        if point.get("sim_ok") is not True:
            row["status"] = SIM_FAILED
            return row
        me, win, waves = manifest["measurement"], manifest["windows"], point.get("waveforms") or {}
        row["w_acq_s"] = delay(waves, me["acq"], win)
        row["w_rel_s"] = delay(waves, me["rel"], win)
        row["tick_s"] = period(waves, me["tick"], win)
        row["raw_period_s"] = period(waves, me["raw"], win)
        row["startup_latency_s"] = startup_latency(waves, me["startup"], win)
    except _Absent:
        row["status"] = ABSENT_CROSSING
    except _Unsettled:
        row["status"] = INSUFFICIENT_SETTLING
    except LockTimingError as e:
        row["status"], row["error"] = MALFORMED, str(e)
    if row["status"] != OK:
        for k in ("w_acq_s", "w_rel_s", "tick_s", "raw_period_s", "startup_latency_s"):
            row[k] = None  # a partial measurement is not a valid one
    return row


# --------------------------------------------------------------------------- #
# grid accounting and grading
# --------------------------------------------------------------------------- #


def _band(values, lo, hi, complete):
    if any(not lo <= x <= hi for x in values):
        return MISS
    return PASS if complete and values else INCONCLUSIVE


def grade_candidate(manifest, rows):
    """Account for every grid coordinate and grade the envelopes.

    Returns a result dict. `complete` is true only if each of the 45
    coordinates appears exactly once with status OK. Duplicates are excluded
    from the aggregates and listed.
    """
    validate_manifest(manifest)
    seen, dup, unexpected = {}, [], []
    for r in rows:
        try:
            k = coord_key(r.get("coord"))
        except LockTimingError:
            unexpected.append(r.get("coord"))
            continue
        if k not in GRID:
            unexpected.append(r["coord"])
        elif k in seen:
            dup.append(k)
        else:
            seen[k] = r
    dup_set = set(dup)
    missing = [k for k in GRID if k not in seen]
    failed = {k: r["status"] for k, r in seen.items() if r["status"] != OK}
    good = {k: r for k, r in seen.items() if r["status"] == OK and k not in dup_set}
    complete = not (missing or dup or unexpected or failed)

    def vals(name):
        return [r[name] for r in good.values()]

    out = {
        "schema": RESULT_SCHEMA,
        "product_id": manifest["product_id"],
        "candidate_id": manifest["candidate_id"],
        "complete": complete,
        "missing": missing, "duplicates": sorted(dup_set), "unexpected": unexpected,
        "failed": failed,
        "diagnostic_raw_period_s": (min(vals("raw_period_s")), max(vals("raw_period_s")))
        if good else None,
        "startup_latency_s": (min(vals("startup_latency_s")), max(vals("startup_latency_s")))
        if good else None,
    }
    bands = {n: _band(vals(f"{n}_s"), *BANDS_S[n], complete) for n in BANDS_S}
    acq, rel = vals("w_acq_s"), vals("w_rel_s")
    if acq and rel:
        hyst = MISS if not max(acq) < min(rel) else (PASS if complete else INCONCLUSIVE)
        ceil = MISS if not max(rel) < W_REL_CEILING_S else (PASS if complete else INCONCLUSIVE)
    else:
        hyst = ceil = INCONCLUSIVE
    bands["hysteresis_max_acq_lt_min_rel"] = hyst
    bands["rel_ceiling_lt_12ns"] = ceil
    out["verdicts"] = bands
    vs = list(bands.values())
    out["verdict"] = MISS if MISS in vs else (PASS if complete and all(v == PASS for v in vs)
                                              else INCONCLUSIVE)
    return out


def handoff(results, required_products):
    """Combine candidate results; ready only for a complete, passing full set.

    `required_products` must name exactly three distinct products. Subset
    reports carry `scope` = "SUBSET" and `handoff_ready` False.
    """
    req = list(required_products)
    if len(req) != REQUIRED_PRODUCT_COUNT or len(set(req)) != len(req):
        raise LockTimingError(f"required_products must be {REQUIRED_PRODUCT_COUNT} distinct ids")
    by = {}
    for r in results:
        by.setdefault(r["product_id"], []).append(r)
    present = sorted(set(by) & set(req))
    absent = [p for p in req if p not in by]
    scope = "FULL" if not absent else "SUBSET"
    ok = scope == "FULL" and all(
        len(by[p]) == 1 and by[p][0]["verdict"] == PASS for p in req)
    return {"scope": scope, "products_present": present, "products_absent": absent,
            "handoff_ready": ok}
