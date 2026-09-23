# PLL ERC supply record: 20260923-085051-13ecfe9

**Supersedes [`20260923-062347-b3abad8`](../20260923-062347-b3abad8/record.md).**
Same layout, same spec content, same verdict — re-run at this repository's
**pinned** `klt` for the first time. Issue #157.

The superseding is the whole point of this record: the one it replaces could
not be reproduced from `layout/requirements.txt`, which is a reproducibility
defect independent of whether its numbers were right. Records are never
edited or deleted here, so the old one stays exactly as written and this one
states what changed.

Read `../README.md` first for what this class of record does and does not
establish. Read this file before `erc.json`; `erc.json` is the raw evidence
this file summarises.

## What was run

```bash
layout/bin/setup-venv.sh          # installs the pin: klayout-tools==0.6.0
layout/.venv/bin/klt erc layout/pll/reports/20260923-084911-13ecfe9/pll_top.gds \
  layout/pll/erc-supply-spec.json \
  --top pll_top --pdk sky130 --format json \
  > layout/pll/erc-reports/20260923-085051-13ecfe9/erc.json
```

| Input | Value |
| --- | --- |
| Layout | `layout/pll/reports/20260923-084911-13ecfe9/pll_top.gds` (the record `layout/pll/reports/LATEST` points at) |
| Layout content hash | `sha256:939f97e0…8d4c` — `erc.json`'s `provenance.input.content_hash`, and the `sha256sum` of the committed GDS |
| Spec | `layout/pll/erc-supply-spec.json` |
| Spec content hash | `sha256:5203d728…4c08` — `erc.json`'s `provenance.spec.content_hash`, and the `sha256sum` of the committed spec |
| `klt` | `0.6.0` — **the pin**, `layout/requirements.txt` → `klayout-tools==0.6.0` |
| KLayout | `0.30.12` |
| Exit code | `0` |

**The `klt` build IS this repo's pinned one, which is what this record exists
to establish.** The superseded record was produced with
`0.5.0+g2f64ab88bfcc`, a build that is not resolvable upstream at all
(`gh api repos/2AMLogic/klayout-tools/commits/2f64ab88bfcc` → HTTP 422, "No
commit found for SHA") and was in any case not what `layout/bin/setup-venv.sh`
installs. This record was produced by running `setup-venv.sh` and then the
command above, with nothing else on `PATH`.

### The layout is byte-identical across the pin bump

`layout/pll/reports/20260923-084911-13ecfe9/pll_top.gds` and the superseded
record's `20260906-195205-4a08c71/pll_top.gds` have the **same** sha256
(`939f97e0…8d4c`), which is also what both `erc.json`s record as
`provenance.input.content_hash`. So the layout record id moved because issue
#157 re-ran both layout flows at the new pin (per `layout/README.md`'s bump
discipline), not because any geometry changed — and every shape count quoted
in `../erc-supply-spec.json`'s own layer justifications still holds verbatim.

The **spec** hash did change (`ee791569…a7a2` → `5203d728…4c08`): the spec's
`_comment` block was updated to name the current layout record and to state
the byte-identity above. No `stackup`/`vias`/`nets` entry was touched.

## Verdict on item 11's own rules

