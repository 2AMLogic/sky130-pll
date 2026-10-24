# Re-qualification under open_pdks f6eeac7 (issue #298, part of #295)

Minted by `layout/bin/run-trivial-cell-flow.sh` at `ba142d6` against
`~/.ciel/sky130A` (`open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`,
the pin in `sim/pdk.json`). `record.md` is the flow's own unedited output.

**Supersedes** `20260924-041449-c53e7c4` and the `open_pdks c6d73a3…`
records `20260814-020940-aa2de71`, `20260819-082033-ecb9795`,
`20260905-184511-4285e0a`, `20260923-084234-13ecfe9`. None was edited.

The design is unchanged, so this is a pure PDK comparison:

| Result | `13ecfe9` (`c6d73a3`) | `c53e7c4` (`f6eeac7`) | this (`f6eeac7`) |
| --- | --- | --- | --- |
| DRC | clean, 0 | clean, 0 | clean, 0 |
| DRC negative control | violations, 2 | violations, 2 | violations, 2 |
| LVS vs. reference | match (8) | match (8) | match (8) |
| LVS broken-device control | mismatch (34) | mismatch (34) | mismatch (34) |
| LVS broken-topology control | mismatch (32) | mismatch (32) | mismatch (32) |
| Extracted devices | 4 | 4 | 4 |

No result changed; no regression to record.
