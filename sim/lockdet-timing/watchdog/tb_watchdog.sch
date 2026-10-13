v {xschem version=3.4.7 file_version=1.2
* tb_watchdog: EN/RSTB step at 20 ns + loads (generated)
}
G {}
K {}
V {}
S {}
E {}
C {devices/vsource.sym} 0 0 0 0 {name=VEN value="PWL(0 0 2e-08 0 2.01e-08 VDD)"}
C {devices/vsource.sym} 200 0 0 0 {name=VRSTB value="PWL(0 0 2e-08 0 2.01e-08 VDD)"}
C {devices/vsource.sym} 400 0 0 0 {name=VDD value=VDD}
C {devices/capa.sym} 600 0 0 0 {name=CRAW value=1e-14}
C {devices/capa.sym} 800 0 0 0 {name=CTICK value=1e-14}
