# pll comp data (generated, public-sources-only)

Generated 2026-08-20 from the upstream comp library's `pll.md` entry by an internal, private-repo-only tool. This is a derived, filtered copy — regenerate rather than hand-edit. Every row below cites a public vendor datasheet or a public distributor pricing page; nothing internal survived extraction.

## Comparable parts

| Vendor | Part | Class | Input | Output range | Jitter | Ref spur / PSRR | Package | Source |
|---|---|---|---|---|---|---|---|---|
| Texas Instruments | CDCE913 / CDCEL913 | 1-PLL, 3-output programmable clock generator | 8–32 MHz crystal, or LVCMOS up to 160 MHz | up to 230 MHz, any output freq | 50 ps typ period jitter | not separately headlined (SSC support for EMI) | TSSOP-14, 5×6.4 mm | Datasheet: [ti.com/lit/ds/symlink/cdce913.pdf](https://www.ti.com/lit/ds/symlink/cdce913.pdf) (SCAS849I) |
| Texas Instruments | LMK61E2 | Ultra-low-jitter fractional-N programmable oscillator, integrated VCO | I2C-configured, internal EEPROM (not an external reference-in part) | up to 1 GHz (LVPECL), 900 MHz (LVDS), 400 MHz (HCSL); default 156.25 MHz | 90 fs RMS typ (f_OUT > 100 MHz) | PSRR −70 dBc | QFM-8, 7×5 mm | Datasheet: [ti.com/lit/ds/symlink/lmk61e2.pdf](https://www.ti.com/lit/ds/symlink/lmk61e2.pdf) (SNAS674C) |

## Sources

| URL | Establishes | Fetched |
|---|---|---|
| https://www.ti.com/lit/ds/symlink/cdce913.pdf | CDCE913/CDCEL913 input/output range, jitter, package | 2026-08-20 |
| https://www.ti.com/lit/ds/symlink/lmk61e2.pdf | LMK61E2 jitter, PSRR, output formats, package | 2026-08-20 |

