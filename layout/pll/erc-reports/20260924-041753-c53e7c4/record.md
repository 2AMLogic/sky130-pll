# PLL ERC supply record: 20260924-041753-c53e7c4

**Supersedes [`20260923-085051-13ecfe9`](../20260923-085051-13ecfe9/record.md).**
Same layout, same declared supplies, same verdict on item 11's own rules —
re-run at this repository's **pinned** `klayout` ENGINE for the first time.
Issue #167.

The superseding is again a reproducibility fix, not a layout or verdict
change: `layout/requirements.txt` pinned `klayout-tools` but not the
`klayout` engine it runs on, so `klayout` floated as an unpinned transitive
dependency. The superseded record's cold install resolved `klayout==0.30.12`
from the unpinned `klayout-tools==0.6.0` spec — confirmed still live at the
time of this fix, a bare `pip install 'klayout-tools==0.6.0'` today resolves
the same `0.30.12`, not the `0.30.10` that build's own engine-mismatch
warning names as tested against — and `klt` warns on every
`drc`/`extract`/`lvs`/`erc` invocation when that happens. This record is the
first one produced after `layout/requirements.txt` pinned `klayout`
explicitly, at `0.30.10`.

Read `../README.md` first for what this class of record does and does not
establish. Read this file before `erc.json`; `erc.json` is the raw evidence
this file summarises.

## What was run

```bash
layout/bin/setup-venv.sh --force   # installs the pins: klayout-tools==0.6.0, klayout==0.30.10
layout/.venv/bin/klt erc layout/pll/reports/20260924-041509-c53e7c4/pll_top.gds \
  layout/pll/erc-supply-spec.json \
  --top pll_top --pdk sky130 --format json \
  > layout/pll/erc-reports/20260924-041753-c53e7c4/erc.json
```

| Input | Value |
| --- | --- |
| Layout | `layout/pll/reports/20260924-041509-c53e7c4/pll_top.gds` (the record `layout/pll/reports/LATEST` points at) |
| Layout content hash | `sha256:939f97e0…8d4c` — `erc.json`'s `provenance.input.content_hash`, and the `sha256sum` of the committed GDS |
| Spec | `layout/pll/erc-supply-spec.json` |
| Spec content hash | `sha256:229d452a…4b25` — `erc.json`'s `provenance.spec.content_hash`, and the `sha256sum` of the committed spec |
| `klt` | `0.6.0` — unchanged, `layout/requirements.txt` → `klayout-tools==0.6.0` |
| KLayout | `0.30.10` — **newly the pin**, `layout/requirements.txt` → `klayout==0.30.10` |
| Exit code | `0`, no engine-mismatch warning on stderr |

**No warning fired.** The superseded record's run (`klt` resolved to a `0.30.12`
engine that day) is the evidence this repo's own `erc.json` carries for the
gap this issue closes: its `provenance.klayout_version` reads `0.30.12`
against a `klayout-tools==0.6.0` build tested against `0.30.10`. This run's
`provenance.klayout_version` reads `0.30.10` — the pin — with a clean
`layout/bin/setup-venv.sh --force` install and a bare `klt erc` invocation,
nothing else on `PATH`.

### The layout is byte-identical across the pin bump

`layout/pll/reports/20260924-041509-c53e7c4/pll_top.gds` and the superseded
record's `20260923-084911-13ecfe9/pll_top.gds` have the **same** sha256
(`939f97e0…8d4c`), which is also what both `erc.json`s record as
`provenance.input.content_hash`. The layout record id moved because issue
#167 re-ran both layout flows at the newly-pinned engine (per
`layout/README.md`'s bump discipline), not because any geometry changed.

The **spec** hash changed (`5203d728…4c08` → `229d452a…4b25`): only the
spec's `_comment` block was updated, to name the current layout record and
this issue's engine pin. No `stackup`/`vias`/`nets` entry was touched.

## Verdict on item 11's own rules

