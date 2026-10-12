#!/usr/bin/env python3
"""Generate the acquisition/release delay-chain candidates (issue #275).

Writes the schematic, the DUT netlist, the self-contained runner decks and the
runner manifests. Pure text generation; the PDK is only read to inline the
cell subcircuits verbatim (so a batch worker needs no local path).

    python3 design/lock-detector/timing/gen_phase_windows.py [--pdk-spice FILE]
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sim"))
from harness import locktiming as L  # noqa: E402

CELLS = "sky130_fd_sc_hd__"
# id -> (acq cell, acq stages, rel cell, rel stages); all non-inverting, drive _1
CANDIDATES = {"s50": ("clkdlybuf4s50_1", 7, "clkdlybuf4s50_1", 18),
              "s25": ("clkdlybuf4s25_1", 14, "clkdlybuf4s25_1", 39)}
LOAD_F, SLEW_S, THR_V = 10e-15, 100e-12, 0.9
WIN = dict(enable_s=20e-9, settle_s=60e-9, window_start_s=100e-9, window_stop_s=800e-9,
           step_s=20e-12, timeout_s=3600)
PERIOD, DELAY, WIDTH = 250e-9, 150e-9, 100e-9  # input: rising 150/400/650 ns, falling 250/500/750


def dut(cid):
    ac, na, rc, nr = CANDIDATES[cid]
    out = [f".subckt phase_win_{cid} IN ACQ REL VDD GND"]
    for tap, cell, n in (("ACQ", ac, na), ("REL", rc, nr)):
        prev = "IN"
        for i in range(1, n + 1):
            nxt = tap if i == n else f"{tap.lower()}{i}"
            out.append(f"X{tap}{i} {prev} GND GND VDD VDD {nxt} {CELLS}{cell}")
            prev = nxt
    return "\n".join(out + [".ends", ""])


def subckt(pdk_text, cell):
    m = re.search(rf"^\.subckt {CELLS}{cell} .*?^\.ends\s*$", pdk_text, re.M | re.S)
    if not m:
        raise SystemExit(f"cell {cell} not in PDK spice")
    return m.group(0) + "\n"


def deck(cid, pdk_text, *, control=False):
    amp = "0.6" if control else "@VDD@"  # control: input never reaches the 0.9 V threshold
    cells = sorted({CANDIDATES[cid][0], CANDIDATES[cid][2]})
    return "\n".join([
        f"* phase-window candidate {cid}{' NEGATIVE CONTROL (input peaks at 0.6 V)' if control else ''}",
        "* cells inlined verbatim from sky130_fd_sc_hd.spice (open_pdks pin in sim/pdk.json)",
        *[subckt(pdk_text, c) for c in cells], dut(cid),
        "VDD VDD 0 @VDD@",
        f"VIN IN 0 PULSE(0 {amp} {DELAY:g} {SLEW_S:g} {SLEW_S:g} {WIDTH:g} {PERIOD:g})",
        f"VRSTB RSTB 0 PWL(0 0 {WIN['enable_s']:g} 0 {WIN['enable_s'] + SLEW_S:g} @VDD@)",
        f"XDUT IN ACQ REL VDD 0 phase_win_{cid}",
        f"CACQ ACQ 0 {LOAD_F:g}", f"CREL REL 0 {LOAD_F:g}", ""])


def manifest(cid, edge):
    ac, na, rc, nr = CANDIDATES[cid]
    pr = lambda tap: dict(input="in", tap=tap, threshold_v=THR_V, input_edge=edge, tap_edge=edge)
    sig = lambda s, e="rising": dict(signal=s, threshold_v=THR_V, edge=e)
    return {"schema": L.MANIFEST_SCHEMA, "product_id": "phase-windows",
            "candidate_id": f"{cid}-{edge}",
            "units": {"time": "s", "voltage": "V", "temperature": "C", "capacitance": "F"},
            "inventory": {"cells": [{"name": CELLS + ac, "drive": "1", "stage": f"acq x{na}"},
                                    {"name": CELLS + rc, "drive": "1", "stage": f"rel x{nr}"}],
                          "taps": ["acq", "rel"], "dividers": ["none: tick is the stimulus"]},
            "measurement": {"load_f": LOAD_F, "slew_s": SLEW_S, "acq": pr("acq"), "rel": pr("rel"),
                            "tick": sig("in"), "raw": sig("in"), "startup": sig("rstb")},
            "windows": dict(WIN),
            "grid": [{"process": p, "temp_c": t, "vdd_v": v} for p, t, v in L.GRID]}


def schematic():
    """xschem schematic: per candidate, two chains from net IN to taps ACQ/REL
    (candidate cid labels its taps ACQ_<cid>/REL_<cid>; see the DUT netlist)."""
    o = ["v {xschem version=3.4.7 file_version=1.2", "* phase_windows candidates (generated)", "}",
         "G {}", "K {}", "V {}", "S {}", "E {}"]
    for row, (cid, tap, cell, n) in enumerate(
            (c, t, cc, nn) for c, (ac, na, rc, nr) in CANDIDATES.items()
            for t, cc, nn in (("ACQ", ac, na), ("REL", rc, nr))):
        y = row * 200
        o.append(f"C {{devices/lab_pin.sym}} -40 {y} 0 0 {{name=pin{tap}i lab=IN}}")
        for i in range(n):
            x = i * 100
            o.append(f"C {{sky130_stdcells/{cell}.sym}} {x} {y} 0 0 {{name=X{tap}{cid.upper()}{i + 1} "
                     "VGND=GND VNB=GND VPB=VDD VPWR=VDD prefix=sky130_fd_sc_hd__}")
            if i:
                o.append(f"N {x - 60} {y} {x - 40} {y} {{}}")
        o.append(f"C {{devices/lab_pin.sym}} {n * 100 - 60} {y} 0 0 {{name=pin{tap}o lab={tap}_{cid}}}")
    return "\n".join(o) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk-spice", default=str(Path.home() / ".volare/sky130A/libs.ref/"
                                               "sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"))
    pdk = Path(ap.parse_args().pdk_spice).read_text()
    out = ROOT / "sim/lockdet-timing/phase/candidates"
    out.mkdir(parents=True, exist_ok=True)
    (ROOT / "design/lock-detector/timing/netlist").mkdir(parents=True, exist_ok=True)
    (ROOT / "design/lock-detector/timing/netlist/phase_windows.spice").write_text(
        "* generated by gen_phase_windows.py; DUT subcircuits only\n"
        + "\n".join(dut(c) for c in CANDIDATES))
    for cid in CANDIDATES:
        (out / f"{cid}.spice").write_text(deck(cid, pdk))
        for edge in ("rising", "falling"):
            (out / f"{cid}-{edge}.json").write_text(
                json.dumps(manifest(cid, edge), indent=1, sort_keys=True) + "\n")
    (out / "control.spice").write_text(deck("s50", pdk, control=True))
    (ROOT / "design/lock-detector/timing/phase_windows.sch").write_text(
        schematic())
    tb = ["v {xschem version=3.4.7 file_version=1.2", "* tb_phase_windows: stimulus + loads (generated)", "}",
          "G {}", "K {}", "V {}", "S {}", "E {}",
          f"C {{devices/vsource.sym}} 0 0 0 0 {{name=VIN value=\"PULSE(0 VDD {DELAY:g} {SLEW_S:g} {SLEW_S:g} {WIDTH:g} {PERIOD:g})\"}}",
          f"C {{devices/vsource.sym}} 200 0 0 0 {{name=VRSTB value=\"PWL(0 0 {WIN['enable_s']:g} 0 {WIN['enable_s'] + SLEW_S:g} VDD)\"}}",
          "C {devices/vsource.sym} 400 0 0 0 {name=VDD value=VDD}",
          f"C {{devices/capa.sym}} 600 0 0 0 {{name=CACQ value={LOAD_F:g}}}",
          f"C {{devices/capa.sym}} 800 0 0 0 {{name=CREL value={LOAD_F:g}}}",
          "C {devices/lab_pin.sym} 0 -30 0 0 {name=p1 lab=IN}", "C {devices/lab_pin.sym} 200 -30 0 0 {name=p2 lab=RSTB}",
          "C {devices/lab_pin.sym} 600 -30 0 0 {name=p3 lab=ACQ}", "C {devices/lab_pin.sym} 800 -30 0 0 {name=p4 lab=REL}"]
    (ROOT / "sim/lockdet-timing/phase/tb_phase_windows.sch").write_text("\n".join(tb) + "\n")
    idx = {"schema": "sky130-pll.lockdet-timing.phase-index/1", "pdk_pin": json.loads(
               (ROOT / "sim/pdk.json").read_text())["open_pdks_commit"],
           "generator": "design/lock-detector/timing/gen_phase_windows.py",
           "grid": "tt/ff/ss/fs/sf x -40/27/125 C x 1.62/1.8/1.98 V (45 per candidate)",
           "stimulus": {"load_f": LOAD_F, "slew_s": SLEW_S, "threshold_v": THR_V, **WIN,
                        "input_period_s": PERIOD, "input_first_rise_s": DELAY, "input_width_s": WIDTH},
           "candidates": {f"{c}-{e}": {"netlist": f"candidates/{c}.spice", "manifest": f"candidates/{c}-{e}.json",
                                       "acq": f"{v[1]}x {CELLS}{v[0]}", "rel": f"{v[3]}x {CELLS}{v[2]}",
                                       "manifest_sha256": hashlib.sha256((out / f"{c}-{e}.json").read_bytes()).hexdigest(),
                                       "netlist_sha256": hashlib.sha256((out / f"{c}.spice").read_bytes()).hexdigest()}
                          for c, v in CANDIDATES.items() for e in ("rising", "falling")}}
    (ROOT / "sim/lockdet-timing/phase/manifest.json").write_text(json.dumps(idx, indent=1, sort_keys=True) + "\n")
    print("generated", ", ".join(CANDIDATES))


if __name__ == "__main__":
    main()
