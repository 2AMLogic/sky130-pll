#!/usr/bin/env python3
"""Generate the sky130-pll supply-current / power campaign inputs (issue #233).

For each block (`vco`, `divider-n4`, `divider-n64`, `pfd-cp`) this writes, under
`sim/power/testbench/`:

    tb_power_<block>.sch       xschem testbench (DUT + V1 + stimulus sources)
    <block>.body.spice         the xschem netlist, reduced to a `klt sim` circuit
                               body (no .lib / .end / .control cards)
    <block>.stages.json        the staged-stimulus table the reducer reads
    <block>.request.json       the `klt sim` request (45-point PVT grid, waveform
                               artifact on, only v(align) and i(V1) saved)

The stage tables below are the single source of truth for the stimulus: the
schematic's PWL / pulse cards, the request's transient length and the reducer's
measurement windows are all emitted from them, so they cannot drift apart.

    python3 sim/power/build.py            # regenerate everything
    python3 sim/power/build.py --check    # exit 1 if a committed file is stale

Needs xschem + the sky130 PDK (netlisting only; no simulation happens here).

Provenance: the testbench/netlisting pattern (one `V1` supply source, label-pin
wiring, xschem -x -n -s -q --rcfile sim/xschemrc) is adapted from
sim/vco-supply-pushing/testbench/tb_vco_pushing.sch and
sim/harness/runner.py::netlist_schematic (this repo). The staged-stimulus idea
(one transient per PVT point, several held operating points) mirrors
sim/harness/measure.py's swept-source campaigns, but holds the points in time
inside one transient because `klt sim` runs one analysis per corner.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TB_DIR = Path(__file__).resolve().parent / "testbench"

PROCESS_CORNERS = ["tt", "ff", "ss", "sf", "fs"]
TEMPS_C = [-40, 27, 125]
SUPPLIES_V = [1.62, 1.80, 1.98]  # row 1: 1.8 V +/- 10 %

STDCELLS_INCLUDE = (
    ".include $PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"
)


def ns(x: float) -> float:
    return x * 1e-9


# --------------------------------------------------------------------------- #
# per-block definitions
# --------------------------------------------------------------------------- #


def _fmt_t(t_s: float) -> str:
    return f"{t_s * 1e9:.4f}".rstrip("0").rstrip(".") + "n"


def vco_block() -> dict:
    """VCTRL ladder. Stage 0 holds VCTRL at 0 V (starving branch off: the ring
    is quiescent -> static / leakage reference); later stages hold VCTRL at
    increasing values spanning the free-running range sim/vco characterizes
    plus a lower tail that brackets 100 MHz at every corner."""
    ladder = [0.70, 0.725, 0.75, 0.775, 0.80, 0.825, 0.85, 0.875, 0.90, 0.95, 1.00, 1.20, 1.60]
    idle_len, seg, settle, cycles = 100.0, 250.0, 100.0, 3
    stages = [
        {"id": "idle", "kind": "idle", "label": "VCTRL=0.00V (idle)", "vctrl": 0.0,
         "t0": ns(0), "t1": ns(idle_len), "settle": ns(60)}
    ]
    t = idle_len
    pwl = [(0.0, 0.0)]
    prev = 0.0
    for v in ladder:
        pwl.append((t, prev))
        pwl.append((t + 2.0, v))
        stages.append({
            "id": f"v{int(round(v * 1000)):04d}", "kind": "active",
            "label": f"VCTRL={v:.3f}V", "vctrl": v,
            "t0": ns(t), "t1": ns(t + seg), "settle": ns(settle), "cycles": cycles,
        })
        prev = v
        t += seg
    pwl_text = "pwl(" + " ".join(f"{_fmt_t(ns(a))} {b}" for a, b in pwl) + ")"
    code = ".ic v(xxxvco.ring0)=0\n"
    return {
        "sources": [("v", "V2", "VCTRL", pwl_text)],
        "name": "vco",
        "dut": "design/vco/vco_ring5.sym",
        "dut_name": "XXVCO",
        "pins": {"VDD": "VDD", "GND": "GND", "VCTRL": "VCTRL", "CLK": "CLK"},
        "code": code, "stdcells": False,
        "align_node": "v(clk)", "save": ["v(clk)", "i(v1)", "v(vctrl)"],
        "tran_step": "50p", "tran_stop": f"{_fmt_t(ns(t))}", "uic": True,
        "stages": stages,
        "title": "sky130 vco_ring5 supply-current campaign",
        "timeout_s": 3600,
        "note": (
            "design/vco/vco_ring5.sch driven open-loop by a staged VCTRL ladder; "
            "i(V1) is the VCO's own VDD current (VCTRL source, .ic card and the "
            "absent CLK load draw nothing from V1)"
        ),
    }


def divider_block(n: int) -> dict:
    """Divider driven at 100 MHz then 250 MHz output-reference frequencies.

    Stage 0 is idle: RESETB released, input clock gated off (state frozen).
    Each active stage runs 2 whole divider output periods and the reducer
    averages over the 2nd (the 1st is warm-up): a whole number of the
    divider's own N-cycle period, so the counter pattern averages exactly.
    """
    assert n in (4, 64)
    nsel = n - 1
    pins = {"NSEL%d" % i: ("VDD" if (nsel >> i) & 1 else "GND") for i in range(6)}
    # Stage boundaries sit at 7 ns mod 20 ns, where both input clocks are low.
    idle_len = 107.0
    stages = [{"id": "idle", "kind": "idle", "label": "clock gated off (idle)",
               "f_in_hz": 0.0, "t0": ns(0), "t1": ns(idle_len), "settle": ns(60)}]
    t = idle_len
    gates = []  # (name, rate_hz, t_on, t_off)
    for rate_hz, tag in ((100e6, "100m"), (250e6, "250m")):
        period = 1e9 / rate_hz
        # one warm-up divider period, the first FBCLK edge (anywhere inside the
        # next period), then one whole measured period: 3 periods, 20 ns grid
        length = 3.0 * n * period
        length = 20.0 * int(-(-length // 20.0))
        stages.append({
            "id": f"f{tag}", "kind": "active",
            "label": f"{rate_hz / 1e6:g} MHz input, N={n}",
            "f_in_hz": rate_hz, "t0": ns(t), "t1": ns(t + length),
            "settle": ns(n * period), "cycles": 1, "div_n": n,
        })
        gates.append((tag, rate_hz, t, t + length))
        t += length
    sources = [
        # unit-amplitude (0..1) clocks; the DUT-facing nets are scaled by v(VDD)
        # so the input swing tracks the supply corner (rail-to-rail drive).
        ("v", "VCK100", "CK100", "pulse(0 1 0 100p 100p 4.9n 10n)"),
        ("v", "VCK250", "CK250", "pulse(0 1 0 100p 100p 1.9n 4n)"),
    ]
    for tag, _rate, ton, toff in gates:
        sources.append((
            "v", f"VEN{tag}", f"EN{tag}",
            f"pwl(0 0 {_fmt_t(ns(ton))} 0 {_fmt_t(ns(ton) + 0.1e-9)} 1 "
            f"{_fmt_t(ns(toff))} 1 {_fmt_t(ns(toff) + 0.1e-9)} 0)",
        ))
    sources.append(("b", "BCLK", "CLK",
                    "v(VDD)*(v(CK100)*v(EN100m)+v(CK250)*v(EN250m))"))
    # RESETB: low at power-up, released inside the idle stage (clock gated off).
    sources.append(("v", "VRST", "RSTU", "pwl(0 0 5n 0 5.1n 1)"))
    sources.append(("b", "BRST", "RESETB", "v(VDD)*v(RSTU)"))
    return {
        "sources": sources,
        "name": f"divider-n{n}",
        "dut": "design/divider/divider_intN.sym",
        "dut_name": "XXDIV",
        "pins": {"VDD": "VDD", "GND": "GND", "CLK": "CLK", "RESETB": "RESETB",
                 "FBCLK": "FBCLK", **pins},
        "code": "", "stdcells": True,
        "align_node": "v(fbclk)", "save": ["v(fbclk)", "i(v1)", "v(clk)"],
        "tran_step": "40p" if n == 64 else "20p", "tran_stop": f"{_fmt_t(ns(t))}",
        "uic": False,
        "stages": stages,
        "title": f"sky130 divider_intN supply-current campaign, N={n}",
        "timeout_s": 7200,
        "note": (
            f"design/divider/divider_intN.sch configured N={n} (NSEL={nsel}); "
            "the input clock is an ideal rail-to-rail source gated per stage; "
            "FBCLK is unloaded"
        ),
    }


def pfd_block() -> dict:
    """PFD + charge pump at the reference-range extremes (row 3: 1 and 25 MHz).

    Stages: idle (REF and DIV held low), then for each reference frequency a
    'lock-like' stage (DIV lags REF by 100 ps -> minimal UP/DN overlap pulses)
    and an 'acquisition' stage (DIV lags REF by a quarter period -> a long
    UP pulse every cycle, the high-activity bound).
    """
    stages = [{"id": "idle", "kind": "idle", "label": "REF and DIV held low (idle)",
               "f_ref_hz": 0.0, "t0": ns(0), "t1": ns(112.0), "settle": ns(60)}]
    # Stage boundaries sit at 32 ns mod 40 ns (and 872 ns mod 1000 ns): REF and
    # every DIV train are low there, so gating never truncates a pulse.
    t = 112.0
    specs = []  # (tag, f_hz, lag_ns, length_ns, settle_periods, cycles)
    plan = [
        ("25m_lock", 25e6, 0.1, 10, 12),
        ("25m_acq", 25e6, 10.0, 10, 12),
        ("1m_lock", 1e6, 0.1, 2, 3),
        ("1m_acq", 1e6, 250.0, 2, 3),
    ]
    ref_terms = {25e6: [], 1e6: []}
    div_terms = []
    sources = [
        # unit-amplitude (0..1) trains, gated per stage and scaled by v(VDD)
        ("v", "VR25", "R25", "pulse(0 1 0 100p 100p 19.9n 40n)"),
        ("v", "VR1", "R1", "pulse(0 1 0 100p 100p 499.9n 1000n)"),
    ]
    for tag, f_hz, lag, settle_p, meas_p in plan:
        period_ns = 1e9 / f_hz
        # settle, the first aligned edge (anywhere in the next period), then the
        # measured cycles
        length = (settle_p + meas_p + 1) * period_ns
        stages.append({
            "id": tag, "kind": "active",
            "label": f"{f_hz / 1e6:g} MHz ref, DIV lag {lag:g} ns",
            "f_ref_hz": f_hz, "lag_s": ns(lag), "t0": ns(t), "t1": ns(t + length),
            "settle": ns(settle_p * period_ns), "cycles": meas_p,
        })
        ton, toff = t, t + length
        width = period_ns / 2 - 0.1
        sources.append((
            "v", f"VD{tag}", f"D{tag}",
            f"pulse(0 1 {lag:g}n 100p 100p {width:g}n {period_ns:g}n)",
        ))
        sources.append((
            "v", f"VEN{tag}", f"EN{tag}",
            f"pwl(0 0 {_fmt_t(ns(ton))} 0 {_fmt_t(ns(ton) + 0.1e-9)} 1 "
            f"{_fmt_t(ns(toff))} 1 {_fmt_t(ns(toff) + 0.1e-9)} 0)",
        ))
        ref_terms[f_hz].append(f"v(EN{tag})")
        div_terms.append(f"v(D{tag})*v(EN{tag})")
        t += length
    sources.append((
        "b", "BREF", "REF",
        "v(VDD)*(v(R25)*(" + "+".join(ref_terms[25e6]) + ")+v(R1)*("
        + "+".join(ref_terms[1e6]) + "))",
    ))
    sources.append(("b", "BDIV", "DIV", "v(VDD)*(" + "+".join(div_terms) + ")"))
    # CP held at 0.9 V (the closed-loop VCTRL operating point) by an ideal source
    sources.append(("v", "VCP", "CP", "0.9"))
    return {
        "sources": sources,
        "name": "pfd-cp",
        "dut": "design/pfd-cp/pfd_cp.sym",
        "dut_name": "XXPFD",
        "pins": {"VDD": "VDD", "GND": "GND", "REF": "REF", "DIV": "DIV", "CP": "CP"},
        "code": "", "stdcells": False,
        "align_node": "v(ref)", "save": ["v(ref)", "i(v1)", "v(div)", "i(vcp)"],
        "tran_step": "100p", "tran_stop": f"{_fmt_t(ns(t))}", "uic": False,
        "stages": stages,
        "title": "sky130 pfd_cp supply-current campaign",
        "timeout_s": 7200,
        "note": (
            "design/pfd-cp/pfd_cp.sch with ideal REF/DIV trains and CP held at "
            "0.9 V by an ideal source (VCP): the charge-pump output current is "
            "drawn from V1 on UP and returned to GND on DN, so i(V1) includes "
            "the pump's delivered current; the loop filter is not present"
        ),
    }


BLOCKS = {
    "vco": vco_block,
    "divider-n4": lambda: divider_block(4),
    "divider-n64": lambda: divider_block(64),
    "pfd-cp": pfd_block,
}


# --------------------------------------------------------------------------- #
# schematic / netlist / request emission
# --------------------------------------------------------------------------- #

_HDR = """v {xschem version=3.4.7 file_version=1.2
* tb_power_%(slug)s.sch -- %(title)s (issue #233)
* GENERATED by sim/power/build.py from its stage table; do not hand-edit.
*
* %(note)s.
*
* V1 is the ONLY supply source on the DUT's VDD net, so i(V1) is the block's
* own supply current. The stimulus (staged sources, idle stage first) is the
* drawn stimulus sources; sim/power/testbench/%(block)s.stages.json is the
* machine-readable stage table the reducer uses.
*
* Provenance: adapted from sim/vco-supply-pushing/testbench/tb_vco_pushing.sch
* (this repo, issue #165): same label-pin wiring, V1 supply, DUT instance style.
}
G {}
V {}
S {}
E {}
"""


def schematic_text(b: dict) -> str:
    out = [_HDR % {"slug": b["name"].replace("-", "_"), "title": b["title"],
                   "note": b["note"], "block": b["name"]}]
    out.append(f"C {{{b['dut']}}} 0 0 0 0 {{name={b['dut_name']}}}")
    # Pin labels on the symbol, placed by sym pin geometry (labels are by name,
    # xschem connects same-named lab_pins, so coordinates only need to touch the
    # symbol's pins: we reuse the geometry of the sibling testbenches).
    geom = {
        "vco": [("VDD", 0, -80), ("GND", 0, 80), ("VCTRL", -130, 0), ("CLK", 130, 0)],
        "divider": [("VDD", 0, -180), ("GND", 0, 180), ("CLK", -130, -140),
                    ("RESETB", -130, -100), ("NSEL0", -130, -60), ("NSEL1", -130, -20),
                    ("NSEL2", -130, 20), ("NSEL3", -130, 60), ("NSEL4", -130, 100),
                    ("NSEL5", -130, 140), ("FBCLK", 130, 0)],
        "pfd": [("VDD", 0, -120), ("GND", 0, 120), ("REF", -130, -40),
                ("DIV", -130, 40), ("CP", 130, 0)],
    }
    key = "vco" if b["name"] == "vco" else ("pfd" if b["name"] == "pfd-cp" else "divider")
    for i, (pin, x, y) in enumerate(geom[key], start=1):
        net = b["pins"][pin]
        out.append(
            f"C {{devices/lab_pin.sym}} {x} {y} 0 0 {{name=p{i} sig_type=std_logic lab={net}}}"
        )
    out.append("C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}")
    out.append("C {devices/lab_pin.sym} 600 -30 0 0 {name=pv1 sig_type=std_logic lab=VDD}")
    out.append("C {devices/gnd.sym} 600 30 0 0 {name=lg1 lab=GND}")
    for i, (kind, name, net, value) in enumerate(b["sources"], start=1):
        x = 600 + 200 * i
        if kind == "v":
            out.append(
                f"C {{devices/vsource.sym}} {x} 0 0 0 {{name={name} value=\"{value}\" savecurrent=false}}"
            )
        else:
            out.append(
                f"C {{devices/bsource.sym}} {x} 0 0 0 {{name={name} VAR=V FUNC=\"{value}\" m=1}}"
            )
        out.append(f"C {{devices/lab_pin.sym}} {x} -30 0 0 {{name=ps{i} sig_type=std_logic lab={net}}}")
        out.append(f"C {{devices/gnd.sym}} {x} 30 0 0 {{name=lgs{i} lab=GND}}")
    code = b["code"]
    if b["stdcells"]:
        code = ("** std-cell subckt library for the divider's gates (resolved on the executing host)\n"
                + STDCELLS_INCLUDE + "\n" + code)
    if code:
        out.append(
            "C {devices/code.sym} 1300 300 0 0 {name=EXTRA\nonly_toplevel=true\nvalue=\"\n"
            + code + "\"\nspice_ignore=false}"
        )
    out.append(
        f"C {{devices/title.sym}} -200 500 0 0 {{name=lt author=\"2AM Logic (issue #233, {b['title']})\"}}"
    )
    return "\n".join(out) + "\n"


def netlist_with_xschem(sch: Path) -> str:
    env = dict(os.environ)
    sys.path.insert(0, str(REPO_ROOT / "sim"))
    from harness import pdk as pdk_mod  # noqa: PLC0415

    resolved = pdk_mod.resolve(REPO_ROOT)
    env.update(resolved.as_env())
    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.run(
            ["xschem", "-x", "-n", "-s", "-q", "--rcfile",
             str(REPO_ROOT / "sim" / "xschemrc"), "-o", td, str(sch)],
            capture_output=True, text=True, cwd=REPO_ROOT, env=env, timeout=120,
        )
        out = Path(td) / f"{sch.stem}.spice"
        if proc.returncode != 0 or not out.is_file():
            raise SystemExit(f"xschem netlisting failed:\n{proc.stdout}\n{proc.stderr}")
        return out.read_text()


_PATH_COMMENT = re.compile(r"^\*\* (sch_path|sym_path):.*$", re.MULTILINE)


def to_body(text: str) -> str:
    """Reduce an xschem top-level netlist to a `klt sim` circuit body."""
    text = _PATH_COMMENT.sub(lambda m: f"** {m.group(1)}: (machine-local path elided)", text)
    out = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low == ".end":
            continue
        if low.startswith(".lib ") or low.startswith(".control") or low.startswith(".endc"):
            raise SystemExit(f"unexpected card in testbench netlist: {line!r}")
        out.append(line)
    body = "\n".join(out) + "\n"
    # Machine-local PDK roots -> the portable form the executing host resolves.
    body = re.sub(r"/[^\s]*/sky130A/libs\.ref", "$PDK_ROOT/sky130A/libs.ref", body)
    return body


def request_for(b: dict, body_name: str) -> dict:
    stop_s = max(s["t1"] for s in b["stages"])
    measurements = []
    for s in b["stages"]:
        # Fixed-window mean of i(V1) over the last half of each stage: a coarse
        # in-simulator cross-check that does not depend on the waveform reducer
        # (not cycle-aligned; see sim/power/README.md).
        t_from = (s["t0"] + s["t1"]) / 2
        measurements.append({
            "name": f"i_xchk_{s['id']}",
            "spice": f".meas tran i_xchk_{s['id']} AVG i(v1) FROM={_fmt_t(t_from)} TO={_fmt_t(s['t1'])}",
            "unit": "A",
        })
    return {
        "netlist": body_name,
        "engine": "ngspice",
        "models": {"pdk": "sky130A", "lib": "libs.tech/ngspice/sky130.lib.spice"},
        "corners": {
            "process": PROCESS_CORNERS,
            "supply_v": {"v1": SUPPLIES_V},
            "temperature_c": TEMPS_C,
        },
        "analysis": {
            "kind": "tran",
            "args": f"{b['tran_step']} {b['tran_stop']}" + (" uic" if b["uic"] else ""),
        },
        "measurements": measurements,
        "options": {
            "timeout_s": b["timeout_s"],
            "keep_artifacts": True,
            "waveforms": True,
            "save_mode": "netlist",
        },
        "backend": "batch",
    }


def build_block(b: dict) -> dict:
    """Return {filename: text} for one block."""
    slug = b["name"].replace("-", "_")
    sch_name = f"tb_power_{slug}.sch"
    sch_text = schematic_text(b)
    with tempfile.TemporaryDirectory() as td:
        sch_path = Path(td) / sch_name
        sch_path.write_text(sch_text)
        body = to_body(netlist_with_xschem(sch_path))
    body += "\n" + ".save " + " ".join(b["save"]) + "\n"
    stages = {
        "schema": "sky130-pll.power.stages/1",
        "block": b["name"],
        "align_node": b["align_node"],
        "tran_stop_s": max(s["t1"] for s in b["stages"]),
        "stages": b["stages"],
        "note": b["note"],
    }
    req = request_for(b, f"{b['name']}.body.spice")
    return {
        sch_name: sch_text,
        f"{b['name']}.body.spice": body,
        f"{b['name']}.stages.json": json.dumps(stages, indent=2) + "\n",
        f"{b['name']}.request.json": json.dumps(req, indent=2) + "\n",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if committed files are stale")
    ap.add_argument("blocks", nargs="*", choices=list(BLOCKS))
    args = ap.parse_args(argv)
    names = args.blocks or list(BLOCKS)
    TB_DIR.mkdir(parents=True, exist_ok=True)
    stale = []
    for name in names:
        for fname, text in build_block(BLOCKS[name]()).items():
            path = TB_DIR / fname
            if args.check:
                if not path.is_file() or path.read_text() != text:
                    stale.append(fname)
            else:
                path.write_text(text)
                print(f"wrote {path.relative_to(REPO_ROOT)}")
    if stale:
        print("stale:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