Item 11 grades three things, and **not** the report's overall `status`
(`docs/design-evidence-tiers.md`, item 11; klayout-tools#1994):

| Item 11 rule | Result | Where to check it |
| --- | --- | --- |
| Every declared supply resolves to exactly **one** electrical island | **PASS** — `VPWR` → 1 island, `VGND` → 1 island | zero `erc.unconnected_net` in `erc_findings` |
| No `erc.supply_short` naming a declared supply | **PASS** | zero `erc.supply_short` in `erc_findings` |
| Zero `erc.missing_tie` | **NOT COMPUTED** — see the superseded record and `../README.md` | no `ties[]` in the spec |

`erc_finding_count` is `0`, and `erc_findings` is byte-for-byte identical to
the superseded record's. Unchanged, as expected from a byte-identical layout
and an unchanged declaration set.

## What the engine pin actually changed in this report

`gate_count` (213), `erc_finding_count` (0), `status` (`clean_partial`),
`erc_status` (`clean`), and every top-level scalar are identical to the
superseded record. The **per-gate antenna breakdown does move**, which is
exactly the class of count this issue's premise warned about — a report
"count" can differ across a `klayout` engine bump on an unchanged input, even
though the verdict itself does not:

| | superseded (`klayout` 0.30.12) | this record (`klayout` 0.30.10, the pin) |
| --- | --- | --- |
| `gate_count` | 213 | 213 |
| Gates with a differing `levels[]` breakdown | — | **131 of 213** |
| Sum of `gate_area_um2` across all gates | 131.489 µm² | **131.489 µm² (identical)** |
| Largest single `gate_area_um2` | 20.0 µm² | **20.0 µm² (identical)** |
| Worst `li1` antenna ratio (limit 75) | 11.640 | **11.640 (identical)** |
| Worst `met1`/`met2` antenna ratio (limit 400) | 11.717 | **11.717 (identical)** |
| Every gate's `antenna_verdict` | `pass_partial` (213/213) | `pass_partial` (213/213, identical, zero flips) |

Every declared supply's net is `null` for every gate in both records (this
spec computes antenna coverage per gate, not per net), so the 131 gates whose
`levels[]` differ are not a change in which shapes belong to which net — they
are a change in **which specific `gate_id` a shared net's cumulative antenna
area gets attributed to** when several gates sit on the same poly/li1/met
chain. For example, `gate31`/`gate32`/`gate33` (three of a matched group)
report `gate_area_um2` of `0.3`/`0.3`/`0.3` at `0.30.12` and `0.6`/`2.0`/`2.0`
at `0.30.10` — different per-gate credit for the same physical net's
cumulative area, consistent with a KLayout-side iteration-order change over
same-net shapes between the two engine point releases, not a change to the
extracted geometry or connectivity itself (the sum, max, and every worst-case
ratio above land on the exact same numbers either way). Nothing here changes
which of item 11's rules pass, and nothing here changes the "does not
establish" list in `../README.md`.

## Everything else in the superseded record still stands

This record deliberately does not restate the substance of
[`20260923-085051-13ecfe9`](../20260923-085051-13ecfe9/record.md) or the
record it in turn supersedes, because none of it changed with this engine
pin and duplicating it would create two places to keep honest. Still true,
verbatim, and still the dominant facts about this result:

- **`erc.missing_tie` is NOT COMPUTED**, and nothing stands in for it —
  `tap.drawing` (65/44) has zero shapes, there is no `power.tapcell_master`,
  and the only `klt lvs` result is a `mismatch`. An absence of evidence, not
  evidence of absence.
- **This reads one of four blocks.** `VPWR`/`VGND` come entirely from the
  divider's abutted standard-cell row — a 142.6 × 2.72 µm strip of a
  569.93 × 233.0 µm block. The three custom-drawn analog blocks carry no
  supply labels and no supply rails at all. Filed as issue #156.
- **Item 11 is not met by this evidence alone**; the Analog column also needs
  item 4's LVS to carry the supply nets in its `net_correspondence` (issue
  #18).
- **The antenna numbers are taken against an unrouted layout** and will
  change once routing lands. Nothing here is a standing antenna sign-off.