Item 11 grades three things, and **not** the report's overall `status`
(`docs/design-evidence-tiers.md`, item 11; klayout-tools#1994):

| Item 11 rule | Result | Where to check it |
| --- | --- | --- |
| Every declared supply resolves to exactly **one** electrical island | **PASS** — `VPWR` → 1 island, `VGND` → 1 island | zero `erc.unconnected_net` in `erc_findings` |
| No `erc.supply_short` naming a declared supply | **PASS** | zero `erc.supply_short` in `erc_findings` |
| Zero `erc.missing_tie` | **NOT COMPUTED** — see the superseded record and `../README.md` | no `ties[]` in the spec |

`erc_finding_count` is `0`. Unchanged from the superseded record, as expected
from a byte-identical layout and an unchanged declaration set.

`status` is now `"clean_partial"` where the superseded record said
`"clean"`. That is a **reporting** change, not a verdict change: `0.6.0` adds
a separate `erc_status` field (`"clean"` here, the connectivity verdict) and
rolls the antenna side's coverage gap — `met3` is declared in the stackup and
sky130's transcribed antenna table has no met3 limit — into the top-level
`status`. Neither field is what item 11 reads, and the two rules it does read
are the table above.

## What the pin bump actually changed in this report

The issue that produced this record asked, correctly, whether a version bump
with no observable diff in the metric it was meant to fix would be worth
flagging. It is observable, and it is large — but **against the old pin, not
against the superseded record**:

- **vs. the superseded record (`0.5.0+g2f64ab88bfcc`)**: the `gates` array is
  **byte-identical** (213 gates, same areas, same ratios, same verdicts). The
  unreproducible build the old record was made with already carried the
  antenna fix. That is consistent, not suspicious: the reproducibility gap
  being closed here was never "the old numbers are wrong", it was "the old
  numbers cannot be regenerated from the pin".
- **vs. the old pin (`klayout-tools==0.4.0`)**: running the identical command
  against the identical layout and spec with `0.4.0` — done once, as a
  control, and not committed as a record because it is a superseded pin, not
  a result — gives materially different and **non-physical** numbers:

  | | `0.4.0` (old pin) | `0.6.0` (this pin) |
  | --- | --- | --- |
  | `gate_count` | 216 | **213** |
  | Largest "gate" area | 300.84 µm² | **20.0 µm²** |
  | Total gate area | 535.59 µm² | **131.49 µm²** |
  | Worst `li1` antenna ratio (limit 75) | 4.076 | **11.640** |
  | Worst `met1`/`met2` ratio (limit 400) | 4.076 | **11.717** |
  | Every gate's `antenna_verdict` | `pass` | `pass_partial` |
  | `provenance` block | absent | present, with both content hashes |
  | `status` / `erc_status` | absent | `clean_partial` / `clean` |

  The three extra "gates" at `0.4.0` are this block's three poly resistors —
  the PFD/CP's 300 µm bias resistor (its 300.84 µm² raw-poly area is the
  300.84 µm largest-gate figure above) and the loop filter's two `res_xhigh`
  devices. They have no gate oxide under them and are not gates. Counting
  them inflates the antenna denominator, which is why `0.4.0` reports worst
  ratios roughly **2.9× lower** than the physical ones: the old pin was not
  merely missing the `provenance` block, it was reporting optimistic antenna
  numbers. This is klayout-tools#1979, fixed by PR #2001 and first published
  in `0.6.0`.

Both runs are `erc_finding_count: 0` — the antenna results pass at either
pin, so nothing here changes a verdict. It changes whether the passing
numbers mean anything.

## Everything else in the superseded record still stands

This record deliberately does not restate the substance of
[`20260923-062347-b3abad8`](../20260923-062347-b3abad8/record.md), because
none of it changed with the pin and duplicating it would create two places to
keep honest. Still true, verbatim, and still the dominant facts about this
result:

- **`erc.missing_tie` is NOT COMPUTED**, and nothing stands in for it —
  `tap.drawing` (65/44) has zero shapes, there is no `power.tapcell_master`,
  and the only `klt lvs` result is a `mismatch`. An absence of evidence, not
  evidence of absence.
- **This reads one of four blocks.** `VPWR`/`VGND` come entirely from the
  divider's abutted standard-cell row — a 142.6 × 2.72 µm strip of a
  569.93 × 232.76 µm block. The three custom-drawn analog blocks carry no
  supply labels and no supply rails at all. Filed as issue #156.
- **Item 11 is not met by this evidence alone**; the Analog column also needs
  item 4's LVS to carry the supply nets in its `net_correspondence` (issue
  #18).
- **The antenna numbers are taken against an unrouted layout** and will
  change once routing lands. Nothing here is a standing antenna sign-off.
- The independent `klayout.db.LayoutToNetlist` island re-derivation recorded
  in the superseded record was run against the same byte-identical stream and
  is not repeated.
