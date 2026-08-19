## DRC Report: /home/ubuntu/loom-workspaces/sky130-pll/.loom/worktrees/issue-46/layout/trivial-cell/reports/20260819-082033-ecb9795/trivial_mos_array.gds
**Status:** ✅ clean
- Deck: sky130
- File: /home/ubuntu/loom-workspaces/sky130-pll/.loom/worktrees/issue-46/layout/trivial-cell/reports/20260819-082033-ecb9795/trivial_mos_array.gds

No violations found.

## LVS Report: trivial_mos_array.gds vs reference.spice
**Status:** ✅ match
- Top: trivial_mos_array
- Engine: klayout

| Category | Severity | Side | Description |
| --- | --- | --- | --- |
| device.body_unverified | warning | layout | 4 NMOS device body terminal(s) were compared against the 'vsubs' deck-synthesized substrate net, not a real schematic net -- no drawn substrate-tap geometry resolved these device(s)' body terminal to a real net (see docs/cli/extract.md, "Coverage") |
| topology | warning | both | both sides pair a net that touches exactly one device terminal and carries no declared pin -- there is no DC path through this node on either side, so this is a real connectivity finding (e.g. an undriven MOS gate), not a routine ambiguous-pairing/hints.same_nets nit; see klt extract's single_terminal_nets[] for the layout-side terminal detail |
| topology | warning | both | both sides pair a net that touches exactly one device terminal and carries no declared pin -- there is no DC path through this node on either side, so this is a real connectivity finding (e.g. an undriven MOS gate), not a routine ambiguous-pairing/hints.same_nets nit; see klt extract's single_terminal_nets[] for the layout-side terminal detail |
| topology | warning | both | both sides pair a net that touches exactly one device terminal and carries no declared pin -- there is no DC path through this node on either side, so this is a real connectivity finding (e.g. an undriven MOS gate), not a routine ambiguous-pairing/hints.same_nets nit; see klt extract's single_terminal_nets[] for the layout-side terminal detail |
| topology | warning | both | both sides pair a net that touches exactly one device terminal and carries no declared pin -- there is no DC path through this node on either side, so this is a real connectivity finding (e.g. an undriven MOS gate), not a routine ambiguous-pairing/hints.same_nets nit; see klt extract's single_terminal_nets[] for the layout-side terminal detail |
| topology | warning | both | both sides pair a net that touches exactly one device terminal and carries no declared pin -- there is no DC path through this node on either side, so this is a real connectivity finding (e.g. an undriven MOS gate), not a routine ambiguous-pairing/hints.same_nets nit; see klt extract's single_terminal_nets[] for the layout-side terminal detail |
| topology | warning | layout | device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch |
| topology | warning | layout | device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch |
