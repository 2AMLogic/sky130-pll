# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

### 2026-09-14

- **Issue #140** (closed): Dedupe _render_provenance between render-record.py and render-pll-record.py

### 2026-09-12

- **PR #145**: sim(pll-lock): raise per-point timeout_s 10800 -> 43200; amend DR-004 (#103)

### 2026-09-11

- **PR #132**: Ship sim/divider standalone PVT testbench, mint N=25 evidence record
- **PR #135**: refactor(sim/harness): dedupe SPICE-literal parsing between measure.py and acmeasure.py
- **PR #136**: sim/harness: per-point parallelism (--jobs) and checkpointed resume (--resume)
- **PR #138**: sim/divider-n64: run the tt process-corner row (9/45), partial progress toward issue #130's full grid
- **PR #139**: sim/divider: mint first evidence records for -n4/-n5/-n63/-n64 siblings
- **PR #141**: sim/divider-n64: run the ff process-corner row (row 2/5), 21/45 points toward issue #130's full grid
- **PR #142**: sim/divider-n64: complete the ss process-corner row (issue #130, partial)
- **PR #143**: sim/divider-n64: complete the full DR-003 45-point PVT grid (sf + fs rows, 45/45 PASS)
- **Issue #137** (closed): Retry the sim/divider-n64 full-grid PVT campaign (issue #130) once host contention clears
- **Issue #134** (closed): Deduplicate SPICE-literal parsing: parse_spice_time/parse_spice_freq share an identical regex and suffix table
- **Issue #133** (closed): sim/harness: per-point parallelism or checkpointed resume needed to make sim/pll-lock's 45-point campaign tractable
- **Issue #131** (closed): Run the sim/divider-n4/-n5/-n63/-n64 PVT campaigns and mint their first sim/ evidence records (deferred by #129)
- **Issue #130** (closed): Complete the full DR-003 45-point PVT grid for sim/divider-n64 and sim/divider-n63 (deferred by #129)
- **Issue #129** (closed): Ship a standalone `sim/divider` PVT testbench and mint the first `sim/` evidence record for divider_intN (turn #114's informal top-frequency and modulus diagnostics into committed 45-point evidence; spec row 4)

