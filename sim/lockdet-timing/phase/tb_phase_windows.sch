v {xschem version=3.4.7 file_version=1.2
* tb_phase_windows: stimulus + loads (generated)
}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} 0 0 0 0 {name=VIN value="PULSE(0 VDD 1.5e-07 1e-10 1e-10 1e-07 2.5e-07)"}
C {devices/vsource.sym} 200 0 0 0 {name=VRSTB value="PWL(0 0 2e-08 0 2.01e-08 VDD)"}
C {devices/vsource.sym} 400 0 0 0 {name=VDD value=VDD}
C {devices/capa.sym} 600 0 0 0 {name=CACQ value=1e-14}
C {devices/capa.sym} 800 0 0 0 {name=CREL value=1e-14}
C {devices/lab_pin.sym} 0 -30 0 0 {name=p1 lab=IN}
C {devices/lab_pin.sym} 200 -30 0 0 {name=p2 lab=RSTB}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p3 lab=ACQ}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p4 lab=REL}
