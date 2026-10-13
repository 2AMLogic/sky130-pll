#!/usr/bin/env python3
"""Generate the independent watchdog primitive and its runner files (issue #276).

Candidate `wdb`: NAND2 (enable) + 29 x buf_1 ring, 6-flop ripple divider
(/64). Controls: `wdb-ctl-en` is `wdb` with EN held low. Pure text generation; cell
subcircuits are inlined verbatim from the pinned PDK spice.

    python3 design/lock-detector/timing/gen_watchdog.py [--pdk-spice FILE]
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

C = "sky130_fd_sc_hd__"
RING_CELL = "buf_1"
STAGES, DIV = 29, 6         # ring buffers; divider flops (ratio 2**DIV)
LOAD_F, SLEW_S, THR_V = 10e-15, 100e-12, 0.9
WIN = dict(enable_s=20e-9, settle_s=60e-9, window_start_s=100e-9, window_stop_s=2000e-9,
           step_s=25e-12, timeout_s=3600)


def dut(name, gate):
    o = [f".subckt {name} EN RSTB RAW TICK VDD GND",
         f"XG EN RAW GND GND VDD VDD n0 {C}{gate}"]
    prev = "n0"
    for i in range(1, STAGES + 1):
        nxt = "RAW" if i == STAGES else f"d{i}"
        o.append(f"XD{i} {prev} GND GND VDD VDD {nxt} {C}{RING_CELL}")
        prev = nxt
    clk = "RAW"
    for i in range(1, DIV + 1):
        q = "TICK" if i == DIV else f"q{i}"
        o.append(f"XF{i} {clk} qn{i} RSTB GND GND VDD VDD {q} qn{i} {C}dfrbp_1")
        clk = q
    return "\n".join(o + [".ends", ""])


def subckt(pdk, cell):
    m = re.search(rf"^\.subckt {C}{cell} .*?^\.ends\s*$", pdk, re.M | re.S)
    if not m:
        raise SystemExit(f"cell {cell} not in PDK spice")
    return m.group(0) + "\n"


def deck(pdk, name, gate, title, en_low=False):
    ven = ("VEN EN 0 0" if en_low else
           f"VEN EN 0 PWL(0 0 {WIN['enable_s']:g} 0 {WIN['enable_s'] + SLEW_S:g} @VDD@)")
    return "\n".join([
        f"* {title}", "* cells inlined verbatim from sky130_fd_sc_hd.spice (open_pdks pin in sim/pdk.json)",
        *[subckt(pdk, c) for c in sorted({gate, RING_CELL, "dfrbp_1"})], dut(name, gate),
        ".options trtol=1",  # step error is solver-controlled, not output-step-limited (see DESIGN.md)
        "VDD VDD 0 @VDD@",
        ven,
        f"VRSTB RSTB 0 PWL(0 0 {WIN['enable_s']:g} 0 {WIN['enable_s'] + SLEW_S:g} @VDD@)",
        f"XDUT EN RSTB RAW TICK VDD 0 {name}",
        f"CRAW RAW 0 {LOAD_F:g}", f"CTICK TICK 0 {LOAD_F:g}", ""])


def manifest(cid):
    sig = lambda s, e="rising": dict(signal=s, threshold_v=THR_V, edge=e)
    # acq/rel are required by the manifest schema but are not watchdog quantities:
    # placeholder raw->tick rising lag, never graded for this product.
    ph = dict(input="raw", tap="tick", threshold_v=THR_V, input_edge="rising", tap_edge="rising")
    return {"schema": L.MANIFEST_SCHEMA, "product_id": "watchdog", "candidate_id": cid,
            "units": {"time": "s", "voltage": "V", "temperature": "C", "capacitance": "F"},
            "inventory": {"cells": [{"name": C + "nand2_1",
                                     "drive": "1", "stage": "enable gate x1"},
                                    {"name": C + RING_CELL, "drive": "1", "stage": f"ring delay x{STAGES}"},
                                    {"name": C + "dfrbp_1", "drive": "1", "stage": f"divider flop x{DIV}"}],
                          "taps": ["raw", "tick"], "dividers": [f"ripple /{2 ** DIV}"]},
            "measurement": {"load_f": LOAD_F, "slew_s": SLEW_S, "acq": ph, "rel": ph,
                            "tick": sig("tick"), "raw": sig("raw"), "startup": sig("raw")},
            "windows": dict(WIN),
            "grid": [{"process": p, "temp_c": t, "vdd_v": v} for p, t, v in L.GRID]}


def sch(title, n_ring):
    o = ["v {xschem version=3.4.7 file_version=1.2", f"* {title} (generated)", "}", "G {}", "K {}", "V {}", "S {}", "E {}",
         f"C {{sky130_stdcells/nand2_1.sym}} 0 0 0 0 {{name=XG VGND=GND VNB=GND VPB=VDD VPWR=VDD prefix=sky130_fd_sc_hd__}}"]
    for i in range(n_ring):
        o.append(f"C {{sky130_stdcells/{RING_CELL}.sym}} {(i + 1) * 100} 0 0 0 {{name=XD{i + 1} VGND=GND VNB=GND VPB=VDD VPWR=VDD prefix=sky130_fd_sc_hd__}}")
    for i in range(DIV):
        o.append(f"C {{sky130_stdcells/dfrbp_1.sym}} {i * 150} 200 0 0 {{name=XF{i + 1} VGND=GND VNB=GND VPB=VDD VPWR=VDD prefix=sky130_fd_sc_hd__}}")
    o += [f"C {{devices/lab_pin.sym}} {x} {y} 0 0 {{name=p{k} lab={l}}}"
          for k, (x, y, l) in enumerate([(-40, 0, "EN"), (-40, 200, "RSTB"), (700, 0, "RAW"), (1000, 200, "TICK")])]
    return "\n".join(o) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk-spice", default=str(Path.home() / ".volare/sky130A/libs.ref/"
                                               "sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"))
    pdk = Path(ap.parse_args().pdk_spice).read_text()
    out = ROOT / "sim/lockdet-timing/watchdog"
    (out / "candidates").mkdir(parents=True, exist_ok=True)
    (ROOT / "design/lock-detector/timing/netlist").mkdir(parents=True, exist_ok=True)
    (ROOT / "design/lock-detector/timing/netlist/watchdog.spice").write_text(
        "* generated by gen_watchdog.py; DUT subcircuits only (wdb)\n"
        + dut("wdb", "nand2_1"))
    (ROOT / "design/lock-detector/timing/watchdog.sch").write_text(sch("watchdog ring + divider", STAGES))
    (out / "candidates/wdb.spice").write_text(deck(pdk, "wdb", "nand2_1", "independent watchdog: NAND2 + 29x buf_1 ring, /64 ripple divider"))
    (out / "candidates/control-en.spice").write_text(deck(pdk, "wdb", "nand2_1", "NEGATIVE CONTROL: wdb with EN held low (never enabled)", en_low=True))
    for cid in ("wdb", "wdb-ctl-en"):
        (out / f"candidates/{cid}.json").write_text(json.dumps(manifest(cid), indent=1, sort_keys=True) + "\n")
    tb = ["v {xschem version=3.4.7 file_version=1.2", "* tb_watchdog: EN/RSTB step at 20 ns + loads (generated)", "}",
          "G {}", "K {}", "V {}", "S {}", "E {}",
          f"C {{devices/vsource.sym}} 0 0 0 0 {{name=VEN value=\"PWL(0 0 {WIN['enable_s']:g} 0 {WIN['enable_s'] + SLEW_S:g} VDD)\"}}",
          f"C {{devices/vsource.sym}} 200 0 0 0 {{name=VRSTB value=\"PWL(0 0 {WIN['enable_s']:g} 0 {WIN['enable_s'] + SLEW_S:g} VDD)\"}}",
          "C {devices/vsource.sym} 400 0 0 0 {name=VDD value=VDD}",
          f"C {{devices/capa.sym}} 600 0 0 0 {{name=CRAW value={LOAD_F:g}}}",
          f"C {{devices/capa.sym}} 800 0 0 0 {{name=CTICK value={LOAD_F:g}}}"]
    (out / "tb_watchdog.sch").write_text("\n".join(tb) + "\n")
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    idx = {"schema": "sky130-pll.lockdet-timing.watchdog-index/1",
           "pdk_pin": json.loads((ROOT / "sim/pdk.json").read_text())["open_pdks_commit"],
           "generator": "design/lock-detector/timing/gen_watchdog.py",
           "grid": "tt/ff/ss/fs/sf x -40/27/125 C x 1.62/1.8/1.98 V (45 per candidate)",
           "stimulus": {"load_f": LOAD_F, "slew_s": SLEW_S, "threshold_v": THR_V, **WIN,
                        "en_rstb_release_s": WIN["enable_s"]},
           "candidates": {cid: {"netlist": f"candidates/{n}.spice", "manifest": f"candidates/{cid}.json",
                                "netlist_sha256": h(out / f"candidates/{n}.spice"),
                                "manifest_sha256": h(out / f"candidates/{cid}.json")}
                          for cid, n in (("wdb", "wdb"), ("wdb-ctl-en", "control-en"))}}
    (out / "manifest.json").write_text(json.dumps(idx, indent=1, sort_keys=True) + "\n")
    print("generated wdb, wdb-ctl-en")


if __name__ == "__main__":
    main()
